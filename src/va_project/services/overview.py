"""KPI tiles of the start page `/` (US-27 AC2), mode «Nur echte», region Schweiz.

Five tiles (Ø Verspätung, Pünktlichkeit, Ausfallquote, Logiernächte, Neuschneetage) over the
whole loaded period, each with Δ against the *same months* one year earlier (only months that
have a value in both years; none → no comparison) and a 12-month sparkline with gaps. A sixth
tile (rendered by the page) shows which months have Ist-Daten.

Delay values are event-weighted over all months (not a mean of monthly means), history only
(BR6), cancellations apart (BR2). Nights = HESTA «Schweiz» (all origins), published months only.
Neuschneetage = Σ over months of the Ø new-snow days per snow station (ΔHS ≥ 5 cm, HR2).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from va_project.services.canton_map import NEW_SNOW_CM, _month_range, data_stamp
from va_project.services.stops import DataNotReadyError
from va_project.storage import overview as q
from va_project.storage.duck import connect

SPARK_MONTHS = 12


@dataclass(frozen=True)
class Kpi:
    key: str
    label: str
    value: float | None
    value_text: str
    delta_text: str | None  # «▲ 0.12 min»; None = no common months with the previous year
    delta_months: tuple[str, ...]  # "01", "02", … compared
    spark: tuple[float | None, ...]  # last SPARK_MONTHS months up to the end of the period


@dataclass(frozen=True)
class Overview:
    month_from: str
    month_to: str
    kpis: tuple[Kpi, ...]
    coverage: tuple[tuple[str, bool], ...]  # (month, Ist-Daten loaded)


@dataclass(frozen=True)
class _Data:
    delays: dict[str, q.DelayMonth]
    nights: dict[str, float]
    snow: dict[str, float | None]
    months: tuple[str, ...]


@lru_cache(maxsize=4)
def _load(curated_dir: Path, stamp: tuple[tuple[str, int], ...]) -> _Data:
    con, created = connect(curated_dir)
    try:
        delays = {}
        if {"agg_delay_stop_day", "dim_station"} <= set(created):
            delays = {d.month: d for d in q.ch_delays(con)}
        nights = q.ch_nights(con) if "fact_hesta_monthly" in created else {}
        snow = {}
        if {"agg_weather_day", "dim_smn_station"} <= set(created):
            snow = q.new_snow_days(con, NEW_SNOW_CM)
    finally:
        con.close()
    months = set(delays) | set(nights) | set(snow)
    if not months:
        raise DataNotReadyError("Noch keine Daten geladen — `python -m va_project.etl.build`.")
    return _Data(delays, nights, snow, _month_range(min(months), max(months)))


def _prev_year(month: str) -> str:
    return f"{int(month[:4]) - 1:04d}{month[4:]}"


def _arrow(diff: float) -> str:
    return "▲" if diff >= 0 else "▼"


def _delay_kpis(d: _Data) -> list[Kpi]:
    def agg(months: Iterable[str]) -> q.DelayMonth | None:
        rows = [d.delays[m] for m in months if m in d.delays]
        if not rows:
            return None
        return q.DelayMonth("", sum(r.n for r in rows), sum(r.n_used for r in rows),
                            sum(r.n_late for r in rows), sum(r.n_canceled for r in rows),
                            sum(r.delay_s_sum for r in rows))  # fmt: skip

    def mean_min(r: q.DelayMonth | None) -> float | None:
        return r.delay_s_sum / r.n_used / 60 if r and r.n_used else None

    def punct(r: q.DelayMonth | None) -> float | None:
        return 1 - r.n_late / r.n_used if r and r.n_used else None

    def cancel(r: q.DelayMonth | None) -> float | None:
        return r.n_canceled / r.n if r and r.n else None

    specs: list[tuple[str, str, Callable[[q.DelayMonth | None], float | None],
                      Callable[[float], str], Callable[[float, float], str]]] = [
        ("delay", "Ø Verspätung", mean_min, lambda v: f"{v:.2f} min",
         lambda a, b: f"{_arrow(a - b)} {abs(a - b):.2f} min"),
        ("punctuality", "Pünktlichkeit (< 3 min)", punct, lambda v: f"{v * 100:.1f} %",
         lambda a, b: f"{_arrow(a - b)} {abs(a - b) * 100:.1f} pp"),
        ("cancel", "Ausfallquote", cancel, lambda v: f"{v * 100:.2f} %",
         lambda a, b: f"{_arrow(a - b)} {abs(a - b) * 100:.2f} pp"),
    ]  # fmt: skip
    pairs = [m for m in d.months if m in d.delays and _prev_year(m) in d.delays]
    out = []
    for key, label, f, fmt, dfmt in specs:
        value = f(agg(d.months))
        now, before = f(agg(pairs)), f(agg(_prev_year(m) for m in pairs))
        out.append(Kpi(
            key, label, value, "–" if value is None else fmt(value),
            dfmt(now, before) if now is not None and before is not None else None,
            tuple(m[5:] for m in pairs) if now is not None else (),
            tuple(f(agg([m])) for m in d.months[-SPARK_MONTHS:]),
        ))  # fmt: skip
    return out


def _sum_kpi(
    key: str, label: str, raw: Mapping[str, float | None], months: tuple[str, ...],
    fmt: Callable[[float], str], dfmt: Callable[[float, float], str],
) -> Kpi:  # fmt: skip
    series = {m: v for m, v in raw.items() if v is not None}
    vals = [series[m] for m in months if m in series]
    value = sum(vals) if vals else None
    pairs = [m for m in months if m in series and _prev_year(m) in series]
    delta = None
    if pairs:
        delta = dfmt(sum(series[m] for m in pairs), sum(series[_prev_year(m)] for m in pairs))
    spark = tuple(series.get(m) for m in months[-SPARK_MONTHS:])
    text = "–" if value is None else fmt(value)
    return Kpi(key, label, value, text, delta, tuple(m[5:] for m in pairs), spark)


def get_overview(curated_dir: Path) -> Overview:
    d = _load(curated_dir, data_stamp(curated_dir))
    nights = _sum_kpi(
        "nights", "Logiernächte", d.nights, d.months,
        lambda v: f"{v / 1e6:.1f} Mio" if v >= 1e5 else f"{v:,.0f}".replace(",", "’"),
        lambda a, b: f"{_arrow(a - b)} {abs(a / b - 1) * 100:.1f} %",
    )  # fmt: skip
    snow = _sum_kpi(
        "snow", "Neuschneetage (Ø Station)", d.snow, d.months,
        lambda v: f"{v:.1f} Tage", lambda a, b: f"{_arrow(a - b)} {abs(a - b):.1f} Tage",
    )  # fmt: skip
    return Overview(
        month_from=d.months[0],
        month_to=d.months[-1],
        kpis=(*_delay_kpis(d), nights, snow),
        coverage=tuple((m, m in d.delays) for m in d.months),
    )
