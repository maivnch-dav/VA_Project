"""Chart colours for Plotly, mirroring assets/tokens.css (Plotly cannot read CSS variables).

Theme «Carbon Mint» (prototype default, UI-SPEC §4; adopted for the app 2026-11-06): charts sit
on dark "screen" cards (#14171a). Values = the --chart-* / --cat-* / --seq-* tokens of
prototypes/shared/themes/carbon-mint.css (dataviz validator: every slot ≥ 3:1 on #14171a).
Categorical hues are assigned in this fixed order, never cycled; on maps and scatter plots use
at most CAT[:3] and add SHAPES beyond that.
"""

from __future__ import annotations

# chart chrome (dark screen)
SURFACE = "#14171a"
HOVER = "#2C353F"
INK = "#F4F6F8"
INK_2 = "#c3cbd3"
MUTED = "#9aa5b1"
GRID = "#262d35"
AXIS = "#3f4a56"
OTHER = "#6f7a86"
ACCENT = "#00FFC2"
FONT = "Inconsolata, ui-monospace, Menlo, monospace"  # numbers, labels, charts

CAT = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
SHAPES = ["circle", "square", "diamond", "triangle-up", "cross", "x", "star", "hexagon"]
# sequential on dark: low values recede into the surface (dark), high values are light
SEQ = ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"]
SEQ_SCALE = [[i / (len(SEQ) - 1), c] for i, c in enumerate(SEQ)]
DIV_SCALE = [[0.0, "#3987e5"], [0.5, "#383835"], [1.0, "#e66767"]]

SRC_HISTORY = CAT[0]  # BR6: source identity, not status
SRC_LIVE = CAT[1]
NOT_COLLECTED = "#262d35"  # --chart-empty


def base_layout(**extra: object) -> dict[str, object]:
    """Dark chart chrome shared by every figure (prototype `SF.layout`)."""
    axis = {"gridcolor": GRID, "linecolor": AXIS, "zerolinecolor": AXIS,
            "tickfont": {"size": 11, "color": INK_2}}  # fmt: skip
    layout: dict[str, object] = {
        "paper_bgcolor": SURFACE,
        "plot_bgcolor": SURFACE,
        "font": {"family": FONT, "size": 12, "color": INK},
        "hoverlabel": {"bgcolor": HOVER, "bordercolor": AXIS, "font": {"color": INK, "size": 12}},
        "xaxis": axis,
        "yaxis": dict(axis),
    }
    layout.update(extra)
    return layout
