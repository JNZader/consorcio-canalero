"""Unit tests for app.domains.geo.processing — DEM/raster processing pipeline.

All rasterio, WhiteboxTools, and filesystem operations are mocked.
Tests verify orchestration logic, parameter passing, and error handling.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch, call

import numpy as np
import pytest

# Mock whitebox before importing processing module
if "whitebox" not in sys.modules:
    mock_wb = MagicMock()
    sys.modules["whitebox"] = mock_wb

from app.domains.geo.processing import (
    TERRAIN_CLASS_LABELS,
    TERRAIN_DRENAJE_NATURAL,
    TERRAIN_RIESGO_ALTO,
    TERRAIN_RIESGO_MEDIO,
    TERRAIN_SIN_RIESGO,
    _MIN_SLOPE_RAD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rasterio_ctx(
    data=None, nodata=None, transform=None, crs=None,
    width=10, height=10, meta=None, bounds=None, is_projected=False,
):
    """Create a mock rasterio dataset context manager."""
    if data is None:
        data = np.ones((height, width), dtype=np.float64)
    if transform is None:
        from unittest.mock import PropertyMock
        transform = MagicMock()
        transform.a = 0.001
        transform.e = -0.001
    if meta is None:
        meta = {"driver": "GTiff", "dtype": "float32", "width": width, "height": height}
    if bounds is None:
        bounds = MagicMock()
        bounds.left, bounds.right = -63.0, -62.0
        bounds.top, bounds.bottom = -32.0, -33.0

    src = MagicMock()
    src.read.return_value = data
    src.nodata = nodata
    src.transform = transform
    src.meta = MagicMock()
    src.meta.copy.return_value = meta.copy()
    src.profile = MagicMock()
    src.profile.copy.return_value = meta.copy()
    src.crs = crs
    src.width = width
    src.height = height
    src.bounds = bounds
    return src


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestTerrainConstants:
    def test_terrain_class_labels_has_five_entries(self):
        assert len(TERRAIN_CLASS_LABELS) == 5

    def test_class_codes_are_sequential(self):
        assert TERRAIN_SIN_RIESGO == 0
        assert TERRAIN_DRENAJE_NATURAL == 1
        assert TERRAIN_RIESGO_ALTO == 2
        assert TERRAIN_RIESGO_MEDIO == 3

    def test_min_slope_rad_is_small_positive(self):
        assert 0 < _MIN_SLOPE_RAD < 0.01


# ---------------------------------------------------------------------------
# ensure_nodata
# ---------------------------------------------------------------------------


class TestEnsureNodata:
    @patch("app.domains.geo.processing.rasterio")
    @patch("app.domains.geo.processing.shutil")
    @patch("app.domains.geo.processing.Path")
    def test_copies_file_when_nodata_already_set(self, mock_path, mock_shutil, mock_rio):
        from app.domains.geo.processing import ensure_nodata

        src = _make_rasterio_ctx(nodata=-32768.0)
        mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
        mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

        result = ensure_nodata("/in.tif", "/out.tif")

        assert result == "/out.tif"
        mock_shutil.copy2.assert_called_once_with("/in.tif", "/out.tif")

    @patch("app.domains.geo.processing.rasterio")
    @patch("app.domains.geo.processing.Path")
    def test_sets_nodata_when_missing(self, mock_path, mock_rio):
        from app.domains.geo.processing import ensure_nodata

        data = np.ones((5, 5), dtype=np.float64)
        src = _make_rasterio_ctx(data=data, nodata=None)

        mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
        mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_path.return_value.parent.mkdir = MagicMock()

        result = ensure_nodata("/in.tif", "/out.tif")

        assert result == "/out.tif"


# ---------------------------------------------------------------------------
# reproject_to_utm
# ---------------------------------------------------------------------------


class TestReprojectToUtm:
    @patch("app.domains.geo.processing.rasterio")
    @patch("app.domains.geo.processing.shutil")
    @patch("app.domains.geo.processing.Path")
    def test_copies_when_already_projected(self, mock_path, mock_shutil, mock_rio):
        from app.domains.geo.processing import reproject_to_utm

        crs = MagicMock()
        crs.is_projected = True
        src = _make_rasterio_ctx(crs=crs)

        mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
        mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

        result = reproject_to_utm("/in.tif", "/out.tif")

        assert result == "/out.tif"
        mock_shutil.copy2.assert_called_once()

    def test_utm_zone_calculation_northern_hemisphere(self):
        # lon=15 → zone = int((15+180)/6)+1 = 33
        zone = int((15 + 180) / 6) + 1
        epsg = 32600 + zone  # Northern hemisphere
        assert epsg == 32633

    def test_utm_zone_calculation_southern_hemisphere(self):
        # lon=-62.5, lat=-32.5 → zone = int((-62.5+180)/6)+1 = 20
        zone = int((-62.5 + 180) / 6) + 1
        epsg = 32700 + zone  # Southern hemisphere
        assert epsg == 32720


# ---------------------------------------------------------------------------
# clip_dem
# ---------------------------------------------------------------------------


class TestClipDem:
    @patch("app.domains.geo.processing.rasterio")
    @patch("app.domains.geo.processing.rasterio_mask")
    @patch("app.domains.geo.processing.Path")
    def test_returns_output_path(self, mock_path, mock_mask, mock_rio):
        from app.domains.geo.processing import clip_dem

        out_image = np.ones((1, 5, 5))
        mock_mask.return_value = (out_image, MagicMock())

        src = _make_rasterio_ctx()
        mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
        mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_path.return_value.parent.mkdir = MagicMock()

        result = clip_dem("/dem.tif", (-63, -33, -62, -32), "/out.tif")

        assert result == "/out.tif"


# ---------------------------------------------------------------------------
# compute_slope
# ---------------------------------------------------------------------------


class TestComputeSlope:
    @patch("app.domains.geo.processing.rasterio")
    @patch("app.domains.geo.processing.Path")
    def test_returns_output_path(self, mock_path, mock_rio):
        from app.domains.geo.processing import compute_slope

        data = np.random.rand(10, 10).astype(np.float64)
        src = _make_rasterio_ctx(data=data, nodata=-9999.0)

        mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
        mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_path.return_value.parent.mkdir = MagicMock()

        result = compute_slope("/dem.tif", "/slope.tif")

        assert result == "/slope.tif"


# ---------------------------------------------------------------------------
# compute_aspect
# ---------------------------------------------------------------------------


class TestComputeAspect:
    @patch("app.domains.geo.processing.rasterio")
    @patch("app.domains.geo.processing.Path")
    def test_returns_output_path(self, mock_path, mock_rio):
        from app.domains.geo.processing import compute_aspect

        data = np.random.rand(10, 10).astype(np.float64)
        src = _make_rasterio_ctx(data=data)

        mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
        mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_path.return_value.parent.mkdir = MagicMock()

        result = compute_aspect("/dem.tif", "/aspect.tif")

        assert result == "/aspect.tif"


# ---------------------------------------------------------------------------
# fill_sinks
# ---------------------------------------------------------------------------


class TestFillSinks:
    @patch("app.domains.geo.processing._get_wbt")
    @patch("app.domains.geo.processing.Path")
    def test_calls_wbt_fill_depressions(self, mock_path, mock_wbt):
        from app.domains.geo.processing import fill_sinks

        mock_path.return_value.parent.mkdir = MagicMock()

        result = fill_sinks("/dem.tif", "/filled.tif")

        assert result == "/filled.tif"
        mock_wbt.return_value.fill_depressions.assert_called_once_with(
            "/dem.tif", "/filled.tif"
        )


# ---------------------------------------------------------------------------
# compute_flow_direction
# ---------------------------------------------------------------------------


class TestComputeFlowDirection:
    @patch("app.domains.geo.processing._get_wbt")
    @patch("app.domains.geo.processing.Path")
    def test_calls_wbt_d8_pointer(self, mock_path, mock_wbt):
        from app.domains.geo.processing import compute_flow_direction

        mock_path.return_value.parent.mkdir = MagicMock()

        result = compute_flow_direction("/filled.tif", "/flowdir.tif")

        assert result == "/flowdir.tif"
        mock_wbt.return_value.d8_pointer.assert_called_once()


# ---------------------------------------------------------------------------
# compute_flow_accumulation
# ---------------------------------------------------------------------------


class TestComputeFlowAccumulation:
    @patch("app.domains.geo.processing._get_wbt")
    @patch("app.domains.geo.processing.Path")
    def test_calls_wbt_d8_flow_accumulation(self, mock_path, mock_wbt):
        from app.domains.geo.processing import compute_flow_accumulation

        mock_path.return_value.parent.mkdir = MagicMock()

        result = compute_flow_accumulation("/filled.tif", "/flowacc.tif")

        assert result == "/flowacc.tif"
        mock_wbt.return_value.d8_flow_accumulation.assert_called_once()


# ---------------------------------------------------------------------------
# compute_twi
# ---------------------------------------------------------------------------


class TestComputeTwi:
    @patch("app.domains.geo.processing.rasterio")
    @patch("app.domains.geo.processing.Path")
    def test_returns_output_path(self, mock_path, mock_rio):
        from app.domains.geo.processing import compute_twi

        slope_data = np.full((5, 5), 10.0, dtype=np.float64)  # 10 degrees
        fa_data = np.full((5, 5), 100.0, dtype=np.float64)

        slope_src = _make_rasterio_ctx(data=slope_data, nodata=-9999.0)
        fa_src = _make_rasterio_ctx(data=fa_data, nodata=-9999.0)

        call_count = [0]
        originals = [slope_src, fa_src]

        def open_side_effect(*args, **kwargs):
            ctx = MagicMock()
            idx = min(call_count[0], 1)
            ctx.__enter__ = MagicMock(return_value=originals[idx])
            ctx.__exit__ = MagicMock(return_value=False)
            call_count[0] += 1
            return ctx

        mock_rio.open.side_effect = open_side_effect
        mock_path.return_value.parent.mkdir = MagicMock()

        result = compute_twi("/slope.tif", "/flowacc.tif", "/twi.tif")

        assert result == "/twi.tif"


# ---------------------------------------------------------------------------
# compute_profile_curvature
# ---------------------------------------------------------------------------


class TestComputeProfileCurvature:
    @patch("app.domains.geo.processing._get_wbt")
    @patch("app.domains.geo.processing.Path")
    def test_returns_correct_path(self, mock_path, mock_wbt):
        from app.domains.geo.processing import compute_profile_curvature

        mock_path.return_value.parent.mkdir = MagicMock()
        mock_path.__truediv__ = MagicMock(return_value=Path("/out/profile_curvature.tif"))

        result = compute_profile_curvature("/filled.tif", "/out")

        mock_wbt.return_value.profile_curvature.assert_called_once()


# ---------------------------------------------------------------------------
# compute_tpi
# ---------------------------------------------------------------------------


class TestComputeTpi:
    @patch("app.domains.geo.processing._get_wbt")
    @patch("app.domains.geo.processing.Path")
    def test_default_radius_creates_21x21_filter(self, mock_path, mock_wbt):
        from app.domains.geo.processing import compute_tpi

        mock_path.return_value.parent.mkdir = MagicMock()
        mock_path.__truediv__ = MagicMock(return_value=Path("/out/tpi.tif"))

        compute_tpi("/filled.tif", "/out", radius=10)

        wbt_call = mock_wbt.return_value.dev_from_mean_elev
        wbt_call.assert_called_once()
        _, kwargs = wbt_call.call_args
        assert kwargs["filterx"] == 21
        assert kwargs["filtery"] == 21


# ---------------------------------------------------------------------------
# extract_drainage_network
# ---------------------------------------------------------------------------


class TestExtractDrainageNetwork:
    @patch("app.domains.geo.processing.rasterio")
    @patch("app.domains.geo.processing.shapes")
    @patch("app.domains.geo.processing.Path")
    @patch("builtins.open", new_callable=mock_open)
    def test_writes_geojson(self, mock_file, mock_path, mock_shapes, mock_rio):
        from app.domains.geo.processing import extract_drainage_network

        fa = np.array([[0, 500, 1500], [200, 800, 2000]], dtype=np.float64)
        src = _make_rasterio_ctx(data=fa, nodata=-9999.0, width=3, height=2)

        mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
        mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_shapes.return_value = [
            ({"type": "Polygon", "coordinates": []}, 1),
        ]
        mock_path.return_value.parent.mkdir = MagicMock()

        result = extract_drainage_network("/fa.tif", 1000, "/drainage.geojson")

        assert result == "/drainage.geojson"
        mock_file.assert_called_once_with("/drainage.geojson", "w")


# ---------------------------------------------------------------------------
# _get_wbt singleton
# ---------------------------------------------------------------------------


class TestGetWbt:
    @patch("app.domains.geo.processing.WhiteboxTools")
    def test_creates_singleton(self, mock_wbt_cls):
        import app.domains.geo.processing as proc

        proc._wbt = None  # Reset singleton
        wbt1 = proc._get_wbt()
        wbt2 = proc._get_wbt()

        assert wbt1 is wbt2
        mock_wbt_cls.return_value.set_verbose_mode.assert_called_with(False)
        proc._wbt = None  # Cleanup


# ---------------------------------------------------------------------------
# convert_to_cog
# ---------------------------------------------------------------------------


class TestConvertToCog:
    def test_default_output_path(self):
        """Verify default output name is .cog.tif when output_path=None."""
        from app.domains.geo.processing import convert_to_cog

        mock_cog_translate = MagicMock()
        mock_cog_profiles = MagicMock()
        mock_cog_profiles.get.return_value = {"compress": "deflate"}

        mock_rio_cogeo_cogeo = MagicMock()
        mock_rio_cogeo_cogeo.cog_translate = mock_cog_translate
        mock_rio_cogeo_profiles = MagicMock()
        mock_rio_cogeo_profiles.cog_profiles = mock_cog_profiles

        with patch.dict("sys.modules", {
            "rio_cogeo": MagicMock(),
            "rio_cogeo.cogeo": mock_rio_cogeo_cogeo,
            "rio_cogeo.profiles": mock_rio_cogeo_profiles,
        }), patch("app.domains.geo.processing.Path") as mock_path:
            mock_path_inst = MagicMock()
            mock_path_inst.with_suffix.return_value = Path("/data/dem.cog.tif")
            mock_path_inst.parent.mkdir = MagicMock()
            mock_path.return_value = mock_path_inst

            convert_to_cog("/data/dem.tif")

        mock_cog_translate.assert_called_once()
