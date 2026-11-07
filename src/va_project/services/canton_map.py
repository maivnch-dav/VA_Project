"""Canton map on `/` (US-30): one calendar month per view, monthly detail per selection.

- Canton colour = HESTA nights (all origins) of the canton's *dominant* tourism region (most
  HESTA municipality nights; 5 cantons span two regions — the other is named in the tooltip).
  Several cantons share a region and so share a colour; that is the data's resolution.
- Bubble size = stop events late ≥ 3 min + cancelled stop events, Ist-Daten only (BR6),
  cancellations counted apart from delay (BR2). Months without Ist-Daten have no bubble value.
- Bubble colour = snow class of the month over the canton's snow stations (HR2 thresholds):
  new snow on ≥ 1 day › snow cover on ≥ 1 day › no snow › no measurement.

Weekly is not offered: HESTA exists only per month, so all layers use the same month.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from va_project.services.stops import DataNotReadyError
from va_project.storage import canton_map as q
from va_project.storage.duck import connect

NEW_SNOW_CM = 5.0  # HR2 default
SNOW_COVER_CM = 1.0  # snow day (SYSTEM-DESIGN agg_weather_month.snow_days)
SNOW_ORDER = ("new", "cover", "none", "unknown")  # strongest first
SNOW_LABELS = {
    "new": "Neuschnee",
    "cover": "Schneedecke",
    "none": "kein Schnee",
    "unknown": "keine Messung",
}
_NEEDS = ("dim_gemeinde", "dim_station", "dim_smn_station")
_STAMP_GLOBS = (
    q.GEOJSON, "_loaded.json", "dim_*.parquet", "agg_weather_day/*.parquet",
    "agg_delay_stop_day/*/*/*.parquet", "fact_hesta_monthly/*/*.parquet",
)  # fmt: skip


@dataclass(frozen=True)
class CantonMonth:
    kanton: str
    name: str
    lon: float
    lat: float
    region_code: str | None
    region: str | None
    other_regions: tuple[str, ...]
    nights: float | None
    nights_estimate: bool
    n_late: int | None
    n_canceled: int | None
    n_events: int | None
    n_stations: int
    snow: str  # key of SNOW_LABELS
    new_snow_days: int
    cover_days: int
    n_snow_stations: int

    @property
    def delay_total(self) -> int | None:
        if self.n_late is None or self.n_canceled is None:
            return None
        return self.n_late + self.n_canceled


@dataclass(frozen=True)
class CantonMap:
    month: str
    months: tuple[str, ...]
    delay_months: tuple[str, ...]
    delay_days: int  # loaded Ist-Daten days in `month` (0 = not loaded)
    days_in_month: int
    cantons: tuple[CantonMonth, ...]
    geojson: dict[str, Any]


@dataclass(frozen=True)
class DetailPoint:
    month: str
    nights: float | None
    nights_estimate: bool
    n_late: int | None
    n_canceled: int | None
    new_snow_days: int
    cover_days: int
    no_snow_days: int
    unknown_days: int


@dataclass(frozen=True)
class CantonDetail:
    kantons: tuple[str, ...]
    names: tuple[str, ...]
    regions: tuple[str, ...]
    n_snow_stations: int
    points: tuple[DetailPoint, ...]


@dataclass(frozen=True)
class _Data:
    geojson: dict[str, Any]
    cantons: dict[str, tuple[str, float, float]]  # kanton → name, lon, lat
    regions: dict[str, list[q.CantonRegion]]  # heaviest first
    nights: dict[tuple[str, str], q.RegionNights]  # (region_code, month)
    delays: dict[tuple[str, str], q.CantonDelays]  # (kanton, month)
    delay_days: dict[str, int]
    snow: dict[str, dict[date, str]]  # kanton → day → class
    snow_stations: dict[str, int]
    months: tuple[str, ...]


def _month_range(first: str, last: str) -> tuple[str, ...]:
    y, m = map(int, first.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return tuple(out)


def _days(month: str) -> list[date]:
    y, m = map(int, month.split("-"))
    return [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]


def data_stamp(curated_dir: Path) -> tuple[tuple[str, int], ...]:
    files = sorted({p for g in _STAMP_GLOBS for p in curated_dir.glob(g)})
    return tuple((str(p), p.stat().st_mtime_ns) for p in files)


def _read(curated_dir: Path) -> _Data:
    geojson = q.load_geojson(curated_dir)
    if geojson is None:
        raise DataNotReadyError(
            "Kantonsgrenzen fehlen — `python -m va_project.etl.build --steps cantons`."
        )
    con, created = connect(curated_dir)
    try:
        if missing := [v for v in _NEEDS if v not in created]:
            raise DataNotReadyError(
                f"{', '.join(missing)} fehlt — `python -m va_project.etl.build` ausführen."
            )
        has_hesta = "fact_hesta_monthly" in created
        regions: dict[str, list[q.CantonRegion]] = defaultdict(list)
        for r in q.canton_regions(con, with_nights=has_hesta):
            regions[r.kanton].append(r)
        nights = {(r.region_code, r.month): r for r in q.region_nights(con)} if has_hesta else {}
        delays, ddays = {}, {}
        if "agg_delay_stop_day" in created:
            delays = {(d.kanton, d.month): d for d in q.canton_delays(con)}
            ddays = q.delay_days(con)
        snow: dict[str, dict[date, str]] = defaultdict(dict)
        if "agg_weather_day" in created:
            if not q.has_column(con, "agg_weather_day", "snow_depth_med_cm"):
                raise DataNotReadyError(
                    "Wetter-Aggregat veraltet — `python -m va_project.etl.build --steps weather`."
                )
            for s in q.canton_snow_days(con, NEW_SNOW_CM, SNOW_COVER_CM):
                snow[s.kanton][s.day] = s.cls
        stations = q.snow_stations(con)
    finally:
        con.close()
    months = {m for _, m in nights} | set(ddays)
    months |= {f"{d:%Y-%m}" for days in snow.values() for d in days}
    if not months:
        raise DataNotReadyError("Weder HESTA, Ist-Daten noch Wetterdaten geladen.")
    cantons = {
        f["id"]: (f["properties"].get("name") or f["id"], f["properties"]["lon"],
                  f["properties"]["lat"])
        for f in geojson["features"]
    }  # fmt: skip
    return _Data(geojson, cantons, dict(regions), nights, delays, ddays, dict(snow), stations,
                 _month_range(min(months), max(months)))  # fmt: skip


@lru_cache(maxsize=4)
def _load(curated_dir: Path, stamp: tuple[tuple[str, int], ...]) -> _Data:
    return _read(curated_dir)


def _data(curated_dir: Path) -> _Data:
    return _load(curated_dir, data_stamp(curated_dir))


def _combine(classes: Sequence[str]) -> str:
    """Strongest class of the day over several cantons (any new snow → new …)."""
    return min(classes, key=SNOW_ORDER.index) if classes else "unknown"


def _snow_counts(data: _Data, kantons: Sequence[str], month: str) -> dict[str, int]:
    counts = dict.fromkeys(SNOW_ORDER, 0)
    for day in _days(month):
        counts[_combine([c for k in kantons if (c := data.snow.get(k, {}).get(day))])] += 1
    return counts


def _month_class(counts: dict[str, int]) -> str:
    return next((c for c in SNOW_ORDER[:3] if counts[c] > 0), "unknown")


def get_canton_map(curated_dir: Path, month: str | None = None) -> CantonMap:
    data = _data(curated_dir)
    delay_months = tuple(sorted(data.delay_days))
    if month is None:  # latest month with Ist-Daten and published nights, else the latest
        with_nights = {m for (_, m), r in data.nights.items() if r.nights is not None}
        both = [m for m in delay_months if m in with_nights]
        month = (both or list(delay_months) or sorted(with_nights) or list(data.months))[-1]
    elif month not in data.months:
        raise ValueError(f"Monat {month} nicht verfügbar ({data.months[0]}–{data.months[-1]})")
    rows = []
    for k, (name, lon, lat) in sorted(data.cantons.items()):
        regs = data.regions.get(k, [])
        main = regs[0] if regs else None
        n = data.nights.get((main.region_code, month)) if main else None
        d = data.delays.get((k, month))
        counts = _snow_counts(data, [k], month)
        rows.append(CantonMonth(
            kanton=k, name=name, lon=lon, lat=lat,
            region_code=main.region_code if main else None,
            region=main.region if main else None,
            other_regions=tuple(r.region for r in regs[1:]),
            nights=n.nights if n else None, nights_estimate=bool(n and n.is_estimate),
            n_late=d.n_late if d else None, n_canceled=d.n_canceled if d else None,
            n_events=d.n if d else None, n_stations=d.n_stations if d else 0,
            snow=_month_class(counts), new_snow_days=counts["new"], cover_days=counts["cover"],
            n_snow_stations=data.snow_stations.get(k, 0),
        ))  # fmt: skip
    return CantonMap(
        month=month,
        months=data.months,
        delay_months=delay_months,
        delay_days=data.delay_days.get(month, 0),
        days_in_month=len(_days(month)),
        cantons=tuple(rows),
        geojson=data.geojson,
    )


def get_canton_detail(curated_dir: Path, kantons: Sequence[str]) -> CantonDetail:
    data = _data(curated_dir)
    sel = tuple(sorted(set(kantons)))
    if not sel:
        raise ValueError("mindestens einen Kanton wählen")
    if unknown := [k for k in sel if k not in data.cantons]:
        raise ValueError(f"unbekannter Kanton: {', '.join(unknown)}")
    regions = {data.regions[k][0].region_code: data.regions[k][0].region
               for k in sel if data.regions.get(k)}  # fmt: skip
    points = []
    for month in data.months:
        vals = [data.nights.get((code, month)) for code in regions]
        nights = None
        if regions and all(v is not None and v.nights is not None for v in vals):
            nights = sum(v.nights for v in vals if v and v.nights is not None)
        late = canc = None
        if month in data.delay_days:
            ds = [d for k in sel if (d := data.delays.get((k, month)))]
            late, canc = sum(d.n_late for d in ds), sum(d.n_canceled for d in ds)
        counts = _snow_counts(data, sel, month)
        points.append(DetailPoint(
            month=month, nights=nights, nights_estimate=any(v and v.is_estimate for v in vals),
            n_late=late, n_canceled=canc, new_snow_days=counts["new"],
            cover_days=counts["cover"], no_snow_days=counts["none"],
            unknown_days=counts["unknown"],
        ))  # fmt: skip
    return CantonDetail(
        kantons=sel,
        names=tuple(data.cantons[k][0] for k in sel),
        regions=tuple(sorted(regions.values())),
        n_snow_stations=sum(data.snow_stations.get(k, 0) for k in sel),
        points=tuple(points),
    )
