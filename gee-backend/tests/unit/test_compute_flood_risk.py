"""
Unit tests for compute_flood_risk function.

Tests:
  - Output range [0-100] for valid pixels
  - Nodata propagation: pixel nodata in ANY input -> nodata in output
  - Default weights sum to ~1.0
  - Custom weights override defaults
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from app.domains.geo.composites import (
    DEFAULT_FLOOD_WEIGHTS,
    compute_flood_risk,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NODATA = -9999.0
SHAPE = (20, 20)
BOUNDS = (-62.8, -32.7, -62.6, -32.5)  # Bell Ville area
CRS = "EPSG:4326"


def _make_geotiff(path: Path, data: np.ndarray, nodata: float = NODATA) -> None:
    """Write a single-band GeoTIFF with synthetic data."""
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


def _create_flood_inputs(area_dir: Path, rng: np.random.Generator) -> None:
    """Create the three prerequisite GeoTIFFs for flood risk."""
    area_dir.mkdir(parents=True, exist_ok=True)

    hand = rng.uniform(0.0, 20.0, size=SHAPE)
    twi = rng.uniform(2.0, 18.0, size=SHAPE)
    slope = rng.uniform(0.0, 30.0, size=SHAPE)

    _make_geotiff(area_dir / "hand.tif", hand)
    _make_geotiff(area_dir / "twi.tif", twi)
    _make_geotiff(area_dir / "slope.tif", slope)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeFloodRiskOutputRange:
    """Output raster values must be in [0, 100] for valid pixels."""

    def test_valid_pixels_in_zero_to_hundred(self, tmp_path: Path):
        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        _create_flood_inputs(area_dir, rng)

        output_path = str(tmp_path / "flood_risk.tif")
        compute_flood_risk(str(area_dir), output_path)

        with rasterio.open(output_path) as src:
            data = src.read(1)
            nodata = src.nodata

        valid = data[data != nodata]
        assert valid.size > 0, "Expected some valid pixels"
        assert valid.min() >= 0.0, f"Min {valid.min()} below 0"
        assert valid.max() <= 100.0, f"Max {valid.max()} above 100"

    def test_output_is_float32(self, tmp_path: Path):
        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        _create_flood_inputs(area_dir, rng)

        output_path = str(tmp_path / "flood_risk.tif")
        compute_flood_risk(str(area_dir), output_path)

        with rasterio.open(output_path) as src:
            assert src.dtypes[0] == "float32"


class TestComputeFloodRiskNodataPropagation:
    """Pixel nodata in ANY input layer must propagate to nodata in output."""

    def test_nodata_in_hand_propagates(self, tmp_path: Path):
        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        _create_flood_inputs(area_dir, rng)

        # Re-write hand.tif with nodata in top-left corner
        hand = rng.uniform(0.0, 20.0, size=SHAPE)
        hand[0, 0] = NODATA
        _make_geotiff(area_dir / "hand.tif", hand)

        output_path = str(tmp_path / "flood_risk.tif")
        compute_flood_risk(str(area_dir), output_path)

        with rasterio.open(output_path) as src:
            data = src.read(1)
            nodata = src.nodata

        assert data[0, 0] == nodata, "Nodata pixel in HAND must produce nodata in output"

    def test_nodata_in_any_layer_is_nodata_in_output(self, tmp_path: Path):
        """Put nodata in different layers at different pixels; all must propagate."""
        rng = np.random.default_rng(seed=99)
        area_dir = tmp_path / "area"
        area_dir.mkdir(parents=True, exist_ok=True)

        hand = rng.uniform(0.0, 20.0, size=SHAPE)
        twi = rng.uniform(2.0, 18.0, size=SHAPE)
        slope = rng.uniform(0.0, 30.0, size=SHAPE)

        # Each layer gets nodata at a different pixel
        hand[1, 1] = NODATA
        twi[2, 2] = NODATA
        slope[3, 3] = NODATA

        _make_geotiff(area_dir / "hand.tif", hand)
        _make_geotiff(area_dir / "twi.tif", twi)
        _make_geotiff(area_dir / "slope.tif", slope)

        output_path = str(tmp_path / "flood_risk.tif")
        compute_flood_risk(str(area_dir), output_path)

        with rasterio.open(output_path) as src:
            data = src.read(1)
            nodata = src.nodata

        for r, c in [(1, 1), (2, 2), (3, 3)]:
            assert data[r, c] == nodata, f"Pixel ({r},{c}) should be nodata"


class TestComputeFloodRiskWeights:
    """Weight validation and custom weight override."""

    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_FLOOD_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_custom_weights_override_defaults(self, tmp_path: Path):
        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        _create_flood_inputs(area_dir, rng)

        # Skew heavily toward TWI
        custom_weights = {"twi": 0.70, "hand": 0.20, "slope": 0.10}
        output_default = str(tmp_path / "flood_default.tif")
        output_custom = str(tmp_path / "flood_custom.tif")

        compute_flood_risk(str(area_dir), output_default)
        compute_flood_risk(str(area_dir), output_custom, weights=custom_weights)

        with rasterio.open(output_default) as src:
            data_default = src.read(1)
        with rasterio.open(output_custom) as src:
            data_custom = src.read(1)

        # Results must differ when weights change
        assert not np.allclose(data_default, data_custom), (
            "Custom weights should produce different output than default weights"
        )

    def test_output_preserves_crs(self, tmp_path: Path):
        rng = np.random.default_rng(seed=42)
        area_dir = tmp_path / "area"
        _create_flood_inputs(area_dir, rng)

        output_path = str(tmp_path / "flood_risk.tif")
        compute_flood_risk(str(area_dir), output_path)

        with rasterio.open(output_path) as src:
            assert src.crs is not None
            assert src.crs.to_epsg() == 4326
