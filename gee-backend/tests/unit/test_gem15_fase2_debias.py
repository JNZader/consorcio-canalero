"""Unit contracts for the fase 2 regional debias (issue #723, S2).

"debias: offset regional ajustado contra GLO-30 sobre terreno estable". The
offset must be MEASURED on stable terrain, not assumed: median of
(GEM-15@EGM2008 - GLO-30) over cells whose 3x3 focal range is below a
threshold, so canals/embankments/alcantarillas cannot drag it. The offset then
aligns GEM-15 vertically to GLO-30 before the hydrology comparison (T4).
"""

from __future__ import annotations

import numpy
import pytest
import rasterio

mod = pytest.importorskip("app.domains.geo.etl.gem15_fase2_debias")


def _write_tif(path, values, *, xres=0.001, yres=0.001, nodata=None):
    values = numpy.asarray(values, dtype="float32")
    height, width = values.shape
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 1,
        "dtype": "float32",
        "transform": rasterio.Affine(xres, 0, -64.0, 0, -yres, -33.0),
        "crs": "EPSG:4326",
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(values, 1)
    return str(path)


class TestStableMask:
    def test_flat_interior_is_stable_edges_and_bumps_are_not(self):
        dem = numpy.zeros((10, 10))
        dem[5, 5] = 30.0  # an embankment-scale bump
        mask = mod.stable_mask(dem, window_range_m=2.0)
        # a perfectly flat cell far from the bump and the raster edge
        assert mask[1, 1]
        # the bump itself and its 3x3 neighbourhood are unstable
        assert not mask[5, 5]
        assert not mask[4, 4]
        # the outermost ring cannot be evaluated -> unstable
        assert not mask[0, 0]
        assert not mask[9, 9]

    def test_nodata_cells_are_never_stable(self):
        dem = numpy.zeros((10, 10))
        dem[2, 2] = -9999.0
        mask = mod.stable_mask(dem, window_range_m=2.0, nodata=-9999.0)
        assert not mask[2, 2]


class TestComputeDebiasOffset:
    def test_measures_median_difference_on_stable_terrain_only(self, tmp_path):
        base = numpy.full((12, 12), 100.0)
        glo30 = base.copy()
        gem15 = base + 1.5  # the true regional offset to recover
        # unstable noise: a 40 m bump whose difference would drag a mean
        glo30[6, 6] += 40.0
        gem15[6, 6] += 40.0 + 25.0
        glo = _write_tif(tmp_path / "glo.tif", glo30)
        gem = _write_tif(tmp_path / "gem.tif", gem15)
        report = mod.compute_debias_offset_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            glo30_path=glo,
            gem15_path=gem,
            window_range_m=2.0,
            min_stable_cells=50,
        )
        assert report["offset_m"] == pytest.approx(1.5, abs=0.01)
        assert report["stable_cells"] > 0
        assert report["stable_fraction"] < 1.0
        # medidor de robustez reportado para el doc
        assert "mad_m" in report

    def test_fails_loudly_when_almost_nothing_is_stable(self, tmp_path):
        rng = numpy.random.default_rng(7)
        glo30 = rng.uniform(0, 50, size=(12, 12))
        gem15 = rng.uniform(0, 50, size=(12, 12))
        glo = _write_tif(tmp_path / "glo.tif", glo30)
        gem = _write_tif(tmp_path / "gem.tif", gem15)
        with pytest.raises(RuntimeError):
            mod.compute_debias_offset_impl(
                rasterio_module=rasterio,
                numpy_module=numpy,
                glo30_path=glo,
                gem15_path=gem,
                window_range_m=0.5,
                min_stable_cells=50,
            )


class TestApplyDebias:
    def test_shifts_gem15_by_the_measured_offset(self, tmp_path):
        gem15 = numpy.full((10, 10), 101.5)
        gem = _write_tif(tmp_path / "gem.tif", gem15)
        out = str(tmp_path / "gem_debiased.tif")
        mod.apply_debias_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            gem15_path=gem,
            offset_m=1.5,
            output_path=out,
        )
        with rasterio.open(out) as src:
            data = src.read(1)
        assert numpy.allclose(data, 100.0)

    def test_nodata_pixels_survive_the_shift(self, tmp_path):
        gem15 = numpy.full((10, 10), 101.5)
        gem15[3, 3] = -9999.0
        gem = _write_tif(tmp_path / "gem.tif", gem15, nodata=-9999.0)
        out = str(tmp_path / "gem_debiased.tif")
        mod.apply_debias_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            gem15_path=gem,
            offset_m=1.5,
            output_path=out,
        )
        with rasterio.open(out) as src:
            data = src.read(1)
            assert src.nodata == -9999.0
        assert data[3, 3] == -9999.0
        assert data[0, 0] == pytest.approx(100.0)


class TestShapeMismatch:
    def test_grids_of_different_shape_fail_loudly(self, tmp_path):
        glo = _write_tif(tmp_path / "glo.tif", numpy.zeros((10, 10)))
        gem = _write_tif(tmp_path / "gem.tif", numpy.zeros((10, 11)))
        with pytest.raises(RuntimeError, match="grillas distintas"):
            mod.compute_debias_offset_impl(
                rasterio_module=rasterio,
                numpy_module=numpy,
                glo30_path=glo,
                gem15_path=gem,
                min_stable_cells=1,
            )
