"""DuckDB views over the curated Parquet files (hive-partitioned)."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import duckdb


class View(NamedTuple):
    glob: str  # relative to the curated directory
    hive_types: str | None  # partition keys stay text ('2025-01' must not become a date)


VIEWS: dict[str, View] = {
    "agg_delay_stop_day": View(
        "agg_delay_stop_day/*/*/*.parquet", "{'source': VARCHAR, 'month': VARCHAR}"
    ),
    "agg_delay_stop_month_hour": View(
        "agg_delay_stop_month_hour/*/*/*.parquet", "{'source': VARCHAR, 'month': VARCHAR}"
    ),
    "fact_weather_10min": View(
        "fact_weather_10min/*/*/*.parquet", "{'station': VARCHAR, 'year': INTEGER}"
    ),
    "fact_hesta_monthly": View("fact_hesta_monthly/*/*.parquet", "{'level': VARCHAR}"),
    # live only (US-02b): one row per stop event, last GTFS-RT observation
    "fact_stop_delay": View("fact_stop_delay/*/*.parquet", "{'date': VARCHAR}"),
    # US-03: dimensions and local-time weather aggregates (single files)
    "dim_station": View("dim_station.parquet", None),
    "dim_gemeinde": View("dim_gemeinde.parquet", None),
    "dim_smn_station": View("dim_smn_station.parquet", None),
    "agg_weather_day": View("agg_weather_day/part.parquet", None),
    "agg_weather_month": View("agg_weather_month/part.parquet", None),
}

# Views over other views, created when all their inputs exist.
# v_station_day: delay per station and service day with municipality, region and the weather
# of that local day at the linked station (snow from the nearest station measuring snow).
DERIVED: dict[str, tuple[tuple[str, ...], str]] = {
    "v_station_day": (
        ("agg_delay_stop_day", "dim_station", "agg_weather_day"),
        """
        SELECT d.*, s.bfs_nr, s.gemeinde, s.kanton, s.tourism_region, s.link_status,
               s.smn_station, s.smn_dist_km, s.smn_snow_station, s.smn_snow_dist_km,
               w.temp_mean_c, w.precip_mm, w.cov_precip,
               ws.snow_depth_max_cm, ws.cov_snow
        FROM agg_delay_stop_day d
        LEFT JOIN dim_station s USING (station_key)
        LEFT JOIN agg_weather_day w
               ON w.station = s.smn_station AND w.local_date = d.service_date
        LEFT JOIN agg_weather_day ws
               ON ws.station = s.smn_snow_station AND ws.local_date = d.service_date
        """,
    ),
}


def connect(
    curated_dir: Path, database: str = ":memory:"
) -> tuple[duckdb.DuckDBPyConnection, list[str]]:
    """Connection with one view per table that has data; returns (connection, created views)."""
    con = duckdb.connect(database)
    created = []
    for name, view in VIEWS.items():
        if not any(curated_dir.glob(view.glob)):
            continue
        glob = str((curated_dir / view.glob).resolve()).replace("'", "''")
        # name, glob and types come from the constant table above, not from user input
        hive = (
            f"hive_partitioning = true, hive_types = {view.hive_types}"
            if view.hive_types
            else "hive_partitioning = false"
        )
        con.execute(
            f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{glob}', {hive})"  # noqa: S608
        )
        created.append(name)
    for name, (needs, sql) in DERIVED.items():
        if all(n in created for n in needs):
            con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")
            created.append(name)
    return con, created
