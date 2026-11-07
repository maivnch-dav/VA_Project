"""Application settings, loaded from environment variables and `.env`."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_TZ = "Europe/Zurich"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8050, ge=1, le=65535)
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Storage
    data_dir: Path = Path("data")

    # Sources — endpoints to be confirmed by the feasibility script (US-01)
    gtfs_rt_api_key: SecretStr | None = None
    gtfs_rt_url: str = "https://api.opentransportdata.swiss/la/gtfs-rt"  # trip updates
    gtfs_sa_url: str = "https://api.opentransportdata.swiss/la/gtfs-sa"  # service alerts
    gtfs_rt_poll_seconds: int = Field(default=60, ge=60)  # ≤ 1 request/min per feed (AC2)
    meteo_stac_url: str = (
        "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-smn"
    )
    meteo_station: str = "CHU"
    bfs_pxweb_url: str = "https://www.pxweb.bfs.admin.ch/api/v1/de"
    service_points_url: str = (
        "https://data.opentransportdata.swiss/en/dataset/service-points-actual-date/permalink"
    )
    # Ist-Daten history (US-02a): monthly archive zips + daily CSVs for months not archived yet
    istdaten_archive_listing_url: str = "https://archive.opentransportdata.swiss/istdaten.php"
    istdaten_archive_base_url: str = "https://archive.opentransportdata.swiss/"
    istdaten_daily_url: str = "https://data.opentransportdata.swiss/en/dataset/ist-daten-v2"
    history_min_free_gb: float = Field(default=3.0, ge=0)  # zip (~1.2 GB) + staging
    # Linking (US-03)
    bfs_communes_url: str = "https://www.agvchapp.bfs.admin.ch/api/communes/levels"
    smn_meta_url: str = (
        "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/ogd-smn_meta_stations.csv"
    )
    # Canton outlines for the map on `/` (swissBOUNDARIES3D; /<BFS canton nr> per feature)
    geoadmin_canton_url: str = (
        "https://api3.geo.admin.ch/rest/services/api/MapServer/"
        "ch.swisstopo.swissboundaries3d-kanton-flaeche.fill"
    )
    # Live collector (US-02b)
    live_raw_keep_days: int = Field(default=3, ge=0)  # raw snapshots kept after compaction
    live_compact_minutes: int = Field(default=60, ge=5)
    meteo_poll_minutes: int = Field(default=10, ge=10)  # SwissMetNet publishes every 10 min

    # Monitoring
    stale_after_minutes: int = Field(default=10, ge=1)

    @field_validator("gtfs_rt_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def curated_dir(self) -> Path:
        return self.data_dir / "curated"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "analytics.duckdb"

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "app.db"

    def ensure_dirs(self) -> None:
        for d in (self.raw_dir, self.curated_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
