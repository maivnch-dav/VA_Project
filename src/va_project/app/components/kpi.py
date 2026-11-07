"""KPI cards of the start page (prototype 00-daten.html `renderKpis`, US-27 AC2)."""

from __future__ import annotations

import plotly.graph_objects as go
from dash import dcc, html

from va_project.app.components import palette as P
from va_project.app.components.common import attrs
from va_project.services.overview import Kpi, Overview

SPARK_HEIGHT = 28
_SPARK_CONFIG = {"staticPlot": True, "displayModeBar": False, "responsive": True}


def sparkline(values: tuple[float | None, ...]) -> go.Figure:
    """Line with gaps (no interpolation) and a dot on the last value."""
    x = list(range(len(values)))
    last = max((i for i, v in enumerate(values) if v is not None), default=None)
    fig = go.Figure(
        go.Scatter(x=x, y=list(values), mode="lines", connectgaps=False,
                   line={"color": P.CAT[0], "width": 1.6}, hoverinfo="skip")
    )  # fmt: skip
    if last is not None:
        dot = {"color": P.CAT[0], "size": 5}
        fig.add_trace(
            go.Scatter(x=[last], y=[values[last]], mode="markers", marker=dot, hoverinfo="skip")
        )
    fig.update_layout(
        height=SPARK_HEIGHT, margin={"l": 2, "r": 4, "t": 3, "b": 3}, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"visible": False, "range": [-0.3, max(len(values) - 1, 1) + 0.3]},
        yaxis={"visible": False},
    )  # fmt: skip
    return fig


def kpi_card(k: Kpi) -> html.Div:
    if k.delta_text is not None:
        cmp = html.Span(f"{k.delta_text} ggü. Vorjahr",
                        title="Vergleich mit denselben Monaten des Vorjahres: "
                        + ", ".join(k.delta_months))  # fmt: skip
    else:
        cmp = html.Span("– kein Vorjahresvergleich", title="Keine gemeinsamen Monate mit Daten")
    n = sum(v is not None for v in k.spark)
    spark = (
        dcc.Graph(figure=sparkline(k.spark), config=_SPARK_CONFIG, className="kpi-spark")  # type: ignore[arg-type]
        if n >= 2
        else html.Div(className="kpi-spark")
    )
    return html.Div(
        [
            html.Div(k.label, className="kpi-label"),
            html.Div(k.value_text, className="kpi-value"),
            html.Div(cmp, className="kpi-delta"),
            spark,
        ],
        className="card kpi-card",
        id=f"kpi-{k.key}",
    )


def coverage_card(o: Overview) -> dcc.Link:
    loaded = sum(ok for _, ok in o.coverage)
    strip = [
        html.Span(title=f"{m}: {'geladen' if ok else 'fehlt'}",
                  className="cov-cell" + (" is-loaded" if ok else ""))
        for m, ok in o.coverage
    ]  # fmt: skip
    return dcc.Link(
        [
            html.Div("Datenabdeckung Ist-Daten", className="kpi-label"),
            html.Div(f"{loaded} / {len(o.coverage)}", className="kpi-value"),
            html.Div("Monate geladen · Datenqualität ↗", className="kpi-delta"),
            html.Div(strip, className="cov-strip", **attrs({"aria-hidden": "true"})),
        ],
        href="/quality",
        className="card kpi-card kpi-link",
        id="kpi-coverage",
    )
