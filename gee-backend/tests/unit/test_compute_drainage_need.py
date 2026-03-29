"""
Unit tests for compute_drainage_need function.

Tests:
  - Output range [0-100] for valid pixels
  - Missing drainage.tif raises FileNotFoundError
  - Nodata propagation
  - Custom weights override
  - Distance penalty effect: mocked euclidean_distance produces
    a gradient so pixels far from drainage score differently.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from app.domains.geo.composites import (
    DEFAULT_DRAINAGE_WEIGHTS,
    compute_drainage_need,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NODATA = -9999.0
SHAPE = (20, 20)
BOUNDS = (-62.8, -32.7, -62.6, -32.5)
CRS = "EPSG:4326"


def _make_geotiff(path: Path, data: np.ndarray, nodata: float = NODATA) -> None:
    """Write a single-band GeoTIFF."""
    transform = from_bounds(*BOUNDS, data.shape[1], data.shape[0])
    meta = {
        "driver": "GTiff",
        "dtype": "float64",
        "count": 1,
        "height": data.shape[0],
        "width": data.shape[1],
        "crs": CRS,
        "transform": transform,
        "nodata": nodata,
    }
    with rasterio.open(str(path), "w", **meta) as dst:
        dst.write(data, 1)


def _create_drainage_inputs(
    area_dir: Path, rng: np.random.Generator, *, include_drainage: bool = True
) -> None:
    """Create prerequisite GeoTIFFs for drainage need computation."""
    area_dir.mkdir(parents=True, exist_ok=True)

    flow_acc = rng.uniform(1.0, 50000.0, size=SHAPE)
    hand = rng.uniform(0.0, 20.0, size=SHAPE)

    _make_geotiff(area_dir / "flow_acc.tif", flow_acc)
    _make_geotiff(area_dir / "hand.tif", hand)

    if include_drainage:
        # Binary drainage raster: 1 = drainage channel, 0 = no channel
        drainage = np.zeros(SHAPE, dtype=np.float64)
        drainage[10, :] = 1.0  # horizontal drainage channel at row 10
        _make_geotiff(area_dir / "drainage.tif", drainage)


def _mock_euclidean_distance(input_path: str, output_path: str) -> int:
    """Mock WBT euclidean_distance: creates a distance raster as linear gradient.

    Simulates distance from the drainage channel at row 10.
    """
    with rasterio.open(input_path) as src:
        meta = src.meta.copy()
        data = src.read(1)

    # Create distance gradient: distance from row 10
    rows = np.arange(data.shape[0])
    dist = np.abs(rows - 10).astype(np.float64)
    dist_raster = np.broadcast_to(dist[:, np.newaxis], data.shape).copy()

    meta.update({"dtype": "float64"})
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(dist_raster, 1)

    return 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeDrainageNeedOutputRange:
    """Output raster values must be in [0, 100] for valid pixels."""

    @patch("app.domains.geo.composites._get_wbt")
    def test_valid_pixels_in_zero_to_hundred(self, mock_wbt, tmp_path: Path):
        wbt = MagicMock()
        wbt.euclidean_distance = _mock_euclidean_distance
        mock_wbt.return_value = wbt

        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        _create_drainage_inputs(area_dir, rng)

        output_path = str(tmp_path / "drainage_need.tif")
        compute_drainage_need(str(area_dir), output_path)

        with rasterio.open(output_path) as src:
            data = src.read(1)
            nodata = src.nodata

        valid = data[data != nodata]
        assert valid.size > 0
        assert valid.min() >= 0.0, f"Min {valid.min()} below 0"
        assert valid.max() <= 100.0, f"Max {valid.max()} above 100"

    @patch("app.domains.geo.composites._get_wbt")
    def test_output_is_float32(self, mock_wbt, tmp_path: Path):
        wbt = MagicMock()
        wbt.euclidean_distance = _mock_euclidean_distance
        mock_wbt.return_value = wbt

        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        _create_drainage_inputs(area_dir, rng)

        output_path = str(tmp_path / "drainage_need.tif")
        compute_drainage_need(str(area_dir), output_path)

        with rasterio.open(output_path) as src:
            assert src.dtypes[0] == "float32"


class TestComputeDrainageNeedMissingDrainage:
    """Missing drainage.tif must raise FileNotFoundError."""

    def test_missing_drainage_raises(self, tmp_path: Path):
        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        _create_drainage_inputs(area_dir, rng, include_drainage=False)

        output_path = str(tmp_path / "drainage_need.tif")
        with pytest.raises(FileNotFoundError, match="drainage.tif not found"):
            compute_drainage_need(str(area_dir), output_path)


class TestComputeDrainageNeedNodataPropagation:
    """Nodata in any input must propagate to output."""

    @patch("app.domains.geo.composites._get_wbt")
    def test_nodata_propagates(self, mock_wbt, tmp_path: Path):
        wbt = MagicMock()
        wbt.euclidean_distance = _mock_euclidean_distance
        mock_wbt.return_value = wbt

        rng = np.random.default_rng(seed=99)
        area_dir = tmp_path / "area"
        area_dir.mkdir(parents=True, exist_ok=True)

        flow_acc = rng.uniform(1.0, 50000.0, size=SHAPE)
        hand = rng.uniform(0.0, 20.0, size=SHAPE)
        drainage = np.zeros(SHAPE, dtype=np.float64)
        drainage[10, :] = 1.0

        # Inject nodata at different pixels
        flow_acc[1, 1] = NODATA
        hand[2, 2] = NODATA

        _make_geotiff(area_dir / "flow_acc.tif", flow_acc)
        _make_geotiff(area_dir / "hand.tif", hand)
        _make_geotiff(area_dir / "drainage.tif", drainage)

        output_path = str(tmp_path / "drainage_need.tif")
        compute_drainage_need(str(area_dir), output_path)

        with rasterio.open(output_path) as src:
            data = src.read(1)
            nodata = src.nodata

        assert data[1, 1] == nodata, "flow_acc nodata must propagate"
        assert data[2, 2] == nodata, "hand nodata must propagate"


class TestComputeDrainageNeedWeights:
    """Weight handling."""

    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_DRAINAGE_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-6)

    @patch("app.domains.geo.composites._get_wbt")
    def test_custom_weights_produce_different_output(self, mock_wbt, tmp_path: Path):
        wbt = MagicMock()
        wbt.euclidean_distance = _mock_euclidean_distance
        mock_wbt.return_value = wbt

        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        _create_drainage_inputs(area_dir, rng)

        custom_weights = {
            "flow_acc": 0.10,
            "hand": 0.10,
            "dist_drainage": 0.80,
        }

        output_default = str(tmp_path / "drain_default.tif")
        output_custom = str(tmp_path / "drain_custom.tif")

        compute_drainage_need(str(area_dir), output_default)
        compute_drainage_need(str(area_dir), output_custom, weights=custom_weights)

        with rasterio.open(output_default) as src:
            data_default = src.read(1)
        with rasterio.open(output_custom) as src:
            data_custom = src.read(1)

        assert not np.allclose(data_default, data_custom), (
            "Custom weights should produce different output"
        )


class TestComputeDrainageNeedDistancePenalty:
    """Pixels far from drainage should have higher drainage need."""

    @patch("app.domains.geo.composites._get_wbt")
    def test_far_pixels_score_differently(self, mock_wbt, tmp_path: Path):
        """With distance as dominant weight, pixels far from drainage
        should score higher than pixels near drainage."""
        wbt = MagicMock()
        wbt.euclidean_distance = _mock_euclidean_distance
        mock_wbt.return_value = wbt

        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        area_dir.mkdir(parents=True, exist_ok=True)

        # Use UNIFORM data for other layers to isolate distance effect
        uniform = np.full(SHAPE, 10.0, dtype=np.float64)
        drainage = np.zeros(SHAPE, dtype=np.float64)
        drainage[10, :] = 1.0

        _make_geotiff(area_dir / "flow_acc.tif", uniform)
        _make_geotiff(area_dir / "hand.tif", uniform)
        _make_geotiff(area_dir / "drainage.tif", drainage)

        # Heavily weight distance
        heavy_dist_weights = {
            "flow_acc": 0.05,
            "hand": 0.05,
            "dist_drainage": 0.90,
        }

        output_path = str(tmp_path / "drainage_need.tif")
        compute_drainage_need(str(area_dir), output_path, weights=heavy_dist_weights)

        with rasterio.open(output_path) as src:
            data = src.read(1)
            nodata = src.nodata

        # Row 0 (far from drainage at row 10) vs row 9 (near drainage)
        far_mean = np.mean(data[0, data[0] != nodata])
        near_mean = np.mean(data[9, data[9] != nodata])

        assert far_mean > near_mean, (
            f"Far pixels (row 0, mean={far_mean:.2f}) should score higher "
            f"than near pixels (row 9, mean={near_mean:.2f})"
        )
