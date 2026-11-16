"""Unit contracts for the EGM96→EGM2008 datum conversion (issue #723, S2).

S2 forbids comparing raw heights across datums: the GEM-15 raster (EGM96
orthometric) must be moved to EGM2008 orthometric BEFORE any comparison with
GLO-30. H_egm2008 = H_egm96 + (N_egm96 - N_egm2008), with N sampled bilinearly
from the two PROJ CDN geoid grids. These tests use REAL rasterio/numpy with
synthetic tiny GeoTIFFs — the sampling math and the fail-closed grid fetch are
the parts that must never be faked.
"""

from __future__ import annotations

import hashlib

import numpy
import pytest
import rasterio

mod = pytest.importorskip("app.domains.geo.etl.gem15_fase2_geoid")


def _write_tif(
    path, values, *, left=0.0, top=0.0, xres=1.0, yres=1.0, dtype="float32", nodata=None
):
    values = numpy.asarray(values, dtype=dtype)
    height, width = values.shape
    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 1,
        "dtype": dtype,
        "transform": rasterio.Affine(xres, 0, left, 0, -yres, top),
        "crs": "EPSG:4326",
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(values, 1)
    return str(path)


class TestBilinearSample:
    def test_exact_at_cell_corners_and_bilinear_at_center(self):
        values = numpy.array([[0.0, 2.0], [4.0, 6.0]])  # row 0 = top (y=top)
        # cell centers: (0.5, -0.5) -> (0+2+4+6)/4 = 3.0
        out = mod.bilinear_sample(
            values,
            left=0.0,
            top=0.0,
            xres=1.0,
            yres=1.0,
            xs=numpy.array([0.5]),
            ys=numpy.array([-0.5]),
        )
        assert out[0] == pytest.approx(3.0)
        # exact at a grid point (0,0)
        out = mod.bilinear_sample(
            values,
            left=0.0,
            top=0.0,
            xres=1.0,
            yres=1.0,
            xs=numpy.array([0.0]),
            ys=numpy.array([0.0]),
        )
        assert out[0] == pytest.approx(0.0)

    def test_clamps_outside_bounds(self):
        values = numpy.array([[1.0, 1.0], [1.0, 1.0]])
        out = mod.bilinear_sample(
            values,
            left=0.0,
            top=0.0,
            xres=1.0,
            yres=1.0,
            xs=numpy.array([99.0]),
            ys=numpy.array([-99.0]),
        )
        assert out[0] == pytest.approx(1.0)


class TestApplyEgm96ToEgm2008:
    @pytest.fixture()
    def rasters(self, tmp_path):
        dem = _write_tif(
            tmp_path / "dem.tif",
            [[100.0, 100.0], [100.0, 100.0]],
            left=-64.0,
            top=-33.0,
            xres=0.001,
            yres=0.001,
        )
        egm96 = _write_tif(
            tmp_path / "egm96.tif",
            [[10.0, 10.0], [10.0, 10.0]],
            left=-180.0,
            top=90.0,
            xres=1.0,
            yres=1.0,
        )
        egm08 = _write_tif(
            tmp_path / "egm08.tif",
            [[9.0, 9.0], [9.0, 9.0]],
            left=-180.0,
            top=90.0,
            xres=1.0,
            yres=1.0,
        )
        return dem, egm96, egm08

    def test_adds_the_undulation_difference(self, tmp_path, rasters):
        dem, egm96, egm08 = rasters
        out = str(tmp_path / "dem_egm2008.tif")
        mod.apply_egm96_to_egm2008_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            dem_path=dem,
            egm96_grid_path=egm96,
            egm2008_grid_path=egm08,
            output_path=out,
        )
        with rasterio.open(out) as src:
            data = src.read(1)
        assert numpy.allclose(data, 101.0)  # 100 + (10 - 9)

    def test_each_grid_sampled_with_own_geometry(self, tmp_path):
        """Regression: the two CDN grids differ in resolution and edge. Sampling
        one with the other's geometry produced ~20 m offsets silently (caught by
        a real-grid probe on 2026-11-16, not by the equal-geometry tests)."""
        dem = _write_tif(
            tmp_path / "dem.tif",
            [[100.0, 100.0], [100.0, 100.0]],
            left=-64.0,
            top=-33.0,
            xres=0.001,
            yres=0.001,
        )
        # egm96-like: 0.25° cells, edge at -180.125
        egm96 = _write_tif(
            tmp_path / "egm96.tif",
            numpy.full((4, 4), 21.0),
            left=-180.125,
            top=90.125,
            xres=0.25,
            yres=0.25,
        )
        # egm08-like: ~0.0417° cells, DIFFERENT edge at -180.0208
        egm08 = _write_tif(
            tmp_path / "egm08.tif",
            numpy.full((40, 40), 20.0),
            left=-180.02083333333333,
            top=90.02083333333333,
            xres=0.041666666666666664,
            yres=0.041666666666666664,
        )
        out = str(tmp_path / "out.tif")
        mod.apply_egm96_to_egm2008_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            dem_path=dem,
            egm96_grid_path=egm96,
            egm2008_grid_path=egm08,
            output_path=out,
        )
        with rasterio.open(out) as src:
            data = src.read(1)
        # 100 + (21 - 20) = 101 everywhere; with the shared-geometry bug the
        # egm08 array indexed at the egm96 grid's coarser cells drifts instead.
        assert numpy.allclose(data, 101.0)

    def test_nodata_pixels_survive(self, tmp_path, rasters):
        dem, egm96, egm08 = rasters
        nodem = _write_tif(
            tmp_path / "dem_nodata.tif",
            [[100.0, -9999.0], [100.0, 100.0]],
            left=-64.0,
            top=-33.0,
            xres=0.001,
            yres=0.001,
            nodata=-9999.0,
        )
        out = str(tmp_path / "out_nodata.tif")
        mod.apply_egm96_to_egm2008_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            dem_path=nodem,
            egm96_grid_path=egm96,
            egm2008_grid_path=egm08,
            output_path=out,
        )
        with rasterio.open(out) as src:
            data = src.read(1)
            assert src.nodata == -9999.0
        assert data[0, 1] == -9999.0
        assert data[0, 0] == pytest.approx(101.0)


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        return iter([self._payload])


class FakeRequests:
    def __init__(self, payloads: dict[str, bytes]):
        self._payloads = payloads
        self.calls: list[str] = []

    def get(self, url, stream=True, timeout=300):
        self.calls.append(url)
        return FakeResponse(self._payloads[url])


class TestEnsureGeoidGrids:
    @pytest.fixture()
    def good_payloads(self):
        egm96 = b"\x00" * 32
        egm08 = b"\xff" * 64
        return {
            "https://cdn.proj.org/us_nga_egm96_15.tif": egm96,
            "https://cdn.proj.org/us_nga_egm08_25.tif": egm08,
        }

    def test_downloads_once_then_skips(self, tmp_path, good_payloads):
        requests = FakeRequests(good_payloads)
        checksums = {
            name: hashlib.sha256(good_payloads[url]).hexdigest()
            for name, url in [
                ("egm96", "https://cdn.proj.org/us_nga_egm96_15.tif"),
                ("egm2008", "https://cdn.proj.org/us_nga_egm08_25.tif"),
            ]
        }
        paths = mod.ensure_geoid_grids_impl(
            requests_module=requests,
            hashlib_module=hashlib,
            grids_dir=str(tmp_path),
            checksums=checksums,
        )
        assert len(requests.calls) == 2
        assert all(p.exists() for p in paths.values())
        second = mod.ensure_geoid_grids_impl(
            requests_module=requests,
            hashlib_module=hashlib,
            grids_dir=str(tmp_path),
            checksums=checksums,
        )
        assert len(requests.calls) == 2  # cache hit, no re-download

    def test_corrupt_download_fails_closed_and_cleans(self, tmp_path, good_payloads):
        bad = dict(good_payloads)
        bad["https://cdn.proj.org/us_nga_egm96_15.tif"] = b"tampered"
        requests = FakeRequests(bad)
        checksums = {
            name: hashlib.sha256(good_payloads[url]).hexdigest()
            for name, url in [
                ("egm96", "https://cdn.proj.org/us_nga_egm96_15.tif"),
                ("egm2008", "https://cdn.proj.org/us_nga_egm08_25.tif"),
            ]
        }
        with pytest.raises(RuntimeError):
            mod.ensure_geoid_grids_impl(
                requests_module=requests,
                hashlib_module=hashlib,
                grids_dir=str(tmp_path),
                checksums=checksums,
            )
        leftovers = list(tmp_path.iterdir())
        assert leftovers == []  # neither the .tmp nor a bad grid survives
