"""Regression for the A7 "D8 blocker": watershed must get the flow_dir POINTER.

WBT ``watershed(d8_pntr, pour_pts, output)`` needs the D8 flow-direction pointer
as its first argument. The historical bug passed the DEM there
(``get_wbt().watershed(dem_path, ...)``), so ``watershed`` silently misread the
elevation raster as a pointer and every downstream catchment was wrong.

These tests drive ``generar_zonificacion_impl`` with fully mocked raster I/O and a
recording WBT stub, and assert the FIRST positional argument to ``watershed`` is
the ``flow_dir_path`` — never the ``dem_path``. Passing the DEM (the regression)
makes them fail.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.domains.geo.intelligence.calculations_hydrology_support import (
    generar_zonificacion_impl,
)

_DEM = "/data/geo/area/output/dem.tif"
_FLOW_ACC = "/data/geo/area/output/flow_acc.tif"
_FLOW_DIR = "/data/geo/area/output/flow_dir.tif"


class _Ctx:
    def __init__(self, obj: Any) -> None:
        self._obj = obj

    def __enter__(self) -> Any:
        return self._obj

    def __exit__(self, *exc: Any) -> bool:
        return False


class _FakeSrc:
    def __init__(self) -> None:
        # 2×2 flow-accumulation array; threshold below picks the bottom row.
        self._arr = np.array([[10, 20], [30, 40]], dtype=np.float32)
        self.meta = {"driver": "GTiff", "dtype": "float32", "count": 1, "nodata": None}
        self.nodata = None
        self.transform = "TRANSFORM"
        self.crs = "EPSG:32720"

    def read(self, _index: int) -> np.ndarray:
        return self._arr


class _FakeWriter:
    def write(self, _arr: np.ndarray, _index: int) -> None:
        pass


class _FakeRasterio:
    """Records the ``watershed`` output path so we can prove it is later read."""

    def open(self, path: str, mode: str = "r", **_profile: Any) -> _Ctx:
        if mode == "w":
            return _Ctx(_FakeWriter())
        return _Ctx(_FakeSrc())


class _FakeWbt:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def watershed(self, *args: Any) -> None:
        self.calls.append(args)


def _run() -> _FakeWbt:
    wbt = _FakeWbt()
    generar_zonificacion_impl(
        _DEM,
        _FLOW_ACC,
        _FLOW_DIR,
        threshold=25,
        get_wbt=lambda: wbt,
        build_empty_geojson=lambda _cols: object(),
        rasterio_module=_FakeRasterio(),
        shapes_fn=lambda *_a, **_k: [],  # no basins → early empty return
    )
    return wbt


def test_watershed_receives_flow_dir_pointer_not_dem() -> None:
    wbt = _run()

    assert wbt.calls, "watershed was never called"
    first_arg = wbt.calls[0][0]
    assert first_arg == _FLOW_DIR, (
        f"watershed arg 1 must be the flow_dir pointer, got {first_arg!r}"
    )
    assert first_arg != _DEM, "watershed arg 1 is the DEM — the D8 regression is back"


def test_dem_is_never_passed_to_watershed() -> None:
    wbt = _run()

    all_args = {arg for call in wbt.calls for arg in call}
    assert _DEM not in all_args, "the DEM leaked into a watershed argument"
    assert _FLOW_DIR in all_args, "the flow_dir pointer never reached watershed"
