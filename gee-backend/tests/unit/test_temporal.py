"""Unit tests for app.domains.geo.temporal — NDWI trend and raster comparison.

ALL external dependencies (ee, xarray, rioxarray, xee, shapely) are mocked
at sys.modules level since they're not installed in the test environment.
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ── Module-level mock setup ───────────────────────

# These modules are imported inside the functions at call time, so we
# need to inject mocks into sys.modules before importing temporal.py.


def _setup_ee_mock():
    """Create a complete ee mock that supports chained calls."""
    mock_ee = MagicMock()
    mock_ee.Geometry.return_value = MagicMock()
    mock_ee.Filter.lt.return_value = MagicMock()

    mock_collection = MagicMock()
    mock_collection.filterBounds.return_value = mock_collection
    mock_collection.filterDate.return_value = mock_collection
    mock_collection.filter.return_value = mock_collection
    mock_collection.select.return_value = mock_collection
    mock_collection.sort.return_value = mock_collection
    mock_collection.map.return_value.select.return_value = mock_collection
    mock_ee.ImageCollection.return_value = mock_collection

    return mock_ee, mock_collection


def _setup_xr_dataset(ndwi_values, n_times=None):
    """Create a mock xarray Dataset with NDWI values and time coords."""
    mock_xr = MagicMock()

    if n_times is None:
        n_times = len(ndwi_values)

    times = np.array(
        [np.datetime64(f"2024-{i+1:02d}-15") for i in range(min(n_times, 12))]
        + [np.datetime64(f"2025-{i+1:02d}-15") for i in range(max(0, n_times - 12))],
        dtype="datetime64[ns]",
    )

    mock_ndwi = MagicMock()
    mock_ndwi.dims = ("time", "lat", "lon")
    mock_ndwi.mean.return_value.values = ndwi_values

    mock_ds = MagicMock()
    mock_ds.__getitem__ = lambda self, key: mock_ndwi
    mock_ds.coords = {"time": MagicMock(values=times)}
    mock_ds.close = MagicMock()

    mock_xr.open_dataset.return_value = mock_ds
    return mock_xr


def _call_analyze_ndwi(count=5, ndwi_values=None, **kwargs):
    """Set up all mocks and call analyze_ndwi_trend_gee."""
    mock_ee, mock_collection = _setup_ee_mock()
    mock_collection.size.return_value.getInfo.return_value = count

    if ndwi_values is None:
        ndwi_values = np.array([0.3, 0.35, 0.32, 0.38, 0.4])

    mock_xr = _setup_xr_dataset(ndwi_values) if count > 0 else MagicMock()

    mock_gee_service = MagicMock()
    mock_gee_service._ensure_initialized = MagicMock()

    # Inject all required modules into sys.modules
    saved_modules = {}
    modules_to_mock = {
        "ee": mock_ee,
        "xarray": mock_xr,
        "xee": MagicMock(),
        "app.domains.geo.gee_service": mock_gee_service,
    }

    for mod_name, mock_mod in modules_to_mock.items():
        saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = mock_mod

    try:
        # Force re-import to pick up the mocked modules
        if "app.domains.geo.temporal" in sys.modules:
            del sys.modules["app.domains.geo.temporal"]

        from app.domains.geo.temporal import analyze_ndwi_trend_gee

        return analyze_ndwi_trend_gee(
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            "2024-01-01",
            "2024-06-01",
            **kwargs,
        )
    finally:
        # Restore original modules
        for mod_name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original
        sys.modules.pop("app.domains.geo.temporal", None)


# ── analyze_ndwi_trend_gee ────────────────────────


class TestAnalyzeNdwiTrendGee:
    """Tests for NDWI time-series analysis (GEE + Xee mocked)."""

    def test_empty_collection_returns_no_images(self):
        result = _call_analyze_ndwi(count=0)
        assert result["image_count"] == 0
        assert result["dates"] == []
        assert result["trend"] is None

    def test_returns_dates_and_values(self):
        values = np.array([0.3, 0.35, 0.32, 0.38, 0.4])
        result = _call_analyze_ndwi(ndwi_values=values)
        assert len(result["dates"]) == 5
        assert len(result["ndwi_values"]) == 5

    def test_trend_calculated_with_enough_data(self):
        values = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        result = _call_analyze_ndwi(ndwi_values=values)
        assert result["trend"] is not None
        assert result["trend"]["slope_per_image"] > 0
        assert result["trend"]["direction"] == "increasing"

    def test_decreasing_trend_direction(self):
        values = np.array([0.5, 0.4, 0.3, 0.2, 0.1])
        result = _call_analyze_ndwi(ndwi_values=values)
        assert result["trend"]["direction"] == "decreasing"

    def test_stable_trend_direction(self):
        values = np.array([0.3, 0.3, 0.3, 0.3, 0.3])
        result = _call_analyze_ndwi(ndwi_values=values)
        assert result["trend"]["direction"] == "stable"

    def test_anomalies_detected(self):
        # Need a value far enough from mean to strictly exceed 2-sigma
        # More points with low variance + one extreme outlier
        values = np.array([0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 2.0])
        result = _call_analyze_ndwi(count=8, ndwi_values=values)
        assert len(result["anomalies"]) > 0
        assert abs(result["anomalies"][0]["deviation_sigma"]) > 2

    def test_no_anomalies_with_uniform_data(self):
        values = np.array([0.3, 0.31, 0.29, 0.3, 0.31])
        result = _call_analyze_ndwi(ndwi_values=values)
        assert result["anomalies"] == []

    def test_nan_values_become_none(self):
        values = np.array([0.3, np.nan, 0.32, 0.38, 0.4])
        result = _call_analyze_ndwi(ndwi_values=values)
        assert result["ndwi_values"][1] is None

    def test_date_range_in_result(self):
        result = _call_analyze_ndwi()
        assert result["date_range"]["start"] == "2024-01-01"
        assert result["date_range"]["end"] == "2024-06-01"

    def test_too_few_points_no_trend(self):
        values = np.array([0.3, 0.4])
        result = _call_analyze_ndwi(count=2, ndwi_values=values)
        assert result["trend"] is None

    def test_r_squared_in_trend(self):
        values = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        result = _call_analyze_ndwi(ndwi_values=values)
        assert "r_squared" in result["trend"]
        # Perfect linear data should give r_squared close to 1
        assert result["trend"]["r_squared"] > 0.99

    def test_image_count_matches(self):
        result = _call_analyze_ndwi(count=7, ndwi_values=np.linspace(0.1, 0.5, 7))
        assert result["image_count"] == 7


# ── compare_rasters_temporal ──────────────────────


def _call_compare_rasters(raster_paths, labels, geometry_wkt=None, raster_data=None):
    """Set up mocks and call compare_rasters_temporal."""
    mock_rioxarray = MagicMock()
    mock_xr = MagicMock()
    mock_shapely_wkt = MagicMock()

    # Build mock DataArrays per raster
    mock_das = []
    if raster_data:
        for data in raster_data:
            mock_da = MagicMock()
            mock_da.values = data
            mock_da.rio.nodata = None
            mock_da.close = MagicMock()
            mock_das.append(mock_da)
        mock_xr.open_dataarray = MagicMock(side_effect=mock_das)

    saved_modules = {}
    modules_to_mock = {
        "rioxarray": mock_rioxarray,
        "xarray": mock_xr,
        "shapely": MagicMock(),
        "shapely.wkt": mock_shapely_wkt,
    }

    for mod_name, mock_mod in modules_to_mock.items():
        saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = mock_mod

    try:
        if "app.domains.geo.temporal" in sys.modules:
            del sys.modules["app.domains.geo.temporal"]

        from app.domains.geo.temporal import compare_rasters_temporal

        return compare_rasters_temporal(raster_paths, labels, geometry_wkt)
    finally:
        for mod_name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original
        sys.modules.pop("app.domains.geo.temporal", None)


class TestCompareRastersTemporal:
    """Tests for multi-raster comparison (xarray/rioxarray mocked)."""

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError, match="same length"):
            _call_compare_rasters(
                raster_paths=["/a.tif", "/b.tif"],
                labels=["one"],
            )

    @patch("pathlib.Path.exists", return_value=False)
    def test_skips_nonexistent_files(self, mock_exists):
        result = _call_compare_rasters(
            raster_paths=["/nonexistent.tif"],
            labels=["missing"],
        )
        assert result["raster_count"] == 0
        assert result["stats"] == []
        assert result["change"] is None

    @patch("pathlib.Path.exists", return_value=True)
    def test_stats_computed_for_valid_raster(self, mock_exists):
        data = [np.array([1.0, 2.0, 3.0, 4.0])]
        result = _call_compare_rasters(
            raster_paths=["/valid.tif"],
            labels=["2024-01"],
            raster_data=data,
        )
        assert result["raster_count"] == 1
        stat = result["stats"][0]
        assert stat["label"] == "2024-01"
        assert stat["mean"] == 2.5
        assert stat["pixel_count"] == 4

    @patch("pathlib.Path.exists", return_value=True)
    def test_change_analysis_two_rasters(self, mock_exists):
        data = [
            np.array([10.0, 20.0]),
            np.array([15.0, 25.0]),
        ]
        result = _call_compare_rasters(
            raster_paths=["/a.tif", "/b.tif"],
            labels=["before", "after"],
            raster_data=data,
        )
        assert result["change"] is not None
        assert result["change"]["from"] == "before"
        assert result["change"]["to"] == "after"
        assert result["change"]["mean_change"] == 5.0

    @patch("pathlib.Path.exists", return_value=True)
    def test_percent_change_calculated(self, mock_exists):
        data = [
            np.array([10.0, 10.0]),
            np.array([12.0, 12.0]),
        ]
        result = _call_compare_rasters(
            raster_paths=["/a.tif", "/b.tif"],
            labels=["t0", "t1"],
            raster_data=data,
        )
        # 20% increase: (12-10)/10 * 100
        assert result["change"]["percent_change"] == 20.0
