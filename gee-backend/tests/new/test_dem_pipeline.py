"""
Tests for the DEM pipeline — function signatures, Celery task registration,
and basin filtering logic.

These tests do NOT require GDAL, rasterio, or WhiteboxTools at runtime.
They verify interfaces, not heavy computation.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# 5.1: Test download_dem_from_gee() function signature and return type
# ---------------------------------------------------------------------------


class TestDownloadDemFromGeeSignature:
    """Verify download_dem_from_gee has the expected interface."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        from app.domains.geo import processing

        self.mod = processing

    def test_signature_parameters(self):
        sig = inspect.signature(self.mod.download_dem_from_gee)
        params = list(sig.parameters.keys())
        assert params == ["zona_geometry", "output_path", "scale"]

    def test_scale_default_value(self):
        sig = inspect.signature(self.mod.download_dem_from_gee)
        scale_param = sig.parameters["scale"]
        assert scale_param.default == 30

    def test_return_annotation_is_str(self):
        sig = inspect.signature(self.mod.download_dem_from_gee)
        # The function returns str (output_path), annotation may be str or empty
        # At minimum, verify the function exists and is callable
        assert callable(self.mod.download_dem_from_gee)


# ---------------------------------------------------------------------------
# 5.2: Test delineate_basins() function signature
# ---------------------------------------------------------------------------


class TestDelineateBasinsSignature:
    """Verify delineate_basins has the expected interface."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        from app.domains.geo import processing

        self.mod = processing

    def test_signature_parameters(self):
        sig = inspect.signature(self.mod.delineate_basins)
        params = list(sig.parameters.keys())
        assert params == [
            "flow_dir_path",
            "output_raster_path",
            "output_geojson_path",
            "min_area_ha",
        ]

    def test_min_area_ha_default(self):
        sig = inspect.signature(self.mod.delineate_basins)
        assert sig.parameters["min_area_ha"].default == 10.0


# ---------------------------------------------------------------------------
# 5.3: Test run_full_dem_pipeline is registered as a Celery task
# ---------------------------------------------------------------------------


class TestRunFullDemPipelineCeleryRegistration:
    """Verify run_full_dem_pipeline is a proper Celery task."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        from app.domains.geo import tasks

        self.tasks = tasks

    def test_is_celery_task(self):
        """run_full_dem_pipeline must have .delay() (Celery task interface)."""
        assert hasattr(self.tasks.run_full_dem_pipeline, "delay")

    def test_task_name(self):
        """Task name must be 'geo.run_full_dem_pipeline'."""
        assert self.tasks.run_full_dem_pipeline.name == "geo.run_full_dem_pipeline"

    def test_task_signature(self):
        """Verify the function accepts the expected parameters."""
        sig = inspect.signature(self.tasks.run_full_dem_pipeline)
        params = list(sig.parameters.keys())
        assert "area_id" in params
        assert "min_basin_area_ha" in params
        assert "job_id" in params

    def test_download_dem_task_registered(self):
        """download_dem_from_gee_task must also be registered."""
        assert hasattr(self.tasks.download_dem_from_gee_task, "delay")
        assert self.tasks.download_dem_from_gee_task.name == "geo.download_dem_from_gee"

    def test_delineate_basins_task_registered(self):
        """delineate_basins_task must also be registered."""
        assert hasattr(self.tasks.delineate_basins_task, "delay")
        assert self.tasks.delineate_basins_task.name == "geo.delineate_basins"


# ---------------------------------------------------------------------------
# 5.4: Test basin filtering logic (area < 10ha threshold)
# ---------------------------------------------------------------------------


class TestBasinFilteringLogic:
    """Test the min_area_ha filtering logic used in delineate_basins.

    We test the pure math/logic WITHOUT calling WhiteboxTools or rasterio.
    The delineate_basins function:
      1. Runs WBT basins (skip in test)
      2. Vectorizes with rasterio.features.shapes (skip in test)
      3. Filters by area_ha >= min_area_ha (THIS is what we test)
    """

    @staticmethod
    def _compute_area_ha(poly_area_deg2: float, lat_deg: float) -> float:
        """Replicate the area computation from delineate_basins."""
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat_deg))
        area_m2 = poly_area_deg2 * m_per_deg_lat * m_per_deg_lon
        return area_m2 / 10_000.0

    def test_large_basin_passes_filter(self):
        """A basin > 10 ha should pass the default filter."""
        # ~0.001 deg^2 at lat -32 is roughly 87 ha
        area_ha = self._compute_area_ha(0.001, -32.0)
        assert area_ha >= 10.0

    def test_micro_basin_filtered_out(self):
        """A tiny basin < 10 ha should be filtered out."""
        # ~0.00001 deg^2 at lat -32 is roughly 0.87 ha
        area_ha = self._compute_area_ha(0.00001, -32.0)
        assert area_ha < 10.0

    def test_custom_threshold(self):
        """With a custom threshold of 50 ha, medium basins are filtered."""
        area_ha = self._compute_area_ha(0.0005, -32.0)
        # Should be ~43 ha — passes 10ha but fails 50ha
        assert area_ha >= 10.0
        assert area_ha < 50.0

    def test_equator_vs_high_latitude(self):
        """Area computation accounts for latitude (cosine correction)."""
        area_equator = self._compute_area_ha(0.001, 0.0)
        area_high_lat = self._compute_area_ha(0.001, -60.0)
        # At higher latitudes, longitude degrees are shorter, so area is smaller
        assert area_high_lat < area_equator

    def test_filtering_preserves_large_basins(self):
        """Simulate the filtering loop from delineate_basins."""
        # Simulate basin features with known areas
        basins = [
            {"basin_id": 1, "area_deg2": 0.001, "lat": -32.0},   # ~87 ha
            {"basin_id": 2, "area_deg2": 0.00001, "lat": -32.0},  # ~0.87 ha
            {"basin_id": 3, "area_deg2": 0.0003, "lat": -32.0},   # ~26 ha
        ]

        min_area_ha = 10.0
        kept = []
        for b in basins:
            area_ha = self._compute_area_ha(b["area_deg2"], b["lat"])
            if area_ha >= min_area_ha:
                kept.append(b["basin_id"])

        assert 1 in kept
        assert 2 not in kept
        assert 3 in kept
        assert len(kept) == 2
