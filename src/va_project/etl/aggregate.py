"""Stop-event staging → `agg_delay_stop_day` and `agg_delay_stop_month_hour`.

BR2: cancelled stops are counted (`n_canceled`), never averaged as a delay. Only events with
an actual time count as `n_actual` (history: `REAL`/`GESCHAETZT`; live: last observed GTFS-RT
delay); forecasts and unknowns are counted separately. Actual delays outside
[DELAY_MIN_S, DELAY_MAX_S] are counted as `n_outlier` and left out of mean/p90. Foreign stations
and pass-throughs are dropped (counted in the result).

`source` and `month` are hive partition keys, so they are not stored inside the files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

DELAY_MIN_S = -30 * 60
DELAY_MAX_S = 6 * 3600
LATE_S = 3 * 60  # SBB punctuality: on time = less than 3 min late

Source = Literal["history", "live"]
# Per source: the stop events in one common shape. `is_actual` = counts towards mean/p90.
# history (Ist-Daten staging): only REAL/GESCHAETZT are actual times, PROGNOSE is a forecast.
# live (fact_stop_delay): the last GTFS-RT observation of a stop is its final delay, so every
#   scheduled stop with a delay counts; no delay = unknown; SKIPPED/CANCELED = cancelled (BR2).
_EVENTS_SQL: dict[Source, str] = {
    "history": """
        SELECT service_date, station_key, station_name, hour_local, delay_s, canceled,
               additional, passthrough, foreign_stop,
               (NOT canceled AND status IN ('REAL', 'GESCHAETZT') AND delay_s IS NOT NULL)
                   AS is_actual,
               status = 'PROGNOSE' AS is_forecast
        FROM read_parquet($files)""",
    "live": """
        SELECT service_date, station_key, station_name, hour_local, delay_s,
               status IN ('CANCELED', 'SKIPPED') AS canceled,
               trip_status IN ('ADDED', 'NEW') AS additional,
               false AS passthrough, foreign_stop,
               (status = 'SCHEDULED' AND delay_s IS NOT NULL) AS is_actual,
               false AS is_forecast
        FROM read_parquet($files)""",
}

_DAY_SQL = """
WITH ev AS (
    SELECT * FROM ({events}) WHERE NOT foreign_stop AND NOT passthrough
), e AS (
    SELECT *, is_actual AND delay_s BETWEEN $lo AND $hi AS used FROM ev
)
SELECT
    service_date,
    station_key,
    mode(nullif(station_name, '')) AS station_name,  -- some stop positions have no name
    count(*)::INTEGER AS n,
    count(*) FILTER (WHERE is_actual)::INTEGER AS n_actual,
    count(*) FILTER (WHERE NOT canceled AND NOT is_actual AND is_forecast)::INTEGER
        AS n_forecast,
    count(*) FILTER (WHERE NOT canceled AND NOT is_actual AND NOT is_forecast)::INTEGER
        AS n_unknown,
    count(*) FILTER (WHERE canceled)::INTEGER AS n_canceled,
    count(*) FILTER (WHERE additional)::INTEGER AS n_additional,
    count(*) FILTER (WHERE is_actual AND NOT used)::INTEGER AS n_outlier,
    avg(delay_s) FILTER (WHERE used) AS mean_delay_s,
    quantile_cont(delay_s, 0.9) FILTER (WHERE used) AS p90_delay_s,
    count(*) FILTER (WHERE used AND delay_s >= $late)::INTEGER AS n_late_3min
FROM e
GROUP BY service_date, station_key
ORDER BY service_date, station_key
"""

_MONTH_HOUR_SQL = """
WITH ev AS (
    SELECT * FROM ({events})
    WHERE NOT foreign_stop AND NOT passthrough AND hour_local IS NOT NULL
), e AS (
    SELECT *, is_actual AND delay_s BETWEEN $lo AND $hi AS used FROM ev
)
SELECT
    station_key,
    hour_local,
    count(*)::INTEGER AS n,
    count(*) FILTER (WHERE is_actual)::INTEGER AS n_actual,
    count(*) FILTER (WHERE canceled)::INTEGER AS n_canceled,
    avg(delay_s) FILTER (WHERE used) AS mean_delay_s,
    quantile_cont(delay_s, 0.9) FILTER (WHERE used) AS p90_delay_s,
    count(*) FILTER (WHERE used AND delay_s >= $late)::INTEGER AS n_late_3min
FROM e
GROUP BY station_key, hour_local
ORDER BY station_key, hour_local
"""

_TOTALS_SQL = """
SELECT count(*), count(*) FILTER (WHERE foreign_stop),
       count(*) FILTER (WHERE passthrough AND NOT foreign_stop)
FROM ({events})
"""


@dataclass(frozen=True)
class MonthAggregate:
    day_path: Path
    month_hour_path: Path
    rows_read: int
    n_foreign: int
    n_passthrough: int
    n: int  # stop events kept (Swiss, not pass-through)
    n_actual: int
    n_canceled: int
    size_bytes: int
    stations: dict[str, int] = field(default_factory=dict)  # station_key → n (for link rates)


def partition_path(curated_dir: Path, table: str, source: Source, month: str) -> Path:
    return curated_dir / table / f"source={source}" / f"month={month}" / "part.parquet"


def _write(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)


def aggregate_month(
    staging_files: list[Path], curated_dir: Path, *, source: Source, month: str
) -> MonthAggregate:
    """Aggregate one month of stop events; replaces that month's partitions.

    history: Ist-Daten staging files · live: `fact_stop_delay` partitions of the month."""
    if not staging_files:
        raise ValueError(f"no staging files for {month}")
    params = {
        "files": [str(p) for p in staging_files],
        "lo": DELAY_MIN_S,
        "hi": DELAY_MAX_S,
        "late": LATE_S,
    }
    events = _EVENTS_SQL[source]  # constant SQL chosen by a Literal, not user input
    con = duckdb.connect()
    try:
        day = con.execute(_DAY_SQL.format(events=events), params).to_arrow_table()
        month_hour = con.execute(_MONTH_HOUR_SQL.format(events=events), params).to_arrow_table()
        totals = con.execute(
            _TOTALS_SQL.format(events=events), {"files": params["files"]}
        ).fetchone()
    finally:
        con.close()
    if totals is None:  # an aggregate query always returns one row
        raise RuntimeError("totals query returned no row")

    day_path = partition_path(curated_dir, "agg_delay_stop_day", source, month)
    mh_path = partition_path(curated_dir, "agg_delay_stop_month_hour", source, month)
    _write(day, day_path)
    _write(month_hour, mh_path)

    stations: dict[str, int] = {}
    for key, n in zip(day["station_key"].to_pylist(), day["n"].to_pylist(), strict=True):
        stations[key] = stations.get(key, 0) + n
    return MonthAggregate(
        day_path=day_path,
        month_hour_path=mh_path,
        rows_read=int(totals[0]),
        n_foreign=int(totals[1]),
        n_passthrough=int(totals[2]),
        n=int(pc.sum(day["n"]).as_py() or 0),
        n_actual=int(pc.sum(day["n_actual"]).as_py() or 0),
        n_canceled=int(pc.sum(day["n_canceled"]).as_py() or 0),
        size_bytes=day_path.stat().st_size + mh_path.stat().st_size,
        stations=stations,
    )
