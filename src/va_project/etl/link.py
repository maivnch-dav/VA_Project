"""Link keys between sources: GTFS stop_id → service point → BFS municipality."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

SLOID_PREFIX = "ch:1:sloid:"
SWISS_UIC_PREFIX = "85"
LinkStatus = Literal["linked", "foreign", "generated", "unknown"]


def station_key(stop_id: str) -> tuple[Literal["sloid", "number"], str] | None:
    """Station-level key of a GTFS stop_id.

    `ch:1:sloid:9000:0:3` → ("sloid", "ch:1:sloid:9000")  (platform/quay stripped)
    `8509000` / `8509000:0:7` → ("number", "8509000")
    """
    s = stop_id.strip()
    if s.startswith(SLOID_PREFIX):
        parts = s.split(":")
        return ("sloid", ":".join(parts[:4])) if len(parts) > 3 and parts[3] else None
    head = s.split(":")[0]
    return ("number", head) if head.isdigit() else None


def live_station_keys(stop_ids: Iterable[str], service_points: pd.DataFrame | None) -> pd.DataFrame:
    """GTFS-RT stop_id → the station key of the history (7-digit BPUIC), name, foreign flag.

    SLOIDs are mapped to their number via service points; a SLOID without a match keeps its
    station-level SLOID (resolved in US-03). 9-digit stop positions are cut to the station.
    """
    by_sloid: dict[str, str] = {}
    names: dict[str, str] = {}
    if service_points is not None:
        sp = service_points.dropna(subset=["number"])
        if "sloid" in sp.columns:
            by_sloid = {str(k): str(v) for k, v in zip(sp["sloid"], sp["number"], strict=True)
                        if pd.notna(k)}  # fmt: skip
        if "name" in sp.columns:
            names = {str(k): str(v) for k, v in zip(sp["number"], sp["name"], strict=True)
                     if pd.notna(v)}  # fmt: skip

    rows = []
    for sid in dict.fromkeys(stop_ids):
        key = station_key(sid)
        if key is None:
            station = sid.strip()
        elif key[0] == "sloid":
            station = by_sloid.get(key[1], key[1])
        else:
            station = key[1]
        if len(station) == 9 and station.isdigit():
            station = station[:7]  # stop position (BPUIC + 2 digits) → station
        foreign = station.isdigit() and not station.startswith(SWISS_UIC_PREFIX)
        rows.append({"stop_id": sid, "station_key": station, "station_name": names.get(station),
                     "foreign_stop": foreign})  # fmt: skip
    return pd.DataFrame(rows, columns=["stop_id", "station_key", "station_name", "foreign_stop"])


def link_stops(stop_ids: pd.Series, service_points: pd.DataFrame) -> pd.DataFrame:
    """Per stop_id: bfs_nr, kanton and why it did (not) link."""
    records = [{str(k): v for k, v in r.items()} for r in service_points.to_dict("records")]
    lookup: dict[str, dict[str, dict[str, Any]]] = {
        "sloid": {str(r["sloid"]): r for r in records if r.get("sloid")},
        "number": {str(r["number"]): r for r in records if r.get("number")},
    }
    cache: dict[str, dict[str, object]] = {}

    def resolve(stop_id: str) -> dict[str, object]:
        key = station_key(stop_id)
        row = lookup[key[0]].get(key[1]) if key is not None else None
        status: LinkStatus
        if row is not None and row.get("country") == "CH" and pd.notna(row.get("bfs_nr")):
            status = "linked"
        elif row is not None and row.get("country") not in ("CH", None):
            status = "foreign"
        elif "_gen" in stop_id:
            status = "generated"
        elif key is not None and key[0] == "number" and not key[1].startswith(SWISS_UIC_PREFIX):
            status = "foreign"
        else:
            status = "unknown"
        linked = row if status == "linked" else None
        return {
            "bfs_nr": linked["bfs_nr"] if linked else None,
            "kanton": linked.get("kanton") if linked else None,
            "link_status": status,
        }

    rows = []
    for sid in stop_ids.astype(str):
        if sid not in cache:
            cache[sid] = resolve(sid)
        rows.append({"stop_id": sid, **cache[sid]})
    out = pd.DataFrame(rows, columns=["stop_id", "bfs_nr", "kanton", "link_status"])
    out["bfs_nr"] = pd.array(out["bfs_nr"].tolist(), dtype="Int64")
    return out


@dataclass(frozen=True)
class LinkRates:
    n_events: int
    n_stops: int
    stop_rate: float  # (a) distinct stops → municipality          target ≥ 80 %
    event_rate: float  #     stop events → municipality
    swiss_event_rate: float  #     … excluding foreign/generated stops
    hesta_event_share: float  # (b) linked events in a HESTA municipality  (reported)
    unlinked_by_reason: dict[str, int] = field(default_factory=dict)


def _share(num: int, den: int) -> float:
    return num / den if den else 0.0


def link_rates(linked: pd.DataFrame, hesta_bfs: set[int]) -> LinkRates:
    ok = linked["link_status"] == "linked"
    swiss = ~linked["link_status"].isin(["foreign", "generated"])
    stops = linked.drop_duplicates("stop_id")
    in_hesta = linked.loc[ok, "bfs_nr"].isin(list(hesta_bfs))
    reasons = linked.loc[~ok, "link_status"].value_counts()
    return LinkRates(
        n_events=len(linked),
        n_stops=len(stops),
        stop_rate=_share(int((stops["link_status"] == "linked").sum()), len(stops)),
        event_rate=_share(int(ok.sum()), len(linked)),
        swiss_event_rate=_share(int(ok.sum()), int(swiss.sum())),
        hesta_event_share=_share(int(in_hesta.sum()), int(ok.sum())),
        unlinked_by_reason={str(k): int(v) for k, v in reasons.items()},
    )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def nearest_point(lat: float, lon: float, points: pd.DataFrame) -> tuple[pd.Series, float]:
    """Nearest row of `points` (needs lat/lon columns) and its distance in km."""
    pts = points.dropna(subset=["lat", "lon"])
    if pts.empty:
        raise ValueError("no points with coordinates")
    p1, p2 = np.radians(lat), np.radians(pts["lat"].to_numpy())
    dl = np.radians(pts["lon"].to_numpy() - lon)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    km = 2 * 6371.0 * np.arcsin(np.sqrt(a))
    i = int(np.argmin(km))
    return pts.iloc[i], float(km[i])


def nearest_points(
    lat: np.ndarray, lon: np.ndarray, points: pd.DataFrame, chunk: int = 5000
) -> tuple[np.ndarray, np.ndarray]:
    """For each (lat, lon): position in `points` of the nearest point, and the haversine km.

    Rows are processed in chunks so 60 k stops × 160 stations stays small in memory.
    """
    if points.empty:
        raise ValueError("no points to choose from")
    p_lat = np.radians(points["lat"].to_numpy(dtype=float))[None, :]
    p_lon = np.radians(points["lon"].to_numpy(dtype=float))[None, :]
    idx = np.empty(len(lat), dtype=np.int64)
    km = np.empty(len(lat), dtype=float)
    for start in range(0, len(lat), chunk):
        la = np.radians(np.asarray(lat[start : start + chunk], dtype=float))[:, None]
        lo = np.radians(np.asarray(lon[start : start + chunk], dtype=float))[:, None]
        a = (
            np.sin((p_lat - la) / 2) ** 2
            + np.cos(la) * np.cos(p_lat) * np.sin((p_lon - lo) / 2) ** 2
        )
        dist = 2 * 6371.0 * np.arcsin(np.sqrt(a))
        best = np.argmin(dist, axis=1)
        idx[start : start + chunk] = best
        km[start : start + chunk] = dist[np.arange(len(best)), best]
    return idx, km
