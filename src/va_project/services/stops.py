"""Linked stations and weather stations (US-03) for the API and the Dash views."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from va_project.storage.duck import connect

BBox = tuple[float, float, float, float]  # lon_min, lat_min, lon_max, lat_max

_BUILD_HINT = "Linking data not built yet — run `python -m va_project.etl.build`."

_STOP_COLUMNS = """
    station_key AS stop_id, NULL AS parent_station, name, lat, lon, bfs_nr, gemeinde, kanton,
    tourism_region, smn_station, smn_dist_km, sloid, link_status, altitude_m, smn_alt_diff_m,
    smn_snow_station, smn_snow_dist_km
"""
# lat/lon are required by the API schema → stations without coordinates are left out
_STOP_FILTER = """
FROM dim_station
WHERE NOT (isnan(lat) OR isnan(lon)) AND lat IS NOT NULL AND lon IS NOT NULL
  AND ($kanton IS NULL OR kanton = $kanton)
  AND ($region IS NULL OR tourism_region = $region OR tourism_region_code = $region)
  AND (NOT $linked_only OR link_status = 'linked')
  AND ($lon_min IS NULL OR (lon BETWEEN $lon_min AND $lon_max
                            AND lat BETWEEN $lat_min AND $lat_max))
"""


class DataNotReadyError(RuntimeError):
    """The curated tables this query needs have not been built yet."""


def _clean(value: Any) -> Any:
    """NaN (as pandas writes missing floats to Parquet) → None, so the JSON stays valid."""
    return None if isinstance(value, float) and math.isnan(value) else value


def _rows(cursor: Any) -> list[dict[str, Any]]:
    cols = [d[0] for d in cursor.description]
    return [{c: _clean(v) for c, v in zip(cols, row, strict=True)} for row in cursor.fetchall()]


def list_stops(
    curated_dir: Path,
    *,
    kanton: str | None = None,
    region: str | None = None,
    bbox: BBox | None = None,
    linked_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    """(total matching, one page of stations ordered by station key)."""
    con, created = connect(curated_dir)
    try:
        if "dim_station" not in created:
            raise DataNotReadyError(_BUILD_HINT)
        lon_min, lat_min, lon_max, lat_max = bbox or (None, None, None, None)
        params: dict[str, Any] = {
            "kanton": kanton, "region": region, "linked_only": linked_only,
            "lon_min": lon_min, "lat_min": lat_min, "lon_max": lon_max, "lat_max": lat_max,
        }  # fmt: skip
        # the SQL text is built from the constants above; values are bound parameters
        row = con.execute("SELECT count(*) " + _STOP_FILTER, params).fetchone()
        total = int(row[0]) if row else 0
        cursor = con.execute(
            "SELECT "
            + _STOP_COLUMNS
            + _STOP_FILTER
            + " ORDER BY station_key LIMIT $limit OFFSET $offset",
            {**params, "limit": limit, "offset": offset},
        )
        return total, _rows(cursor)
    finally:
        con.close()


def list_weather_stations(curated_dir: Path) -> list[dict[str, Any]]:
    con, created = connect(curated_dir)
    try:
        if "dim_smn_station" not in created:
            raise DataNotReadyError(_BUILD_HINT)
        cursor = con.execute(
            "SELECT station, name, kanton, lat, lon, altitude_m, has_temp, has_precip, has_snow "
            "FROM dim_smn_station ORDER BY station"
        )
        return _rows(cursor)
    finally:
        con.close()
