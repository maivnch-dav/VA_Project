"""Shared HTTP access: timeouts, retry with backoff, clear errors per source."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import requests

from va_project import __version__

log = logging.getLogger(__name__)

USER_AGENT = f"SwissFlowVA/{__version__} (FHGR Visual Analytics course project)"
MAX_RETRY_AFTER_S = 120.0


class SourceError(RuntimeError):
    def __init__(
        self, source: str, status: int | None, message: str, retry_after: float | None = None
    ) -> None:
        super().__init__(
            f"{source}: HTTP {status}: {message}" if status else f"{source}: {message}"
        )
        self.source = source
        self.status = status
        self.retry_after = retry_after  # seconds the source asked us to wait (429)


class AccessDeniedError(SourceError):
    """401/403 — missing key or subscription; retrying cannot help."""


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _retry_after(resp: requests.Response, default: float) -> float:
    try:
        return min(float(resp.headers.get("Retry-After", default)), MAX_RETRY_AFTER_S)
    except ValueError:
        return default


def fetch(
    session: requests.Session,
    url: str,
    *,
    source: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: Any = None,
    timeout: float = 60.0,
    retries: int = 3,
    backoff: float = 2.0,
    stream: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> requests.Response:
    """Request with retries on 429, 5xx and connection errors; raise SourceError otherwise."""
    last_error: SourceError | None = None
    for attempt in range(retries):
        wait = backoff * 2**attempt
        try:
            resp = session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
                timeout=timeout,
                stream=stream,
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = SourceError(source, None, f"{type(e).__name__}: {e}")
        else:
            if resp.ok:
                return resp
            detail = " ".join(resp.text[:400].split())[:200]  # one line for logs/reports
            if resp.status_code in (401, 403):
                raise AccessDeniedError(source, resp.status_code, detail)
            retry_after = None
            if resp.status_code == 429:
                wait = retry_after = _retry_after(resp, wait)
            elif resp.status_code < 500:
                raise SourceError(source, resp.status_code, detail)
            last_error = SourceError(source, resp.status_code, detail, retry_after)

        if attempt < retries - 1:
            log.warning("%s — retry %d/%d in %.0fs", last_error, attempt + 1, retries - 1, wait)
            sleep(wait)

    raise last_error or SourceError(source, None, "retries must be >= 1")
