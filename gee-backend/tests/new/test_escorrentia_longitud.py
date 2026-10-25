"""GEO-2 regression: runoff ``longitud_m`` must be metres, not the step count.

``simular_escorrentia_impl`` reported ``longitud_m = len(coords)`` — one vertex
per D8 step (~one 30 m GLO-30 cell) — so a 150 km trace reported
``longitud_m = 5000``. The LineString the function already builds carries the
true length in the flow-direction raster's CRS units; the DEM pipeline writes
those rasters in UTM after ``reproject_to_utm``, so the units are metres.

The synthetic raster below is UTM-like with 30 m cells. The walk takes 5 D8
moves (3 east, 2 south-east); vertices after the start land on grid corners
(the transform's col/row anchor points), so the true LineString length is
30*sqrt(2)/2 + 30 + 30 + 2*30*sqrt(2) ≈ 166.07 m — decisively NOT the vertex
count. The pre-fix code fails every assertion here: it returned 6 for
``longitud_m`` and 6 for ``pasos`` (the starting vertex counted as a "step").
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from affine import Affine
from shapely.geometry import LineString

from app.domains.geo.intelligence.calculations_hydrology_support import (
    simular_escorrentia_impl,
)

_CELL = 30.0  # GLO-30 metres
# North-up UTM-like transform: metres, EPSG of the flow-dir raster.
_TRANSFORM = Affine(_CELL, 0.0, 500_000.0, 0.0, -_CELL, 7_000_000.0)

# Path: (2,1) -E-> (2,2) -E-> (2,3) -E-> (2,4) -SE-> (3,5) -SE-> (4,6); the
# final cell holds 0 (not a D8 code), so the walk stops there.
_MOVES = 5  # 3 * east + 2 * south-east
# Start vertex sits at the first cell's centre; each later vertex lands on the
# grid corner the transform computes, so segment lengths are:
# half-diagonal + 2 orthogonal + 2 full diagonals.
_EXPECTED_LENGTH_M = _CELL * math.sqrt(2) / 2 + 2 * _CELL + 2 * _CELL * math.sqrt(2)


class _Ctx:
    def __init__(self, obj: Any) -> None:
        self._obj = obj

    def __enter__(self) -> Any:
        return self._obj

    def __exit__(self, *exc: Any) -> bool:
        return False


class _FakeRasterio:
    """Serves the flow-dir and flow-acc arrays by path, like test_zonification_d8."""

    def __init__(self, fd: np.ndarray, fa: np.ndarray) -> None:
        self._fd = fd
        self._fa = fa

    def open(self, path: str, *_args: Any, **_kwargs: Any) -> _Ctx:
        arr = self._fd if "dir" in str(path) else self._fa
        return _Ctx(SimpleNamespace(read=lambda _band: arr, transform=_TRANSFORM, nodata=None))


def _run_trace() -> dict[str, Any]:
    fd = np.zeros((7, 7), dtype=np.int16)
    fd[2, 1], fd[2, 2], fd[2, 3] = 1, 1, 1  # east
    fd[2, 4], fd[3, 5] = 128, 128  # south-east
    fd[4, 6] = 0  # not a D8 code: the walk stops here
    fa = np.full((7, 7), 100.0, dtype=np.float32)
    # Start at the centre of cell (row=2, col=1).
    punto = (500_000.0 + 1.5 * _CELL, 7_000_000.0 - 2.5 * _CELL)
    return simular_escorrentia_impl(
        "/data/geo/area/output/flow_dir.tif",
        "/data/geo/area/output/flow_acc.tif",
        punto,
        50.0,
        max_steps=100,
        rasterio_module=_FakeRasterio(fd, fa),
        empty_geojson=lambda *_a: pytest.fail("the trace must not come back empty"),
    )


def test_longitud_m_is_true_length_not_vertex_count() -> None:
    props = _run_trace()["features"][0]["properties"]

    assert props["longitud_m"] == pytest.approx(_EXPECTED_LENGTH_M, abs=0.01)


def test_pasos_counts_d8_moves_not_vertices() -> None:
    props = _run_trace()["features"][0]["properties"]

    assert props["pasos"] == _MOVES


def test_longitud_m_matches_the_geometry_it_returns() -> None:
    """The number in the properties must equal the LineString's own length."""
    feature = _run_trace()["features"][0]
    line = LineString(feature["geometry"]["coordinates"])

    assert feature["properties"]["longitud_m"] == pytest.approx(line.length, abs=0.01)
