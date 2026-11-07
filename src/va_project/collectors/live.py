"""Live collector (US-02b): GTFS-RT and MeteoSwiss for a time window, on demand.

    python -m va_project.collectors.live --hours 48 | --until 2026-10-02T18:00
           [--stations all|none|CHU,DAV] [--compact-only] [--selbsttest]

Polls Trip Updates every GTFS_RT_POLL_SECONDS (Service Alerts too while the key is subscribed)
and SwissMetNet `now` files every METEO_POLL_MINUTES, writes raw Parquet snapshots, compacts
every LIVE_COMPACT_MINUTES and once at the end. Ctrl+C (or SIGTERM) stops cleanly and prints
a summary. At most one request per feed and interval: a failed poll is not retried at once,
the following polls are skipped with exponential backoff; every missing snapshot is logged.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import signal
import sys
import tempfile
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, Protocol, TextIO
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from google.transit import gtfs_realtime_pb2 as pb

from va_project.collectors import gtfs_rt, meteo
from va_project.collectors.history import load_service_points
from va_project.collectors.http import AccessDeniedError, SourceError, fetch, make_session
from va_project.config import LOCAL_TZ, Settings, configure_logging, get_settings
from va_project.etl.compact import TRIP_UPDATES, WEATHER, CompactResult, compact_live, fact_path
from va_project.storage.ledger import Ledger

log = logging.getLogger(__name__)

GB_PER_DAY = 2.3  # raw Trip Updates, measured in US-01 (1.6 MB per snapshot)
MISSING_TARGET = 0.05  # AC4
EARLY_TICK_S = 1.0  # a tick sooner than interval − this after the last one is ignored
_GB = 1024**3


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --- one feed ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Snapshot:
    frame: pd.DataFrame
    feed_ts: int | None = None  # feed header time; unchanged → received but not written again


@dataclass(frozen=True)
class Missing:
    at: datetime
    reason: str
    count: int = 1


class Poller:
    """Polls one feed once per tick and counts what arrived and what is missing (AC2, AC4).

    Never sends more than one request per interval: after a failure the next polls are skipped
    with exponential backoff (or the source's Retry-After) instead of retrying immediately."""

    def __init__(
        self,
        name: str,
        fetch: Callable[[datetime], Snapshot],
        write: Callable[[Snapshot, datetime], int],
        interval_s: float,
        *,
        clock: Callable[[], datetime] = _utcnow,
        fatal_on_denied: bool = False,
        max_backoff_s: float = 600.0,
    ) -> None:
        self.name = name
        self.fetch = fetch
        self.write = write
        self.interval_s = interval_s
        self.clock = clock
        self.fatal_on_denied = fatal_on_denied
        self.max_backoff_s = max_backoff_s
        self.requests = self.received = self.duplicates = self.empty = self.bytes_written = 0
        self.missing: list[Missing] = []
        self.disabled: str | None = None
        self._first: datetime | None = None
        self._last_tick: datetime | None = None
        self._excluded = 0
        self._failures = 0
        self._skip_until: datetime | None = None
        self._last_feed_ts: int | None = None
        self._lock = threading.Lock()

    def expected(self) -> int:
        if self._first is None or self._last_tick is None:
            return 0
        span = (self._last_tick - self._first).total_seconds()
        return round(span / self.interval_s) + 1 - self._excluded

    def missing_count(self) -> int:
        return max(0, self.expected() - self.received)

    def missing_rate(self) -> float:
        return self.missing_count() / self.expected() if self.expected() else 0.0

    def _miss(self, now: datetime, reason: str, count: int = 1) -> None:
        self.missing.append(Missing(now, reason, count))
        log.warning("%s: %d missing snapshot(s) at %s — %s", self.name, count,
                    f"{now:%Y-%m-%d %H:%M:%S}Z", reason)  # fmt: skip

    def _fail(self, now: datetime, error: Exception) -> None:
        self._failures += 1
        wait = min(self.interval_s * 2 ** (self._failures - 1), self.max_backoff_s)
        wait = max(wait, getattr(error, "retry_after", None) or 0.0)
        self._skip_until = now + timedelta(seconds=wait - EARLY_TICK_S)
        self._miss(now, f"{error} (next poll in ≥ {wait:.0f} s)")

    def tick(self) -> None:
        with self._lock:
            now = self.clock()
            if self.disabled:
                return
            if self._last_tick is not None:
                since = (now - self._last_tick).total_seconds()
                if since < self.interval_s - EARLY_TICK_S:
                    return  # coalesced/early tick: keeps ≤ 1 request per interval
                gap = round(since / self.interval_s) - 1
                if since > 1.5 * self.interval_s and gap > 0:
                    self._miss(now, "no poll in between (laptop asleep or process paused)", gap)
            self._first = self._first or now
            self._last_tick = now
            if self._skip_until is not None and now < self._skip_until:
                self._miss(now, "backing off after errors")
                return

            self.requests += 1
            try:
                snap = self.fetch(now)
            except AccessDeniedError as e:
                if self.fatal_on_denied:
                    raise
                self.disabled, self._excluded = str(e), self._excluded + 1
                log.warning("%s disabled for this run: %s", self.name, e)
                return
            except (SourceError, ValueError, requests.RequestException) as e:
                self._fail(now, e)
                return
            self._failures, self._skip_until = 0, None

            if snap.feed_ts is not None and snap.feed_ts == self._last_feed_ts:
                self.received += 1
                self.duplicates += 1
                return
            if snap.frame.empty:
                self.received += 1
                self.empty += 1
                return
            try:
                self.bytes_written += self.write(snap, now)
            except OSError as e:
                self._miss(now, f"write failed: {e}")
                return
            self._last_feed_ts = snap.feed_ts
            self.received += 1

    def report(self) -> dict[str, Any]:
        return {
            "expected": self.expected(), "received": self.received, "requests": self.requests,
            "duplicates": self.duplicates, "empty": self.empty, "missing": self.missing_count(),
            "missing_rate": round(self.missing_rate(), 4), "bytes": self.bytes_written,
            "disabled": self.disabled,
            "missing_log": [{"at": m.at.isoformat(), "reason": m.reason, "count": m.count}
                            for m in self.missing],
        }  # fmt: skip


# --- sources and raw files -----------------------------------------------------------------


def raw_writer(folder: Path, prefix: str = "") -> Callable[[Snapshot, datetime], int]:
    """`folder/date=YYYY-MM-DD/{prefix}HHMMSS.parquet` (UTC); written atomically."""

    def write(snap: Snapshot, now: datetime) -> int:
        at = now.astimezone(UTC)
        path = folder / f"date={at:%Y-%m-%d}" / f"{prefix}{at:%H%M%S}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        snap.frame.to_parquet(tmp, index=False, compression="zstd")
        tmp.replace(path)
        return path.stat().st_size

    return write


def trip_updates_source(
    settings: Settings, session: requests.Session
) -> Callable[[datetime], Snapshot]:
    def get(now: datetime) -> Snapshot:
        key = settings.gtfs_rt_api_key
        assert key is not None  # checked by run()  # noqa: S101
        raw = gtfs_rt.fetch_feed(session, settings.gtfs_rt_url, key, "gtfs_rt_trip_updates", 1)
        feed = gtfs_rt.parse_feed(raw)
        frame = gtfs_rt.trip_updates_frame(feed, now, include_bare_trips=True)
        return Snapshot(frame, feed.header.timestamp)

    return get


def alerts_source(settings: Settings, session: requests.Session) -> Callable[[datetime], Snapshot]:
    def get(now: datetime) -> Snapshot:
        key = settings.gtfs_rt_api_key
        assert key is not None  # checked by run()  # noqa: S101
        raw = gtfs_rt.fetch_feed(session, settings.gtfs_sa_url, key, "gtfs_rt_alerts", 1)
        feed = gtfs_rt.parse_feed(raw)
        return Snapshot(gtfs_rt.alerts_frame(feed, now), feed.header.timestamp)

    return get


def meteo_source(
    settings: Settings, session: requests.Session, stations: list[str] | None
) -> Callable[[datetime], Snapshot]:
    """All (or the chosen) SwissMetNet stations' `now` files in one snapshot."""
    hrefs: dict[str, str] = {}

    def get(now: datetime) -> Snapshot:
        if not hrefs:  # one STAC listing per run
            listing = meteo.now_hrefs(session, settings.meteo_stac_url)
            wanted = set(listing) if stations is None else {s.upper() for s in stations}
            hrefs.update({s: h for s, h in listing.items() if s in wanted})
            if not hrefs:
                raise SourceError(meteo.SOURCE, None, f"no `now` file for {sorted(wanted)}")
        frames, failed = [], []
        for station, href in sorted(hrefs.items()):
            try:
                resp = fetch(session, href, source=meteo.SOURCE, retries=1, timeout=30)
                frames.append(meteo.parse_observations(resp.content))
            except (SourceError, ValueError, KeyError, requests.RequestException) as e:
                failed.append(station)
                log.debug("meteo %s: %s", station, e)
        if failed:
            log.warning("meteo: %d/%d stations failed: %s", len(failed), len(hrefs),
                        ", ".join(failed[:10]))  # fmt: skip
        if not frames:
            raise SourceError(meteo.SOURCE, None, "every station failed")
        return Snapshot(pd.concat(frames, ignore_index=True).assign(ingested_at=now))

    return get


# --- run -----------------------------------------------------------------------------------


class Scheduler(Protocol):
    def add_job(self, func: Callable[[], None], trigger: str, *, seconds: float, id: str,
                **kw: Any) -> Any: ...  # fmt: skip
    def start(self) -> None: ...
    def shutdown(self, wait: bool = True) -> None: ...


@dataclass
class _Compactions:
    results: list[CompactResult] = field(default_factory=list)
    failed: str | None = None


def _free_space_needed(hours: float) -> float:
    return hours / 24 * GB_PER_DAY + 1.0


def _fact_rows(settings: Settings, dates: set[str]) -> int:
    paths = [fact_path(settings.curated_dir, d) for d in dates]
    return sum(pq.ParquetFile(p).metadata.num_rows for p in paths if p.exists())


def _print_summary(
    settings: Settings, pollers: list[Poller], comp: _Compactions, started: datetime,
    ended: datetime, early: bool, out: TextIO,
) -> dict[str, Any]:  # fmt: skip
    hours = (ended - started).total_seconds() / 3600
    print(f"\nSummary · ran {hours:.1f} h{' (stopped early)' if early else ''}", file=out)
    for p in pollers:
        if p.disabled:
            print(f"  {p.name:<13} disabled — {p.disabled}", file=out)
            continue
        print(f"  {p.name:<13} expected {p.expected()} · received {p.received}"
              f" (unchanged {p.duplicates}, empty {p.empty}) · missing {p.missing_count()}"
              f" ({p.missing_rate():.1%}) · {p.bytes_written / 1e6:.1f} MB", file=out)  # fmt: skip
    trips = pollers[0]
    if trips.expected():
        ok = trips.missing_rate() < MISSING_TARGET
        print(f"  AC4 (trip_updates missing < {MISSING_TARGET:.0%}):"
              f" {'OK' if ok else 'NOT MET'}", file=out)  # fmt: skip

    dates = {d for r in comp.results for d in r.dates}
    months = sorted({m for r in comp.results for m in r.months})
    deleted = [d for r in comp.results for d in r.raw_deleted]
    files = sum(r.files for r in comp.results)
    print(f"  compaction: {files} snapshots → {_fact_rows(settings, dates):,} stop events in"
          f" {len(dates)} service day(s) {', '.join(sorted(dates))}"
          f" · live aggregates {', '.join(months) or '–'}"
          f" · {sum(r.weather_rows for r in comp.results):,} weather rows"
          f" · raw deleted {', '.join(deleted) or '–'}", file=out)  # fmt: skip
    if comp.failed:
        print(f"  compaction failed: {comp.failed} — raw kept; run --compact-only", file=out)
    return {
        "started_at": started.isoformat(), "ended_at": ended.isoformat(), "stopped_early": early,
        "feeds": {p.name: p.report() for p in pollers},
        "compaction": {"snapshots": files, "dates": sorted(dates), "months": months,
                       "raw_deleted": deleted, "failed": comp.failed},
    }  # fmt: skip


def run(
    settings: Settings,
    until: datetime,
    *,
    session: requests.Session | None = None,
    meteo_stations: list[str] | None = None,
    out: TextIO | None = None,
    clock: Callable[[], datetime] = _utcnow,
    stop: threading.Event | None = None,
    scheduler: Scheduler | None = None,
) -> int:
    """Collect until `until` (or until `stop` is set / Ctrl+C). `meteo_stations`: None = all,
    [] = no weather. Returns 0, 1 (final compaction failed) or 2 (could not run / key denied)."""
    out = out or sys.stdout
    started = clock()
    stop = stop or threading.Event()
    local = ZoneInfo(LOCAL_TZ)
    print(f"SwissFlow VA — live collector (US-02b) · {started.astimezone(local):%Y-%m-%d %H:%M}"
          f" → {until.astimezone(local):%Y-%m-%d %H:%M} ({LOCAL_TZ})", file=out)  # fmt: skip
    if settings.gtfs_rt_api_key is None:
        print("GTFS_RT_API_KEY missing in .env — https://api-manager.opentransportdata.swiss/",
              file=out)  # fmt: skip
        return 2
    hours = max(0.0, (until - started).total_seconds() / 3600)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(settings.data_dir).free / _GB
    if free < _free_space_needed(hours):
        print(f"only {free:.1f} GB free in {settings.data_dir}, a {hours:.0f} h window needs"
              f" ~{_free_space_needed(hours):.1f} GB of raw snapshots", file=out)  # fmt: skip
        return 2

    sess = session or make_session()
    sp = load_service_points(settings, sess)
    ledger = Ledger(settings.curated_dir / "_loaded.json")
    raw = settings.raw_dir
    poll_s = settings.gtfs_rt_poll_seconds
    pollers = [
        Poller("trip_updates", trip_updates_source(settings, sess), raw_writer(raw / TRIP_UPDATES),
               poll_s, clock=clock, fatal_on_denied=True),
        Poller("alerts", alerts_source(settings, sess), raw_writer(raw / "gtfs_rt/alerts"),
               poll_s, clock=clock),
    ]  # fmt: skip
    if meteo_stations != []:
        pollers.append(Poller("meteo", meteo_source(settings, sess, meteo_stations),
                              raw_writer(raw / WEATHER, "smn_"),
                              settings.meteo_poll_minutes * 60, clock=clock))  # fmt: skip

    fatal: list[str] = []
    comp = _Compactions()
    comp_lock = threading.Lock()

    def poll_job(p: Poller) -> Callable[[], None]:
        def job() -> None:
            try:
                p.tick()
            except AccessDeniedError as e:
                fatal.append(str(e))
                stop.set()
            except Exception:
                log.exception("%s: poll crashed", p.name)

        return job

    def compact_job() -> None:
        with comp_lock:
            try:
                comp.results.append(compact_live(settings, ledger, sp))
            except Exception as e:
                log.exception("compaction failed")
                comp.failed = str(e)
            else:
                comp.failed = None

    try:
        for p in pollers:  # first poll right away; also checks the key
            poll_job(p)()
    except KeyboardInterrupt:
        stop.set()

    if not fatal and clock() < until and not stop.is_set():
        sched = scheduler or BackgroundScheduler(
            timezone=UTC,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30},
        )
        for p in pollers:
            if not p.disabled:
                sched.add_job(poll_job(p), "interval", seconds=p.interval_s, id=p.name)
        sched.add_job(compact_job, "interval", seconds=settings.live_compact_minutes * 60,
                      id="compact")  # fmt: skip
        sched.start()
        print("collecting … Ctrl+C stops and prints a summary", file=out)
        try:
            while not stop.wait(max(0.0, min(1.0, (until - clock()).total_seconds()))):
                if clock() >= until:
                    break
        except KeyboardInterrupt:
            print("\nCtrl+C — finishing the running poll …", file=out)
        finally:
            try:
                sched.shutdown(wait=True)
            except KeyboardInterrupt:  # second Ctrl+C: do not wait for the running poll
                sched.shutdown(wait=False)

    if fatal:  # e.g. key revoked mid-run: still compact what was collected
        print(f"stopped: {fatal[0]}", file=out)
    ended = clock()
    try:
        print("compacting …", file=out)
        compact_job()
    except KeyboardInterrupt:
        comp.failed = "interrupted"
    report = _print_summary(settings, pollers, comp, started, ended, ended < until, out)

    runs = settings.curated_dir / "live_runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"run={started:%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  run report: {path}", file=out)
    return 2 if fatal else 1 if comp.failed else 0


def compact_only(settings: Settings, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    ledger = Ledger(settings.curated_dir / "_loaded.json")
    res = compact_live(settings, ledger, load_service_points(settings, make_session()))
    print(f"compacted {res.files} snapshots · service days {', '.join(res.dates) or '–'}"
          f" · live aggregates {', '.join(res.months) or '–'} · {res.weather_rows:,} weather rows"
          f" · raw deleted {', '.join(res.raw_deleted) or '–'}", file=out)  # fmt: skip
    return 0


# --- self-test -----------------------------------------------------------------------------


def _demo_feed(at: datetime, delay: int, cancelled: bool = False) -> bytes:
    f = pb.FeedMessage()
    f.header.gtfs_realtime_version = "2.0"
    f.header.timestamp = int(at.timestamp())
    tu = f.entity.add(id="demo").trip_update
    tu.trip.trip_id, tu.trip.start_date, tu.trip.start_time = "demo", f"{at:%Y%m%d}", "25:10:00"
    if cancelled:
        tu.trip.schedule_relationship = pb.TripDescriptor.CANCELED
        return f.SerializeToString()
    u = tu.stop_time_update.add(stop_sequence=1, stop_id="ch:1:sloid:9000:0:3")
    u.arrival.delay = delay
    return f.SerializeToString()


def selbsttest(out: TextIO | None = None) -> int:
    """Backoff, rate limit and compaction semantics on synthetic feeds — no network access."""
    out = out or sys.stdout
    t0 = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
    now = [t0]
    calls: list[datetime] = []

    def flaky(at: datetime) -> Snapshot:
        calls.append(at)
        if len(calls) <= 3:
            raise SourceError("demo", 503, "unavailable")
        return Snapshot(pd.DataFrame({"x": [1]}), len(calls))

    p = Poller("demo", flaky, lambda s, at: 1, 60, clock=lambda: now[0])
    for _ in range(12):
        p.tick()
        now[0] += timedelta(seconds=30)  # ticks twice as often as allowed
        p.tick()
        now[0] += timedelta(seconds=30)
    gaps = [(b - a).total_seconds() for a, b in pairwise(calls)]

    with tempfile.TemporaryDirectory() as d:
        s = Settings(_env_file=None, data_dir=Path(d))  # type: ignore[call-arg]
        write = raw_writer(s.raw_dir / TRIP_UPDATES)
        for i, (delay, cancelled) in enumerate([(60, False), (240, False)]):
            at = t0 + timedelta(minutes=i)
            feed = gtfs_rt.parse_feed(_demo_feed(at, delay, cancelled))
            write(Snapshot(gtfs_rt.trip_updates_frame(feed, at, include_bare_trips=True)), at)
        sp = pd.DataFrame({"number": ["8509000"], "sloid": ["ch:1:sloid:9000"], "name": ["Chur"]})
        ledger = Ledger(s.curated_dir / "_loaded.json")
        compact_live(s, ledger, sp, today=t0.date())
        first = pd.read_parquet(fact_path(s.curated_dir, "2026-09-30")).iloc[0]
        at = t0 + timedelta(minutes=2)
        feed = gtfs_rt.parse_feed(_demo_feed(at, 0, cancelled=True))
        write(Snapshot(gtfs_rt.trip_updates_frame(feed, at, include_bare_trips=True)), at)
        compact_live(s, ledger, sp, today=t0.date())
        last = pd.read_parquet(fact_path(s.curated_dir, "2026-09-30")).iloc[0]

    results = [
        ("GTFS-RT: ≤ 1 request per minute, also while ticking faster", min(gaps) >= 60),
        ("GTFS-RT: exponential backoff after errors, then recovers",
         [int(g) for g in gaps[:4]] == [60, 120, 240, 60] and p.received == 5),
        ("GTFS-RT: every missing snapshot counted (3 errors + 4 skipped)", p.missing_count() == 7),
        ("Compaction: last observation kept", first.delay_s == 240),
        ("Compaction: SLOID → BPUIC (history key)", first.station_key == "8509000"),
        ("Compaction: hour from start_time 25:10 → 1", first.hour_local == 1),
        ("Compaction: late cancellation is not a delay (BR2)",
         last.status == "CANCELED" and pd.isna(last.delay_s)),
    ]  # fmt: skip
    for name, ok in results:
        print(f"  [{'OK' if ok else 'FEHL'}] {name}", file=out)
    passed = all(bool(ok) for _, ok in results)
    print("SELBSTTEST " + ("OK" if passed else "FEHLGESCHLAGEN"), file=out)
    return 0 if passed else 1


# --- CLI -----------------------------------------------------------------------------------


def parse_until(value: str, now: datetime) -> datetime:
    """ISO date-time; without an offset it is Zurich local time."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(LOCAL_TZ))
    if dt <= now:
        raise ValueError(f"--until {value} is in the past")
    return dt


def _positive_hours(value: str) -> float:
    try:
        hours = float(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from e
    if hours <= 0:
        raise argparse.ArgumentTypeError("--hours must be > 0")
    return hours


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    window = p.add_mutually_exclusive_group()
    window.add_argument("--hours", type=_positive_hours, help="collect for this many hours")
    window.add_argument("--until", metavar="YYYY-MM-DDTHH:MM", help="collect until (Zurich time)")
    p.add_argument("--stations", default="all", help="MeteoSwiss: all, none or e.g. CHU,DAV")
    p.add_argument("--compact-only", action="store_true", help="only compact raw snapshots")
    p.add_argument("--selbsttest", action="store_true", help="offline logic check, no network")
    args = p.parse_args(argv)
    if args.selbsttest:
        return selbsttest()

    now = _utcnow()
    until = None
    if not args.compact_only:
        if args.hours is None and args.until is None:
            p.error("one of --hours or --until is required")
        try:
            until = (
                now + timedelta(hours=args.hours) if args.hours else parse_until(args.until, now)
            )
        except ValueError as e:
            p.error(str(e))

    settings = get_settings()
    configure_logging(settings)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)  # one INFO line per job run
    settings.ensure_dirs()
    if until is None:
        return compact_only(settings)

    stations = {"all": None, "none": []}.get(args.stations.lower(), args.stations.split(","))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())  # docker stop → clean shutdown
    return run(settings, until, meteo_stations=stations, stop=stop)


if __name__ == "__main__":
    sys.exit(main())
