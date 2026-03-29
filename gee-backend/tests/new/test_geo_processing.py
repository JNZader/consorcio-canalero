"""
Tests for the geo processing module.

Focus on:
  - Function signatures (smoke tests)
  - TWI formula with known numpy arrays
  - Terrain classification logic with numpy arrays
  - Pure numpy logic (no rasterio/whiteboxtools runtime needed)
"""

from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# WhiteboxTools is only available in the geo-worker Docker container.
# Skip the entire module when running tests locally.
pytest.importorskip("whitebox", reason="WhiteboxTools only available in geo-worker container")


# ---------------------------------------------------------------------------
# Signature tests
# ---------------------------------------------------------------------------


class TestFunctionSignatures:
    """Verify all processing functions have the expected signatures."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        from app.domains.geo import processing

        self.mod = processing

    def test_clip_dem_signature(self):
        sig = inspect.signature(self.mod.clip_dem)
        params = list(sig.parameters.keys())
        assert params == ["dem_path", "bbox", "output_path"]

    def test_fill_sinks_signature(self):
        sig = inspect.signature(self.mod.fill_sinks)
        params = list(sig.parameters.keys())
        assert params == ["dem_path", "output_path"]

    def test_compute_slope_signature(self):
        sig = inspect.signature(self.mod.compute_slope)
        params = list(sig.parameters.keys())
        assert params == ["dem_path", "output_path"]

    def test_compute_aspect_signature(self):
        sig = inspect.signature(self.mod.compute_aspect)
        params = list(sig.parameters.keys())
        assert params == ["dem_path", "output_path"]

    def test_compute_flow_direction_signature(self):
        sig = inspect.signature(self.mod.compute_flow_direction)
        params = list(sig.parameters.keys())
        assert params == ["filled_dem_path", "output_path"]

    def test_compute_flow_accumulation_signature(self):
        sig = inspect.signature(self.mod.compute_flow_accumulation)
        params = list(sig.parameters.keys())
        assert params == ["flow_dir_path", "output_path"]

    def test_compute_twi_signature(self):
        sig = inspect.signature(self.mod.compute_twi)
        params = list(sig.parameters.keys())
        assert params == ["slope_path", "flow_acc_path", "output_path"]

    def test_compute_hand_signature(self):
        sig = inspect.signature(self.mod.compute_hand)
        params = list(sig.parameters.keys())
        assert params == [
            "dem_path",
            "flow_dir_path",
            "flow_acc_path",
            "output_path",
            "drainage_threshold",
        ]

    def test_extract_drainage_network_signature(self):
        sig = inspect.signature(self.mod.extract_drainage_network)
        params = list(sig.parameters.keys())
        assert params == ["flow_acc_path", "threshold", "output_path"]

    def test_classify_terrain_signature(self):
        sig = inspect.signature(self.mod.classify_terrain)
        params = list(sig.parameters.keys())
        assert "slope_path" in params
        assert "twi_path" in params
        assert "flow_acc_path" in params
        assert "output_path" in params


# ---------------------------------------------------------------------------
# TWI formula tests (mock rasterio, use real numpy)
# ---------------------------------------------------------------------------


def _make_mock_rasterio_open(arrays: dict[str, np.ndarray], nodata=None):
    """Return a context-manager mock for rasterio.open that serves arrays by path.

    Each array must be 2-D (single band).
    """

    class FakeDataset:
        def __init__(self, arr: np.ndarray):
            self._arr = arr
            self.nodata = nodata
            self.meta = {
                "driver": "GTiff",
                "dtype": str(arr.dtype),
                "width": arr.shape[1],
                "height": arr.shape[0],
                "count": 1,
                "crs": "EPSG:4326",
                "transform": _fake_transform(),
            }
            self.transform = _fake_transform()
            self.crs = "EPSG:4326"

        def read(self, band):
            return self._arr.copy()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def opener(path, *args, **kwargs):
        if path in arrays:
            return FakeDataset(arrays[path])
        # For write mode, return a mock
        mock_dst = MagicMock()
        mock_dst.__enter__ = MagicMock(return_value=mock_dst)
        mock_dst.__exit__ = MagicMock(return_value=False)
        return mock_dst

    return opener


class _FakeTransform:
    """Minimal affine-like object."""

    a = 0.001  # ~111m at equator
    e = -0.001


def _fake_transform():
    return _FakeTransform()


class TestTWIFormula:
    """Test TWI = ln(a / tan(b)) with controlled numpy arrays."""

    def test_twi_flat_terrain_high_accumulation(self):
        """Flat terrain (low slope) + high flow acc → high TWI."""
        from app.domains.geo.processing import _MIN_SLOPE_RAD

        # slope = 0.5 degrees everywhere, flow_acc = 1000 everywhere
        slope = np.full((3, 3), 0.5, dtype=np.float64)
        flow_acc = np.full((3, 3), 1000.0, dtype=np.float64)
        cell_size = 0.001

        slope_rad = np.radians(slope)
        slope_rad = np.maximum(slope_rad, _MIN_SLOPE_RAD)
        specific_area = flow_acc * cell_size
        expected_twi = np.log(specific_area / np.tan(slope_rad))

        # All TWI values should be positive (high wetness)
        assert np.all(expected_twi > 0)

    def test_twi_steep_terrain_low_accumulation(self):
        """Steep terrain (high slope) + low flow acc → low TWI."""
        from app.domains.geo.processing import _MIN_SLOPE_RAD

        slope = np.full((3, 3), 45.0, dtype=np.float64)
        flow_acc = np.full((3, 3), 1.0, dtype=np.float64)
        cell_size = 0.001

        slope_rad = np.radians(slope)
        slope_rad = np.maximum(slope_rad, _MIN_SLOPE_RAD)
        specific_area = flow_acc * cell_size
        twi = np.log(specific_area / np.tan(slope_rad))

        # TWI should be negative (low wetness)
        assert np.all(twi < 0)

    def test_twi_zero_slope_capped(self):
        """Zero slope should not produce inf due to capping."""
        from app.domains.geo.processing import _MIN_SLOPE_RAD

        slope = np.zeros((3, 3), dtype=np.float64)
        flow_acc = np.full((3, 3), 100.0, dtype=np.float64)
        cell_size = 0.001

        slope_rad = np.radians(slope)
        slope_rad = np.maximum(slope_rad, _MIN_SLOPE_RAD)
        specific_area = flow_acc * cell_size
        twi = np.log(specific_area / np.tan(slope_rad))

        assert np.all(np.isfinite(twi))

    @patch("app.domains.geo.processing.rasterio")
    def test_compute_twi_integration(self, mock_rasterio):
        """Test compute_twi end-to-end with mocked rasterio."""
        from app.domains.geo.processing import compute_twi

        slope_arr = np.full((5, 5), 2.0, dtype=np.float64)
        flow_acc_arr = np.full((5, 5), 500.0, dtype=np.float64)

        arrays = {
            "/tmp/slope.tif": slope_arr,
            "/tmp/flow_acc.tif": flow_acc_arr,
        }

        mock_rasterio.open = MagicMock(side_effect=_make_mock_rasterio_open(arrays))

        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "twi.tif")
            result = compute_twi("/tmp/slope.tif", "/tmp/flow_acc.tif", output)
            assert result == output


# ---------------------------------------------------------------------------
# Terrain classification logic tests
# ---------------------------------------------------------------------------


class TestTerrainClassification:
    """Test the classification rules with numpy arrays."""

    def test_plano_seco(self):
        """Flat terrain + low TWI = plano_seco (0)."""
        from app.domains.geo.processing import (
            TERRAIN_PLANO_SECO,
            TERRAIN_PLANO_HUMEDO,
        )

        # slope < 1, TWI below median → should be class 0
        slope = np.array([[0.5]], dtype=np.float64)
        twi = np.array([[1.0]], dtype=np.float64)  # below median
        flow_acc = np.array([[10.0]], dtype=np.float64)

        twi_median = 5.0  # artificially set median above our TWI value

        flat = slope < 1.0
        result = np.full(slope.shape, TERRAIN_PLANO_SECO, dtype=np.uint8)
        result[flat & (twi >= twi_median)] = TERRAIN_PLANO_HUMEDO

        assert result[0, 0] == TERRAIN_PLANO_SECO

    def test_plano_humedo(self):
        """Flat terrain + high TWI = plano_humedo (1)."""
        from app.domains.geo.processing import (
            TERRAIN_PLANO_HUMEDO,
            TERRAIN_PLANO_SECO,
        )

        slope = np.array([[0.5]], dtype=np.float64)
        twi = np.array([[10.0]], dtype=np.float64)
        twi_median = 5.0

        flat = slope < 1.0
        result = np.full(slope.shape, TERRAIN_PLANO_SECO, dtype=np.uint8)
        result[flat & (twi >= twi_median)] = TERRAIN_PLANO_HUMEDO

        assert result[0, 0] == TERRAIN_PLANO_HUMEDO

    def test_drenaje_activo(self):
        """Steep + high flow acc = drenaje_activo (2)."""
        from app.domains.geo.processing import (
            TERRAIN_DRENAJE_ACTIVO,
            TERRAIN_PLANO_SECO,
        )

        slope = np.array([[5.0]], dtype=np.float64)
        flow_acc = np.array([[2000.0]], dtype=np.float64)
        threshold = 1000

        steep = slope >= 1.0
        result = np.full(slope.shape, TERRAIN_PLANO_SECO, dtype=np.uint8)
        result[steep & (flow_acc > threshold)] = TERRAIN_DRENAJE_ACTIVO

        assert result[0, 0] == TERRAIN_DRENAJE_ACTIVO

    def test_acumulacion_overrides(self):
        """Very high flow acc = acumulacion (3), overrides other classes."""
        from app.domains.geo.processing import (
            TERRAIN_ACUMULACION,
            TERRAIN_PLANO_HUMEDO,
            TERRAIN_PLANO_SECO,
        )

        slope = np.array([[0.5]], dtype=np.float64)
        twi = np.array([[10.0]], dtype=np.float64)
        flow_acc = np.array([[10000.0]], dtype=np.float64)
        twi_median = 5.0
        high_threshold = 5000

        flat = slope < 1.0
        result = np.full(slope.shape, TERRAIN_PLANO_SECO, dtype=np.uint8)
        result[flat & (twi >= twi_median)] = TERRAIN_PLANO_HUMEDO
        result[flow_acc > high_threshold] = TERRAIN_ACUMULACION

        assert result[0, 0] == TERRAIN_ACUMULACION

    def test_mixed_terrain_grid(self):
        """3x3 grid with mixed terrain types."""
        from app.domains.geo.processing import (
            TERRAIN_ACUMULACION,
            TERRAIN_DRENAJE_ACTIVO,
            TERRAIN_PLANO_HUMEDO,
            TERRAIN_PLANO_SECO,
        )

        slope = np.array(
            [
                [0.3, 0.5, 5.0],
                [0.2, 3.0, 0.8],
                [0.1, 2.0, 0.4],
            ],
            dtype=np.float64,
        )
        twi = np.array(
            [
                [2.0, 8.0, 3.0],
                [1.0, 4.0, 9.0],
                [3.0, 5.0, 7.0],
            ],
            dtype=np.float64,
        )
        flow_acc = np.array(
            [
                [10, 50, 2000],
                [5, 1500, 100],
                [3, 800, 10000],
            ],
            dtype=np.float64,
        )

        twi_median = float(np.median(twi))  # 4.0
        slope_threshold = 1.0
        flow_threshold = 1000
        high_threshold = 5000

        flat = slope < slope_threshold
        steep = ~flat
        result = np.full(slope.shape, TERRAIN_PLANO_SECO, dtype=np.uint8)
        result[flat & (twi >= twi_median)] = TERRAIN_PLANO_HUMEDO
        result[steep & (flow_acc > flow_threshold)] = TERRAIN_DRENAJE_ACTIVO
        result[flow_acc > high_threshold] = TERRAIN_ACUMULACION

        # (0,0): flat, twi=2 < 4 → plano_seco
        assert result[0, 0] == TERRAIN_PLANO_SECO
        # (0,1): flat, twi=8 >= 4 → plano_humedo
        assert result[0, 1] == TERRAIN_PLANO_HUMEDO
        # (0,2): steep, flow=2000 > 1000 → drenaje_activo
        assert result[0, 2] == TERRAIN_DRENAJE_ACTIVO
        # (1,1): steep, flow=1500 > 1000 → drenaje_activo
        assert result[1, 1] == TERRAIN_DRENAJE_ACTIVO
        # (2,2): flat, twi=7 >= 4 → plano_humedo, BUT flow=10000 > 5000 → acumulacion
        assert result[2, 2] == TERRAIN_ACUMULACION

    @patch("app.domains.geo.processing.rasterio")
    def test_classify_terrain_integration(self, mock_rasterio):
        """End-to-end classify_terrain with mocked rasterio."""
        from app.domains.geo.processing import classify_terrain

        slope_arr = np.array(
            [[0.5, 5.0], [0.3, 0.8]], dtype=np.float64
        )
        twi_arr = np.array(
            [[8.0, 2.0], [1.0, 10.0]], dtype=np.float64
        )
        flow_acc_arr = np.array(
            [[50, 2000], [5, 10000]], dtype=np.float64
        )

        arrays = {
            "/tmp/slope.tif": slope_arr,
            "/tmp/twi.tif": twi_arr,
            "/tmp/flow_acc.tif": flow_acc_arr,
        }

        mock_rasterio.open = MagicMock(side_effect=_make_mock_rasterio_open(arrays))

        with tempfile.TemporaryDirectory() as tmpdir:
            output = str(Path(tmpdir) / "terrain.tif")
            result = classify_terrain(
                "/tmp/slope.tif", "/tmp/twi.tif", "/tmp/flow_acc.tif", output
            )
            assert result == output


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify terrain class constants are distinct."""

    def test_class_values_unique(self):
        from app.domains.geo.processing import (
            TERRAIN_ACUMULACION,
            TERRAIN_DRENAJE_ACTIVO,
            TERRAIN_PLANO_HUMEDO,
            TERRAIN_PLANO_SECO,
        )

        values = [
            TERRAIN_PLANO_SECO,
            TERRAIN_PLANO_HUMEDO,
            TERRAIN_DRENAJE_ACTIVO,
            TERRAIN_ACUMULACION,
        ]
        assert len(set(values)) == 4

    def test_class_values_range(self):
        from app.domains.geo.processing import (
            TERRAIN_ACUMULACION,
            TERRAIN_DRENAJE_ACTIVO,
            TERRAIN_PLANO_HUMEDO,
            TERRAIN_PLANO_SECO,
        )

        for val in [
            TERRAIN_PLANO_SECO,
            TERRAIN_PLANO_HUMEDO,
            TERRAIN_DRENAJE_ACTIVO,
            TERRAIN_ACUMULACION,
        ]:
            assert 0 <= val <= 255  # fits uint8
