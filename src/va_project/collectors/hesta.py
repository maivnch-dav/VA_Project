"""BFS HESTA (hotel accommodation statistics) via the PxWeb API, json-stat2 format."""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable
from typing import Any

import pandas as pd
import requests

from va_project.collectors.http import fetch

SOURCE = "hesta"
TABLE_GEMEINDE = "px-x-1003020000_101"  # Jahr × Monat × Gemeinde × Herkunftsland × Indikator
TABLE_REGION = "px-x-1003020000_103"  # … × Tourismusregion × …

_AREA_DIMS = ("Gemeinde", "Tourismusregion")
_INDICATORS = {"Ankünfte": "arrivals", "Logiernächte": "nights"}


def table_url(base: str, table: str) -> str:
    return f"{base}/{table}/{table}.px"


def fetch_metadata(session: requests.Session, base: str, table: str) -> dict[str, Any]:
    return fetch(session, table_url(base, table), source=SOURCE).json()  # type: ignore[no-any-return]


def code_for_label(meta: dict[str, Any], dim: str, label: str) -> str:
    """Codes differ between tables (e.g. total = '0' vs '00'); labels are the stable key."""
    var = next(v for v in meta["variables"] if v["code"] == dim)
    for code, text in zip(var["values"], var["valueTexts"], strict=True):
        if text == label:
            return str(code)
    raise LookupError(f"{label!r} not found in dimension {dim!r}")


def dim_codes(meta: dict[str, Any], dim: str) -> list[str]:
    return [str(c) for c in next(v for v in meta["variables"] if v["code"] == dim)["values"]]


ALL = ["*"]


def build_query(selections: dict[str, list[str]]) -> dict[str, Any]:
    """PxWeb *eliminates* (sums away) dimensions that are not listed, so every dimension
    needed in the result must be selected — use `ALL` for all values."""
    return {
        "query": [
            {
                "code": dim,
                "selection": {"filter": "all" if values == ALL else "item", "values": values},
            }
            for dim, values in selections.items()
        ],
        "response": {"format": "json-stat2"},
    }


def fetch_table(
    session: requests.Session, base: str, table: str, selections: dict[str, list[str]]
) -> dict[str, Any]:
    resp = fetch(
        session, table_url(base, table), source=SOURCE, method="POST", json=build_query(selections)
    )
    return resp.json()  # type: ignore[no-any-return]


def _dense(obj: Any, n: int) -> list[Any]:
    """json-stat2 `value`/`status` may be an array, a sparse {index: v} object or a scalar."""
    if obj is None:
        return [None] * n
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return [obj.get(str(i)) for i in range(n)]
    return [obj] * n


def parse_jsonstat2(doc: dict[str, Any]) -> pd.DataFrame:
    """Long format: one row per cell; `<dim>` = code, `<dim>_label` = text."""
    dims: list[str] = doc["id"]
    cats = []
    for d in dims:
        cat = doc["dimension"][d]["category"]
        index = cat["index"]
        codes = sorted(index, key=lambda k: index[k]) if isinstance(index, dict) else list(index)
        cats.append([(c, cat.get("label", {}).get(c, c)) for c in codes])

    n = 1
    for size in doc["size"]:
        n *= size
    values, status = _dense(doc.get("value"), n), _dense(doc.get("status"), n)

    rows = []
    for i, combo in enumerate(itertools.product(*cats)):  # row-major, last dim fastest
        row: dict[str, Any] = {}
        for d, (code, label) in zip(dims, combo, strict=True):
            row[d], row[f"{d}_label"] = code, label
        row["value"], row["status"] = values[i], status[i]
        rows.append(row)
    df = pd.DataFrame(rows)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def to_records(cells: pd.DataFrame, level: str) -> pd.DataFrame:
    """Normalise to year, month, area, country, indicator, value. Year totals are dropped;
    unpublished or suppressed cells stay NaN (never 0) and are flagged `suppressed`."""
    area = next(d for d in _AREA_DIMS if d in cells.columns)
    df = cells[cells["Monat"] != "YYYY"]
    return pd.DataFrame({
        "year": df["Jahr"].astype(int),
        "month": df["Monat"].astype(int),
        "level": level,
        "area_code": df[area].astype(str),
        "area_name": df[f"{area}_label"],
        "herkunftsland": df["Herkunftsland_label"],
        "indicator": df["Indikator_label"].map(_INDICATORS),
        "value": df["value"],
        "suppressed": df["value"].isna(),
        "status": df["status"],
    }).reset_index(drop=True)  # fmt: skip


# --- history (US-02a) -------------------------------------------------------

LEVELS = {TABLE_GEMEINDE: "gemeinde", TABLE_REGION: "region"}
RECORD_COLUMNS = ["year", "month", "level", "area_code", "area_name", "herkunftsland",
                  "indicator", "value", "suppressed", "status"]  # fmt: skip


def fetch_history(
    session: requests.Session,
    base: str,
    table: str,
    months: list[str],
    *,
    pause: float = 1.0,
    sleep: Callable[[float], None] | None = None,
) -> pd.DataFrame:
    """Records (see `to_records`) for the given `YYYY-MM` months that the table contains.

    One query per month: a full year of _101 exceeds PxWeb's cell limit (HTTP 403).
    """
    meta = fetch_metadata(session, base, table)
    area = next(v["code"] for v in meta["variables"] if v["code"] in _AREA_DIMS)
    years, month_codes = set(dim_codes(meta, "Jahr")), set(dim_codes(meta, "Monat"))
    frames = []
    for ym in months:
        year, month = ym[:4], str(int(ym[5:]))
        if year not in years or month not in month_codes:
            continue
        selection = {"Jahr": [year], "Monat": [month], area: ALL, "Herkunftsland": ALL,
                     "Indikator": ALL}  # fmt: skip
        doc = fetch_table(session, base, table, selection)
        frames.append(to_records(parse_jsonstat2(doc), level=LEVELS.get(table, table)))
        (sleep or time.sleep)(pause)  # be polite to PxWeb
    if not frames:
        return pd.DataFrame(columns=RECORD_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def to_monthly_fact(records: pd.DataFrame) -> pd.DataFrame:
    """One row per year × month × area × country with `arrivals` and `nights` columns.

    `level` is left out (it is the hive partition key). Tables _101/_103 hold final
    figures, so `is_estimate` is False; HESTA-Flash (BR4) would set it.
    """
    keys = ["year", "month", "area_code", "area_name", "herkunftsland"]
    # unstack keeps NaN cells; pivot_table(dropna=False) would build the full cross product
    wide = records.set_index([*keys, "indicator"])["value"].unstack("indicator")
    wide = wide.reindex(columns=list(_INDICATORS.values())).reset_index()
    wide.columns.name = None
    suppressed = records.groupby(keys)["suppressed"].any().reset_index()
    out = wide.merge(suppressed, on=keys, how="left")
    out["is_estimate"] = False
    return out
