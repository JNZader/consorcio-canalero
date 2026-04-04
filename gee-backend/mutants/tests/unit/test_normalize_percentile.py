"""
Unit tests for normalize_percentile function.

Tests:
  - Normal range: known values map correctly to [0, 1]
  - All-nodata: returns zeros array
  - Single value: uniform band returns 0.5 for valid pixels
  - Outlier clipping: values outside percentile range clamp to [0, 1]
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domains.geo.composites import normalize_percentile


class TestNormalizePercentileNormalRange:
    """Input array with known values maps to [0, 1] with correct percentile bounds."""

    def test_output_range_is_zero_to_one(self):
        """All valid output pixels must be in [0, 1]."""
        rng = np.random.default_rng(seed=42)
        data = rng.uniform(10.0, 100.0, size=(10, 10)).astype(np.float64)
        nodata_mask = np.zeros((10, 10), dtype=bool)

        result = normalize_percentile(data, nodata_mask)

        assert result.dtype == np.float32
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_percentile_boundaries_correct(self):
        """Pixels at p2 map to ~0, pixels at p98 map to ~1."""
        # Evenly spaced 0..99 in a 10x10 grid
        data = np.arange(100, dtype=np.float64).reshape(10, 10)
        nodata_mask = np.zeros((10, 10), dtype=bool)

        result = normalize_percentile(data, nodata_mask, low=2.0, high=98.0)

        p_low = np.percentile(data, 2.0)
        p_high = np.percentile(data, 98.0)

        # Value at p_low should normalize to 0
        idx_low = np.unravel_index(np.argmin(np.abs(data - p_low)), data.shape)
        assert result[idx_low] == pytest.approx(0.0, abs=0.02)

        # Value at p_high should normalize to 1
        idx_high = np.unravel_index(np.argmin(np.abs(data - p_high)), data.shape)
        assert result[idx_high] == pytest.approx(1.0, abs=0.02)

    def test_nodata_pixels_are_zero_in_output(self):
        """Masked pixels must be 0.0 regardless of input value."""
        data = np.full((10, 10), 50.0, dtype=np.float64)
        nodata_mask = np.zeros((10, 10), dtype=bool)
        # Mark top row as nodata
        nodata_mask[0, :] = True
        data[0, :] = -9999.0

        result = normalize_percentile(data, nodata_mask)

        np.testing.assert_array_equal(result[0, :], 0.0)

    def test_nodata_excluded_from_percentile_computation(self):
        """Nodata values (-9999) must not skew the percentile range."""
        data = np.arange(100, dtype=np.float64).reshape(10, 10)
        nodata_mask = np.zeros((10, 10), dtype=bool)

        # Inject extreme nodata that would shift percentiles if included
        nodata_mask[0, 0] = True
        data[0, 0] = -999999.0

        result = normalize_percentile(data, nodata_mask)

        # Without nodata exclusion, the min would be -999999 and most
        # values would cluster near 1.0.  With exclusion, valid pixels
        # still span the full [0, 1] range.
        valid_result = result[~nodata_mask]
        assert valid_result.min() < 0.1
        assert valid_result.max() > 0.9


class TestNormalizePercentileAllNodata:
    """Entire array is nodata -- returns zeros."""

    def test_all_nodata_returns_zeros(self):
        data = np.full((10, 10), -9999.0, dtype=np.float64)
        nodata_mask = np.ones((10, 10), dtype=bool)

        result = normalize_percentile(data, nodata_mask)

        assert result.shape == (10, 10)
        assert result.dtype == np.float32
        np.testing.assert_array_equal(result, 0.0)


class TestNormalizePercentileSingleValue:
    """All valid pixels have the same value -- p_high == p_low edge case."""

    def test_single_value_returns_half(self):
        """When all valid pixels are identical, result should be 0.5."""
        data = np.full((10, 10), 42.0, dtype=np.float64)
        nodata_mask = np.zeros((10, 10), dtype=bool)

        result = normalize_percentile(data, nodata_mask)

        expected = np.full((10, 10), 0.5, dtype=np.float32)
        np.testing.assert_array_equal(result, expected)

    def test_single_value_with_nodata_returns_half_for_valid(self):
        """Mixed nodata + single-value valid pixels."""
        data = np.full((10, 10), 42.0, dtype=np.float64)
        nodata_mask = np.zeros((10, 10), dtype=bool)
        nodata_mask[:5, :] = True

        result = normalize_percentile(data, nodata_mask)

        # Valid pixels = 0.5, nodata pixels = 0.0
        np.testing.assert_array_equal(result[5:, :], 0.5)
        np.testing.assert_array_equal(result[:5, :], 0.0)


class TestNormalizePercentileOutlierClipping:
    """Values outside the percentile range get clipped to [0, 1]."""

    def test_extreme_low_clipped_to_zero(self):
        """Values far below p2 must clamp to 0.0."""
        data = np.arange(100, dtype=np.float64).reshape(10, 10)
        # Add extreme low outlier
        data[0, 0] = -1000.0
        nodata_mask = np.zeros((10, 10), dtype=bool)

        result = normalize_percentile(data, nodata_mask)

        assert result[0, 0] == 0.0

    def test_extreme_high_clipped_to_one(self):
        """Values far above p98 must clamp to 1.0."""
        data = np.arange(100, dtype=np.float64).reshape(10, 10)
        # Add extreme high outlier
        data[9, 9] = 100000.0
        nodata_mask = np.zeros((10, 10), dtype=bool)

        result = normalize_percentile(data, nodata_mask)

        assert result[9, 9] == 1.0

    def test_custom_percentile_bounds(self):
        """Custom low/high percentiles work correctly."""
        data = np.arange(100, dtype=np.float64).reshape(10, 10)
        nodata_mask = np.zeros((10, 10), dtype=bool)

        result = normalize_percentile(data, nodata_mask, low=10.0, high=90.0)

        assert result.dtype == np.float32
        assert result.min() >= 0.0
        assert result.max() <= 1.0
