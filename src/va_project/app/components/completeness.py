"""CompletenessHeatmap: source (rows) × local day (columns), colour = received / expected."""

from __future__ import annotations

from datetime import timedelta

import plotly.graph_objects as go

from va_project.app.components.palette import FONT, INK, NOT_COLLECTED, SEQ, SURFACE
from va_project.services.quality import DataQuality

Q_NONE = NOT_COLLECTED  # not collected — not a quality defect
Q_LOW = SEQ[0]  # ≤ FLOOR (dark: low values recede)
Q_MID = SEQ[3]
Q_HIGH = SEQ[-1]  # 100 %
FLOOR = 0.8  # the scale spans FLOOR … 100 %; everything below is as light as FLOOR

TITLE = "Vollständigkeit je Quelle und Tag"
UNIT = "Anteil der erwarteten Werte, die vorhanden sind (%)"


def completeness_figure(dq: DataQuality) -> go.Figure:
    days = [dq.date_from + timedelta(days=i) for i in range((dq.date_to - dq.date_from).days + 1)]
    col = {d: i for i, d in enumerate(days)}
    row = {s: i for i, s in enumerate(dq.sources)}
    # -1 = not collected (grey); 0 … 1 = ratio rescaled to FLOOR … 100 %
    z: list[list[float]] = [[-1.0] * len(days) for _ in row]
    text: list[list[str]] = [["nicht erhoben"] * len(days) for _ in row]
    for c in dq.completeness:
        i, j = row[c.source], col[c.day]
        z[i][j] = min(1.0, max(0.0, (c.ratio - FLOOR) / (1 - FLOOR)))
        detail = f"{c.received:,} von {c.expected:,}".replace(",", "'") if c.expected else ""
        text[i][j] = " · ".join(filter(None, [f"{c.ratio:.1%} vollständig", detail, c.note]))

    fig = go.Figure(
        go.Heatmap(
            x=days,
            y=list(dq.sources.values()),
            z=z,
            zmin=-1,
            zmax=1,
            xgap=1 if len(days) <= 120 else 0,  # gaps on long ranges read as stripes
            ygap=3,
            showscale=False,
            colorscale=[[0, Q_NONE], [0.4999, Q_NONE], [0.5, Q_LOW], [0.75, Q_MID], [1, Q_HIGH]],
            customdata=text,
            hovertemplate="%{y} · %{x|%d.%m.%Y}<br>%{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        title={"text": f"{TITLE}<br><sup>{UNIT}</sup>", "x": 0, "xanchor": "left"},
        height=120 + 42 * len(row),
        margin={"l": 10, "r": 10, "t": 60, "b": 30},
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font={
            "family": FONT,
            "size": 13,
            "color": INK,
        },
        xaxis={"type": "date", "showgrid": False},
        yaxis={"autorange": "reversed", "showgrid": False, "automargin": True},
    )
    return fig
