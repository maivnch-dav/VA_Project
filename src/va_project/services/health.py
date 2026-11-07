"""Data freshness per source, based on the newest file the collectors wrote."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from va_project.config import Settings

HealthStatus = Literal["ok", "degraded", "down"]


@dataclass(frozen=True)
class SourceSpec:
    subdir: str
    max_age: timedelta | None  # None = use Settings.stale_after_minutes (real-time feeds)


SOURCES: dict[str, SourceSpec] = {
    "gtfs_rt_trip_updates": SourceSpec("raw/gtfs_rt/trip_updates", None),
    "gtfs_rt_alerts": SourceSpec("raw/gtfs_rt/alerts", None),
    "meteo_smn": SourceSpec("raw/meteo/smn", timedelta(minutes=30)),  # published every 10 min
    "hesta": SourceSpec("raw/hesta", timedelta(days=45)),  # monthly
    "gtfs_static": SourceSpec("raw/gtfs_static", timedelta(days=400)),  # yearly timetable
    # history loader runs on demand; the archive adds one month at a time
    "istdaten": SourceSpec("curated/agg_delay_stop_day/source=history", timedelta(days=45)),
}


@dataclass(frozen=True)
class SourceHealth:
    name: str
    last_ingest_at: datetime | None
    stale: bool


@dataclass(frozen=True)
class Health:
    status: HealthStatus
    sources: list[SourceHealth]


def _newest_mtime(directory: Path) -> datetime | None:
    if not directory.is_dir():
        return None
    mtimes = [p.stat().st_mtime for p in directory.rglob("*") if p.is_file()]
    return datetime.fromtimestamp(max(mtimes), tz=UTC) if mtimes else None


def get_health(settings: Settings) -> Health:
    now = datetime.now(UTC)
    sources = []
    for name, spec in SOURCES.items():
        last = _newest_mtime(settings.data_dir / spec.subdir)
        max_age = spec.max_age or timedelta(minutes=settings.stale_after_minutes)
        stale = last is None or now - last > max_age
        sources.append(SourceHealth(name=name, last_ingest_at=last, stale=stale))

    status: HealthStatus
    if all(s.last_ingest_at is None for s in sources):
        status = "down"
    elif any(s.stale for s in sources):
        status = "degraded"
    else:
        status = "ok"
    return Health(status=status, sources=sources)
