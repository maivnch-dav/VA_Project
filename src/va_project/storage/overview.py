"""SQL for the KPI tiles of the start page `/` (US-27 AC2): Switzerland per local month."""

from __future__ import annotations

from typing import NamedTuple

import duckdb

from va_project.storage.canton_map import (
    HESTA_SWITZERLAND,
    HESTA_TOTAL,
    MIN_COVERAGE,
    SNOW_STATION_DAY_CTE,
)


class DelayMonth(NamedTuple):
    month: str
    n: int  # planned stop events
    n_used: int  # with an actual time, outliers excluded (basis of mean and late share)
    n_late: int  # ≥ 3 min
    n_canceled: int
    delay_s_sum: float  # Σ mean_delay_s × n_used → event-weighted mean


def ch_delays(con: duckdb.DuckDBPyConnection) -> list[DelayMonth]:
    """Ist-Daten (history, BR6) of stations linked to a Swiss municipality, per month."""
    rows = con.execute(
        """
        SELECT strftime(d.service_date, '%Y-%m'), sum(d.n), sum(d.n_actual - d.n_outlier),
               sum(d.n_late_3min), sum(d.n_canceled),
               sum(CASE WHEN isnan(d.mean_delay_s) THEN 0
                        ELSE d.mean_delay_s * (d.n_actual - d.n_outlier) END)
        FROM agg_delay_stop_day d JOIN dim_station s USING (station_key)
        WHERE d.source = 'history' AND s.link_status = 'linked'
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    return [DelayMonth(m, int(n), int(u), int(late), int(c), float(s or 0))
            for m, n, u, late, c, s in rows]  # fmt: skip


def ch_nights(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """HESTA nights «Schweiz», all origins; unpublished/suppressed months are left out."""
    rows = con.execute(
        """
        SELECT printf('%04d-%02d', year, month), sum(nights)
        FROM fact_hesta_monthly
        WHERE level = 'region' AND area_code = $ch AND herkunftsland = $total
              AND nights IS NOT NULL AND NOT isnan(nights)
        GROUP BY 1
        """,
        {"ch": HESTA_SWITZERLAND, "total": HESTA_TOTAL},
    ).fetchall()
    return {m: float(v) for m, v in rows}


def new_snow_days(con: duckdb.DuckDBPyConnection, new_snow_cm: float) -> dict[str, float | None]:
    """Ø over the snow stations of the days with ΔHS ≥ new_snow_cm, per month with weather rows.

    A station counts in a month only if it has at least one day with a known ΔHS there; a month
    without any such station is None (not 0).
    """
    rows = con.execute(
        SNOW_STATION_DAY_CTE  # noqa: S608 — constant SQL text; values are bound parameters
        + """
        , st AS (
            SELECT station, strftime(local_date, '%Y-%m') AS month,
                   count(*) FILTER (WHERE hn >= $new) AS n_new, count(hn) AS n_known
            FROM h GROUP BY ALL
        )
        SELECT month, avg(n_new) FILTER (WHERE n_known > 0) FROM st GROUP BY 1
        """,
        {"cov": MIN_COVERAGE, "new": new_snow_cm},
    ).fetchall()
    return {m: None if v is None else float(v) for m, v in rows}
