"""Dash application factory. Run with `python -m va_project.app.dash_app`."""

from __future__ import annotations

from pathlib import Path

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, dcc, html
from flask import Flask

from va_project.api.errors import register_error_handlers
from va_project.api.routes import create_api
from va_project.app.components.common import attrs
from va_project.app.pages import home, quality
from va_project.config import Settings, configure_logging, get_settings

ASSETS_DIR = Path(__file__).parent / "assets"

# (href, label) — UI-SPEC §1 sitemap, same order as the prototype nav (prototypes/shared/app.js)
NAV_PAGES: list[tuple[str, str]] = [
    ("/", "Daten"),  # Datenüberblick (US-27)
    ("/hypothesen", "Hypothesen"),
    ("/h1", "H1"),
    ("/h2", "H2"),
    ("/h3", "H3"),
    ("/h4", "H4"),
    ("/h5", "H5"),
    ("/quality", "Datenqualität"),
]
FONTS = (
    "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700"
    "&family=Inconsolata:wght@400;500;700&family=Quicksand:wght@400;500;600;700&display=swap"
)


def _navbar() -> html.Header:
    """Prototype nav: sticky carbon bar, red brand mark, mint current page (UI-SPEC §5)."""
    return html.Header(
        html.Div(
            [
                html.A(
                    [
                        html.Span("+", className="brand-mark", **attrs({"aria-hidden": "true"})),
                        html.Span("SwissFlow\u00a0VA", className="display fs-5"),
                    ],
                    href="/",
                    className="sf-brand",
                ),
                html.Nav(
                    dbc.Nav(
                        [dbc.NavLink(label, href=href, active="exact") for href, label in NAV_PAGES]
                    ),
                    **attrs({"aria-label": "Seiten"}),
                ),
            ],
            className="sf-nav-inner",
        ),
        id="NavBar",
        className="sf-nav",
    )


def create_app(settings: Settings | None = None) -> Dash:
    settings = settings or get_settings()
    settings.ensure_dirs()

    server = Flask(__name__)
    server.register_blueprint(create_api(settings))
    register_error_handlers(server)

    app = Dash(
        __name__,
        server=server,  # type: ignore[arg-type]  # Dash 4 stubs omit Flask; documented usage
        title="SwissFlow VA",
        assets_folder=str(ASSETS_DIR),
        external_stylesheets=[dbc.themes.BOOTSTRAP, FONTS],
        suppress_callback_exceptions=True,
    )
    app.layout = html.Div(
        [
            dcc.Location(id="url"),
            _navbar(),
            html.Main(id="page-content", className="sf-main"),
        ],
        className="sf-app",
        **attrs({"data-bs-theme": "dark"}),
    )

    labels = dict(NAV_PAGES)
    quality.register_callbacks(app, settings)
    home.register_callbacks(app, settings)

    @app.callback(Output("page-content", "children"), Input("url", "pathname"))
    def _render(pathname: str | None) -> html.Div:
        if pathname == quality.PATH:
            return quality.layout()
        if pathname in (home.PATH, None):
            return home.layout(settings)
        label = labels.get(pathname or "/")
        if label is None:
            return html.Div([html.H3("404"), html.P(f"Seite {pathname} nicht gefunden.")])
        return html.Div([html.H3(label), html.P("Noch nicht implementiert.")])

    return app


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    create_app(settings).run(host=settings.app_host, port=settings.app_port, debug=settings.debug)


if __name__ == "__main__":
    main()
