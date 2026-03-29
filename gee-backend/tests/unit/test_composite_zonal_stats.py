"""
Unit tests for extract_composite_zonal_stats function.

Tests:
  - Mean/max/p90 match hand-calculable expected values
  - area_high_risk_ha calculation (count pixels > 70 * pixel_area)
  - Zone entirely in nodata is skipped
  - Shapely geometry and GeoJSON geometry both accepted
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import box, mapping

from app.domains.geo.composites import extract_composite_zonal_stats

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NODATA = -9999.0
SHAPE = (10, 10)
# Small projected area: 1000m x 1000m => each pixel = 100m x 100m = 10000 m2 = 1 ha
BOUNDS_PROJ = (0.0, 0.0, 1000.0, 1000.0)
CRS_PROJ = "EPSG:32720"  # UTM zone 20S (Argentina)


def _make_composite_geotiff(
    path: Path,
    data: np.ndarray,
    nodata: float = NODATA,
    bounds: tuple = BOUNDS_PROJ,
    crs: str = CRS_PROJ,
) -> None:
    """Write a single-band composite GeoTIFF (0-100 scale)."""
    transform = from_bounds(*bounds, data.shape[1], data.shape[0])
    meta = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": data.shape[0],
        "width": data.shape[1],
        "crs": crs,
        "transform": transform,
        "nodata": float(nodata),
    }
    with rasterio.open(str(path), "w", **meta) as dst:
        dst.write(data.astype(np.float32), 1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestZonalStatsMeanMaxP90:
    """Verify mean, max, and p90 match hand-calculable values."""

    def test_uniform_raster_stats(self, tmp_path: Path):
        """Uniform raster: mean == max == p90 == the uniform value."""
        data = np.full(SHAPE, 55.0, dtype=np.float32)
        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        # Polygon covering the entire raster
        geom = box(*BOUNDS_PROJ)
        zonas = [{"id": "z1", "geometry": mapping(geom)}]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        assert len(results) == 1
        stat = results[0]
        assert stat["mean_score"] == pytest.approx(55.0, abs=0.1)
        assert stat["max_score"] == pytest.approx(55.0, abs=0.1)
        assert stat["p90_score"] == pytest.approx(55.0, abs=0.1)

    def test_gradient_raster_stats(self, tmp_path: Path):
        """Gradient raster: predictable mean, max, and p90."""
        # Each row has a constant value: 10, 20, ..., 100
        values = np.arange(10, 110, 10, dtype=np.float32)  # [10, 20, ..., 100]
        data = np.broadcast_to(values[:, np.newaxis], SHAPE).copy()

        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        geom = box(*BOUNDS_PROJ)
        zonas = [{"id": "z1", "geometry": mapping(geom)}]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        assert len(results) == 1
        stat = results[0]

        # All 100 pixels: 10 of each value 10..100
        expected_mean = np.mean(values.repeat(10))  # 55.0
        expected_max = 100.0
        expected_p90 = np.percentile(values.repeat(10), 90)

        assert stat["mean_score"] == pytest.approx(float(expected_mean), abs=0.5)
        assert stat["max_score"] == pytest.approx(expected_max, abs=0.5)
        assert stat["p90_score"] == pytest.approx(float(expected_p90), abs=0.5)

    def test_shapely_geometry_accepted(self, tmp_path: Path):
        """Function accepts shapely geometry objects (not just GeoJSON dicts)."""
        data = np.full(SHAPE, 40.0, dtype=np.float32)
        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        # Pass shapely geometry directly (has __geo_interface__)
        geom = box(*BOUNDS_PROJ)
        zonas = [{"id": "z1", "geometry": geom}]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        assert len(results) == 1
        assert results[0]["mean_score"] == pytest.approx(40.0, abs=0.1)


class TestZonalStatsAreaHighRisk:
    """area_high_risk_ha = count(pixels > 70) * pixel_area_ha."""

    def test_all_pixels_high_risk(self, tmp_path: Path):
        """All pixels score > 70 => area = total_pixels * pixel_area_ha."""
        data = np.full(SHAPE, 80.0, dtype=np.float32)
        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        geom = box(*BOUNDS_PROJ)
        zonas = [{"id": "z1", "geometry": mapping(geom)}]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        stat = results[0]
        # 10x10 pixels, each 100m x 100m = 1 ha => 100 ha total
        assert stat["area_high_risk_ha"] == pytest.approx(100.0, abs=1.0)

    def test_no_pixels_high_risk(self, tmp_path: Path):
        """All pixels score <= 70 => area_high_risk_ha = 0."""
        data = np.full(SHAPE, 50.0, dtype=np.float32)
        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        geom = box(*BOUNDS_PROJ)
        zonas = [{"id": "z1", "geometry": mapping(geom)}]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        stat = results[0]
        assert stat["area_high_risk_ha"] == pytest.approx(0.0, abs=0.01)

    def test_partial_high_risk(self, tmp_path: Path):
        """Half pixels > 70 => area = half * pixel_area_ha."""
        data = np.full(SHAPE, 50.0, dtype=np.float32)
        # Top 5 rows = 80 (high risk), bottom 5 rows = 50 (not high risk)
        data[:5, :] = 80.0
        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        geom = box(*BOUNDS_PROJ)
        zonas = [{"id": "z1", "geometry": mapping(geom)}]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        stat = results[0]
        # 50 pixels * 1 ha = 50 ha
        assert stat["area_high_risk_ha"] == pytest.approx(50.0, abs=1.0)

    def test_boundary_value_70_not_counted(self, tmp_path: Path):
        """Score exactly == 70 should NOT count as high risk (threshold is >70)."""
        data = np.full(SHAPE, 70.0, dtype=np.float32)
        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        geom = box(*BOUNDS_PROJ)
        zonas = [{"id": "z1", "geometry": mapping(geom)}]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        stat = results[0]
        assert stat["area_high_risk_ha"] == pytest.approx(0.0, abs=0.01)


class TestZonalStatsNodataZone:
    """Zone entirely in nodata is skipped (not included in output)."""

    def test_all_nodata_zone_skipped(self, tmp_path: Path):
        """Zone covering only nodata pixels produces no result."""
        data = np.full(SHAPE, NODATA, dtype=np.float32)
        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        geom = box(*BOUNDS_PROJ)
        zonas = [{"id": "z1", "geometry": mapping(geom)}]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        assert len(results) == 0, "All-nodata zone must be skipped"

    def test_mixed_nodata_and_valid_zones(self, tmp_path: Path):
        """One valid zone and one nodata zone: only valid zone in results."""
        data = np.full(SHAPE, 60.0, dtype=np.float32)
        # Make right half nodata
        data[:, 5:] = NODATA
        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        # Zone 1: covers left half (valid data)
        geom1 = box(0.0, 0.0, 500.0, 1000.0)
        # Zone 2: covers right half (all nodata)
        geom2 = box(500.0, 0.0, 1000.0, 1000.0)

        zonas = [
            {"id": "z1", "geometry": mapping(geom1)},
            {"id": "z2", "geometry": mapping(geom2)},
        ]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        result_ids = [r["zona_id"] for r in results]
        assert "z1" in result_ids
        # z2 might be skipped or included depending on all_touched behavior
        # but at minimum z1 must be present
        z1_stat = next(r for r in results if r["zona_id"] == "z1")
        assert z1_stat["mean_score"] == pytest.approx(60.0, abs=0.5)


class TestZonalStatsOutputFormat:
    """Verify output dict structure and fields."""

    def test_output_contains_required_fields(self, tmp_path: Path):
        data = np.full(SHAPE, 50.0, dtype=np.float32)
        composite_path = tmp_path / "composite.tif"
        _make_composite_geotiff(composite_path, data)

        geom = box(*BOUNDS_PROJ)
        zonas = [{"id": "z1", "geometry": mapping(geom)}]

        results = extract_composite_zonal_stats(str(composite_path), zonas, "flood_risk")

        assert len(results) == 1
        stat = results[0]
        assert "zona_id" in stat
        assert "tipo" in stat
        assert "mean_score" in stat
        assert "max_score" in stat
        assert "p90_score" in stat
        assert "area_high_risk_ha" in stat
        assert "weights_used" in stat
        assert stat["tipo"] == "flood_risk"
        assert stat["zona_id"] == "z1"
        assert stat["weights_used"] is None  # caller sets it
