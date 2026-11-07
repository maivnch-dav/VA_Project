"""Response/request models mirroring docs/api-spec.yaml."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceHealthOut(BaseModel):
    name: str
    last_ingest_at: datetime | None
    stale: bool


class HealthOut(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    sources: list[SourceHealthOut]


class Problem(BaseModel):
    """RFC 7807 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None


# --- US-03 --------------------------------------------------------------------


class StopsQuery(BaseModel):
    """Query string of GET /stops (unknown parameters are ignored)."""

    kanton: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    region: str | None = Field(default=None, max_length=100)  # tourism region name or code
    bbox: str | None = Field(default=None, pattern=r"^-?\d+(\.\d+)?(,-?\d+(\.\d+)?){3}$")
    linked_only: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    @field_validator("bbox")
    @classmethod
    def _ordered_bbox(cls, v: str | None) -> str | None:
        if v is not None:
            lon_min, lat_min, lon_max, lat_max = map(float, v.split(","))
            if lon_min > lon_max or lat_min > lat_max:
                raise ValueError("bbox must be lon_min,lat_min,lon_max,lat_max")
        return v

    def bbox_tuple(self) -> tuple[float, float, float, float] | None:
        if self.bbox is None:
            return None
        a, b, c, d = map(float, self.bbox.split(","))
        return a, b, c, d


class StopOut(BaseModel):
    stop_id: str
    parent_station: str | None = None
    name: str
    lat: float
    lon: float
    bfs_nr: int | None = None
    gemeinde: str | None = None
    kanton: str | None = None
    tourism_region: str | None = None
    smn_station: str | None = None
    smn_dist_km: float | None = None
    # additions to the original spec (US-03)
    sloid: str | None = None
    link_status: str
    altitude_m: float | None = None
    smn_alt_diff_m: float | None = None
    smn_snow_station: str | None = None
    smn_snow_dist_km: float | None = None


class StopsPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[StopOut]


class WeatherStationOut(BaseModel):
    station: str
    name: str
    lat: float
    lon: float
    altitude_m: int | None = None
    kanton: str | None = None
    has_temp: bool = False
    has_precip: bool = False
    has_snow: bool = False


# --- US-04 --------------------------------------------------------------------


class DataQualityQuery(BaseModel):
    """Query string of GET /data-quality: local days, both optional (default = loaded data)."""

    model_config = ConfigDict(populate_by_name=True)

    date_from: date | None = Field(default=None, alias="from")
    date_to: date | None = Field(default=None, alias="to")


class QualitySourceOut(BaseModel):
    id: str
    label: str


class CompletenessCellOut(BaseModel):
    source: str
    day: date
    expected: int
    received: int
    ratio: float
    note: str | None = None


class GapOut(BaseModel):
    source: str
    start: date
    end: date
    kind: str
    description: str
    count: int


class UnlinkedStationOut(BaseModel):
    station_key: str
    name: str | None = None
    kanton: str | None = None
    reason: str
    n_events: int
    sources: str


class DataQualityOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_from: date = Field(serialization_alias="from")
    date_to: date = Field(serialization_alias="to")
    sources: list[QualitySourceOut]
    completeness: list[CompletenessCellOut]
    gaps: list[GapOut]
    kpis: dict[str, float | None]
    link_rate: float | None
    unlinked_stops: list[UnlinkedStationOut]
