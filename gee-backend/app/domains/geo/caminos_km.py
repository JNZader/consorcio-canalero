"""Unique-centerline kilometres for the coloured-roads legend.

``lzn`` is an IDECOR attribute and is sometimes the *whole route* copied onto
every piece. Totals ignore ``lzn``. Endpoints snap at 2 m in UTM 32720; edge
length is WGS84 haversine (same radius as Turf) along the original vertices.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, hypot, radians, sin, sqrt
from typing import Any, Iterable

SNAP_M = 2.0
_UTM = "EPSG:32720"
# @turf/helpers earthRadius — Medir uses the same sphere.
TURF_EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class UniqueEdge:
    ccn: str
    hct: str
    rst: str
    length_m: float


def _line_coords(geometry: dict[str, Any] | None) -> list[tuple[float, float]] | None:
    if not geometry or geometry.get("type") != "LineString":
        return None
    raw = geometry.get("coordinates") or []
    if len(raw) < 2:
        return None
    return [(float(point[0]), float(point[1])) for point in raw]


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = radians(a[0]), radians(a[1])
    lon2, lat2 = radians(b[0]), radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    chord = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * TURF_EARTH_RADIUS_M * atan2(sqrt(chord), sqrt(max(0.0, 1.0 - chord)))


def _geodesic_length_m(coords_ll: list[tuple[float, float]]) -> float:
    total = 0.0
    for index in range(1, len(coords_ll)):
        total += _haversine_m(coords_ll[index - 1], coords_ll[index])
    return total


def _metric_endpoints(coords_ll: list[tuple[float, float]]):
    import geopandas as gpd
    from shapely.geometry import LineString

    series = gpd.GeoSeries([LineString(coords_ll)], crs=4326).to_crs(_UTM)
    line = series.iloc[0]
    metric = list(line.coords)
    start = (float(metric[0][0]), float(metric[0][1]))
    end = (float(metric[-1][0]), float(metric[-1][1]))
    return start, end


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


def unique_network_edges(features: Iterable[dict[str, Any]]) -> list[UniqueEdge]:
    """One edge per snapped node pair; longest geometry wins."""
    pieces: list[tuple[str, str, str, float]] = []
    points: list[tuple[float, float]] = []
    for feature in features:
        props = feature.get("properties") or {}
        coords = _line_coords(feature.get("geometry"))
        if coords is None:
            continue
        length_m = _geodesic_length_m(coords)
        if length_m <= 0:
            continue
        try:
            start, end = _metric_endpoints(coords)
        except Exception:
            continue
        ccn = str(props.get("ccn") or "Sin consorcio")
        hct = str(props.get("hct") or "Desconocido")
        rst = str(props.get("rst") or "Desconocido")
        pieces.append((ccn, hct, rst, length_m))
        points.extend((start, end))
    if not pieces:
        return []
    cluster = _cluster(points)
    edges: dict[tuple[int, int], UniqueEdge] = {}
    for index, (ccn, hct, rst, length_m) in enumerate(pieces):
        a = cluster[index * 2]
        b = cluster[index * 2 + 1]
        if a == b:
            continue
        key = (a, b) if a < b else (b, a)
        current = edges.get(key)
        if current is None or length_m > current.length_m:
            edges[key] = UniqueEdge(ccn=ccn, hct=hct, rst=rst, length_m=length_m)
    return list(edges.values())


def deduped_network_km_by_ccn(features: Iterable[dict[str, Any]]) -> dict[str, float]:
    """Unique edge kilometres per consorcio, ignoring ``lzn``."""
    km: dict[str, float] = {}
    for edge in unique_network_edges(features):
        km[edge.ccn] = km.get(edge.ccn, 0.0) + edge.length_m / 1000.0
    return km
