"""Canton outlines (swissBOUNDARIES3D via the geo.admin.ch API) for the canton map on `/`.

One request per canton (BFS canton number = feature id), WGS84 (`sr=4326`). The full outlines
are ~0.5 MB per canton; they are simplified with Douglas–Peucker (pure Python, no shapely) to
~250 m, which is invisible at country zoom and keeps the GeoJSON small for the browser.
Shared borders are simplified per canton, so tiny slivers between cantons are possible.

Each feature gets `id` = canton abbreviation and an interior point (`lon`, `lat`) for the
bubble: the area centroid, moved inside the polygon when it falls outside or into a hole
(e.g. St. Gallen around Appenzell).
"""

from __future__ import annotations

import json
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any, TextIO

import requests

from va_project.collectors.bfs_communes import CANTON_ABBR
from va_project.collectors.http import fetch

SOURCE = "swisstopo_cantons"
TOLERANCE_DEG = 0.0025  # ≈ 190 m east-west / 280 m north-south at 47° N
DIGITS = 4  # ≈ 10 m

Point = list[float]
Ring = list[Point]
Polygon = list[Ring]  # outer ring first, then holes


def _seg_dist2(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return (p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2


def _douglas_peucker(points: Ring, tolerance: float) -> Ring:
    """Iterative (an explicit stack) so 24 000-point outlines do not hit the recursion limit."""
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    tol2 = tolerance * tolerance
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        best, idx = 0.0, -1
        for i in range(first + 1, last):
            d = _seg_dist2(points[i], points[first], points[last])
            if d > best:
                best, idx = d, i
        if idx >= 0 and best > tol2:
            keep[idx] = True
            stack += [(first, idx), (idx, last)]
    return [p for p, k in zip(points, keep, strict=True) if k]


def simplify_ring(ring: Ring, tolerance: float) -> Ring | None:
    """Simplified closed ring, or None when it collapses (smaller than the tolerance)."""
    if len(ring) < 4:
        return None
    # split at the point farthest from the start so a closed ring has two distinct ends
    far = max(range(len(ring)), key=lambda i: _seg_dist2(ring[i], ring[0], ring[0]))
    if far == 0:
        return None
    head = _douglas_peucker(ring[: far + 1], tolerance)
    tail = _douglas_peucker(ring[far:], tolerance)
    out = [[round(x, DIGITS), round(y, DIGITS)] for x, y in head[:-1] + tail]
    out[-1] = out[0]
    return out if len({tuple(p) for p in out}) >= 3 else None


def _area_centroid(ring: Ring) -> tuple[float, float, float]:
    """(signed area, cx, cy) by the shoelace formula."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in pairwise(ring):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a /= 2
    return (a, cx / (6 * a), cy / (6 * a)) if a else (0.0, ring[0][0], ring[0][1])


def _in_ring(x: float, y: float, ring: Ring) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in pairwise(ring):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _in_polygon(x: float, y: float, poly: Polygon) -> bool:
    return _in_ring(x, y, poly[0]) and not any(_in_ring(x, y, h) for h in poly[1:])


def _scanline_point(poly: Polygon, y: float) -> tuple[float, float]:
    """Middle of the widest inside stretch of the horizontal line at `y`."""
    xs = sorted(
        x0 + (y - y0) * (x1 - x0) / (y1 - y0)
        for ring in poly
        for (x0, y0), (x1, y1) in pairwise(ring)
        if (y0 > y) != (y1 > y)
    )
    pairs = list(zip(xs[::2], xs[1::2], strict=False))
    if not pairs:
        return poly[0][0][0], poly[0][0][1]
    a, b = max(pairs, key=lambda p: p[1] - p[0])
    return (a + b) / 2, y


def interior_point(polygons: list[Polygon]) -> tuple[float, float]:
    """Bubble position: centroid of the largest part, moved inside if it is not."""
    poly = max(polygons, key=lambda p: abs(_area_centroid(p[0])[0]))
    parts = [_area_centroid(r) for r in poly]
    area = abs(parts[0][0]) - sum(abs(a) for a, _, _ in parts[1:])
    cx = (abs(parts[0][0]) * parts[0][1] - sum(abs(a) * x for a, x, _ in parts[1:])) / area
    cy = (abs(parts[0][0]) * parts[0][2] - sum(abs(a) * y for a, _, y in parts[1:])) / area
    if _in_polygon(cx, cy, poly):
        return round(cx, DIGITS), round(cy, DIGITS)
    x, y = _scanline_point(poly, cy)
    return round(x, DIGITS), round(y, DIGITS)


def to_feature(raw: dict[str, Any], tolerance: float = TOLERANCE_DEG) -> dict[str, Any]:
    """geo.admin.ch feature → simplified GeoJSON feature keyed by canton abbreviation."""
    geom, props = raw.get("geometry") or {}, raw.get("properties") or {}
    if "ak" not in props or geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"{SOURCE}: format changed — need properties.ak and a polygon geometry")
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    out: list[Polygon] = []
    for poly in polys:
        outer = simplify_ring(poly[0], tolerance)
        if outer is None:
            continue  # tiny exclave
        holes = [h for h in (simplify_ring(r, tolerance) for r in poly[1:]) if h is not None]
        out.append([outer, *holes])
    if not out:
        raise ValueError(f"{SOURCE}: canton {props['ak']} vanished after simplification")
    lon, lat = interior_point(out)
    return {
        "type": "Feature",
        "id": props["ak"],
        "properties": {"kanton": props["ak"], "name": props.get("name"), "lon": lon, "lat": lat},
        "geometry": {"type": "MultiPolygon", "coordinates": out},
    }


def fetch_canton(session: requests.Session, url: str, nr: int) -> dict[str, Any]:
    resp = fetch(session, f"{url}/{nr}", source=SOURCE, params={"geometryFormat": "geojson",
                                                                "sr": 4326})  # fmt: skip
    feature: dict[str, Any] = resp.json()["feature"]
    return feature


def build(session: requests.Session, url: str, out: Path) -> int:
    """Fetch, simplify and write all 26 cantons as one FeatureCollection; returns the count."""
    features = [to_feature(fetch_canton(session, url, nr)) for nr in sorted(CANTON_ABBR)]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    tmp.replace(out)
    return len(features)


def selbsttest(out: TextIO = sys.stdout) -> int:
    """Simplification and interior point on a synthetic ring — no network access."""
    square = [[x / 100, 0.0] for x in range(101)] + [[1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    hole = [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6], [0.4, 0.4]]
    ring = simplify_ring(square, 0.01)
    x, y = interior_point([[square, hole]])
    checks = {
        "collinear points removed": ring is not None and len(ring) == 5,
        "interior point not in hole": _in_polygon(x, y, [square, hole]),
    }
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}", file=out)
    return 0 if all(checks.values()) else 1
