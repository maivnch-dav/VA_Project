"""Service points (Dienststellen) — official stop list with BFS municipality number."""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import requests

from va_project.collectors.http import fetch

SOURCE = "service_points"

_COLUMNS = {
    "number": "number",
    "sloid": "sloid",
    "designationOfficial": "name",
    "isoCountryCode": "country",
    "cantonAbbreviation": "kanton",
    "fsoNumber": "bfs_nr",
    "municipalityName": "municipality",
    "wgs84North": "lat",
    "wgs84East": "lon",
    "height": "height_m",
    "stopPoint": "is_stop",
}


def fetch_service_points(session: requests.Session, url: str) -> bytes:
    return fetch(session, url, source=SOURCE, timeout=120).content


def _csv_bytes(data: bytes) -> bytes:
    if data[:2] != b"PK":
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        return z.read(name)


def parse_service_points(data: bytes) -> pd.DataFrame:
    """Accepts the zipped download or the raw CSV (`;`-separated, UTF-8 with BOM)."""
    raw = pd.read_csv(
        io.BytesIO(_csv_bytes(data)),
        sep=";",
        encoding="utf-8-sig",
        usecols=list(_COLUMNS),
        dtype=str,
        keep_default_na=False,
    )
    df = raw.rename(columns=_COLUMNS).replace({"": None})
    df["bfs_nr"] = pd.to_numeric(df["bfs_nr"], errors="coerce").astype("Int64")
    for col in ("lat", "lon", "height_m"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["is_stop"] = df["is_stop"].eq("true")
    return df.drop_duplicates("number", keep="last").reset_index(drop=True)
