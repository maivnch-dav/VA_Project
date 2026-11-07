"""MeteoSwiss SwissMetNet (Open Government Data) via the geo.admin STAC API."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
import requests

from va_project.collectors.http import fetch

SOURCE = "meteo_smn"

# Verified against ogd-smn_meta_parameters.csv (2026-09-29).
PARAMS: dict[str, str] = {
    "tre200s0": "temp_c",  # air temperature 2 m, current value, °C
    "rre150z0": "precip_mm",  # precipitation, 10-min sum, mm
    "htoauts0": "snow_depth_cm",  # snow depth (automatic), cm
    "sre000z0": "sunshine_min",  # sunshine duration, 10-min sum, min
    "fkl010z0": "wind_ms",  # scalar wind speed, 10-min mean, m/s (fu3010z0 would be km/h)
}


def parse_observations(raw: bytes) -> pd.DataFrame:
    """Parse a station CSV (`;`-separated, `dd.mm.yyyy HH:MM` in UTC)."""
    df = pd.read_csv(io.BytesIO(raw), sep=";", encoding="latin-1", dtype={"station_abbr": str})
    out = pd.DataFrame({
        "station": df["station_abbr"].str.strip(),
        "ts": pd.to_datetime(df["reference_timestamp"], format="%d.%m.%Y %H:%M", utc=True),
    })  # fmt: skip
    for code, name in PARAMS.items():
        col = df[code] if code in df.columns else pd.Series(float("nan"), index=df.index)
        out[name] = pd.to_numeric(col, errors="coerce").astype("float64")
    return out.sort_values("ts", ignore_index=True)


def fetch_station_item(session: requests.Session, stac_url: str, station: str) -> dict[str, Any]:
    resp = fetch(session, f"{stac_url}/items/{station.lower()}", source=SOURCE)
    return resp.json()  # type: ignore[no-any-return]


def station_location(item: dict[str, Any]) -> tuple[float, float]:
    """(lat, lon) from a STAC item (GeoJSON order is lon, lat)."""
    lon, lat = item["geometry"]["coordinates"][:2]
    return float(lat), float(lon)


def fetch_observations(
    session: requests.Session, stac_url: str, station: str, period: str = "now"
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """10-minute observations (`t` granularity). Returns (frame, STAC item)."""
    item = fetch_station_item(session, stac_url, station)
    s = station.lower()
    asset = item.get("assets", {}).get(f"ogd-smn_{s}_t_{period}.csv")
    if asset is None:
        raise LookupError(f"No 10-minute '{period}' asset for station {s} in STAC item")
    resp = fetch(session, asset["href"], source=SOURCE)
    return parse_observations(resp.content), item


# --- history (US-02a) -------------------------------------------------------


def _items(session: requests.Session, stac_url: str) -> list[dict[str, Any]]:
    """Every station item of the collection, following STAC pagination."""
    items: list[dict[str, Any]] = []
    url: str | None = f"{stac_url}/items"
    params: dict[str, Any] | None = {"limit": 100}
    while url:
        doc = fetch(session, url, source=SOURCE, params=params).json()
        items += doc.get("features", [])
        links = doc.get("links", [])
        url, params = next((lk["href"] for lk in links if lk.get("rel") == "next"), None), None
    return items


def list_stations(session: requests.Session, stac_url: str) -> pd.DataFrame:
    """All SwissMetNet stations (station, name, lat, lon), following STAC pagination."""
    rows = []
    for item in _items(session, stac_url):
        lat, lon = station_location(item)
        name = item.get("properties", {}).get("title")
        rows.append({"station": str(item["id"]).upper(), "name": name, "lat": lat, "lon": lon})
    return pd.DataFrame(rows, columns=["station", "name", "lat", "lon"])


def now_hrefs(session: requests.Session, stac_url: str) -> dict[str, str]:
    """Station → URL of its 10-minute `now` file (live collector: one listing per run)."""
    out = {}
    for item in _items(session, stac_url):
        s = str(item["id"]).lower()
        asset = item.get("assets", {}).get(f"ogd-smn_{s}_t_now.csv")
        if asset is not None:
            out[s.upper()] = str(asset["href"])
    return out


def history_asset(station: str, year: int, current_year: int) -> str:
    """Past years are in the decade file `historical_YYY0-YYY9`, this year in `recent`."""
    s = station.lower()
    if year >= current_year:
        return f"ogd-smn_{s}_t_recent.csv"
    decade = year // 10 * 10
    return f"ogd-smn_{s}_t_historical_{decade}-{decade + 9}.csv"


def fetch_history(
    session: requests.Session, stac_url: str, station: str, years: list[int], current_year: int
) -> dict[int, pd.DataFrame]:
    """10-minute observations per UTC year; each asset is downloaded at most once."""
    item = fetch_station_item(session, stac_url, station)
    assets = item.get("assets", {})
    cache: dict[str, pd.DataFrame] = {}

    def load(name: str) -> pd.DataFrame:
        if name not in cache:
            asset = assets.get(name)
            cache[name] = (
                parse_observations(
                    fetch(session, asset["href"], source=SOURCE, timeout=300).content
                )
                if asset is not None
                else parse_observations(b"station_abbr;reference_timestamp\r\n")
            )
        return cache[name]

    out = {}
    for year in years:
        names = [history_asset(station, year, current_year)]
        if year == current_year - 1:  # historical file may not have rolled over yet
            names.append(history_asset(station, current_year, current_year))
        df = pd.DataFrame()
        for name in names:
            obs = load(name)
            df = obs[obs["ts"].dt.year == year].reset_index(drop=True)
            if not df.empty:
                break
        out[year] = df
    return out


# --- station metadata (US-03) -------------------------------------------------

_META_COLUMNS = {
    "station_abbr": "station",
    "station_name": "name",
    "station_canton": "kanton",
    "station_coordinates_wgs84_lat": "lat",
    "station_coordinates_wgs84_lon": "lon",
    "station_height_masl": "altitude_m",
}


def fetch_meta_stations(session: requests.Session, url: str) -> bytes:
    return fetch(session, url, source=SOURCE).content


def parse_meta_stations(raw: bytes) -> pd.DataFrame:
    """`ogd-smn_meta_stations.csv` (`;`-separated, Windows-1252): coordinates and altitude."""
    df = pd.read_csv(io.BytesIO(raw), sep=";", encoding="cp1252", dtype=str)
    out = df[list(_META_COLUMNS)].rename(columns=_META_COLUMNS)
    out["station"] = out["station"].str.strip().str.upper()
    for col in ("lat", "lon"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["altitude_m"] = pd.to_numeric(out["altitude_m"], errors="coerce").round().astype("Int64")
    return out.reset_index(drop=True)
