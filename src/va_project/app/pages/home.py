"""/ — Datenüberblick (start page). First panel: canton map (US-30).

Canton fill = tourism nights of the dominant region, bubble area = late + cancelled stop
events, bubble colour = snow class; one calendar month (HESTA is monthly). Map top left,
detail panel top right: click a canton or lasso bubbles → monthly series of the selection.
"""

from __future__ import annotations

import logging
from typing import Any

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Dash, Input, Output, ctx, dcc, html, no_update

from va_project.app.components.canton_map import (
    FOOT_MAP,
    detail_figures,
    kantons_from_event,
    map_figure,
    month_label,
)
from va_project.app.components.common import attrs, empty_state, source_footnote
from va_project.app.components.kpi import coverage_card, kpi_card
from va_project.config import Settings
from va_project.services.canton_map import get_canton_detail, get_canton_map
from va_project.services.overview import get_overview
from va_project.services.stops import DataNotReadyError

log = logging.getLogger(__name__)

PATH = "/"
_GRAPH_CONFIG = {
    "displaylogo": False,
    "responsive": True,  # follow the card height
    "scrollZoom": True,
    "modeBarButtonsToRemove": ["toImage"],
}
DETAIL_TITLE = "Details"
_SHOW = {"display": "inline-block"}
_HIDE = {"display": "none"}
FOOT_DETAIL = (
    "BFS HESTA (_103) · Ist-Daten (opentransportdata.swiss, Historie; Ausfälle getrennt) · "
    "MeteoSchweiz SMN (Tagesmedian Schneehöhe, Tage mit ≥ 90 % Messwerten)"
)


def _month_options(settings: Settings) -> tuple[list[dict[str, str]], str | None, Any]:
    try:
        m = get_canton_map(settings.curated_dir)
    except DataNotReadyError as e:
        return [], None, empty_state("Kantonskarte: Daten fehlen.", str(e))
    with_delays = set(m.delay_months)
    options = [
        {"label": month_label(mo) + (" · Ist-Daten ✓" if mo in with_delays else ""), "value": mo}
        for mo in reversed(m.months)
    ]
    return options, m.month, None


def _hint() -> html.Div:
    return html.Div(
        [
            html.P("Noch kein Kanton gewählt.", className="mb-1"),
            html.P(
                "Klick auf einen Kanton (oder seine Blase) zeigt hier die Monatsverläufe von "
                "Logiernächten, Verspätungen/Ausfällen und Schnee. Lasso über mehrere Blasen "
                "fasst die gewählten Kantone zusammen.",
                className="text-ink2 small mb-0",
            ),
        ],
        className="empty-state",
    )


def _map_card(options: list[dict[str, str]], default: str | None) -> html.Section:
    picker = html.Label(
        [
            "Monat",
            dcc.Dropdown(
                id="home-month", options=options, value=default, clearable=False,
                style={"minWidth": "220px"},
            ),
        ],
        className="month-picker",
    )  # fmt: skip
    return html.Section(
        [
            html.Div(
                [
                    html.H2("Kantone: Tourismus, ÖV-Verspätungen und Schnee"),
                    html.Span(
                        [
                            dcc.Link("→ H2", href="/h2"),
                            " · ",
                            dcc.Link("→ H3", href="/h3"),
                            " · ",
                            dcc.Link("→ H4", href="/h4"),
                        ],
                        className="viz-links",
                    ),
                ],
                className="viz-head",
            ),
            html.Div(picker, className="my-2"),
            html.P(
                "Fläche = Logiernächte der Tourismusregion des Kantons · Blasenfläche = "
                "verspätete (≥ 3 min) + ausgefallene Halte · Blasenfarbe = Schnee. "
                "Klick auf einen Kanton = Details · Lasso über Blasen = mehrere Kantone.",
                className="text-ink2 small mb-1",
            ),
            html.Div(id="home-map-status", className="small mb-1"),
            html.Div(
                dcc.Graph(id="home-map", config=_GRAPH_CONFIG, style={"height": "100%"}),  # type: ignore[arg-type]
                className="map-fill",
            ),
            source_footnote(FOOT_MAP),
        ],
        className="viz-card",
        **attrs({"aria-label": "Kantonskarte"}),
    )


def _detail_card() -> html.Section:
    return html.Section(
        [
            html.Div(
                [
                    html.H2(DETAIL_TITLE, id="home-detail-title"),
                    html.Button(
                        "Schliessen",
                        id="home-detail-close",
                        n_clicks=0,
                        className="btn-close-panel",
                        style=_HIDE,
                    ),
                ],
                className="detail-head",
            ),
            html.Div(_hint(), id="home-detail-body"),
        ],
        id="home-detail",
        className="viz-card",
        **attrs({"aria-label": "Details zur Auswahl", "aria-live": "polite"}),
    )


def _kpis(settings: Settings) -> html.Section | None:
    """Six KPI cards (US-27 AC2): whole loaded period, Schweiz, only real data («Nur echte»)."""
    try:
        o = get_overview(settings.curated_dir)
    except DataNotReadyError:
        return None
    except Exception:
        log.exception("KPI overview failed")
        return html.Section(dbc.Alert("Kennzahlen konnten nicht geladen werden.", color="danger"))
    cards = [kpi_card(k) for k in o.kpis] + [coverage_card(o)]
    period = f"{month_label(o.month_from)} – {month_label(o.month_to)} · Schweiz · nur echte Daten"
    return html.Section(
        [
            html.P(period, className="kpi-period"),
            dbc.Row([dbc.Col(c, xs=6, md=4, xl=2) for c in cards], className="g-3"),
        ],
        className="mb-4",
        **attrs({"aria-label": "Kennzahlen"}),
    )


def layout(settings: Settings) -> html.Div:
    options, default, problem = _month_options(settings)
    kpis = _kpis(settings)
    if problem is not None:
        return html.Div([kpis, problem])
    return html.Div(
        [
            kpis,
            # one row, stretched: the map card grows to the height of the detail card
            dbc.Row(
                [
                    dbc.Col(_map_card(options, default), xs=12, lg=7, className="fill-col"),
                    dbc.Col(_detail_card(), xs=12, lg=5, className="fill-col"),
                ],
                className="g-3",
            ),
        ]
    )


def update_map(settings: Settings, month: str | None) -> tuple[go.Figure, Any]:
    """Map figure and status line for one month (pure, so tests call it directly)."""
    try:
        m = get_canton_map(settings.curated_dir, month)
    except DataNotReadyError as e:
        return go.Figure(), dbc.Alert(str(e), color="warning")
    except ValueError as e:
        return go.Figure(), dbc.Alert(str(e), color="warning")
    except Exception:
        log.exception("canton map failed")
        return go.Figure(), dbc.Alert("Fehler beim Laden der Kantonskarte.", color="danger")
    label = month_label(m.month)
    if m.delay_days == 0:
        status: Any = dbc.Alert(
            f"Ist-Daten für {label} nicht geladen — Blasen zeigen nur Schnee (gleiche Grösse). "
            f"Geladen: {', '.join(map(month_label, m.delay_months)) or 'keine'}.",
            color="secondary", className="py-1 mb-1",
        )  # fmt: skip
    elif m.delay_days < m.days_in_month:
        status = html.Span(
            f"Ist-Daten {label}: {m.delay_days} von {m.days_in_month} Tagen geladen.",
            className="text-warning-emphasis",
        )
    else:
        status = ""
    return map_figure(m), status


def detail(settings: Settings, kantons: list[str]) -> tuple[str, Any]:
    """Panel title and body for a selection of cantons."""
    try:
        d = get_canton_detail(settings.curated_dir, kantons)
    except (DataNotReadyError, ValueError) as e:
        return DETAIL_TITLE, dbc.Alert(str(e), color="warning")
    except Exception:
        log.exception("canton detail failed")
        return DETAIL_TITLE, dbc.Alert("Fehler beim Laden der Details.", color="danger")
    names = ", ".join(d.names)
    title = f"Kanton {names}" if len(d.names) == 1 else f"{len(d.names)} Kantone: {names}"
    graphs = [
        dcc.Graph(figure=f, config={"displaylogo": False}, className="mb-2")
        for f in detail_figures(d)
    ]
    note = html.P(
        "Logiernächte: Summe der Tourismusregionen der gewählten Kantone (jede Region einmal). "
        "Schnee: ein Tag zählt als Neuschnee, wenn an einer Station der Auswahl Neuschnee fiel.",
        className="text-muted small",
    )
    return title, html.Div([note, *graphs, source_footnote(FOOT_DETAIL)])


def panel_update(
    settings: Settings,
    trigger: str | None,
    prop: str,
    click: dict[str, Any] | None,
    selected: dict[str, Any] | None,
) -> tuple[Any, Any, Any]:
    """Right panel after a click, a lasso or «Schliessen» (pure, so tests call it directly)."""
    if trigger == "home-detail-close":
        return DETAIL_TITLE, _hint(), _HIDE
    kantons = kantons_from_event(selected if prop == "selectedData" else click)
    if not kantons:
        return no_update, no_update, no_update  # empty lasso keeps what is shown
    title, body = detail(settings, kantons)
    return title, body, _SHOW


def register_callbacks(app: Dash, settings: Settings) -> None:
    @app.callback(
        Output("home-map", "figure"),
        Output("home-map-status", "children"),
        Input("home-month", "value"),
    )
    def _map(month: str | None) -> tuple[go.Figure, Any]:
        return update_map(settings, month)

    @app.callback(
        Output("home-detail-title", "children"),
        Output("home-detail-body", "children"),
        Output("home-detail-close", "style"),
        Input("home-map", "clickData"),
        Input("home-map", "selectedData"),
        Input("home-detail-close", "n_clicks"),
        prevent_initial_call=True,
    )
    def _detail(
        click: dict[str, Any] | None, selected: dict[str, Any] | None, _n: int
    ) -> tuple[Any, Any, Any]:
        prop = (ctx.triggered[0]["prop_id"] if ctx.triggered else "").split(".")[-1]
        return panel_update(settings, ctx.triggered_id, prop, click, selected)
