"""Link the sources (US-03): dimension tables and local-time weather aggregates.

    python -m va_project.etl.build [--steps weather,dims] [--selbsttest]

`weather` rebuilds agg_weather_day/month from fact_weather_10min (offline).
`cantons` (opt-in, needs network once) fetches and simplifies the 26 canton outlines for the
canton map on `/` (curated/dim_canton.geojson).
`dims` fetches the BFS municipality levels and SwissMetNet station metadata, rebuilds
dim_gemeinde, dim_smn_station and dim_station, and writes the AC1 report of stations with
delay data that could not be linked to a municipality (curated/reports/unlinked_stations.csv).
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TextIO
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from va_project.collectors import bfs_communes, cantons, hesta, meteo
from va_project.collectors.history import load_service_points
from va_project.collectors.http import SourceError, make_session
from va_project.config import LOCAL_TZ, Settings, configure_logging, get_settings
from va_project.etl.dims import (
    LinkSummary,
    build_dim_gemeinde,
    build_dim_smn_station,
    build_dim_station,
    unlinked_report,
)
from va_project.etl.weather import aggregate_weather, station_capabilities
from va_project.storage.duck import connect

STEPS = ("weather", "dims")  # default
ALL_STEPS = (*STEPS, "cantons")
LINK_TARGET = 0.8  # AC1
HESTA_TOTAL_REGION = "8100"  # "Schweiz" in _103


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def _save_raw(settings: Settings, folder: str, raw: bytes, today: date) -> None:
    path = settings.raw_dir / folder / f"fetched={today:%Y-%m-%d}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def _hesta(curated: Path, level: str) -> pd.DataFrame | None:
    path = curated / "fact_hesta_monthly" / f"level={level}" / "part.parquet"
    return pd.read_parquet(path, columns=["area_code", "area_name"]) if path.exists() else None


def region_names(settings: Settings, session: requests.Session) -> dict[str, str]:
    """Tourism region code → HESTA label, so dims and fact_hesta_monthly join by name too."""
    regions = _hesta(settings.curated_dir, "region")
    if regions is not None:
        pairs = regions.drop_duplicates("area_code").itertuples(index=False)
        names = {str(code): str(name) for code, name in pairs}
    else:
        meta = hesta.fetch_metadata(session, settings.bfs_pxweb_url, hesta.TABLE_REGION)
        var = next(v for v in meta["variables"] if v["code"] == "Tourismusregion")
        names = dict(zip(map(str, var["values"]), var["valueTexts"], strict=True))
    names.pop(HESTA_TOTAL_REGION, None)
    return names


def data_stations(curated: Path) -> pd.DataFrame:
    """Stations with stop events in the delay aggregates (both sources): key, name, events."""
    con, created = connect(curated)
    try:
        if "agg_delay_stop_day" not in created:
            return pd.DataFrame(columns=["station_key", "station_name", "n"])
        return con.execute(
            "SELECT station_key, mode(nullif(station_name, '')) AS station_name, sum(n) AS n "
            "FROM agg_delay_stop_day GROUP BY station_key ORDER BY station_key"
        ).df()
    finally:
        con.close()


def _pct(x: float) -> str:
    return f"{x:.1%}"


def _print_summary(summary: LinkSummary, n_linked: int, out: TextIO) -> None:
    ok = "OK" if summary.station_rate >= LINK_TARGET else "FAIL"
    print(
        f"  stations linked {_pct(summary.station_rate)} ({n_linked}/{summary.n_stations})"
        f" · events {_pct(summary.event_rate)} · in Switzerland {_pct(summary.swiss_station_rate)}"
        f" · AC1 target ≥ {LINK_TARGET:.0%}: {ok}",
        file=out,
    )
    reasons = ", ".join(f"{k} {v}" for k, v in summary.by_reason.items()) or "none"
    print(f"  not linked: {reasons}", file=out)


def _print_weather_links(stations: pd.DataFrame, keys: pd.Series, out: TextIO) -> None:
    st = stations[stations["station_key"].isin(keys) & (stations["link_status"] == "linked")]
    if st.empty:
        return
    d, snow = st["smn_dist_km"], st["smn_snow_dist_km"]
    far_alt = int((st["smn_alt_diff_m"].abs() > 500).sum())
    print(
        f"  weather: nearest station median {d.median():.1f} km (p90 {d.quantile(0.9):.1f} km)"
        f" · snow station median {snow.median():.1f} km · {far_alt} stations > 500 m"
        " above/below their weather station",
        file=out,
    )


def build_dims(
    settings: Settings, session: requests.Session, today: date, out: TextIO
) -> LinkSummary | None:
    now = datetime.now(UTC)
    cur = settings.curated_dir
    levels_raw = bfs_communes.fetch_levels(session, settings.bfs_communes_url, today)
    meta_raw = meteo.fetch_meta_stations(session, settings.smn_meta_url)
    sp = load_service_points(settings, session)
    if sp is None:
        raise SourceError("service_points", None, "no saved or downloadable service points")
    names = region_names(settings, session)
    _save_raw(settings, "bfs_communes", levels_raw, today)
    _save_raw(settings, "meteo/meta_stations", meta_raw, today)

    hesta_g = _hesta(cur, "gemeinde")
    hesta_codes = set() if hesta_g is None else {int(c) for c in hesta_g["area_code"].unique()}
    gemeinden = build_dim_gemeinde(bfs_communes.parse_levels(levels_raw), names, hesta_codes, now)
    smn = build_dim_smn_station(meteo.parse_meta_stations(meta_raw), station_capabilities(cur), now)
    stations = build_dim_station(sp, gemeinden, smn, now)
    _write_parquet(gemeinden, cur / "dim_gemeinde.parquet")
    _write_parquet(smn, cur / "dim_smn_station.parquet")
    _write_parquet(stations, cur / "dim_station.parquet")
    print(
        f"  dim_gemeinde {len(gemeinden)} · dim_smn_station {len(smn)}"
        f" ({int(smn['has_snow'].sum())} measure snow) · dim_station {len(stations)}",
        file=out,
    )
    stale = sorted(hesta_codes - set(gemeinden["bfs_nr"]))
    if stale:
        print(f"  HESTA _101 municipalities not in the current list: "
              f"{', '.join(map(str, stale))} (use region data)", file=out)  # fmt: skip

    data = data_stations(cur)
    if data.empty:
        print("  no delay aggregates yet — AC1 report skipped", file=out)
        return None
    report, summary = unlinked_report(data, stations)
    path = cur / "reports" / "unlinked_stations.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(path, index=False)
    _print_summary(summary, summary.n_stations - len(report), out)
    _print_weather_links(stations, data["station_key"], out)
    print(f"  report: {path}", file=out)
    return summary


def run(
    settings: Settings,
    steps: Sequence[str] = STEPS,
    *,
    session: requests.Session | None = None,
    out: TextIO = sys.stdout,
    today: date | None = None,
) -> int:
    sess = session or make_session()
    today = today or datetime.now(ZoneInfo(LOCAL_TZ)).date()
    failures = 0
    print("SwissFlow VA — linking build (US-03)", file=out)
    if "weather" in steps:
        print("\nWeather aggregates (Europe/Zurich days and months):", file=out)
        try:
            w = aggregate_weather(settings.curated_dir)
            print(f"  {w.n_stations} stations · {w.n_days:,} station-days", file=out)
        except FileNotFoundError as e:
            print(f"  weather skipped: {e}", file=out)
    if "dims" in steps:
        print("\nDimensions:", file=out)
        try:
            build_dims(settings, sess, today, out)
        except (SourceError, ValueError) as e:
            print(f"  dims failed: {e}", file=out)
            failures += 1
    if "cantons" in steps:
        print("\nCanton outlines (swissBOUNDARIES3D):", file=out)
        path = settings.curated_dir / "dim_canton.geojson"
        try:
            n = cantons.build(sess, settings.geoadmin_canton_url, path)
            print(f"  {n} cantons · {path.stat().st_size / 1e6:.1f} MB → {path}", file=out)
        except (SourceError, ValueError, KeyError) as e:
            print(f"  cantons failed: {e}", file=out)
            failures += 1
    print(f"\nDone — {failures} failure(s).", file=out)
    return 0 if failures == 0 else 2


def selbsttest(out: TextIO = sys.stdout) -> int:
    """Linking and local-time rules on synthetic data — no network access."""
    from va_project.etl.timeutil import local_month

    now = datetime(2026, 9, 30, tzinfo=UTC)
    levels = bfs_communes.parse_levels(
        b"HistoricalCode,BfsCode,Name,CantonId,STREG2022\n1,3901,Chur,18,1\n2,371,Biel/Bienne,2,8\n"
    )
    gemeinden = build_dim_gemeinde(levels, {"1": "Graubünden", "8": "Jura & Drei-Seen-Land"},
                                   {3901}, now)  # fmt: skip
    smn = build_dim_smn_station(
        pd.DataFrame({"station": ["CHU", "DAV"], "name": ["Chur", "Davos"], "kanton": ["GR"] * 2,
                      "lat": [46.8706, 46.8130], "lon": [9.5308, 9.8436],
                      "altitude_m": [556, 1594]}),
        pd.DataFrame({"station": ["CHU", "DAV"], "has_temp": [True] * 2,
                      "has_precip": [True] * 2, "has_snow": [False, True]}),
        now,
    )  # fmt: skip
    sp = pd.read_csv(io.StringIO(
        "number,sloid,name,country,bfs_nr,lat,lon,height_m\n"
        "8509000,ch:1:sloid:9000,Chur,CH,3901,46.853,9.529,585\n"
        "8506162,,Ermatingen,CH,9329,47.67,9.08,396\n"
    ), dtype={"number": str})  # fmt: skip
    st = build_dim_station(sp, gemeinden, smn, now).set_index("station_key")
    chur = st.loc["8509000"]
    results = [
        ("Linking: BFS municipality and tourism region",
         chur.bfs_nr == 3901 and chur.tourism_region == "Graubünden"),
        ("Linking: lake code is not a municipality", st.loc["8506162", "link_status"] == "lake"),
        ("Weather: nearest by haversine, distance stored",
         chur.smn_station == "CHU" and 0 < chur.smn_dist_km < 3),
        ("Weather: snow from nearest station measuring snow", chur.smn_snow_station == "DAV"),
        ("Time: 31.12. 23:30 UTC is January in Zurich",
         local_month(datetime(2025, 12, 31, 23, 30, tzinfo=UTC)) == "2026-01"),
    ]  # fmt: skip
    for name, ok in results:
        print(f"  [{'OK' if ok else 'FEHL'}] {name}", file=out)
    passed = all(bool(ok) for _, ok in results)
    print("SELBSTTEST " + ("OK" if passed else "FEHLGESCHLAGEN"), file=out)
    return 0 if passed else 1


def _steps(value: str) -> list[str]:
    items = [s.strip() for s in value.split(",") if s.strip()]
    if not items or set(items) - set(ALL_STEPS):
        raise argparse.ArgumentTypeError(f"choose from {', '.join(ALL_STEPS)}; got {value!r}")
    return items


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--steps", type=_steps, default=list(STEPS), help="weather,dims (default) · cantons"
    )
    p.add_argument("--selbsttest", action="store_true", help="offline logic check, no network")
    args = p.parse_args(argv)
    if args.selbsttest:
        return selbsttest()
    settings = get_settings()
    configure_logging(settings)
    settings.ensure_dirs()
    return run(settings, args.steps)


if __name__ == "__main__":
    sys.exit(main())
