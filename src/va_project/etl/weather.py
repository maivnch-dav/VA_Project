"""`fact_weather_10min` (UTC) → `agg_weather_day` and `agg_weather_month` (Europe/Zurich).

Days and months are local calendar days/months (AC3). Each day carries a coverage per
parameter (readings / expected 10-min slots of that local day, so 138 or 150 on DST switch
days). Monthly values use only days with coverage ≥ COMPLETE_SHARE for that parameter;
`n_days_<param>` says how many days that is. A snow day has a max snow depth ≥ SNOW_DAY_CM.
`snow_depth_med_cm` is the daily median: the snow sensors spike in summer (a few 10-min values
of 10–25 cm on bare ground), which the max picks up and the median ignores (canton map, US-30).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from va_project.config import LOCAL_TZ

COMPLETE_SHARE = 0.9
SNOW_DAY_CM = 1.0
FACT_GLOB = "fact_weather_10min/*/*/*.parquet"

_DAY_SQL = """
WITH obs AS (
    SELECT DISTINCT ON (station, ts)  -- history and live may both hold a reading
        station, ts, timezone($tz, ts) AS local_ts,
        temp_c, precip_mm, snow_depth_cm, sunshine_min, wind_ms
    FROM read_parquet($glob, hive_partitioning = true, union_by_name = true,
                      hive_types = {'station': VARCHAR, 'year': INTEGER})
), d AS (
    SELECT station, local_ts::DATE AS local_date,
           count(temp_c) AS n_temp, count(precip_mm) AS n_precip,
           count(snow_depth_cm) AS n_snow, count(sunshine_min) AS n_sun,
           avg(temp_c) AS temp_mean_c, min(temp_c) AS temp_min_c, max(temp_c) AS temp_max_c,
           sum(precip_mm) AS precip_mm, max(snow_depth_cm) AS snow_depth_max_cm,
           median(snow_depth_cm) AS snow_depth_med_cm,
           sum(sunshine_min) AS sunshine_min, max(wind_ms) AS wind_max_ms
    FROM obs
    GROUP BY station, local_date
), e AS (
    SELECT *, ((epoch(timezone($tz, (local_date + 1)::TIMESTAMP))
                - epoch(timezone($tz, local_date::TIMESTAMP))) // 600)::INTEGER AS expected_obs
    FROM d
)
SELECT station, local_date, expected_obs,
       n_temp / expected_obs AS cov_temp, n_precip / expected_obs AS cov_precip,
       n_snow / expected_obs AS cov_snow, n_sun / expected_obs AS cov_sun,
       temp_mean_c, temp_min_c, temp_max_c, precip_mm, snow_depth_max_cm, snow_depth_med_cm,
       sunshine_min, wind_max_ms
FROM e
ORDER BY station, local_date
"""

_MONTH_SQL = """
SELECT station, strftime(local_date, '%Y-%m') AS month,
       count(*)::INTEGER AS n_days,
       count(*) FILTER (WHERE cov_temp >= $ok)::INTEGER AS n_days_temp,
       count(*) FILTER (WHERE cov_precip >= $ok)::INTEGER AS n_days_precip,
       count(*) FILTER (WHERE cov_snow >= $ok)::INTEGER AS n_days_snow,
       count(*) FILTER (WHERE cov_sun >= $ok)::INTEGER AS n_days_sun,
       avg(temp_mean_c) FILTER (WHERE cov_temp >= $ok) AS temp_mean_c,
       min(temp_min_c) FILTER (WHERE cov_temp >= $ok) AS temp_min_c,
       max(temp_max_c) FILTER (WHERE cov_temp >= $ok) AS temp_max_c,
       sum(precip_mm) FILTER (WHERE cov_precip >= $ok) AS precip_mm,
       count(*) FILTER (WHERE cov_snow >= $ok AND snow_depth_max_cm >= $snow)::INTEGER
           AS snow_days,
       max(snow_depth_max_cm) FILTER (WHERE cov_snow >= $ok) AS snow_depth_max_cm,
       sum(sunshine_min) FILTER (WHERE cov_sun >= $ok) / 60 AS sunshine_h
FROM read_parquet($day)
GROUP BY station, month
ORDER BY station, month
"""


@dataclass(frozen=True)
class WeatherAggregate:
    day_path: Path
    month_path: Path
    n_stations: int
    n_days: int


def _write(con: duckdb.DuckDBPyConnection, sql: str, params: dict[str, object], path: Path) -> int:
    table = con.execute(sql, params).to_arrow_table()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)
    return int(table.num_rows)


def aggregate_weather(curated_dir: Path) -> WeatherAggregate:
    """Rebuild both weather aggregates from all 10-minute readings (small: ~15 M rows)."""
    if not any(curated_dir.glob(FACT_GLOB)):
        raise FileNotFoundError(f"no fact_weather_10min files under {curated_dir}")
    day_path = curated_dir / "agg_weather_day" / "part.parquet"
    month_path = curated_dir / "agg_weather_month" / "part.parquet"
    con = duckdb.connect()
    try:
        n_days = _write(con, _DAY_SQL, {"tz": LOCAL_TZ, "glob": str(curated_dir / FACT_GLOB)},
                        day_path)  # fmt: skip
        _write(con, _MONTH_SQL, {"ok": COMPLETE_SHARE, "snow": SNOW_DAY_CM, "day": str(day_path)},
               month_path)  # fmt: skip
        row = con.execute(
            "SELECT count(DISTINCT station) FROM read_parquet($p)", {"p": str(day_path)}
        ).fetchone()
    finally:
        con.close()
    return WeatherAggregate(day_path, month_path, int(row[0]) if row else 0, n_days)


_CAPS_SQL = """
SELECT station,
       avg((temp_c IS NOT NULL)::INTEGER) >= $share AS has_temp,
       avg((precip_mm IS NOT NULL)::INTEGER) >= $share AS has_precip,
       avg((snow_depth_cm IS NOT NULL)::INTEGER) >= $share AS has_snow
FROM read_parquet($glob, hive_partitioning = true, union_by_name = true,
                  hive_types = {'station': VARCHAR, 'year': INTEGER})
GROUP BY station
ORDER BY station
"""


def station_capabilities(curated_dir: Path, share: float = COMPLETE_SHARE) -> pd.DataFrame:
    """Which parameters each station measured for (almost) the whole loaded period.

    ≥ 90 %, not "at all": a sensor added mid-period (CHU snow depth from April 2025) would
    otherwise be chosen and leave the earlier months without values.
    """
    cols = ["station", "has_temp", "has_precip", "has_snow"]
    if not any(curated_dir.glob(FACT_GLOB)):
        return pd.DataFrame(columns=cols)
    con = duckdb.connect()
    try:
        df = con.execute(_CAPS_SQL, {"share": share, "glob": str(curated_dir / FACT_GLOB)}).df()
    finally:
        con.close()
    return df[cols]
