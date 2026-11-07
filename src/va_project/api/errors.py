"""RFC 7807 error responses for everything under /api/."""

from __future__ import annotations

import logging

from flask import Flask, Response, abort, request
from werkzeug.exceptions import HTTPException, InternalServerError

from va_project.api.schemas import Problem

log = logging.getLogger(__name__)
PROBLEM_JSON = "application/problem+json"


def problem_response(status: int, title: str, detail: str | None = None) -> Response:
    body = Problem(title=title, status=status, detail=detail).model_dump_json(exclude_none=True)
    return Response(body, status=status, mimetype=PROBLEM_JSON)


def register_error_handlers(server: Flask) -> None:
    """Only API paths get problem+json; Dash pages keep Flask's default handling."""

    @server.before_request
    def _guard_api_namespace() -> None:
        # Dash's catch-all "/<path>" would otherwise answer unknown API paths with HTML.
        # Routing errors (404/405) are raised by Flask after this hook — leave them alone.
        if request.routing_exception is not None:
            return
        if request.path.startswith("/api/") and not (request.endpoint or "").startswith("api_v1."):
            abort(404)

    @server.errorhandler(HTTPException)
    def _http_error(e: HTTPException) -> Response | HTTPException:
        if not request.path.startswith("/api/"):
            return e
        return problem_response(e.code or 500, e.name, e.description)

    @server.errorhandler(Exception)
    def _unhandled(e: Exception) -> Response | HTTPException:
        log.exception("Unhandled error on %s", request.path)
        if not request.path.startswith("/api/"):
            return InternalServerError()
        # never leak internals to the client
        return problem_response(500, "Internal Server Error")
