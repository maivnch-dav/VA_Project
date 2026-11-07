"""Small building blocks shared by all pages (docs/UI-SPEC.md §5)."""

from __future__ import annotations

from typing import Any

import dash_bootstrap_components as dbc
from dash import html


def kpi_tile(label: str, value: str, note: str = "", ok: bool | None = None) -> dbc.Card:
    """KpiTile: label, value, note; `ok` adds a status badge (icon + text, never colour only)."""
    badge = None
    if ok is not None:
        badge = html.Span(
            ("✓ Ziel erreicht" if ok else "! beachten"),
            className=f"kpi-status {'kpi-ok' if ok else 'kpi-warn'}",
        )
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(label, className="kpi-label"),
                html.Div(value, className="kpi-value"),
                html.Div([badge, html.Span(note, className="kpi-note")], className="kpi-foot"),
            ]
        ),
        className="kpi-tile h-100",
    )


def source_footnote(text: str) -> html.Div:
    """SourceFootnote under every chart (BR3)."""
    return html.Div(f"Quelle: {text}", className="source-footnote")


def empty_state(message: str, hint: str | None = None) -> html.Div:
    return html.Div(
        [html.P(message, className="mb-1"), html.Code(hint) if hint else None],
        className="empty-state",
    )


def attrs(values: dict[str, str]) -> dict[str, Any]:
    """aria-* / data-* attributes for `**` (Dash's stubs type-check every keyword)."""
    return dict(values)
