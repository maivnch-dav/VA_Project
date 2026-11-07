"""Figures for the canton map on `/` (US-30): choropleth + bubbles, and the monthly detail."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from va_project.app.components import palette as P
from va_project.services.canton_map import SNOW_LABELS, CantonDetail, CantonMap, CantonMonth

# bubble colours: blue is taken by the choropleth → orange/green + two neutrals (≤ 3 hues)
SNOW_COLORS = {"new": P.CAT[1], "cover": P.CAT[2], "none": P.INK_2, "unknown": P.OTHER}
BUBBLE_MAX_PX = 46
BUBBLE_MIN_PX = 5
BUBBLE_NO_DATA_PX = 9
CENTER = {"lon": 8.23, "lat": 46.80}
MAP_STYLE = "carto-darkmatter"  # D26; tiles from CARTO (© OpenStreetMap, CARTO), no token needed
MONTHS_DE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

FOOT_MAP = (
    "BFS HESTA Logiernächte (_103, Tourismusregion, alle Herkunftsländer) · Ist-Daten "
    "(opentransportdata.swiss, Historie) · MeteoSchweiz SMN Schneehöhe (Tagesmedian) · "
    "Kantonsgrenzen swisstopo swissBOUNDARIES3D · Karte © OpenStreetMap, CARTO"
)


def fmt_int(x: float | None) -> str:
    """Swiss thousands separator (1’234’567); '–' for missing."""
    return "–" if x is None else f"{x:,.0f}".replace(",", "’")


def month_label(month: str) -> str:
    y, m = month.split("-")
    return f"{MONTHS_DE[int(m) - 1]} {y}"


def _region_text(c: CantonMonth) -> str:
    if c.region is None:
        return "keine Tourismusregion"
    extra = f" (auch: {', '.join(c.other_regions)})" if c.other_regions else ""
    return f"{c.region}{extra}"


def _nights_text(c: CantonMonth) -> str:
    if c.nights is None:
        return "nicht veröffentlicht / unterdrückt"
    return fmt_int(c.nights) + (" (Schätzung)" if c.nights_estimate else "")


def _choropleth(m: CantonMap) -> list[go.Choroplethmap]:
    known = [c for c in m.cantons if c.nights is not None]
    missing = [c for c in m.cantons if c.nights is None]
    common: dict[str, Any] = {
        "geojson": m.geojson,
        "featureidkey": "id",
        "marker": {"line": {"color": "rgba(244,246,248,0.35)", "width": 0.8}, "opacity": 0.9},
        "hovertemplate": "<b>%{customdata[1]}</b><br>Tourismusregion: %{customdata[2]}"
        "<br>Logiernächte der Region: %{customdata[3]}<extra></extra>",
        "showlegend": False,
    }
    traces = [
        go.Choroplethmap(
            locations=[c.kanton for c in known],
            z=[c.nights for c in known],
            customdata=[[c.kanton, c.name, _region_text(c), _nights_text(c)] for c in known],
            colorscale=P.SEQ_SCALE,
            zmin=0,
            colorbar={
                "title": {
                    "text": "Logiernächte<br>der Region",
                    "font": {"size": 12, "color": P.INK_2},
                },
                "tickfont": {"color": P.INK_2},
                "bgcolor": "rgba(20,23,26,0.6)",
                "outlinewidth": 0,
                "thickness": 12,
                "len": 0.6,
                "x": 1.0,
                "xanchor": "right",
                "tickformat": "~s",
            },
            name="Logiernächte",
            **common,
        )
    ]
    if missing:  # grey, labelled — never coloured as 0
        traces.append(
            go.Choroplethmap(
                locations=[c.kanton for c in missing],
                z=[0] * len(missing),
                customdata=[[c.kanton, c.name, _region_text(c), _nights_text(c)] for c in missing],
                colorscale=[[0, P.NOT_COLLECTED], [1, P.NOT_COLLECTED]],
                showscale=False,
                name="nicht veröffentlicht",
                **common,
            )
        )
    return traces


def _sizes(m: CantonMap) -> tuple[list[float], float]:
    """Marker sizes (area ∝ value) and the sizeref Plotly needs for that."""
    values = [c.delay_total or 0 for c in m.cantons]
    top = max(values, default=0)
    if m.delay_days == 0 or top == 0:
        return [BUBBLE_NO_DATA_PX] * len(values), 1.0
    return [float(v) for v in values], 2.0 * top / BUBBLE_MAX_PX**2


def _bubbles(m: CantonMap) -> list[go.Scattermap]:
    sizes, sizeref = _sizes(m)
    no_data = m.delay_days == 0
    traces = []
    for cls, label in SNOW_LABELS.items():
        idx = [i for i, c in enumerate(m.cantons) if c.snow == cls]
        if not idx:
            continue
        rows = [m.cantons[i] for i in idx]
        traces.append(
            go.Scattermap(
                lon=[c.lon for c in rows],
                lat=[c.lat for c in rows],
                mode="markers",
                name=label,
                marker={
                    "size": [sizes[i] for i in idx],
                    "sizemode": "diameter" if no_data else "area",
                    "sizeref": sizeref,
                    "sizemin": BUBBLE_MIN_PX,
                    "color": SNOW_COLORS[cls],
                    "opacity": 0.55 if no_data else 0.9,
                },
                customdata=[
                    [
                        c.kanton,
                        c.name,
                        fmt_int(c.n_late),
                        fmt_int(c.n_canceled),
                        fmt_int(c.delay_total),
                        fmt_int(c.n_events),
                        c.n_stations,
                        SNOW_LABELS[c.snow],
                        c.new_snow_days,
                        c.cover_days,
                        c.n_snow_stations,
                    ]
                    for c in rows
                ],
                hovertemplate=(
                    "<b>%{customdata[1]}</b><br>"
                    + (
                        "Ist-Daten für diesen Monat nicht geladen<br>"
                        if no_data
                        else "Verspätet ≥ 3 min: %{customdata[2]}<br>"
                        "Ausgefallen: %{customdata[3]}<br>"
                        "Summe (Blasengrösse): %{customdata[4]}<br>"
                        "Halte-Ereignisse: %{customdata[5]} an %{customdata[6]} Halten<br>"
                    )
                    + "Schnee: %{customdata[7]} · %{customdata[8]} Tage Neuschnee, "
                    "%{customdata[9]} Tage Schneedecke (%{customdata[10]} Schneestationen)"
                    "<extra></extra>"
                ),
            )
        )
    return traces


def map_figure(m: CantonMap) -> go.Figure:
    fig = go.Figure([*_choropleth(m), *_bubbles(m)])
    fig.update_layout(
        P.base_layout(),
        map={"style": MAP_STYLE, "center": CENTER, "zoom": 6.4},
        autosize=True,  # height comes from the card (fills the row, see tokens.css .map-fill)
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        dragmode="lasso",
        clickmode="event",
        uirevision="canton-map",  # keep zoom/pan when the month changes
        legend={
            "title": {"text": "Blasenfarbe: Schnee im Monat"},
            "orientation": "h",
            "x": 0.01,
            "y": 0.99,
            "yanchor": "top",
            "bgcolor": "rgba(20,23,26,0.85)",
            "font": {"size": 12, "color": P.INK},
        },
    )
    return fig


def kantons_from_event(data: dict[str, Any] | None) -> list[str]:
    """Canton codes from Plotly clickData / selectedData (choropleth or bubble points)."""
    out: list[str] = []
    for p in (data or {}).get("points") or []:
        code = p.get("location")
        if code is None and isinstance(p.get("customdata"), list) and p["customdata"]:
            code = p["customdata"][0]
        if isinstance(code, str) and code not in out:
            out.append(code)
    return out


def _line_layout(fig: go.Figure, title: str, unit: str) -> go.Figure:
    fig.update_layout(
        P.base_layout(),
        title={"text": f"{title}<br><sup>{unit}</sup>", "x": 0,
               "font": {"size": 14, "color": P.INK, "family": "Quicksand, system-ui, sans-serif"}},
        height=250,  # three stacked in the side panel
        margin={"l": 50, "r": 10, "t": 60, "b": 30},
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.2, "font": {"color": P.INK_2}},
        separators=".’",
    )  # fmt: skip
    fig.update_xaxes(tickformat="%m.%Y", gridcolor=P.GRID, linecolor=P.AXIS, dtick="M2")
    fig.update_yaxes(gridcolor=P.GRID, linecolor=P.AXIS, rangemode="tozero", tickformat=",~s")
    return fig


def detail_figures(d: CantonDetail) -> tuple[go.Figure, go.Figure, go.Figure]:
    x = [f"{p.month}-01" for p in d.points]
    line: dict[str, Any] = {"mode": "lines+markers", "connectgaps": False}

    nights = go.Figure(go.Scatter(
        x=x, y=[p.nights for p in d.points], name="Logiernächte",
        line={"color": P.CAT[0], "width": 2}, marker={"size": 6}, **line,
    ))  # fmt: skip
    _line_layout(nights, "Logiernächte", f"Anzahl pro Monat · Region(en): {', '.join(d.regions)}")

    delays = go.Figure([
        go.Scatter(x=x, y=[p.n_late for p in d.points], name="Verspätet ≥ 3 min",
                   line={"color": P.CAT[0], "width": 2}, marker={"size": 8}, **line),
        go.Scatter(x=x, y=[p.n_canceled for p in d.points], name="Ausgefallen",
                   line={"color": P.CAT[1], "width": 2, "dash": "dot"},
                   marker={"size": 8, "symbol": "square"}, **line),
    ])  # fmt: skip
    n_loaded = sum(p.n_late is not None for p in d.points)
    _line_layout(delays, "Verspätungen und Ausfälle (Ist-Daten)",
                 f"Halte-Ereignisse pro Monat · Ist-Daten für {n_loaded} von {len(d.points)} "
                 "Monaten geladen (Lücke = nicht geladen)")  # fmt: skip

    snow = go.Figure([
        go.Scatter(x=x, y=[p.new_snow_days for p in d.points], name=SNOW_LABELS["new"],
                   line={"color": SNOW_COLORS["new"], "width": 2}, **line),
        go.Scatter(x=x, y=[p.cover_days for p in d.points],
                   name="Schneedecke (ohne Neuschnee)",
                   line={"color": SNOW_COLORS["cover"], "width": 2}, **line),
        go.Scatter(x=x, y=[p.no_snow_days for p in d.points], name=SNOW_LABELS["none"],
                   line={"color": SNOW_COLORS["none"], "width": 2, "dash": "dash"}, **line),
        go.Scatter(x=x, y=[p.unknown_days for p in d.points], name=SNOW_LABELS["unknown"],
                   line={"color": SNOW_COLORS["unknown"], "width": 1, "dash": "dot"},
                   visible="legendonly", **line),
    ])  # fmt: skip
    _line_layout(snow, "Schnee: Neuschnee – Schneedecke – kein Schnee",
                 f"Tage pro Monat · {d.n_snow_stations} SMN-Schneestationen · "
                 "Neuschnee = ΔHS ≥ 5 cm, Schneedecke = HS ≥ 1 cm")  # fmt: skip
    snow.update_yaxes(tickformat="d")
    return nights, delays, snow
