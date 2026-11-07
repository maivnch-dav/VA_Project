"""SQL for the canton map on `/` (US-30): tourism nights, delays and snow per canton.

All queries take a connection from `storage.duck.connect`; the caller checks which views
exist. Values are bound parameters; the SQL text is constant.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

import duckdb

HESTA_TOTAL = "Herkunftsland - Total"
HESTA_SWITZERLAND = "8100"  # "Schweiz" row of _103, not a region
GEOJSON = "dim_canton.geojson"
MIN_COVERAGE = 0.9  # a station-day counts only with ≥ 90 % of its 10-min values (HR2)


# Per snow-measuring SMN station and local day: hs = daily *median* snow depth with ≥ 90 % coverage
# (else NULL), hn = max(0, hs − hs of the day before) when both days count (HR2 ΔHS, D13).
# Needs the parameter $cov. Used by the canton map and the KPI «Neuschneetage» (services/overview).
SNOW_STATION_DAY_CTE = """
WITH v AS (  -- NaN → NULL first: DuckDB sorts NaN above every number
    SELECT w.station, s.kanton, w.local_date,
           CASE WHEN NOT isnan(w.cov_snow) AND w.cov_snow >= $cov
                     AND NOT isnan(w.snow_depth_med_cm)
                THEN w.snow_depth_med_cm END AS hs
    FROM agg_weather_day w
    JOIN dim_smn_station s ON s.station = w.station AND s.has_snow
), d AS (
    SELECT *, lag(hs) OVER win AS prev_hs, lag(local_date) OVER win AS prev_date
    FROM v WINDOW win AS (PARTITION BY station ORDER BY local_date)
), h AS (
    SELECT station, kanton, local_date, hs,
           CASE WHEN prev_date = local_date - 1 THEN greatest(0, hs - prev_hs) END AS hn
    FROM d
)
"""


class RegionNights(NamedTuple):
    region_code: str
    region: str
    month: str  # YYYY-MM, local calendar month
    nights: float | None  # None = suppressed / not published
    is_estimate: bool


class CantonRegion(NamedTuple):
    kanton: str
    region_code: str
    region: str
    nights: float  # HESTA municipality nights over all loaded months (dominance weight)
    n_gemeinden: int


class CantonDelays(NamedTuple):
    kanton: str
    month: str
    n: int  # planned stop events
    n_actual: int
    n_late: int  # ≥ 3 min (n_late_3min, fixed in the aggregate, D14)
    n_canceled: int
    n_stations: int


class CantonSnowDay(NamedTuple):
    kanton: str
    day: date
    cls: str  # new | cover | none | unknown


def load_geojson(curated_dir: Path) -> dict[str, Any] | None:
    path = curated_dir / GEOJSON
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def region_nights(con: duckdb.DuckDBPyConnection) -> list[RegionNights]:
    rows = con.execute(
        """
        SELECT area_code, any_value(area_name), printf('%04d-%02d', year, month),
               sum(nights), coalesce(bool_or(is_estimate), false)
        FROM fact_hesta_monthly
        WHERE level = 'region' AND herkunftsland = $total AND area_code <> $ch
        GROUP BY ALL ORDER BY 1, 3
        """,
        {"total": HESTA_TOTAL, "ch": HESTA_SWITZERLAND},
    ).fetchall()
    return [RegionNights(str(c), str(n), m, _num(v), bool(e)) for c, n, m, v, e in rows]


def canton_regions(con: duckdb.DuckDBPyConnection, *, with_nights: bool) -> list[CantonRegion]:
    """Every (canton, tourism region) pair, heaviest first within a canton.

    Weight = HESTA municipality nights of all loaded months (suppressed cells count 0), then the
    number of municipalities, so a canton without HESTA data still gets a region.
    """
    nights = (
        "SELECT TRY_CAST(area_code AS BIGINT) AS bfs_nr, sum(nights) AS nights "
        "FROM fact_hesta_monthly WHERE level = 'gemeinde' AND herkunftsland = $total GROUP BY 1"
        if with_nights
        else "SELECT NULL::BIGINT AS bfs_nr, NULL::DOUBLE AS nights WHERE false"
    )
    rows = con.execute(
        f"""
        WITH n AS ({nights})
        SELECT g.kanton, g.tourism_region_code, any_value(g.tourism_region),
               coalesce(sum(n.nights), 0), count(*)
        FROM dim_gemeinde g LEFT JOIN n USING (bfs_nr)
        WHERE g.bfs_nr < 9000 AND g.kanton IS NOT NULL AND g.tourism_region_code IS NOT NULL
        GROUP BY ALL ORDER BY 1, 4 DESC, 5 DESC, 2
        """,  # noqa: S608 — `nights` is one of two constant strings above
        {"total": HESTA_TOTAL} if with_nights else {},
    ).fetchall()
    return [CantonRegion(k, str(c), str(r), float(n), int(g)) for k, c, r, n, g in rows]


def canton_delays(con: duckdb.DuckDBPyConnection) -> list[CantonDelays]:
    """History only (BR6); stations linked to a Swiss municipality; cancellations apart (BR2)."""
    rows = con.execute(
        """
        SELECT s.kanton, strftime(d.service_date, '%Y-%m'), sum(d.n), sum(d.n_actual),
               sum(d.n_late_3min), sum(d.n_canceled), count(DISTINCT d.station_key)
        FROM agg_delay_stop_day d JOIN dim_station s USING (station_key)
        WHERE d.source = 'history' AND s.link_status = 'linked' AND s.kanton IS NOT NULL
        GROUP BY ALL ORDER BY 1, 2
        """
    ).fetchall()
    return [CantonDelays(k, m, *(int(x or 0) for x in rest)) for k, m, *rest in rows]


def delay_days(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Loaded Ist-Daten days per month (a month with fewer days than the calendar is partial)."""
    rows = con.execute(
        "SELECT strftime(service_date, '%Y-%m'), count(DISTINCT service_date) "
        "FROM agg_delay_stop_day WHERE source = 'history' GROUP BY 1"
    ).fetchall()
    return {m: int(n) for m, n in rows}


def has_column(con: duckdb.DuckDBPyConnection, view: str, column: str) -> bool:
    rows = con.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = $v AND column_name = $c",
        {"v": view, "c": column},
    ).fetchall()
    return bool(rows)


def snow_stations(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    rows = con.execute(
        "SELECT kanton, count(*) FROM dim_smn_station WHERE has_snow AND kanton IS NOT NULL "
        "GROUP BY 1"
    ).fetchall()
    return {k: int(n) for k, n in rows}


def canton_snow_days(
    con: duckdb.DuckDBPyConnection, new_snow_cm: float, cover_cm: float
) -> list[CantonSnowDay]:
    """Snow class per canton and local day over the canton's snow-measuring SMN stations.

    Per station: HS = daily *median* snow depth (the max picks up summer sensor spikes),
    counted with ≥ 90 % coverage; new snow HN = max(0, HS − HS of the day
    before) when both days count (HR2, ΔHS — SwissMetNet has no new-snow sensor, D13).
    Per canton-day: `new` if any station has HN ≥ new_snow_cm, else `cover` if any has
    HS ≥ cover_cm, else `none` if any station measured, else `unknown`.
    """
    rows = con.execute(
        SNOW_STATION_DAY_CTE  # noqa: S608 — constant SQL text; values are bound parameters
        + """
        SELECT kanton, local_date,
               CASE WHEN bool_or(hn >= $new) THEN 'new'
                    WHEN bool_or(hs >= $cover) THEN 'cover'
                    WHEN count(hs) > 0 THEN 'none'
                    ELSE 'unknown' END
        FROM h WHERE kanton IS NOT NULL GROUP BY ALL ORDER BY 1, 2
        """,
        {"cov": MIN_COVERAGE, "new": new_snow_cm, "cover": cover_cm},
    ).fetchall()
    return [CantonSnowDay(k, d, c) for k, d, c in rows]


def _num(v: Any) -> float | None:
    """NaN (pandas writes missing floats as NaN) and NULL → None."""
    return None if v is None or v != v else float(v)
