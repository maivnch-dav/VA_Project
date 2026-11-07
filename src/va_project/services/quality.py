"""Data quality (US-04): completeness per source × local day, gaps, KPIs and unlinked stations.

A cell is received / expected for one source on one local day (Europe/Zurich). Days on which a
source was not collected at all (month not loaded, no live run, not published yet, no access)
have no cell — the view shows them grey — and are listed as gaps of their own kind, never as
incomplete. History (Ist-Daten) and live (GTFS-RT) are separate rows (BR6).
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from va_project.etl.timeutil import LOCAL, slots_per_local_day
from va_project.services.stops import DataNotReadyError
from va_project.storage.duck import connect
from va_project.storage.ledger import Ledger
from va_project.storage.reports import load_live_runs

# source id → row label (German UI)
SOURCES: dict[str, str] = {
    "istdaten": "Ist-Daten (Historie)",
    "gtfs_rt_trip_updates": "GTFS-RT Trip Updates (Live)",
    "gtfs_rt_alerts": "GTFS-RT Alerts (Live)",
    "meteo": "MeteoSchweiz SMN",
    "hesta_region": "BFS HESTA Region (_103)",
    "hesta_gemeinde": "BFS HESTA Gemeinde (_101)",
}
LIVE_FEEDS = {"trip_updates": "gtfs_rt_trip_updates", "alerts": "gtfs_rt_alerts"}
HESTA_LEVELS = {"region": "hesta_region", "gemeinde": "hesta_gemeinde"}

KIND_INCOMPLETE = "unvollständig"
KIND_NOT_LOADED = "nicht geladen"
KIND_UNPUBLISHED = "noch nicht veröffentlicht"
KIND_SUPPRESSED = "unterdrückt (Datenschutz)"
KIND_MISSING_SNAPSHOTS = "Snapshots fehlen"
KIND_NO_ACCESS = "kein Zugriff"
KIND_OUTLIER = "Ausreißer"

GAP_THRESHOLD = 0.95  # a day below this share of expected values is listed as a gap
OUTLIER_THRESHOLD = 0.001  # share of actual times outside [−30 min, +6 h]
MAX_RANGE_DAYS = 731  # ~24 months

_NOTHING_LOADED = (
    "No data loaded yet — run `python -m va_project.collectors.history` "
    "(and `python -m va_project.etl.build`)."
)
_BACKOFF_SUFFIX = re.compile(r"\s*\(next poll in [^)]*\)$")


class RangeError(ValueError):
    """Invalid date range (from after to, or longer than MAX_RANGE_DAYS)."""


@dataclass(frozen=True)
class Cell:
    source: str
    day: date
    expected: int
    received: int
    note: str | None = None

    @property
    def ratio(self) -> float:
        return self.received / self.expected if self.expected else 0.0


@dataclass(frozen=True)
class Gap:
    source: str
    start: date
    end: date
    kind: str
    description: str
    count: int


@dataclass(frozen=True)
class DataQuality:
    date_from: date
    date_to: date
    sources: dict[str, str]
    completeness: list[Cell]
    gaps: list[Gap]
    kpis: dict[str, float | None]
    unlinked: list[dict[str, Any]]


Part = tuple[list[Cell], list[Gap]]


# --- helpers -------------------------------------------------------------------------------


def merge_day_ranges(days: Iterable[date]) -> list[tuple[date, date]]:
    """Consecutive days → (first, last) ranges, sorted; duplicates are ignored."""
    ranges: list[tuple[date, date]] = []
    for day in sorted(set(days)):
        if ranges and day - ranges[-1][1] == timedelta(days=1):
            ranges[-1] = (ranges[-1][0], day)
        else:
            ranges.append((day, day))
    return ranges


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def _month(d: date) -> str:
    return f"{d:%Y-%m}"


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def _day_gaps(source: str, days: Iterable[date], kind: str, description: str) -> list[Gap]:
    return [
        Gap(source, a, b, kind, description, (b - a).days + 1) for a, b in merge_day_ranges(days)
    ]


def _local_day_shares(start: datetime, end: datetime) -> list[tuple[date, float]]:
    """How much of [start, end] falls on each local day (shares sum to 1)."""
    start, end = start.astimezone(LOCAL), end.astimezone(LOCAL)
    # timestamps, not same-tzinfo subtraction (that is wall-clock arithmetic → wrong on DST days)
    total = end.timestamp() - start.timestamp()
    if total <= 0:
        return [(start.date(), 1.0)]
    shares = []
    day = start.date()
    while day <= end.date():
        lo = max(start, datetime.combine(day, time(), LOCAL))
        hi = min(end, datetime.combine(day + timedelta(days=1), time(), LOCAL))
        seconds = hi.timestamp() - lo.timestamp()
        if seconds > 0:
            shares.append((day, seconds / total))
        day += timedelta(days=1)
    return shares


# --- date range ----------------------------------------------------------------------------


def _data_bounds(
    con: duckdb.DuckDBPyConnection, created: list[str], runs: list[dict[str, Any]]
) -> tuple[date, date] | None:
    lows: list[date] = []
    highs: list[date] = []

    def add(row: tuple[Any, ...] | None) -> None:
        if row and row[0] is not None:
            lows.append(row[0])
            highs.append(row[1])

    if "agg_delay_stop_day" in created:
        add(
            con.execute(
                "SELECT min(service_date), max(service_date) FROM agg_delay_stop_day "
                "WHERE source = 'history'"
            ).fetchone()
        )
    if "agg_weather_day" in created:
        add(con.execute("SELECT min(local_date), max(local_date) FROM agg_weather_day").fetchone())
    if "fact_hesta_monthly" in created:
        row = con.execute(
            "SELECT min(year * 100 + month), max(year * 100 + month) FROM fact_hesta_monthly "
            "WHERE NOT coalesce(suppressed, false)"
        ).fetchone()
        if row and row[0] is not None:
            lo, hi = int(row[0]), int(row[1])
            lows.append(date(lo // 100, lo % 100, 1))
            highs.append(_month_end(hi // 100, hi % 100))
    for run in runs:
        lows.append(datetime.fromisoformat(run["started_at"]).astimezone(LOCAL).date())
        highs.append(
            datetime.fromisoformat(run.get("ended_at") or run["started_at"])
            .astimezone(LOCAL)
            .date()
        )
    return (min(lows), max(highs)) if lows else None


def _resolve_range(
    bounds: tuple[date, date], date_from: date | None, date_to: date | None
) -> tuple[date, date]:
    to = date_to or bounds[1]
    frm = date_from or max(bounds[0], to - timedelta(days=MAX_RANGE_DAYS - 1))
    if frm > to:
        raise RangeError(f"from ({frm}) must not be after to ({to})")
    if (to - frm).days + 1 > MAX_RANGE_DAYS:
        raise RangeError(f"range is limited to {MAX_RANGE_DAYS} days")
    return frm, to


# --- sources -------------------------------------------------------------------------------


def _history(
    con: duckdb.DuckDBPyConnection,
    created: list[str],
    ledger: Ledger,
    frm: date,
    to: date,
    kpis: dict[str, float | None],
) -> Part:
    kpis["actual_share"] = kpis["outlier_share"] = None
    if "agg_delay_stop_day" not in created:
        return [], []
    # last loaded day per month over all data (not only the range): partial-month tails
    last_day = dict(
        con.execute(
            "SELECT month, max(service_date) FROM agg_delay_stop_day WHERE source = 'history' "
            "GROUP BY month"
        ).fetchall()
    )
    if not last_day:
        return [], []
    rows = con.execute(
        """
        SELECT service_date, sum(n - n_canceled)::BIGINT, sum(n_actual)::BIGINT,
               sum(n_outlier)::BIGINT
        FROM agg_delay_stop_day
        WHERE source = 'history' AND month BETWEEN $m0 AND $m1
          AND service_date BETWEEN $d0 AND $d1
        GROUP BY service_date
        """,
        {"m0": _month(frm), "m1": _month(to), "d0": frm, "d1": to},
    ).fetchall()
    by_day = {r[0]: (int(r[1]), int(r[2]), int(r[3])) for r in rows}
    first_month, last_month = min(last_day), max(last_day)

    cells: list[Cell] = []
    not_loaded: list[date] = []
    unpublished: list[date] = []
    for day in _days(frm, to):
        month = _month(day)
        if month not in last_day:
            if first_month < month < last_month:
                not_loaded.append(day)
            continue
        if day in by_day:
            expected, actual, _ = by_day[day]
            cells.append(Cell("istdaten", day, expected, actual))
        elif (
            (entry := ledger.get("istdaten", month))
            and entry.get("status") == "partial"
            and day > last_day[month]
        ):
            unpublished.append(day)
        else:
            cells.append(Cell("istdaten", day, 0, 0, "keine Daten"))

    gaps = _day_gaps(
        "istdaten", not_loaded, KIND_NOT_LOADED, "Monat nicht geladen (collectors.history)"
    )
    gaps += _day_gaps(
        "istdaten", unpublished, KIND_UNPUBLISHED, "Tage des laufenden Monats noch nicht im Archiv"
    )
    outlier_days = [d for d, (_, a, o) in by_day.items() if a and o / a > OUTLIER_THRESHOLD]
    for a, b in merge_day_ranges(outlier_days):
        span = [by_day[d] for d in _days(a, b)]
        n_out, n_act = sum(s[2] for s in span), sum(s[1] for s in span)
        gaps.append(
            Gap(
                "istdaten",
                a,
                b,
                KIND_OUTLIER,
                f"{n_out / n_act:.2%} der Ist-Zeiten außerhalb [−30 min, +6 h]",
                n_out,
            )
        )

    total_exp = sum(v[0] for v in by_day.values())
    total_act = sum(v[1] for v in by_day.values())
    kpis["actual_share"] = _ratio(total_act, total_exp)
    kpis["outlier_share"] = _ratio(sum(v[2] for v in by_day.values()), total_act)
    return cells, gaps


def _live(runs: list[dict[str, Any]], frm: date, to: date, kpis: dict[str, float | None]) -> Part:
    expected: dict[tuple[str, date], float] = defaultdict(float)
    missing: dict[tuple[str, date], int] = defaultdict(int)
    reasons: dict[tuple[str, date, str], int] = defaultdict(int)
    gaps: list[Gap] = []
    kpis["live_missing_rate"] = None
    for run in runs:
        start = datetime.fromisoformat(run["started_at"])
        end = datetime.fromisoformat(run.get("ended_at") or run["started_at"])
        for feed, report in (run.get("feeds") or {}).items():
            source = LIVE_FEEDS.get(feed)
            if source is None or not isinstance(report, dict):
                continue
            if report.get("disabled"):
                a = max(start.astimezone(LOCAL).date(), frm)
                b = min(end.astimezone(LOCAL).date(), to)
                if a <= b:
                    gaps.append(
                        Gap(
                            source,
                            a,
                            b,
                            KIND_NO_ACCESS,
                            f"Feed deaktiviert: {report['disabled']}",
                            0,
                        )
                    )
                continue
            total = int(report.get("expected") or 0)
            for day, share in _local_day_shares(start, end):
                expected[(source, day)] += total * share
            for m in report.get("missing_log") or []:
                day = datetime.fromisoformat(m["at"]).astimezone(LOCAL).date()
                count = int(m.get("count", 1))
                missing[(source, day)] += count
                reasons[(source, day, _BACKOFF_SUFFIX.sub("", str(m.get("reason", ""))))] += count
            if source == "gtfs_rt_trip_updates" and total and start.astimezone(LOCAL).date() <= to:
                kpis["live_missing_rate"] = int(report.get("missing") or 0) / total  # latest run

    cells = []
    for (source, day), exp in sorted(expected.items()):
        n = round(exp)
        if frm <= day <= to and n > 0:
            cells.append(Cell(source, day, n, max(0, n - missing[(source, day)])))
    gaps += [
        Gap(source, day, day, KIND_MISSING_SNAPSHOTS, reason or "ohne Angabe", count)
        for (source, day, reason), count in sorted(reasons.items())
        if frm <= day <= to
    ]
    return cells, gaps


def _weather(con: duckdb.DuckDBPyConnection, created: list[str], frm: date, to: date) -> list[Cell]:
    if not {"agg_weather_day", "dim_smn_station"} <= set(created):
        return []
    row = con.execute("SELECT min(local_date), max(local_date) FROM agg_weather_day").fetchone()
    if not row or row[0] is None:
        return []
    a, b = max(frm, row[0]), min(to, row[1])
    if a > b:
        return []
    days = _days(a, b)
    q_days = pd.DataFrame(
        {"day": pd.to_datetime(days), "slots": [slots_per_local_day(d) for d in days]}
    )
    con.register("q_days", q_days)
    rows = con.execute(
        """
        WITH st AS (
            SELECT station, coalesce(has_temp, false)::INT AS t,
                   coalesce(has_precip, false)::INT AS p
            FROM dim_smn_station WHERE has_temp OR has_precip
        )
        SELECT CAST(d.day AS DATE) AS day,
               sum((st.t + st.p) * d.slots)::BIGINT AS expected,
               sum(d.slots * (st.t * CASE WHEN isnan(w.cov_temp) THEN 0
                                         ELSE coalesce(w.cov_temp, 0) END
                              + st.p * CASE WHEN isnan(w.cov_precip) THEN 0
                                            ELSE coalesce(w.cov_precip, 0) END)) AS received
        FROM q_days d CROSS JOIN st
        LEFT JOIN agg_weather_day w ON w.station = st.station AND w.local_date = CAST(d.day AS DATE)
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    con.unregister("q_days")
    return [Cell("meteo", r[0], int(r[1]), round(r[2])) for r in rows if r[1]]


def _hesta(
    con: duckdb.DuckDBPyConnection,
    created: list[str],
    frm: date,
    to: date,
    kpis: dict[str, float | None],
) -> Part:
    for level_source in HESTA_LEVELS.values():
        kpis[f"{level_source}_suppressed"] = None
    if "fact_hesta_monthly" not in created:
        return [], []
    rows = con.execute(
        """
        SELECT level, year::INT, month::INT, count(*)::BIGINT,
               count(*) FILTER (WHERE coalesce(suppressed, false))::BIGINT,
               bool_or(coalesce(is_estimate, false))
        FROM fact_hesta_monthly GROUP BY ALL ORDER BY 1, 2, 3
        """
    ).fetchall()
    cells: list[Cell] = []
    gaps: list[Gap] = []
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    unpublished: dict[str, list[tuple[date, date]]] = defaultdict(list)
    for level, year, month, n, n_supp, estimate in rows:
        source = HESTA_LEVELS.get(level)
        a, b = max(date(year, month, 1), frm), min(_month_end(year, month), to)
        if source is None or a > b:
            continue
        if n_supp == n:  # nothing published for this month yet (BFS lags ~2 months)
            unpublished[source].append((a, b))
            continue
        totals[source][0] += n
        totals[source][1] += n_supp
        note = "Monatswert" + (" · geschätzt (HESTA-Flash)" if estimate else "")
        cells += [Cell(source, d, n, n - n_supp, note) for d in _days(a, b)]
    for source, months in unpublished.items():
        for a, b in merge_day_ranges(d for m in months for d in _days(*m)):
            n_months = len({_month(d) for d in _days(a, b)})
            gaps.append(
                Gap(
                    source,
                    a,
                    b,
                    KIND_UNPUBLISHED,
                    "BFS publiziert mit ≈ 2 Monaten Verzug",
                    n_months,
                )
            )
    for source, (n, n_supp) in totals.items():
        kpis[f"{source}_suppressed"] = _ratio(n_supp, n)
    return cells, gaps


def _cell_gaps(cells: list[Cell]) -> list[Gap]:
    """Days below GAP_THRESHOLD, merged per source. Live feeds list their missing snapshots
    with the logged reason instead; HESTA counts suppressed cells once per month."""
    low: dict[str, dict[date, Cell]] = defaultdict(dict)
    for c in cells:
        if c.source not in LIVE_FEEDS.values() and c.ratio < GAP_THRESHOLD:
            low[c.source][c.day] = c
    gaps = []
    for source, by_day in low.items():
        hesta = source in HESTA_LEVELS.values()
        for a, b in merge_day_ranges(by_day):
            span = [by_day[d] for d in _days(a, b)]
            if hesta:  # one monthly value repeated per day → count each month once
                span = list({_month(c.day): c for c in span}.values())
            exp = sum(c.expected for c in span)
            rec = sum(c.received for c in span)
            empty = sum(1 for c in span if not c.expected)
            if hesta:
                desc = f"{1 - rec / exp:.1%} der Werte aus Datenschutzgründen «...»"
            elif exp:
                desc = f"Ø {rec / exp:.1%} der erwarteten Werte vorhanden"
                desc += f"; {empty} Tag(e) ohne Daten" if empty else ""
            else:
                desc = "keine Daten"
            gaps.append(
                Gap(source, a, b, KIND_SUPPRESSED if hesta else KIND_INCOMPLETE, desc, exp - rec)
            )
    return gaps


def _unlinked(
    con: duckdb.DuckDBPyConnection, created: list[str], frm: date, to: date
) -> tuple[float | None, list[dict[str, Any]]]:
    """Stations with delay data in the range that have no BFS municipality (US-03)."""
    if not {"agg_delay_stop_day", "dim_station"} <= set(created):
        return None, []
    cursor = con.execute(
        """
        SELECT a.station_key, coalesce(any_value(s.name), any_value(a.station_name)) AS name,
               any_value(s.kanton) AS kanton,
               coalesce(any_value(s.link_status), 'not_in_service_points') AS reason,
               sum(a.n)::BIGINT AS n_events,
               array_to_string(list_sort(list(DISTINCT a.source)), ',') AS sources
        FROM agg_delay_stop_day a LEFT JOIN dim_station s USING (station_key)
        WHERE a.month BETWEEN $m0 AND $m1 AND a.service_date BETWEEN $d0 AND $d1
        GROUP BY a.station_key
        ORDER BY n_events DESC, a.station_key
        """,
        {"m0": _month(frm), "m1": _month(to), "d0": frm, "d1": to},
    )
    cols = [d[0] for d in cursor.description]
    rows = [dict(zip(cols, r, strict=True)) for r in cursor.fetchall()]
    linked = sum(1 for r in rows if r["reason"] == "linked")
    return _ratio(linked, len(rows)), [r for r in rows if r["reason"] != "linked"]


# --- entry point ---------------------------------------------------------------------------


def get_data_quality(
    curated_dir: Path, date_from: date | None = None, date_to: date | None = None
) -> DataQuality:
    """Quality of everything loaded between date_from and date_to (local days, inclusive).

    Missing bounds default to the loaded data (at most MAX_RANGE_DAYS, ending at the newest day).
    Raises DataNotReadyError when nothing is loaded and RangeError for an invalid range."""
    runs = load_live_runs(curated_dir)
    ledger = Ledger(curated_dir / "_loaded.json")
    con, created = connect(curated_dir)
    try:
        bounds = _data_bounds(con, created, runs)
        if bounds is None:
            raise DataNotReadyError(_NOTHING_LOADED)
        frm, to = _resolve_range(bounds, date_from, date_to)
        kpis: dict[str, float | None] = {}
        cells, gaps = _history(con, created, ledger, frm, to, kpis)
        live_cells, live_gaps = _live(runs, frm, to, kpis)
        weather = _weather(con, created, frm, to)
        hesta_cells, hesta_gaps = _hesta(con, created, frm, to, kpis)
        cells += live_cells + weather + hesta_cells
        gaps += live_gaps + hesta_gaps + _cell_gaps(cells)
        kpis["weather_completeness"] = _ratio(
            sum(c.received for c in weather), sum(c.expected for c in weather)
        )
        kpis["link_rate"], unlinked = _unlinked(con, created, frm, to)
    finally:
        con.close()
    order = {s: i for i, s in enumerate(SOURCES)}
    gaps.sort(key=lambda g: (order[g.source], g.start, g.kind))
    return DataQuality(frm, to, dict(SOURCES), cells, gaps, kpis, unlinked)
