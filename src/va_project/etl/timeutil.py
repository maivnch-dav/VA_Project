"""UTC ↔ Europe/Zurich helpers. Data is stored in UTC; days and months are local (CLAUDE.md)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from va_project.config import LOCAL_TZ

LOCAL = ZoneInfo(LOCAL_TZ)


def _local(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("timestamp has no timezone; store and pass UTC-aware values")
    return ts.astimezone(LOCAL)


def local_date(ts: datetime) -> date:
    return _local(ts).date()


def local_month(ts: datetime) -> str:
    return f"{_local(ts):%Y-%m}"


def slots_per_local_day(day: date, minutes: int = 10) -> int:
    """Number of `minutes` intervals in a local day: 138/150 on DST switch days (10 min)."""
    # same-tzinfo subtraction is wall-clock arithmetic in Python → compare in UTC
    start = datetime.combine(day, time(), LOCAL).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(), LOCAL).astimezone(UTC)
    return int((end - start).total_seconds() // (minutes * 60))
