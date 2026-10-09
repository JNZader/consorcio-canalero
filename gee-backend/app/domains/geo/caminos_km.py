"""Unique-centerline kilometres for the coloured-roads legend.

``lzn`` is an IDECOR attribute and is sometimes the *whole route* copied onto
every piece. Totals use projected geometry, with endpoints snapped at 2 m and
one edge kept per node pair (the longest), matching the elevation-profile graph.
"""

from __future__ import annotations

from math import hypot
from typing import Any, Iterable

SNAP_M = 2.0
_UTM = "EPSG:32720"


def _line_coords(geometry: dict[str, Any] | None) -> list[tuple[float, float]] | None:
    if not geometry or geometry.get("type") != "LineString":
        return None
    raw = geometry.get("coordinates") or []
    if len(raw) < 2:
        return None
    return [(float(point[0]), float(point[1])) for point in raw]


def _metric_line(coords_ll: list[tuple[float, float]]):
    import geopandas as gpd
    from shapely.geometry import LineString

    series = gpd.GeoSeries([LineString(coords_ll)], crs=4326).to_crs(_UTM)
    line = series.iloc[0]
    return list(line.coords), float(line.length)


def _cluster(points: list[tuple[float, float]]) -> list[int]:
    parent = list(range(len(points)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i, a in enumerate(points):
        for j in range(i + 1, len(points)):
            b = points[j]
            if hypot(a[0] - b[0], a[1] - b[1]) <= SNAP_M:
                parent[find(j)] = find(i)
    compact: dict[int, int] = {}
    next_id = 0
    labels: list[int] = []
    for index in range(len(points)):
        root = find(index)
        if root not in compact:
            compact[root] = next_id
            next_id += 1
        labels.append(compact[root])
    return labels


def deduped_network_km_by_ccn(features: Iterable[dict[str, Any]]) -> dict[str, float]:
    """Unique edge kilometres per consorcio, ignoring ``lzn``."""
    pieces: list[tuple[str, list[tuple[float, float]], float]] = []
    points: list[tuple[float, float]] = []
    for feature in features:
        props = feature.get("properties") or {}
        coords = _line_coords(feature.get("geometry"))
        if coords is None:
            continue
        metric, length_m = _metric_line(coords)
        if len(metric) < 2 or length_m <= 0:
            continue
        ccn = str(props.get("ccn") or "Sin consorcio")
        start = (float(metric[0][0]), float(metric[0][1]))
        end = (float(metric[-1][0]), float(metric[-1][1]))
        pieces.append((ccn, [start, end], length_m))
        points.extend((start, end))
    if not pieces:
        return {}
    cluster = _cluster(points)
    edges: dict[tuple[int, int], tuple[float, str]] = {}
    for index, (ccn, _ends, length_m) in enumerate(pieces):
        a = cluster[index * 2]
        b = cluster[index * 2 + 1]
        if a == b:
            continue
        key = (a, b) if a < b else (b, a)
        current = edges.get(key)
        if current is None or length_m > current[0]:
            edges[key] = (length_m, ccn)
    km: dict[str, float] = {}
    for length_m, ccn in edges.values():
        km[ccn] = km.get(ccn, 0.0) + length_m / 1000.0
    return km
