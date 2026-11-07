"""WSGI entry point for gunicorn: `gunicorn va_project.app.wsgi:server`."""

from va_project.app.dash_app import create_app
from va_project.config import configure_logging, get_settings

configure_logging(get_settings())
server = create_app().server
