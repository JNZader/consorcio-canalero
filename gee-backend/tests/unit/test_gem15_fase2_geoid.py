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
    """Point-registered: los valores viven en CENTROS de celda, no en la
    esquina del transform (WARNING R3-geoid-halfcell-anchoring)."""

    def test_exact_at_grid_points_and_bilinear_between(self):
        values = numpy.array([[0.0, 2.0], [4.0, 6.0]])  # row 0 = top (y=top)
        # valores en (0.5,-0.5), (1.5,-0.5), (0.5,-1.5), (1.5,-1.5)
        out = mod.bilinear_sample(
            values,
            left=0.0,
            top=0.0,
            xres=1.0,
            yres=1.0,
            xs=numpy.array([0.5]),
            ys=numpy.array([-0.5]),
        )
        assert out[0] == pytest.approx(0.0)
        # equidistante de los 4 valores -> promedio
        out = mod.bilinear_sample(
            values,
            left=0.0,
            top=0.0,
            xres=1.0,
            yres=1.0,
            xs=numpy.array([1.0]),
            ys=numpy.array([-1.0]),
        )
        assert out[0] == pytest.approx(3.0)

    def test_half_cell_anchor_gradient_field(self):
        # con gradiente y punto INTERIOR: el anclaje point-registered pone el
        # primer valor en x=0.5; muestrear x=0.75 da 0.25 (fracción entre los
        # valores 0 y 1), no 0.75 como haría el anclaje a la esquina
        values = numpy.arange(16, dtype="float64").reshape(4, 4)
        out = mod.bilinear_sample(
            values,
            left=0.0,
            top=0.0,
            xres=1.0,
            yres=1.0,
            xs=numpy.array([0.75]),
            ys=numpy.array([-0.5]),
        )
        assert out[0] == pytest.approx(0.25)

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
        a real-grid probe on 2026-11-16). The egm08 fixture carries a COLUMN
        GRADIENT so a constant-field interpolation cannot mask a geometry
        mixup (WARNING R3-vacuous-geometry-regression)."""
        dem = _write_tif(
            tmp_path / "dem.tif",
            [[100.0, 100.0], [100.0, 100.0]],
            left=-64.0,
            top=-33.0,
            xres=0.001,
            yres=0.001,
        )
        # grillas LOCALES que cubren el DEM, con geometrías DISTINTAS entre sí
        # (resolución y borde diferentes, como las reales del CDN)
        # egm96-like: celdas de 0.5°, borde en -64.5/-32.5, undulación constante 21
        egm96 = _write_tif(
            tmp_path / "egm96.tif",
            numpy.full((4, 4), 21.0),
            left=-64.5,
            top=-32.5,
            xres=0.5,
            yres=0.5,
        )
        # egm08-like: celdas de 0.1°, borde en -64.35/-32.35, v(r,c) = 20 + 0.5*c
        egm08 = _write_tif(
            tmp_path / "egm08.tif",
            20.0 + 0.5 * numpy.tile(numpy.arange(7, dtype="float64"), (7, 1)),
            left=-64.35,
            top=-32.35,
            xres=0.1,
            yres=0.1,
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
        # esperado con aritmética directa (no vía la función): col CORRECTO =
        # geometría egm08 (~3.0); con el bug de geometría compartida el col
        # saldría de la transform egm96 (~0.5) y el resultado difiere >1 m.
        left08, res08 = -64.35, 0.1
        col_centers = numpy.array([-64.0 + 0.001 * (j + 0.5) for j in range(2)])
        expected_cols = (col_centers - left08) / res08 - 0.5
        expected = 100.0 + (21.0 - (20.0 + 0.5 * expected_cols))
        assert numpy.allclose(data, numpy.tile(expected, (2, 1)), atol=0.01)
        # no-vacuidad: el cálculo con la geometría equivocada da OTRO número
        buggy_cols = (col_centers + 64.5) / 0.5 - 0.5
        buggy = 100.0 + (21.0 - (20.0 + 0.5 * buggy_cols))
        assert not numpy.allclose(data, numpy.tile(buggy, (2, 1)), atol=0.01)

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
