"""History loader (US-02a): Ist-Daten delays, MeteoSwiss 10-minute data and HESTA by month.

    python -m va_project.collectors.history --from 2025-01 [--to YYYY-MM]
           [--sources istdaten,meteo,hesta] [--stations all|CHU,DAV] [--keep-zip] [--selbsttest]

Re-runs skip what `curated/_loaded.json` marks complete; an interrupted run resumes (partial
zip download, staged days). Months not archived yet are loaded from daily CSVs as partial.
"""

from __future__ import annotations

import argparse
import io
import logging
import shutil
import sys
import zipfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TextIO
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd
import requests

from va_project.collectors import hesta, istdaten, meteo, service_points
from va_project.collectors.http import SourceError, make_session
from va_project.config import LOCAL_TZ, Settings, configure_logging, get_settings
from va_project.etl.aggregate import aggregate_month
from va_project.etl.link import link_stops
from va_project.storage.ledger import Ledger

log = logging.getLogger(__name__)

SOURCES = ("istdaten", "meteo", "hesta")
SIZE_TARGET_MB = 50.0  # AC4: curated size per month
_GB = 1024**3


@dataclass
class MonthReport:
    month: str
    status: str  # loaded | partial | skipped | unchanged | missing | failed
    variant: str = ""
    days: int = 0
    rows_read: int = 0
    n: int = 0
    n_canceled: int = 0
    n_foreign: int = 0
    n_passthrough: int = 0
    actual_share: float | None = None  # n_actual / non-cancelled stop events
    station_link_rate: float | None = None  # stations with a BFS municipality
    event_link_rate: float | None = None  # … weighted by stop events
    size_mb: float = 0.0
    note: str = ""


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def _print_month(r: MonthReport, out: TextIO) -> None:
    if r.status in ("skipped", "unchanged", "missing", "failed"):
        print(f"  {r.month}  {r.status}{' — ' + r.note if r.note else ''}", file=out)
        return
    size_flag = "" if r.size_mb < SIZE_TARGET_MB else f" (> target {SIZE_TARGET_MB:.0f} MB)"
    print(
        f"  {r.month}  {r.status:<8} {r.variant:<10} {r.days:>2} days · {r.rows_read:>11,} rows"
        f" · actual {_pct(r.actual_share)} · stations linked {_pct(r.station_link_rate)}"
        f" (events {_pct(r.event_link_rate)}) · {r.size_mb:.1f} MB{size_flag}",
        file=out,
    )
    extra = f"    cancelled {r.n_canceled:,} · foreign dropped {r.n_foreign:,}"
    extra += f" · pass-through dropped {r.n_passthrough:,}"
    print(extra + (f" · {r.note}" if r.note else ""), file=out)


# --- linking (AC4) ----------------------------------------------------------


def load_service_points(settings: Settings, session: requests.Session) -> pd.DataFrame | None:
    """Newest saved service-point list, else download and save one; None if unavailable."""
    folder = settings.raw_dir / "service_points"
    saved = sorted(folder.glob("fetched=*.parquet"))
    if saved:
        return pd.read_parquet(saved[-1])
    try:
        df = service_points.parse_service_points(
            service_points.fetch_service_points(session, settings.service_points_url)
        )
    except SourceError as e:
        log.warning("service points unavailable, link rate not reported: %s", e)
        return None
    folder.mkdir(parents=True, exist_ok=True)
    df.to_parquet(folder / f"fetched={datetime.now(UTC):%Y-%m-%d}.parquet", index=False)
    return df


def link_rates(
    stations: dict[str, int], sp: pd.DataFrame | None
) -> tuple[float | None, float | None]:
    if sp is None or not stations:
        return None, None
    linked = link_stops(pd.Series(list(stations), dtype=str), sp)
    ok = (linked["link_status"] == "linked").to_numpy()
    weights = np.array(list(stations.values()), dtype=float)
    return float(ok.mean()), float(weights[ok].sum() / weights.sum())


# --- Ist-Daten --------------------------------------------------------------


def _check_free_space(folder: Path, min_gb: float) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(folder).free / _GB
    if free < min_gb:
        raise OSError(f"only {free:.1f} GB free in {folder}, need {min_gb:.1f} GB")


def _load_month(
    settings: Settings,
    session: requests.Session,
    plan: istdaten.MonthPlan,
    staging: Path,
    keep_zip: bool,
    sp: pd.DataFrame | None,
) -> tuple[MonthReport, dict[str, object]]:
    tmp = settings.tmp_dir / "istdaten"
    _check_free_space(tmp, settings.history_min_free_gb)
    zip_path = tmp / f"{plan.month}.zip"
    if plan.kind == "daily":
        for day, url in plan.urls.items():
            if istdaten.staging_path(staging, day).exists():
                continue
            csv = istdaten.download(session, url, tmp / f"{day}.csv")
            with csv.open("rb") as f:
                istdaten.stage_csv(f, istdaten.staging_path(staging, day))
            csv.unlink()
    else:
        istdaten.download(session, plan.urls["zip"], zip_path)
        try:
            istdaten.stage_zip(zip_path, staging)
        except zipfile.BadZipFile as e:
            zip_path.unlink(missing_ok=True)  # corrupt download → fetch again next run
            raise SourceError(istdaten.SOURCE, None, f"{zip_path.name}: {e}") from e

    days = istdaten.staged_days(staging)
    all_days = {d.isoformat() for d in istdaten.days_of_month(plan.month)}
    missing = sorted(all_days - set(days))
    complete = plan.kind != "daily" or not missing
    agg = aggregate_month(
        [istdaten.staging_path(staging, d) for d in days],
        settings.curated_dir,
        source="history",
        month=plan.month,
    )
    station_rate, event_rate = link_rates(agg.stations, sp)
    non_canceled = agg.n - agg.n_canceled
    report = MonthReport(
        month=plan.month,
        status="loaded" if complete else "partial",
        variant=plan.kind,
        days=len(days),
        rows_read=agg.rows_read,
        n=agg.n,
        n_canceled=agg.n_canceled,
        n_foreign=agg.n_foreign,
        n_passthrough=agg.n_passthrough,
        actual_share=agg.n_actual / non_canceled if non_canceled else None,
        station_link_rate=station_rate,
        event_link_rate=event_rate,
        size_mb=agg.size_bytes / 1024**2,
        note=f"{len(missing)} days missing" if missing else "",
    )
    if complete:
        shutil.rmtree(staging, ignore_errors=True)
        if not keep_zip:
            zip_path.unlink(missing_ok=True)
    entry: dict[str, object] = {**asdict(report), "complete": complete, "day_list": days}
    return report, entry


def load_istdaten(
    settings: Settings,
    session: requests.Session,
    months: list[str],
    ledger: Ledger,
    keep_zip: bool = False,
) -> list[MonthReport]:
    todo = [m for m in months if not ledger.is_complete("istdaten", m)]
    reports = [MonthReport(m, "skipped", note="already loaded") for m in months if m not in todo]
    if not todo:
        return reports
    archive = istdaten.fetch_archive_listing(
        session, settings.istdaten_archive_listing_url, settings.istdaten_archive_base_url
    )
    daily: dict[str, str] = {}
    if any(m not in archive for m in todo):
        try:
            daily = istdaten.fetch_daily_page(session, settings.istdaten_daily_url)
        except SourceError as e:
            log.warning("daily Ist-Daten page unavailable: %s", e)
    sp = load_service_points(settings, session)

    for month in todo:
        plan = istdaten.plan_month(month, archive, daily)
        if plan is None:
            reports.append(MonthReport(month, "missing", note="not in archive or daily files"))
            continue
        staging = settings.tmp_dir / "istdaten" / month
        prev = ledger.get("istdaten", month)
        if prev is not None and prev.get("variant") != plan.kind:
            shutil.rmtree(staging, ignore_errors=True)  # e.g. daily → archive: start clean
        elif prev is not None and set(plan.urls) <= set(istdaten.staged_days(staging)):
            reports.append(MonthReport(month, "unchanged", note="no new daily files"))
            continue
        try:
            report, entry = _load_month(settings, session, plan, staging, keep_zip, sp)
        except (
            SourceError, OSError, ValueError, NotImplementedError, duckdb.Error,
            requests.RequestException,
        ) as e:  # fmt: skip
            # one bad month (network, disk, format change) must not abort the others
            log.error("istdaten %s failed: %s", month, e)
            reports.append(MonthReport(month, "failed", variant=plan.kind, note=str(e)))
            continue
        ledger.put("istdaten", month, entry)
        reports.append(report)
    return sorted(reports, key=lambda r: r.month)


# --- MeteoSwiss -------------------------------------------------------------


@dataclass
class MeteoSummary:
    stations: int = 0
    years_loaded: int = 0
    years_skipped: int = 0
    rows: int = 0
    empty: int = 0
    failed: list[str] = field(default_factory=list)


def load_meteo(
    settings: Settings,
    session: requests.Session,
    months: list[str],
    ledger: Ledger,
    stations: list[str] | None,
    today: date,
) -> MeteoSummary:
    # dim_smn_station (with altitude) is built by `python -m va_project.etl.build` (US-03)
    listing = meteo.list_stations(session, settings.meteo_stac_url)

    wanted = listing["station"].tolist() if stations is None else [s.upper() for s in stations]
    years = sorted({int(m[:4]) for m in months})
    summary = MeteoSummary(stations=len(wanted))
    for st in wanted:
        todo = [y for y in years if not ledger.is_complete("meteo", f"{st}:{y}")]
        summary.years_skipped += len(years) - len(todo)
        if not todo:
            continue
        try:
            got = meteo.fetch_history(session, settings.meteo_stac_url, st, todo, today.year)
        except SourceError as e:
            log.warning("meteo %s failed: %s", st, e)
            summary.failed.append(st)
            continue
        for year, df in got.items():
            if df.empty:
                summary.empty += 1
                continue
            path = settings.curated_dir / "fact_weather_10min" / f"station={st}" / f"year={year}"
            path.mkdir(parents=True, exist_ok=True)
            df.drop(columns="station").assign(ingested_at=datetime.now(UTC)).to_parquet(
                path / "part.parquet", index=False
            )
            ledger.put("meteo", f"{st}:{year}", {"complete": year < today.year, "rows": len(df)})
            summary.years_loaded += 1
            summary.rows += len(df)
    return summary


# --- HESTA ------------------------------------------------------------------


def load_hesta(
    settings: Settings, session: requests.Session, months: list[str], ledger: Ledger
) -> dict[str, dict[str, object]]:
    """Always re-fetched (BFS revises figures and publishes with ~2 months lag)."""
    now = datetime.now(UTC)
    result: dict[str, dict[str, object]] = {}
    for table, level in hesta.LEVELS.items():
        rec = hesta.fetch_history(session, settings.bfs_pxweb_url, table, months)
        raw = settings.raw_dir / "hesta" / table / f"fetched={now:%Y-%m-%d}.parquet"
        raw.parent.mkdir(parents=True, exist_ok=True)
        rec.to_parquet(raw, index=False)

        fact = hesta.to_monthly_fact(rec).assign(ingested_at=now)
        path = settings.curated_dir / "fact_hesta_monthly" / f"level={level}" / "part.parquet"
        if path.exists():  # keep months outside this run
            old = pd.read_parquet(path)
            fetched = set(zip(fact["year"], fact["month"], strict=True))
            keep = [(y, m) not in fetched for y, m in zip(old["year"], old["month"], strict=True)]
            fact = pd.concat([old[keep], fact], ignore_index=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        fact.to_parquet(path, index=False)

        published = rec.dropna(subset=["value"])
        ym = int((published["year"] * 100 + published["month"]).max()) if len(published) else 0
        last = f"{ym // 100:04d}-{ym % 100:02d}" if ym else None
        info: dict[str, object] = {"rows": len(fact), "last_published": last}
        ledger.put("hesta", table, {"complete": False, **info})
        result[table] = info
    return result


# --- CLI --------------------------------------------------------------------


def run(
    settings: Settings,
    months: list[str],
    sources: Sequence[str] = SOURCES,
    *,
    stations: list[str] | None = None,
    keep_zip: bool = False,
    session: requests.Session | None = None,
    out: TextIO = sys.stdout,
    today: date | None = None,
) -> int:
    sess = session or make_session()
    today = today or datetime.now(ZoneInfo(LOCAL_TZ)).date()
    ledger = Ledger(settings.curated_dir / "_loaded.json")
    print(f"SwissFlow VA — history loader (US-02a) · {months[0]} … {months[-1]}", file=out)
    failures = 0

    if "istdaten" in sources:
        print("\nIst-Daten (source=history):", file=out)
        try:
            reports = load_istdaten(settings, sess, months, ledger, keep_zip)
        except SourceError as e:
            print(f"  failed: {e}", file=out)
            failures += 1
        else:
            for r in reports:
                _print_month(r, out)
            failures += sum(r.status == "failed" for r in reports)

    if "meteo" in sources:
        print("\nMeteoSwiss 10-minute:", file=out)
        try:
            ms = load_meteo(settings, sess, months, ledger, stations, today)
        except SourceError as e:
            print(f"  failed: {e}", file=out)
            failures += 1
        else:
            print(
                f"  {ms.stations} stations · {ms.years_loaded} station-years loaded"
                f" ({ms.rows:,} rows) · {ms.years_skipped} already complete"
                f" · {ms.empty} without data",
                file=out,
            )
            if ms.failed:
                print(f"  failed stations: {', '.join(ms.failed)}", file=out)
                failures += len(ms.failed)

    if "hesta" in sources:
        print("\nHESTA:", file=out)
        try:
            for table, info in load_hesta(settings, sess, months, ledger).items():
                print(f"  {table}: {info['rows']:,} rows · last published month"
                      f" {info['last_published']}", file=out)  # fmt: skip
        except SourceError as e:
            print(f"  failed: {e}", file=out)
            failures += 1

    print(f"\nDone — {failures} failure(s). Ledger: {ledger.path}", file=out)
    return 0 if failures == 0 else 2


def selbsttest(out: TextIO = sys.stdout) -> int:
    """BR2 semantics on a synthetic day — no network access."""
    import tempfile

    header = ";".join([
        "BETRIEBSTAG", "FAHRT_BEZEICHNER", "ZUSATZFAHRT_TF", "FAELLT_AUS_TF", "BPUIC",
        "HALTESTELLEN_NAME", "ANKUNFTSZEIT", "AN_PROGNOSE", "AN_PROGNOSE_STATUS",
        "ABFAHRTSZEIT", "AB_PROGNOSE", "AB_PROGNOSE_STATUS", "DURCHFAHRT_TF",
    ])  # fmt: skip
    d = "15.01.2025"
    rows = [
        f"{d};a;false;false;8509000;Chur;{d} 10:00;{d} 10:04:00;REAL;;;;false",
        f"{d};b;false;true;8509000;Chur;{d} 11:00;{d} 11:30:00;PROGNOSE;;;;false",
        f"{d};c;false;false;8509000;Chur;{d} 12:00;;UNBEKANNT;;;;false",
        f"{d};d;false;false;5510017;Budapest;;;;{d} 06:30;{d} 06:35:00;REAL;false",
    ]
    csv = ("\n".join([header, *rows]) + "\n").encode()
    with tempfile.TemporaryDirectory() as d:
        stage = Path(d) / "day=2025-01-15.parquet"
        istdaten.stage_csv(io.BytesIO(csv), stage)
        agg = aggregate_month([stage], Path(d), source="history", month="2025-01")
        day = pd.read_parquet(agg.day_path).iloc[0]
    results = [
        ("Ist-Daten: foreign station dropped", agg.n == 3 and agg.n_foreign == 1),
        ("Ist-Daten: cancelled counted, never a delay", day.n_canceled == 1),
        ("Ist-Daten: only REAL/GESCHAETZT averaged", day.n_actual == 1 and day.mean_delay_s == 240),
        ("Ist-Daten: UNBEKANNT counted separately", day.n_unknown == 1),
        ("MeteoSwiss: this year from `recent`",
         meteo.history_asset("CHU", 2026, 2026) == "ogd-smn_chu_t_recent.csv"),
    ]  # fmt: skip
    for name, ok in results:
        print(f"  [{'OK' if ok else 'FEHL'}] {name}", file=out)
    passed = all(bool(ok) for _, ok in results)
    print("SELBSTTEST " + ("OK" if passed else "FEHLGESCHLAGEN"), file=out)
    return 0 if passed else 1


def _sources(value: str) -> list[str]:
    items = [s.strip() for s in value.split(",") if s.strip()]
    unknown = sorted(set(items) - set(SOURCES))
    if unknown or not items:
        raise argparse.ArgumentTypeError(f"choose from {', '.join(SOURCES)}; got {value!r}")
    return items


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--from", dest="start", metavar="YYYY-MM", help="first month to load")
    p.add_argument("--to", dest="end", metavar="YYYY-MM", help="last month (default: this month)")
    p.add_argument("--sources", type=_sources, default=list(SOURCES), help="istdaten,meteo,hesta")
    p.add_argument("--stations", default="all", help="MeteoSwiss stations: all or e.g. CHU,DAV")
    p.add_argument("--keep-zip", action="store_true", help="keep Ist-Daten zips after loading")
    p.add_argument("--selbsttest", action="store_true", help="offline logic check, no network")
    args = p.parse_args(argv)
    if args.selbsttest:
        return selbsttest()
    if args.start is None:
        p.error("--from is required")
    end = args.end or f"{datetime.now(ZoneInfo(LOCAL_TZ)):%Y-%m}"
    try:
        months = istdaten.month_range(args.start, end)
    except ValueError as e:
        p.error(str(e))
    stations = None if args.stations == "all" else args.stations.split(",")
    settings = get_settings()
    configure_logging(settings)
    settings.ensure_dirs()
    return run(settings, months, args.sources, stations=stations, keep_zip=args.keep_zip)


if __name__ == "__main__":
    sys.exit(main())
