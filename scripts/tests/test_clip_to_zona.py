"""Tests for ``clip_to_zona``.

The WFS BBOX filter returns features whose envelope intersects the zona bbox —
this is an UPPER BOUND.  We tighten with real shapely intersection so only
features that ACTUALLY overlap the zona polygon remain.  Features fully outside
the zona are dropped; features crossing the boundary are clipped.
"""

from __future__ import annotations

from shapely.geometry import shape

from scripts.etl_pilar_verde.clip import clip_to_zona


def _feature(coords: list[list[float]], **props) -> dict:
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": [coords]},
    }


ZONA = _feature(
    [
        [-62.7, -32.6],
        [-62.3, -32.6],
        [-62.3, -32.4],
        [-62.7, -32.4],
        [-62.7, -32.6],
    ]
)


INSIDE = _feature(
    [
        [-62.55, -32.55],
        [-62.50, -32.55],
        [-62.50, -32.50],
        [-62.55, -32.50],
        [-62.55, -32.55],
    ],
    id="inside",
)

OUTSIDE = _feature(
    [
        [-63.10, -33.10],
        [-63.00, -33.10],
        [-63.00, -33.00],
        [-63.10, -33.00],
        [-63.10, -33.10],
    ],
    id="outside",
)

# Crosses eastern boundary of zona (x=-62.3)
CROSSING = _feature(
    [
        [-62.35, -32.50],
        [-62.20, -32.50],
        [-62.20, -32.45],
        [-62.35, -32.45],
        [-62.35, -32.50],
    ],
    id="crossing",
)


class TestClipToZona:
    def test_feature_fully_inside_is_kept_unchanged(self):
        result = clip_to_zona([INSIDE], zona_polygon_feature=ZONA)
        assert len(result) == 1
        assert result[0]["properties"]["id"] == "inside"

    def test_feature_fully_outside_is_dropped(self):
        result = clip_to_zona([OUTSIDE], zona_polygon_feature=ZONA)
        assert result == []

    def test_feature_crossing_boundary_is_clipped(self):
        result = clip_to_zona([CROSSING], zona_polygon_feature=ZONA)
        assert len(result) == 1
        clipped_geom = shape(result[0]["geometry"])
        zona_geom = shape(ZONA["geometry"])
        # The clipped feature must be fully contained in the zona polygon.
        assert zona_geom.buffer(1e-9).contains(clipped_geom)
        # And its area must be smaller than the original.
        original_geom = shape(CROSSING["geometry"])
        assert clipped_geom.area < original_geom.area

    def test_properties_are_preserved(self):
        result = clip_to_zona([INSIDE], zona_polygon_feature=ZONA)
        assert result[0]["properties"] == {"id": "inside"}

    def test_empty_input_returns_empty(self):
        result = clip_to_zona([], zona_polygon_feature=ZONA)
        assert result == []

    def test_mixed_batch_returns_only_intersecting(self):
        result = clip_to_zona(
            [INSIDE, OUTSIDE, CROSSING],
            zona_polygon_feature=ZONA,
        )
        ids = {f["properties"]["id"] for f in result}
        assert ids == {"inside", "crossing"}
