"""/quality — Data Quality (US-04): completeness heatmap, KPIs, gap list and unlinked stations.

Has its own date range until the Global Filter Bar (US-05/06) exists.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html
from dash.dash_table.DataTable import DataTable

from va_project.app.components.common import empty_state, kpi_tile, source_footnote
from va_project.app.components.completeness import FLOOR, Q_HIGH, Q_LOW, Q_NONE, completeness_figure
from va_project.config import Settings
from va_project.services.quality import DataQuality, RangeError, get_data_quality
from va_project.services.stops import DataNotReadyError

log = logging.getLogger(__name__)

PATH = "/quality"
LINK_TARGET = 0.8  # BRD G1a / US-03 AC1
LIVE_MISSING_TARGET = 0.05  # US-02b AC4

REASONS = {
    "foreign": "Ausland",
    "not_in_service_points": "nicht in Dienststellen",
    "no_bfs": "ohne BFS-Gemeinde",
    "outdated_bfs": "veraltete BFS-Nummer",
    "lake": "See (BFS ≥ 9000)",
    "unknown": "unbekannt",
}
FOOTNOTE = (
    "Ist-Daten & GTFS-RT (opentransportdata.swiss), MeteoSchweiz SMN, BFS HESTA · "
    "Tage in Europe/Zurich · Historie und Live getrennt"
)

GAP_COLUMNS = [
    {"id": "source", "name": "Quelle"},
    {"id": "start", "name": "Von"},
    {"id": "end", "name": "Bis"},
    {"id": "kind", "name": "Art"},
    {"id": "description", "name": "Beschreibung"},
    {"id": "count", "name": "Anzahl", "type": "numeric"},
]
UNLINKED_COLUMNS = [
    {"id": "station_key", "name": "BPUIC"},
    {"id": "name", "name": "Halt"},
    {"id": "kanton", "name": "Kanton"},
    {"id": "reason", "name": "Grund"},
    {"id": "n_events", "name": "Halte-Ereignisse", "type": "numeric"},
    {"id": "sources", "name": "Quelle"},
]


def _table(table_id: str, columns: list[Any]) -> DataTable:  # DataTable.Columns dicts
    return DataTable(
        id=table_id,
        columns=columns,
        data=[],
        export_format="csv",
        export_headers="display",
        sort_action="native",
        filter_action="native",
        page_size=15,
        style_table={"overflowX": "auto"},
        style_cell={
            "textAlign": "left",
            "fontFamily": "var(--font-sans)",
            "fontSize": "var(--fs-sm)",
            "whiteSpace": "normal",
            "height": "auto",
        },
        style_header={"fontWeight": "600", "backgroundColor": "var(--surface)"},
        css=[{"selector": ".export", "rule": "margin-bottom: var(--sp-2)"}],
    )


def _swatch(color: str) -> html.Span:
    return html.Span(className="q-swatch", style={"background": color})


def _legend() -> html.Div:
    swatch = _swatch
    return html.Div(
        [
            swatch(Q_NONE),
            "nicht erhoben (kein Mangel)",
            swatch(Q_LOW),
            f"≤ {FLOOR:.0%}",
            swatch(Q_HIGH),
            "100 %",
        ],
        className="q-legend",
    )


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.H3("Datenqualität", className="me-3 mb-0"),
                    dcc.DatePickerRange(
                        id="quality-range",
                        style={"maxWidth": "360px"},
                        display_format="DD.MM.YYYY",
                        first_day_of_week=1,
                        clearable=True,
                        start_date_placeholder_text="ganzer Zeitraum",
                        end_date_placeholder_text="bis",
                    ),
                ],
                className="d-flex align-items-center flex-wrap gap-2 mb-2",
            ),
            dcc.Loading(
                [
                    html.Div(id="quality-status", className="text-muted mb-2"),
                    dbc.Row(id="quality-kpis", className="g-3 mb-3"),
                    dbc.Card(
                        dbc.CardBody(
                            [
                                dcc.Graph(id="quality-heatmap", config={"displaylogo": False}),
                                _legend(),
                                source_footnote(FOOTNOTE),
                            ]
                        ),
                        className="mb-3",
                    ),
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Lücken und Auffälligkeiten"),
                                html.P(id="quality-gaps-sub", className="text-muted small"),
                                _table("quality-gaps", GAP_COLUMNS),
                            ]
                        ),
                        className="mb-3",
                    ),
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Nicht verknüpfte Halte"),
                                html.P(
                                    "Halte mit Verspätungsdaten, aber ohne BFS-Gemeinde",
                                    className="text-muted small",
                                ),
                                _table("quality-unlinked", UNLINKED_COLUMNS),
                                source_footnote(
                                    "Dienststellen (opentransportdata.swiss), BFS Gemeindestand"
                                ),
                            ]
                        )
                    ),
                ]
            ),
        ]
    )


def _pct(x: float | None, digits: int = 1) -> str:
    return "–" if x is None else f"{x * 100:.{digits}f} %"


def _kpis(k: dict[str, float | None]) -> list[dbc.Col]:
    link, live = k.get("link_rate"), k.get("live_missing_rate")
    tiles = [
        kpi_tile(
            "Halte → BFS-Gemeinde",
            _pct(link),
            f"Ziel ≥ {LINK_TARGET:.0%}",
            None if link is None else link >= LINK_TARGET,
        ),
        kpi_tile(
            "Ist-Daten mit Ist-Zeit", _pct(k.get("actual_share")), "REAL/GESCHAETZT, ohne Ausfälle"
        ),
        kpi_tile(
            "Ausreißer (Ist-Daten)", _pct(k.get("outlier_share"), 3), "außerhalb [−30 min, +6 h]"
        ),
        kpi_tile(
            "MeteoSchweiz vollständig",
            _pct(k.get("weather_completeness")),
            "Temperatur + Niederschlag, alle SMN-Stationen",
        ),
        kpi_tile(
            "HESTA unterdrückt",
            f"{_pct(k.get('hesta_region_suppressed'))} / "
            f"{_pct(k.get('hesta_gemeinde_suppressed'))}",
            "Region / Gemeinde · Datenschutz",
        ),
        kpi_tile(
            "Live-Snapshots fehlend",
            _pct(live),
            f"letzter Lauf · Ziel < {LIVE_MISSING_TARGET:.0%}",
            None if live is None else live < LIVE_MISSING_TARGET,
        ),
    ]
    return [dbc.Col(t, xs=12, md=6, xl=2) for t in tiles]


def _parse(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _rows(dq: DataQuality) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gaps = [
        {
            "source": dq.sources[g.source],
            "start": g.start.isoformat(),
            "end": g.end.isoformat(),
            "kind": g.kind,
            "description": g.description,
            "count": g.count,
        }
        for g in dq.gaps
    ]
    unlinked = [{**u, "reason": REASONS.get(u["reason"], u["reason"])} for u in dq.unlinked]
    return gaps, unlinked


Outputs = tuple[Any, list[dbc.Col], go.Figure, list[dict[str, Any]], str, list[dict[str, Any]]]


def update(settings: Settings, start: str | None, end: str | None) -> Outputs:
    """All outputs of the page for one date range (pure, so tests call it directly)."""
    empty_fig = go.Figure(
        layout={"height": 80, "xaxis": {"visible": False}, "yaxis": {"visible": False}}
    )
    try:
        dq = get_data_quality(settings.curated_dir, _parse(start), _parse(end))
    except DataNotReadyError:
        status: Any = empty_state(
            "Noch keine Daten geladen.", "python -m va_project.collectors.history --from 2025-01"
        )
        return status, [], empty_fig, [], "", []
    except (RangeError, ValueError) as e:
        return dbc.Alert(f"Ungültiger Zeitraum: {e}", color="warning"), [], empty_fig, [], "", []
    except Exception:
        log.exception("data quality view failed")
        alert = dbc.Alert(
            "Fehler beim Laden der Datenqualität — Zeitraum erneut wählen.", color="danger"
        )
        return alert, [], empty_fig, [], "", []
    gaps, unlinked = _rows(dq)
    status = f"Zeitraum {dq.date_from:%d.%m.%Y} – {dq.date_to:%d.%m.%Y}"
    sub = f"{len(gaps)} Einträge · Tage unter 95 % zusammengefasst · Export als CSV"
    return status, _kpis(dq.kpis), completeness_figure(dq), gaps, sub, unlinked


def register_callbacks(app: Dash, settings: Settings) -> None:
    @app.callback(
        Output("quality-status", "children"),
        Output("quality-kpis", "children"),
        Output("quality-heatmap", "figure"),
        Output("quality-gaps", "data"),
        Output("quality-gaps-sub", "children"),
        Output("quality-unlinked", "data"),
        Input("quality-range", "start_date"),
        Input("quality-range", "end_date"),
    )
    def _update(start: str | None, end: str | None) -> Outputs:
        return update(settings, start, end)
