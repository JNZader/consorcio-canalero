#!/usr/bin/env python3
"""Derive the rainfall-multi-parcel fixture geometry from the bundled catastro
GeoJSON. Mirrors the ``derive-catastro-fixture.mjs`` pattern: this is the
RUNNABLE measurement that pins the three parcel rings and the two cameras, so
the claim "real-derived, stable, non-overlapping" can be re-checked whenever
the catastro dataset is refreshed.

Run from the worktree root::

    python3 scripts/tests/fixtures/derive_rainfall_multi_parcel.py

Outputs the JSON the W2.1 fixture file embeds (without the synthetic rainfall
facts, which are added by hand from the design's controlled-facts table).
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEOJSON = (
    HERE.parent.parent.parent / "consorcio-web" / "public" / "data" / "catastro_rural_cu.geojson"
)

# ---------- geometry helpers (planar; good to <1% at this latitude) ----------
EARTH_LAT_M = 110_574.0
EARTH_LON_M = 111_320.0


def lon_lat_scale(lat: float) -> tuple[float, float]:
    return EARTH_LAT_M, EARTH_LON_M * math.cos(math.radians(lat))


def ring_area_m2(ring: list[list[float]]) -> float:
    """Shoelace area in m^2 (closed ring, lng-first coords)."""
    if len(ring) < 4:
        return 0.0
    lat0 = ring[0][1]
    return abs(ring_planar_area(ring, lat0))


def ring_planar_area(ring: list[list[float]], ref_lat: float) -> float:
    slat, slon = lon_lat_scale(ref_lat)
    acc = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i][0] * slon, ring[i][1] * slat
        x1, y1 = ring[i + 1][0] * slon, ring[i + 1][1] * slat
        acc += x0 * y1 - x1 * y0
    return acc / 2.0


def point_in_ring(point: tuple[float, float], ring: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon (closed ring)."""
    x, y = point
    inside = False
    n = len(ring) - 1
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        crosses = (yi > y) != (yj > y)
        if crosses and x < ((xj - xi) * (y - yi)) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def metres_to_boundary(point: tuple[float, float], ring: list[list[float]]) -> float:
    """Minimum distance from a point (lng, lat) to the ring, in metres."""
    slat, slon = lon_lat_scale(point[1])
    px, py = point[0] * slon, point[1] * slat
    min_d = math.inf
    for i in range(len(ring) - 1):
        ax, ay = ring[i][0] * slon, ring[i][1] * slat
        bx, by = ring[i + 1][0] * slon, ring[i + 1][1] * slat
        dx, dy = bx - ax, by - ay
        lsq = dx * dx + dy * dy
        t = 0.0 if lsq == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / lsq))
        qx, qy = ax + t * dx, ay + t * dy
        d = math.hypot(px - qx, py - qy)
        if d < min_d:
            min_d = d
    return min_d


def max_clearance_point(ring: list[list[float]]) -> tuple[float, float]:
    """A point INSIDE the ring maximizing the distance to the nearest edge
    (iterative farthest-point sampling over the ring vertices' Voronoi-ish
    neighbours). Cheaper than a full medial-axis: sample a grid of candidate
    points inside the bounding box and keep the inside one with max clearance.
    """
    xs = [c[0] for c in ring[:-1]]
    ys = [c[1] for c in ring[:-1]]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    best = (x0 + x1) / 2, (y0 + y1) / 2
    best_d = -1.0
    steps = 16
    for i in range(steps + 1):
        for j in range(steps + 1):
            cx = x0 + (x1 - x0) * i / steps
            cy = y0 + (y1 - y0) * j / steps
            if not point_in_ring((cx, cy), ring):
                continue
            d = metres_to_boundary((cx, cy), ring)
            if d > best_d:
                best_d = d
                best = (cx, cy)
    # Refine around the best candidate.
    span = max(x1 - x0, y1 - y0)
    for _ in range(3):
        x0r, x1r = best[0] - span / 8, best[0] + span / 8
        y0r, y1r = best[1] - span / 8, best[1] + span / 8
        for i in range(steps + 1):
            for j in range(steps + 1):
                cx = x0r + (x1r - x0r) * i / steps
                cy = y0r + (y1r - y0r) * j / steps
                if not point_in_ring((cx, cy), ring):
                    continue
                d = metres_to_boundary((cx, cy), ring)
                if d > best_d:
                    best_d = d
                    best = (cx, cy)
        span /= 4
    return best


def rings_overlap(ring_a: list[list[float]], ring_b: list[list[float]]) -> bool:
    """Cheap overlap check: any vertex of A inside B, or vice versa."""
    for c in ring_a[:-1]:
        if point_in_ring((c[0], c[1]), ring_b):
            return True
    for c in ring_b[:-1]:
        if point_in_ring((c[0], c[1]), ring_a):
            return True
    return False


def metres(p_a: tuple[float, float], p_b: tuple[float, float]) -> float:
    slat, slon = lon_lat_scale((p_a[1] + p_b[1]) / 2)
    return math.hypot((p_a[0] - p_b[0]) * slon, (p_a[1] - p_b[1]) * slat)


# ---------- camera projection sanity (Web Mercator, tile size 512) ----------
def meters_per_pixel(lat: float, zoom: int) -> float:
    return 156_543.03392 * math.cos(math.radians(lat)) / (2**zoom)


def visible_extent_m(viewport_px: int, lat: float, zoom: int) -> float:
    return viewport_px * meters_per_pixel(lat, zoom)


def main() -> int:
    coll = json.loads(GEOJSON.read_text(encoding="utf-8"))
    features = coll["features"]

    # (1) Single-ring polygons whose centroid-like max-clearance point is inside.
    candidates = []
    for f in features:
        geom = f.get("geometry") or {}
        if geom.get("type") != "Polygon":
            continue
        coords = geom.get("coordinates") or []
        if len(coords) != 1:
            continue
        ring = coords[0]
        if len(ring) < 4:
            continue
        ip = max_clearance_point(ring)
        if not point_in_ring(ip, ring):
            continue
        area = ring_area_m2(ring)
        if area < 50_000:  # < 5 ha: too small to be a safe click target
            continue
        clearance = metres_to_boundary(ip, ring)
        candidates.append(
            {
                "feature": f,
                "ring": ring,
                "interior": ip,
                "area_m2": area,
                "clearance_m": clearance,
            }
        )

    # (2) Find a cluster of three nearby, pairwise non-overlapping candidates
    # whose interior points all fit inside a ~2km box (one zoom-14 mobile frame).
    candidates.sort(key=lambda c: c["area_m2"])
    candidates = candidates[::-1]  # larger first

    target_span_m = 2_000.0
    chosen = None
    for i, a in enumerate(candidates):
        if a["clearance_m"] < 80:
            continue
        near = [
            b
            for b in candidates[i + 1 :]
            if metres(a["interior"], b["interior"]) <= target_span_m and b["clearance_m"] >= 80
        ]
        for j, b in enumerate(near):
            if rings_overlap(a["ring"], b["ring"]):
                continue
            for c in near[j + 1 :]:
                if rings_overlap(a["ring"], c["ring"]):
                    continue
                if rings_overlap(b["ring"], c["ring"]):
                    continue
                xs = [a["interior"][0], b["interior"][0], c["interior"][0]]
                ys = [a["interior"][1], b["interior"][1], c["interior"][1]]
                span_m = max(
                    (max(xs) - min(xs)) * EARTH_LON_M * math.cos(math.radians(sum(ys) / 3)),
                    (max(ys) - min(ys)) * EARTH_LAT_M,
                )
                if span_m > target_span_m:
                    continue
                chosen = (a, b, c)
                break
            if chosen:
                break
        if chosen:
            break

    if not chosen:
        print("No three-parcel cluster found.", file=sys.stderr)
        return 1

    a, b, c = chosen
    parcels = [a, b, c]
    # Order west -> east so A/B/C read left-to-right on the map.
    parcels.sort(key=lambda p: p["interior"][0])
    # Stable assignment A / B / C.

    # ---------- cameras: pick a zoom where all three parcels have >= 12 CSS px
    # edge clearance AND >= 6 CSS px radius clickable disks that don't overlap ----------
    center_lat = sum(p["interior"][1] for p in parcels) / 3
    center_lng = sum(p["interior"][0] for p in parcels) / 3

    def disk_radius_px(zoom: int) -> float:
        # min clearance / (m per px) gives the smaller of the two radii we can
        # safely use; the design requires >= 6 CSS px radius.
        mpp = meters_per_pixel(center_lat, zoom)
        return min(p["clearance_m"] for p in parcels) / mpp

    def edge_clearance_px(zoom: int) -> float:
        mpp = meters_per_pixel(center_lat, zoom)
        return min(p["clearance_m"] for p in parcels) / mpp

    def pairwise_disk_distance_px(zoom: int) -> float:
        mpp = meters_per_pixel(center_lat, zoom)
        dists = []
        for i in range(3):
            for j in range(i + 1, 3):
                dists.append(metres(parcels[i]["interior"], parcels[j]["interior"]) / mpp)
        return min(dists)

    # Mobile 390x844; the ficha sheet covers the bottom ~half, so usable width
    # is 390 and usable height is ~400. Desktop 1280x720 with no sheet.
    # A zoom works if disk_radius_px >= 6, edge_clearance_px >= 12, and
    # pairwise_disk_distance_px >= 2 * disk_radius_px + safety (say > 30).
    def fits(zoom: int, usable_w_px: int, usable_h_px: int) -> bool:
        if edge_clearance_px(zoom) < 14:
            return False
        r = disk_radius_px(zoom)
        if r < 6:
            return False
        if pairwise_disk_distance_px(zoom) < 2 * r + 24:
            return False
        # All three interior points must project INSIDE the usable rectangle.
        # The camera centres on (centre_lat, centre_lng); localhost Web Mercator
        # gives us a width/2 and height/2 in metres converted by meters_per_pixel.
        mpp = meters_per_pixel(center_lat, zoom)
        half_w_m = usable_w_px / 2 * mpp
        half_h_m = usable_h_px / 2 * mpp
        slat, slon = lon_lat_scale(center_lat)
        for p in parcels:
            dx_m = (p["interior"][0] - center_lng) * slon
            dy_m = (p["interior"][1] - center_lat) * slat
            if abs(dx_m) > half_w_m or abs(dy_m) > half_h_m:
                return False
        return True

    mobile_zoom = None
    for z in range(13, 18):
        if fits(z, 360, 380):  # mobile usable area, conservative
            mobile_zoom = z
            break
    desktop_zoom = None
    for z in range(12, 18):
        if fits(z, 1240, 700):
            desktop_zoom = z
            break

    if mobile_zoom is None or desktop_zoom is None:
        print(
            f"No camera fit found (mobile={mobile_zoom}, desktop={desktop_zoom}).",
            file=sys.stderr,
        )
        return 2

    # Geometry SHA-256 + provenance.
    def ring_digest(ring: list[list[float]]) -> str:
        return hashlib.sha256(
            json.dumps(ring, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

    out = {
        "center": {
            "lat": center_lat,
            "lng": center_lng,
            "zoom_mobile": mobile_zoom,
            "zoom_desktop": desktop_zoom,
        },
        "meters_per_pixel": {
            "mobile": meters_per_pixel(center_lat, mobile_zoom),
            "desktop": meters_per_pixel(center_lat, desktop_zoom),
        },
        "parcels": [
            {
                "alias": alias,
                "feature_id": str(
                    p["feature"].get("properties", {}).get("Nomenclatura") or p["feature"].get("id")
                ),
                "nomenclature": str(p["feature"]["properties"]["Nomenclatura"]),
                "interior_lng_lat": list(p["interior"]),
                "clearance_m": p["clearance_m"],
                "area_m2": p["area_m2"],
                "ring": p["ring"],
                "ring_sha256": ring_digest(p["ring"]),
            }
            for alias, p in zip(("A", "B", "C"), parcels)
        ],
        "checks": {
            "disk_radius_px_mobile": disk_radius_px(mobile_zoom),
            "edge_clearance_px_mobile": edge_clearance_px(mobile_zoom),
            "pairwise_disk_distance_px_mobile": pairwise_disk_distance_px(mobile_zoom),
            "disk_radius_px_desktop": disk_radius_px(desktop_zoom),
            "edge_clearance_px_desktop": edge_clearance_px(desktop_zoom),
            "pairwise_disk_distance_px_desktop": pairwise_disk_distance_px(desktop_zoom),
        },
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
