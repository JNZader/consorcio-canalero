"""Unique-centerline km for coloured roads — geometry, not Σ lzn."""

from __future__ import annotations

from app.domains.geo.caminos_km import deduped_network_km_by_ccn
from app.domains.geo.gee_service_analytics_support import build_colored_roads


def _feat(ccn: str, lzn: float, coords: list[list[float]], *, ccc: str = "CC") -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {"ccn": ccn, "ccc": ccc, "lzn": lzn},
    }


def test_duplicate_same_endpoints_count_once() -> None:
    coords = [[-62.50, -32.55], [-62.49, -32.55]]
    features = [
        _feat("C.C. 269", 10.0, coords),
        _feat("C.C. 269", 10.0, coords),
    ]
    km = deduped_network_km_by_ccn(features)
    assert km["C.C. 269"] < 2.0
    assert km["C.C. 269"] > 0.7
    payload = build_colored_roads(features, colors=["#f00"], safe_float=float)
    assert payload["consorcios"][0]["tramos"] == 2
    assert payload["metadata"]["total_km"] == payload["consorcios"][0]["longitud_km"]
    assert payload["metadata"]["total_km"] == round(km["C.C. 269"], 2)


def test_chain_sums_geometry_not_copied_route_lzn() -> None:
    """T269-03 style: three touching pieces, each carrying the whole-route lzn."""
    a = [[-62.50, -32.58], [-62.50, -32.57]]
    b = [[-62.50, -32.57], [-62.50, -32.56]]
    c = [[-62.50, -32.56], [-62.50, -32.55]]
    features = [
        _feat("C.C. 269", 16.0, a),
        _feat("C.C. 269", 16.0, b),
        _feat("C.C. 269", 16.0, c),
    ]
    km = deduped_network_km_by_ccn(features)
    # ~3 × 1.11 km of latitude, not 48 km of copied lzn.
    assert 2.5 < km["C.C. 269"] < 4.0
    payload = build_colored_roads(features, colors=["#0f0"], safe_float=float)
    assert payload["metadata"]["total_km"] != 48.0
    assert payload["consorcios"][0]["longitud_km"] == round(km["C.C. 269"], 2)
