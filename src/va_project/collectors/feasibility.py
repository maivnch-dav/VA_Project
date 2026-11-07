"""US-01 feasibility check for all sources.

    python -m va_project.collectors.feasibility              # live check, report only
    python -m va_project.collectors.feasibility --save       # also write raw Parquet to DATA_DIR
    python -m va_project.collectors.feasibility --selbsttest # offline logic check, no network

Exit code: 0 = every check OK, 2 = partially OK, 1 = nothing usable.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TextIO

import pandas as pd
import requests
from google.transit import gtfs_realtime_pb2 as pb

from va_project.collectors import gtfs_rt, hesta, meteo, service_points
from va_project.collectors.http import AccessDeniedError, SourceError, make_session
from va_project.config import Settings, configure_logging, get_settings
from va_project.etl.link import LinkRates, link_rates, link_stops, nearest_point

STOP_LINK_TARGET = 0.80  # BRD G1 (a)
Status = Literal["ok", "skipped", "failed"]


@dataclass
class Check:
    source: str
    status: Status = "ok"
    records: int = 0
    missing: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class Collected:
    trip_updates: pd.DataFrame | None = None
    alerts: pd.DataFrame | None = None
    weather: pd.DataFrame | None = None
    weather_item: dict[str, Any] | None = None
    hesta: pd.DataFrame | None = None
    hesta_bfs: set[int] = field(default_factory=set)
    stops: pd.DataFrame | None = None


def _missing(df: pd.DataFrame, cols: Sequence[str]) -> dict[str, float]:
    return {c: float(df[c].isna().mean()) if len(df) else 0.0 for c in cols}


def _pct(x: float) -> str:
    return f"{x:6.1%}"


def _guard(check: Check, action: Callable[[], None]) -> None:
    """Run a source check; turn expected failures into a readable status."""
    try:
        action()
    except AccessDeniedError as e:
        check.status = "failed"
        check.notes.append(f"access denied — {e}")
        check.notes.append("→ check the key/subscription for this API in the API manager")
    except (SourceError, ValueError, LookupError, KeyError) as e:
        check.status = "failed"
        check.notes.append(f"{type(e).__name__}: {e}")


# --- individual checks ------------------------------------------------------


def _check_trip_updates(s: Settings, sess: requests.Session, now: datetime, c: Collected) -> Check:
    check = Check("gtfs_rt_trip_updates")
    key = s.gtfs_rt_api_key
    if key is None:
        check.status = "skipped"
        check.notes.append(
            "no GTFS_RT_API_KEY in .env — https://api-manager.opentransportdata.swiss/"
        )
        return check

    def run() -> None:
        raw = gtfs_rt.fetch_feed(sess, s.gtfs_rt_url, key, check.source)
        feed = gtfs_rt.parse_feed(raw)
        df = gtfs_rt.trip_updates_frame(feed, ingested_at=now)
        c.trip_updates = df
        trips = [e.trip_update.trip for e in feed.entity if e.HasField("trip_update")]
        cancelled = sum(t.schedule_relationship == pb.TripDescriptor.CANCELED for t in trips)
        delayable = df[
            ~df["stop_status"].isin(["SKIPPED", "NO_DATA"])
            & ~df["trip_status"].isin(["CANCELED", "DELETED"])
        ]
        check.records = len(df)
        check.missing = {
            "delay_s (non-skipped, non-cancelled)": float(delayable["delay_s"].isna().mean())
            if len(delayable) else 0.0,
            **_missing(df, ["route_id"]),
        }  # fmt: skip
        age = now - df["feed_ts"].iloc[0].to_pydatetime() if len(df) else None
        check.notes += [
            f"{len(raw) / 1e6:.1f} MB, {len(trips)} trips, {cancelled} cancelled, "
            f"{int((df['stop_status'] == 'SKIPPED').sum())} skipped stops",
            f"feed age: {age.total_seconds():.0f} s" if age is not None else "empty feed",
        ]
        if len(df) == 0:
            check.status = "failed"

    _guard(check, run)
    return check


def _check_alerts(s: Settings, sess: requests.Session, now: datetime, c: Collected) -> Check:
    check = Check("gtfs_rt_alerts")
    key = s.gtfs_rt_api_key
    if key is None:
        check.status = "skipped"
        check.notes.append("no GTFS_RT_API_KEY in .env")
        return check

    def run() -> None:
        feed = gtfs_rt.parse_feed(gtfs_rt.fetch_feed(sess, s.gtfs_sa_url, key, check.source))
        df = gtfs_rt.alerts_frame(feed, ingested_at=now)
        c.alerts = df
        check.records = len(df)
        check.missing = _missing(df, ["active_to", "header"])
        check.notes.append(f"effects: {df['effect'].value_counts().head(3).to_dict()}")

    _guard(check, run)
    return check


def _check_meteo(s: Settings, sess: requests.Session, now: datetime, c: Collected) -> Check:
    check = Check("meteo_smn")

    def run() -> None:
        df, item = meteo.fetch_observations(sess, s.meteo_stac_url, s.meteo_station)
        c.weather, c.weather_item = df, item
        check.records = len(df)
        check.missing = _missing(df, list(meteo.PARAMS.values()))
        if len(df):
            last = df["ts"].max().to_pydatetime()
            check.notes.append(
                f"station {s.meteo_station}: {df['ts'].min():%Y-%m-%d %H:%M} → "
                f"{last:%H:%M} UTC, latest {(now - last).total_seconds() / 60:.0f} min old"
            )

    _guard(check, run)
    return check


def _check_hesta(s: Settings, sess: requests.Session, now: datetime, c: Collected) -> Check:
    check = Check("hesta")

    def run() -> None:
        # municipality list first: the link metric (b) must not depend on the table query
        gem_meta = hesta.fetch_metadata(sess, s.bfs_pxweb_url, hesta.TABLE_GEMEINDE)
        c.hesta_bfs = {int(x) for x in hesta.dim_codes(gem_meta, "Gemeinde") if x.isdigit()}
        check.notes.append(f"Gemeinde table covers {len(c.hesta_bfs)} municipalities")

        meta = hesta.fetch_metadata(sess, s.bfs_pxweb_url, hesta.TABLE_REGION)
        region = hesta.code_for_label(meta, "Tourismusregion", "Graubünden")
        years = hesta.dim_codes(meta, "Jahr")[-2:]
        selections = {
            "Jahr": years,
            "Monat": hesta.ALL,
            "Tourismusregion": [region],
            "Herkunftsland": hesta.ALL,
            "Indikator": hesta.ALL,
        }
        doc = hesta.fetch_table(sess, s.bfs_pxweb_url, hesta.TABLE_REGION, selections)
        rec = hesta.to_records(hesta.parse_jsonstat2(doc), level="region")
        c.hesta = rec
        published = rec[rec["value"].notna()]
        latest: tuple[int, int] | None = None
        if len(published):
            last = published.sort_values(["year", "month"]).iloc[-1]
            latest = (int(last["year"]), int(last["month"]))
            before = (rec["year"] * 12 + rec["month"]) <= latest[0] * 12 + latest[1]
            suppressed = float(rec.loc[before, "value"].isna().mean())
        else:
            suppressed = 1.0
        check.records = len(rec)
        check.missing = {"value (published months)": suppressed}
        check.notes.append(
            f"Graubünden, {years[0]}–{years[-1]}, {rec['herkunftsland'].nunique()} countries; "
            f"latest published month: {latest[0]}-{latest[1]:02d}"
            if latest
            else "no data"
        )
        if latest:
            lag = (now.year * 12 + now.month) - (latest[0] * 12 + latest[1])
            check.notes.append(f"publication lag ≈ {lag} months")

    _guard(check, run)
    return check


def _check_service_points(
    s: Settings, sess: requests.Session, _now: datetime, c: Collected
) -> Check:
    check = Check("service_points")

    def run() -> None:
        df = service_points.parse_service_points(
            service_points.fetch_service_points(sess, s.service_points_url)
        )
        c.stops = df
        ch = df[(df["country"] == "CH") & df["is_stop"]]
        check.records = len(df)
        check.missing = {"bfs_nr (Swiss stop points)": float(ch["bfs_nr"].isna().mean())}
        check.notes.append(f"{len(ch)} Swiss stop points, {df['country'].nunique()} countries")

    _guard(check, run)
    return check


def _check_links(c: Collected) -> Check:
    check = Check("links")
    if c.trip_updates is None or c.stops is None:
        check.status = "skipped"
        check.notes.append("needs GTFS-RT trip updates and service points")
        return check

    rates: LinkRates = link_rates(link_stops(c.trip_updates["stop_id"], c.stops), c.hesta_bfs)
    check.records = rates.n_events
    check.notes += [
        f"(a) stop → Gemeinde: {_pct(rates.stop_rate)} of {rates.n_stops} stops "
        f"(target ≥ {STOP_LINK_TARGET:.0%}); events {_pct(rates.event_rate)}, "
        f"Swiss events {_pct(rates.swiss_event_rate)}",
        f"(b) linked events in a HESTA municipality: {_pct(rates.hesta_event_share)} "
        "(rest → Tourismusregion, US-03)",
        f"unlinked by reason: {rates.unlinked_by_reason or '—'}",
    ]
    if rates.stop_rate < STOP_LINK_TARGET:
        check.status = "failed"

    if c.weather_item is not None:
        lat, lon = meteo.station_location(c.weather_item)
        swiss = c.stops[(c.stops["country"] == "CH") & c.stops["is_stop"]]
        row, km = nearest_point(lat, lon, swiss)
        check.notes.append(f"weather station → nearest stop: {row['name']} ({km:.1f} km)")
    return check


# --- saving -----------------------------------------------------------------


def _save(s: Settings, c: Collected, now: datetime) -> list[Path]:
    day, hms = f"date={now:%Y-%m-%d}", f"{now:%H%M%S}"
    targets: list[tuple[pd.DataFrame | None, Path]] = [
        (c.trip_updates, s.raw_dir / "gtfs_rt" / "trip_updates" / day / f"{hms}.parquet"),
        (c.alerts, s.raw_dir / "gtfs_rt" / "alerts" / day / f"{hms}.parquet"),
        (c.weather, s.raw_dir / "meteo" / "smn" / day / f"{s.meteo_station.lower()}_{hms}.parquet"),
        (c.hesta, s.raw_dir / "hesta" / hesta.TABLE_REGION / f"fetched={now:%Y-%m-%d}.parquet"),
        (c.stops, s.raw_dir / "service_points" / f"fetched={now:%Y-%m-%d}.parquet"),
    ]
    written = []
    for df, path in targets:
        if df is not None and len(df):
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
            written.append(path)
    return written


# --- report -----------------------------------------------------------------


def _print_check(ch: Check, out: TextIO) -> None:
    mark = {"ok": "[OK]  ", "skipped": "[SKIP]", "failed": "[FEHL]"}[ch.status]
    print(f"\n{mark} {ch.source}: {ch.records} records", file=out)
    for col, share in ch.missing.items():
        print(f"         missing {col}: {_pct(share)}", file=out)
    for note in ch.notes:
        print(f"         {note}", file=out)


def run(
    settings: Settings,
    out: TextIO = sys.stdout,
    save: bool = False,
    session: requests.Session | None = None,
) -> int:
    sess = session or make_session()
    now = datetime.now(UTC)
    c = Collected()
    print(f"SwissFlow VA — feasibility check (US-01) · {now:%Y-%m-%d %H:%M} UTC", file=out)

    checks = [
        fn(settings, sess, now, c)
        for fn in (_check_trip_updates, _check_alerts, _check_meteo, _check_hesta,
                   _check_service_points)
    ]  # fmt: skip
    checks.append(_check_links(c))
    for ch in checks:
        _print_check(ch, out)

    if save:
        paths = _save(settings, c, now)
        print(f"\nSaved {len(paths)} files under {settings.raw_dir}", file=out)

    n_ok = sum(ch.status == "ok" for ch in checks)
    print(f"\nSummary: {n_ok}/{len(checks)} checks OK", file=out)
    return 0 if n_ok == len(checks) else (1 if n_ok == 0 else 2)


# --- offline self-test ------------------------------------------------------


def selbsttest(out: TextIO = sys.stdout) -> int:
    """Run parsers and linking on synthetic data — no network access."""
    now = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    results: list[tuple[str, bool]] = []

    feed = pb.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(now.timestamp())
    tu = feed.entity.add(id="t").trip_update
    tu.trip.trip_id = "t"
    u = tu.stop_time_update.add(stop_sequence=1, stop_id="ch:1:sloid:9000:0:1")
    u.arrival.delay = 120
    u = tu.stop_time_update.add(stop_sequence=2, stop_id="8509002")
    u.schedule_relationship = pb.TripUpdate.StopTimeUpdate.SKIPPED
    df = gtfs_rt.trip_updates_frame(gtfs_rt.parse_feed(feed.SerializeToString()), now)
    ok = df["delay_s"].iloc[0] == 120 and pd.isna(df["delay_s"].iloc[1])
    results.append(("GTFS-RT: delay parsed, skipped stop is not a delay", bool(ok)))

    w = meteo.parse_observations(
        b"station_abbr;reference_timestamp;tre200s0;fkl010z0\r\nCHU;29.09.2026 12:00;17.5;\r\n"
    )
    ok = w["ts"].iloc[0] == pd.Timestamp(now) and pd.isna(w["wind_ms"].iloc[0])
    results.append(("MeteoSwiss: UTC timestamp, empty field is NaN", bool(ok)))

    doc = {
        "id": ["Jahr", "Monat", "Tourismusregion", "Herkunftsland", "Indikator"],
        "size": [1, 2, 1, 1, 1],
        "dimension": {
            "Jahr": {"category": {"index": {"2026": 0}, "label": {"2026": "2026"}}},
            "Monat": {"category": {"index": {"7": 0, "8": 1},
                                   "label": {"7": "Juli", "8": "August"}}},
            "Tourismusregion": {"category": {"index": {"1": 0}, "label": {"1": "Graubünden"}}},
            "Herkunftsland": {"category": {"index": {"00": 0}, "label": {"00": "Total"}}},
            "Indikator": {"category": {"index": {"2": 0}, "label": {"2": "Logiernächte"}}},
        },
        "value": [668545, None],
        "status": {"1": "..."},
    }  # fmt: skip
    rec = hesta.to_records(hesta.parse_jsonstat2(doc), level="region")
    ok = rec["value"].iloc[0] == 668545 and bool(rec["suppressed"].iloc[1])
    results.append(("HESTA: unpublished month is NaN, not 0", bool(ok)))

    sp = service_points.parse_service_points(
        b"number;sloid;designationOfficial;isoCountryCode;cantonAbbreviation;fsoNumber;"
        b"municipalityName;wgs84North;wgs84East;height;stopPoint\n"
        b"8509000;ch:1:sloid:9000;Chur;CH;GR;3901;Chur;46.853;9.529;585;true\n"
        b"8509002;ch:1:sloid:9002;Landquart;CH;GR;3955;Landquart;46.965;9.555;527;true\n"
    )
    rates = link_rates(link_stops(df["stop_id"], sp), hesta_bfs={3901})
    ok = rates.stop_rate == 1.0 and rates.hesta_event_share == 0.5
    results.append(("Linking: sloid + number → BFS municipality, HESTA share", ok))

    for name, ok in results:
        print(f"  [{'OK' if ok else 'FEHL'}] {name}", file=out)
    passed = all(ok for _, ok in results)
    print("SELBSTTEST " + ("OK" if passed else "FEHLGESCHLAGEN"), file=out)
    return 0 if passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--selbsttest", action="store_true", help="offline logic check, no network")
    p.add_argument("--save", action="store_true", help="write raw Parquet files to DATA_DIR/raw")
    args = p.parse_args(argv)
    if args.selbsttest:
        return selbsttest()
    settings = get_settings()
    configure_logging(settings)
    return run(settings, save=args.save)


if __name__ == "__main__":
    sys.exit(main())
