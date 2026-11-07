"""BFS municipality levels (agvchapp): Gemeinde → canton and tourism region.

`STREG2022` is the BFS tourism-region classification; its codes are the same as the
`Tourismusregion` codes of HESTA table _103 (checked 2026-09-30, all 2110 municipalities).
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import requests

from va_project.collectors.http import fetch

SOURCE = "bfs_communes"
TOURISM_LEVEL = "STREG2022"

# BFS canton numbers (CantonId) → official abbreviation
CANTON_ABBR: dict[int, str] = dict(enumerate(
    ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR", "SO", "BS", "BL",
     "SH", "AR", "AI", "SG", "GR", "AG", "TG", "TI", "VD", "VS", "NE", "GE", "JU"],
    start=1,
))  # fmt: skip


def fetch_levels(session: requests.Session, url: str, on: date) -> bytes:
    """Municipalities valid on `on` with their spatial levels (CSV)."""
    return fetch(session, url, source=SOURCE, params={"date": f"{on:%d-%m-%Y}"}).content


def parse_levels(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", dtype=str)
    missing = [c for c in ("BfsCode", "Name", "CantonId", TOURISM_LEVEL) if c not in df.columns]
    if missing:
        raise ValueError(f"BFS levels format changed — missing columns: {', '.join(missing)}")
    return pd.DataFrame({
        "bfs_nr": df["BfsCode"].astype("int64"),
        "name": df["Name"],
        "kanton": df["CantonId"].astype(int).map(CANTON_ABBR),
        "tourism_region_code": df[TOURISM_LEVEL].str.strip(),
    }).sort_values("bfs_nr", ignore_index=True)  # fmt: skip
