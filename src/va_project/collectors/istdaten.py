"""Ist-Daten (actual arrival/departure times): monthly archive zips and daily CSVs.

Each stop event is reduced to a small per-day staging file (service day, station, local
hour, status, delay, flags). `etl.aggregate` turns a month of staging files into the
history aggregates; the raw CSVs are never stored (SYSTEM-DESIGN D10).

Format facts (checked 2026-09-30): v1 zips (2025-01…2026-06) have 21 columns and no SLOID,
v2 zips (from 2025-07) add SLOID. Times are Europe/Zurich wall-clock strings without an
offset, so hour and month are already local; the delay is the difference of two wall-clock
times (on the DST fall-back night this is off by one hour when the two times fall in
different folds — the aggregation drops such values as outliers).
"""

from __future__ import annotations

import calendar
import logging
import re
import shutil
import subprocess
import time
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import IO, Literal
from urllib.parse import urljoin

import duckdb
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import requests

from va_project.collectors.http import SourceError, fetch

log = logging.getLogger(__name__)

SOURCE = "istdaten"
REQUIRED_COLUMNS = (
    "BETRIEBSTAG", "ZUSATZFAHRT_TF", "FAELLT_AUS_TF", "BPUIC", "HALTESTELLEN_NAME",
    "ANKUNFTSZEIT", "AN_PROGNOSE", "AN_PROGNOSE_STATUS",
    "ABFAHRTSZEIT", "AB_PROGNOSE", "AB_PROGNOSE_STATUS", "DURCHFAHRT_TF",
)  # fmt: skip
SWISS_UIC_PREFIX = "85"
# The last days of real monthly zips are Deflate64 (method 9), which Python's zipfile cannot
# read; those members are streamed through the system `unzip` (Info-ZIP) instead.
UNZIP_METHODS = {9}

MonthKind = Literal["archive_v2", "archive_v1", "daily"]

_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_ARCHIVE_RE = re.compile(r'href="(istdaten/\d{4}/ist-daten-(v2-)?(\d{4}-\d{2})\.zip)"')
_DAILY_RE = re.compile(r'https?://[^"\s<>]+/(\d{4}-\d{2}-\d{2})_istdaten\.csv', re.IGNORECASE)
_MEMBER_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_istdaten\.csv$", re.IGNORECASE)
_STAGING_RE = re.compile(r"^day=(\d{4}-\d{2}-\d{2})\.parquet$")

# Arrival if the stop has a planned arrival, else departure (first stop) — same rule as the
# GTFS-RT view. Missing status → UNBEKANNT. Foreign/pass-through rows are kept but flagged,
# so the monthly report can count them.
_STAGE_SQL = """
WITH raw AS (
    SELECT
        strptime(BETRIEBSTAG, '%d.%m.%Y')::DATE AS service_date,
        -- 9 digits = stop position (BPUIC + 2, since 2026) → station-level 7-digit number
        CASE WHEN regexp_full_match(trim(BPUIC), '[0-9]{9}') THEN left(trim(BPUIC), 7)
             ELSE trim(BPUIC) END AS station_key,
        HALTESTELLEN_NAME AS station_name,
        lower(FAELLT_AUS_TF) = 'true' AS canceled,
        lower(ZUSATZFAHRT_TF) = 'true' AS additional,
        lower(DURCHFAHRT_TF) = 'true' AS passthrough,
        NOT starts_with(trim(BPUIC), '85') AS foreign_stop,
        try_strptime(nullif(ANKUNFTSZEIT, ''), ['%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M']) AS arr_plan,
        try_strptime(nullif(AN_PROGNOSE, ''), ['%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M']) AS arr_act,
        nullif(upper(trim(AN_PROGNOSE_STATUS)), '') AS arr_status,
        try_strptime(nullif(ABFAHRTSZEIT, ''), ['%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M']) AS dep_plan,
        try_strptime(nullif(AB_PROGNOSE, ''), ['%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M']) AS dep_act,
        nullif(upper(trim(AB_PROGNOSE_STATUS)), '') AS dep_status
    FROM src
)
SELECT
    service_date,
    station_key,
    station_name,
    hour(coalesce(arr_plan, dep_plan))::TINYINT AS hour_local,
    coalesce(CASE WHEN arr_plan IS NOT NULL THEN arr_status ELSE dep_status END, 'UNBEKANNT')
        AS status,
    -- BIGINT: some real actual times are decades off (3.9e9 s in 2025-01) → counted as outliers
    CASE WHEN arr_plan IS NOT NULL THEN date_diff('second', arr_plan, arr_act)
         ELSE date_diff('second', dep_plan, dep_act) END::BIGINT AS delay_s,
    canceled,
    additional,
    passthrough,
    foreign_stop
FROM raw
"""


# --- months & sources -------------------------------------------------------


def _parse_month(month: str) -> tuple[int, int]:
    m = _MONTH_RE.match(month)
    if m is None:
        raise ValueError(f"month must be YYYY-MM, got {month!r}")
    return int(m.group(1)), int(m.group(2))


def month_range(start: str, end: str) -> list[str]:
    y, m = _parse_month(start)
    y_end, m_end = _parse_month(end)
    if (y, m) > (y_end, m_end):
        raise ValueError(f"--from {start} is after --to {end}")
    out = []
    while (y, m) <= (y_end, m_end):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def days_of_month(month: str) -> list[date]:
    y, m = _parse_month(month)
    return [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]


def parse_archive_listing(html: str, base_url: str) -> dict[str, dict[str, str]]:
    """month → {"v1": url, "v2": url} from the archive's file listing."""
    out: dict[str, dict[str, str]] = {}
    for path, v2, month in _ARCHIVE_RE.findall(html):
        out.setdefault(month, {})["v2" if v2 else "v1"] = urljoin(base_url, path)
    return out


def parse_daily_page(html: str) -> dict[str, str]:
    """ISO day → CSV url from the dataset page (the CKAN API refuses scripted access)."""
    found = {day: url for url, day in ((m.group(0), m.group(1)) for m in _DAILY_RE.finditer(html))}
    return dict(sorted(found.items()))


def fetch_archive_listing(
    session: requests.Session, url: str, base_url: str
) -> dict[str, dict[str, str]]:
    return parse_archive_listing(fetch(session, url, source=SOURCE).text, base_url)


def fetch_daily_page(session: requests.Session, url: str) -> dict[str, str]:
    return parse_daily_page(fetch(session, url, source=SOURCE).text)


@dataclass(frozen=True)
class MonthPlan:
    month: str
    kind: MonthKind
    urls: dict[str, str]  # archive: {"zip": url}; daily: {ISO day: url}
    complete: bool  # False = daily CSVs do not (yet) cover every day of the month


def plan_month(
    month: str, archive: dict[str, dict[str, str]], daily: dict[str, str]
) -> MonthPlan | None:
    """v2 zip (has SLOID, newer) > v1 zip > daily CSVs for the months not archived yet."""
    variants = archive.get(month, {})
    if "v2" in variants:
        return MonthPlan(month, "archive_v2", {"zip": variants["v2"]}, complete=True)
    if "v1" in variants:
        return MonthPlan(month, "archive_v1", {"zip": variants["v1"]}, complete=True)
    days = {d: u for d, u in daily.items() if d.startswith(month)}
    if not days:
        return None
    complete = set(days) == {d.isoformat() for d in days_of_month(month)}
    return MonthPlan(month, "daily", days, complete=complete)


# --- download ---------------------------------------------------------------


def download(
    session: requests.Session,
    url: str,
    dest: Path,
    *,
    attempts: int = 5,
    chunk_size: int = 8 << 20,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Stream `url` to `dest`, resuming an earlier `.part` file with an HTTP Range request."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for attempt in range(attempts):
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else None
        try:
            resp = fetch(
                session, url, source=SOURCE, headers=headers, stream=True, timeout=120, sleep=sleep
            )
        except SourceError as e:
            if e.status == 416 and offset:  # nothing left to fetch; zip is validated on open
                break
            raise
        mode = "ab" if resp.status_code == 206 and offset else "wb"
        try:
            with resp, part.open(mode) as f:
                for chunk in resp.iter_content(chunk_size):
                    f.write(chunk)
        except (
            requests.ConnectionError,
            requests.Timeout,
            requests.exceptions.ChunkedEncodingError,  # connection dropped mid-body
        ) as e:
            wait = min(60.0, 5.0 * 2**attempt)
            log.warning("%s: download interrupted (%s), resuming in %.0fs", SOURCE, e, wait)
            sleep(wait)
            continue
        break
    else:
        raise SourceError(SOURCE, None, f"download of {url} interrupted {attempts} times")
    part.replace(dest)
    return dest


# --- staging ----------------------------------------------------------------


def staging_path(staging_dir: Path, day: str) -> Path:
    return staging_dir / f"day={day}.parquet"


def staged_days(staging_dir: Path) -> list[str]:
    if not staging_dir.is_dir():
        return []
    days = (_STAGING_RE.match(p.name) for p in staging_dir.iterdir())
    return sorted(m.group(1) for m in days if m)


def stage_csv(stream: IO[bytes], out: Path) -> int:
    """Reduce one day's CSV to the staging layout; returns the number of rows read."""
    header = stream.readline().decode("utf-8-sig").strip().split(";")
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"Ist-Daten format changed — missing columns: {', '.join(missing)}")
    reader = pacsv.open_csv(
        stream,
        read_options=pacsv.ReadOptions(column_names=header, block_size=32 << 20),
        parse_options=pacsv.ParseOptions(delimiter=";"),
        convert_options=pacsv.ConvertOptions(
            include_columns=list(REQUIRED_COLUMNS),
            column_types=dict.fromkeys(REQUIRED_COLUMNS, pa.string()),
            strings_can_be_null=False,
        ),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    rows = 0
    con = duckdb.connect()
    try:
        con.register("src", reader)
        batches = con.execute(_STAGE_SQL).to_arrow_reader(1 << 20)
        with pq.ParquetWriter(tmp, batches.schema, compression="zstd") as writer:
            for batch in batches:
                writer.write_batch(batch)
                rows += batch.num_rows
        tmp.replace(out)
    finally:
        con.close()
        tmp.unlink(missing_ok=True)
    return rows


@contextmanager
def _open_member(z: zipfile.ZipFile, zip_path: Path, info: zipfile.ZipInfo) -> Iterator[IO[bytes]]:
    if info.compress_type not in UNZIP_METHODS:
        with z.open(info) as f:
            yield f
        return
    unzip = shutil.which("unzip")
    if unzip is None:
        raise OSError(f"{info.filename} is Deflate64-compressed; install `unzip` to read it")
    if info.filename.startswith("-"):
        raise OSError(f"refusing suspicious member name {info.filename!r}")
    # no shell; the binary path is resolved and the member name comes from the zip directory
    proc = subprocess.Popen(  # noqa: S603
        [unzip, "-p", str(zip_path), info.filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.stdout, proc.stderr
    if stdout is None or stderr is None:  # cannot happen with PIPE; narrows the types
        raise OSError("unzip pipes not available")
    try:
        yield stdout
    except BaseException as e:
        proc.kill()
        proc.wait()
        err = stderr.read().decode(errors="replace").strip()
        if err:  # e.g. a parser error caused by unzip failing → show unzip's reason too
            e.add_note(f"unzip: {err}")
        raise
    finally:
        stdout.close()
    err = stderr.read().decode(errors="replace").strip()
    stderr.close()
    proc.wait()
    if proc.returncode != 0:
        raise OSError(f"unzip {info.filename} failed (exit {proc.returncode}): {err}")


def stage_zip(zip_path: Path, staging_dir: Path) -> list[str]:
    """Stage every day in a monthly archive; days staged earlier are skipped (resume)."""
    done = []
    with zipfile.ZipFile(zip_path) as z:
        for info in sorted(z.infolist(), key=lambda i: i.filename):
            m = _MEMBER_RE.search(info.filename)
            if m is None:
                log.warning("%s: ignoring unexpected member %s", SOURCE, info.filename)
                continue
            out = staging_path(staging_dir, m.group(1))
            if out.exists():
                continue
            t0 = time.monotonic()
            try:
                with _open_member(z, zip_path, info) as f:
                    n = stage_csv(f, out)
            except BaseException:
                out.unlink(missing_ok=True)  # never leave a day that looks staged
                raise
            log.info("%s %s: %d rows in %.0fs", SOURCE, m.group(1), n, time.monotonic() - t0)
            done.append(m.group(1))
    return done
