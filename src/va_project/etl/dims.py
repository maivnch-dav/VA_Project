"""Dimension tables linking the three sources (US-03).

- `dim_gemeinde`: BFS municipality → canton, tourism region (BFS STREG2022 = HESTA _103
  codes), whether HESTA _101 publishes it (else use the region, SYSTEM-DESIGN §9).
- `dim_smn_station`: SwissMetNet stations with altitude and which parameters they measure.
- `dim_station`: every service point (key = 7-digit BPUIC, the key of both delay sources)
  → municipality, region, nearest weather station and nearest station with snow depth
  (haversine, AC2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd

from va_project.etl.link import SWISS_UIC_PREFIX, nearest_points

LAKE_BFS_MIN = 9000  # BFS codes ≥ 9000 are lakes (e.g. 9329 Bodensee), not municipalities

StationStatus = Literal["linked", "lake", "outdated_bfs", "no_bfs", "foreign", "unknown"]


def build_dim_gemeinde(
    levels: pd.DataFrame, region_names: dict[str, str], hesta_codes: set[int], now: datetime
) -> pd.DataFrame:
    out = levels.copy()
    out["tourism_region"] = out["tourism_region_code"].map(region_names)
    out["in_hesta_101"] = out["bfs_nr"].isin(list(hesta_codes))
    out["ingested_at"] = now
    return out[["bfs_nr", "name", "kanton", "tourism_region_code", "tourism_region",
                "in_hesta_101", "ingested_at"]]  # fmt: skip


def build_dim_smn_station(meta: pd.DataFrame, caps: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """`caps`: station, has_temp, has_precip, has_snow — from the loaded readings."""
    out = meta.merge(caps, on="station", how="left")
    for col in ("has_temp", "has_precip", "has_snow"):
        out[col] = out[col].astype("boolean").fillna(False).astype(bool)
    out["ingested_at"] = now
    return out


def _status(sp: pd.DataFrame, gemeinde_codes: set[int]) -> pd.Series:
    country = sp["country"]
    bfs = sp["bfs_nr"]
    swiss_number = sp["number"].astype(str).str.startswith(SWISS_UIC_PREFIX)
    conditions = [
        (country == "CH") & bfs.isin(list(gemeinde_codes)).fillna(False),
        (country == "CH") & (bfs >= LAKE_BFS_MIN).fillna(False),
        (country == "CH") & bfs.notna(),
        country == "CH",
        country.notna() | ~swiss_number,
    ]
    choices = ["linked", "lake", "outdated_bfs", "no_bfs", "foreign"]
    return pd.Series(np.select(conditions, choices, "unknown"), index=sp.index)


def _nearest(stops: pd.DataFrame, smn: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """`<prefix>`, `<prefix>_dist_km`, altitude of the nearest station in `smn`."""
    out = pd.DataFrame(index=stops.index, columns=[prefix, f"{prefix}_dist_km", "_alt"])
    has_xy = stops["lat"].notna() & stops["lon"].notna()
    cand = smn.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    if cand.empty or not has_xy.any():
        return out
    xy = stops.loc[has_xy]
    idx, km = nearest_points(xy["lat"].to_numpy(), xy["lon"].to_numpy(), cand)
    out.loc[has_xy, prefix] = cand["station"].to_numpy()[idx]
    out.loc[has_xy, f"{prefix}_dist_km"] = km
    out.loc[has_xy, "_alt"] = cand["altitude_m"].to_numpy()[idx]
    return out


def build_dim_station(
    service_points: pd.DataFrame, gemeinden: pd.DataFrame, smn: pd.DataFrame, now: datetime
) -> pd.DataFrame:
    sp = service_points.dropna(subset=["number"]).drop_duplicates("number", keep="last")
    sp = sp.reset_index(drop=True)
    out = pd.DataFrame({
        "station_key": sp["number"].astype(str),
        "sloid": sp["sloid"],
        "name": sp["name"],
        "lat": sp["lat"],
        "lon": sp["lon"],
        "altitude_m": pd.to_numeric(sp["height_m"], errors="coerce"),
        "country": sp["country"],
        "link_status": _status(sp, set(gemeinden["bfs_nr"])),
    })  # fmt: skip
    linked = out["link_status"] == "linked"
    out["bfs_nr"] = sp["bfs_nr"].where(linked).astype("Int64")
    g = gemeinden.rename(columns={"name": "gemeinde"}).drop(columns="ingested_at")
    out = out.merge(g, on="bfs_nr", how="left")
    out["in_hesta_101"] = out["in_hesta_101"].astype("boolean").fillna(False).astype(bool)

    main = _nearest(out, smn[smn["has_temp"] & smn["has_precip"]], "smn_station")
    snow = _nearest(out, smn[smn["has_snow"]], "smn_snow_station")
    out["smn_station"] = main["smn_station"]
    out["smn_dist_km"] = main["smn_station_dist_km"].astype(float).round(3)  # metre precision
    out["smn_alt_diff_m"] = (out["altitude_m"] - main["_alt"].astype(float)).round(1)
    out["smn_snow_station"] = snow["smn_snow_station"]
    out["smn_snow_dist_km"] = snow["smn_snow_station_dist_km"].astype(float).round(3)
    out["ingested_at"] = now
    return out[["station_key", "sloid", "name", "lat", "lon", "altitude_m", "country",
                "link_status", "bfs_nr", "gemeinde", "kanton", "tourism_region_code",
                "tourism_region", "in_hesta_101", "smn_station", "smn_dist_km", "smn_alt_diff_m",
                "smn_snow_station", "smn_snow_dist_km", "ingested_at"]]  # fmt: skip


@dataclass(frozen=True)
class LinkSummary:
    n_stations: int
    station_rate: float  # AC1: stations with a BFS municipality (target ≥ 80 %)
    event_rate: float  # … weighted by stop events
    swiss_station_rate: float  # … excluding stations located abroad
    by_reason: dict[str, int] = field(default_factory=dict)


def unlinked_report(
    data_stations: pd.DataFrame, dim_station: pd.DataFrame
) -> tuple[pd.DataFrame, LinkSummary]:
    """`data_stations`: station_key, station_name, n (stop events in the delay aggregates)."""
    status = dim_station.set_index("station_key")["link_status"]
    df = data_stations.copy()
    df["reason"] = df["station_key"].map(status).fillna("not_in_service_points")
    linked = df["reason"] == "linked"
    swiss = df["reason"] != "foreign"
    report = df[~linked].sort_values(["n", "station_key"], ascending=[False, True])
    report = report.reset_index(drop=True)
    n = len(df)
    summary = LinkSummary(
        n_stations=n,
        station_rate=float(linked.mean()) if n else 0.0,
        event_rate=float(df.loc[linked, "n"].sum() / df["n"].sum()) if n else 0.0,
        swiss_station_rate=float(linked.sum() / swiss.sum()) if swiss.any() else 0.0,
        by_reason={str(k): int(v) for k, v in report["reason"].value_counts().sort_index().items()},
    )
    return report, summary
