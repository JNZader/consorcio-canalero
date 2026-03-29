"""
Tests for Phase 1 bug fixes in the geo domain.

Covers:
  - TipoGeoJob enum has all expected values including GEE types
  - dispatch_job maps every TipoGeoJob to a Celery task
  - compute_hand task signature matches processing.compute_hand
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Task 1.1: TipoGeoJob enum completeness
# ---------------------------------------------------------------------------


class TestTipoGeoJobEnum:
    """Verify TipoGeoJob contains all required values."""

    def test_has_gee_flood(self):
        from app.domains.geo.models import TipoGeoJob

        assert hasattr(TipoGeoJob, "GEE_FLOOD")
        assert TipoGeoJob.GEE_FLOOD.value == "gee_flood"

    def test_has_gee_classification(self):
        from app.domains.geo.models import TipoGeoJob

        assert hasattr(TipoGeoJob, "GEE_CLASSIFICATION")
        assert TipoGeoJob.GEE_CLASSIFICATION.value == "gee_classification"

    def test_all_expected_values_present(self):
        from app.domains.geo.models import TipoGeoJob

        expected = {
            "dem_pipeline",
            "slope",
            "aspect",
            "flow_dir",
            "flow_acc",
            "twi",
            "hand",
            "drainage",
            "terrain_class",
            "gee_flood",
            "gee_classification",
            "dem_full_pipeline",
            "basin_delineation",
            "composite_analysis",
        }
        actual = {member.value for member in TipoGeoJob}
        assert expected == actual


# ---------------------------------------------------------------------------
# Task 1.2: dispatch_job maps all TipoGeoJob values
# ---------------------------------------------------------------------------


class TestDispatchJobMapping:
    """Verify the task dispatch map covers every TipoGeoJob value."""

    @patch("app.domains.geo.service.repo")
    def test_dispatch_map_covers_all_tipos(self, mock_repo):
        """Every TipoGeoJob value must have a corresponding task launcher."""
        from app.domains.geo.models import TipoGeoJob
        from app.domains.geo.service import _get_task_dispatch_map

        dispatch_map = _get_task_dispatch_map()

        for member in TipoGeoJob:
            assert member in dispatch_map or member.value in dispatch_map, (
                f"TipoGeoJob.{member.name} ({member.value}) is not in the dispatch map"
            )

    @patch("app.domains.geo.service.repo")
    def test_dispatch_job_creates_job_and_dispatches(self, mock_repo):
        """dispatch_job should create a job record and call the task."""
        from app.domains.geo.models import TipoGeoJob
        from app.domains.geo.service import dispatch_job

        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.id = "test-uuid-1234"
        mock_repo.create_job.return_value = mock_job

        # Mock the Celery task result
        mock_celery_result = MagicMock()
        mock_celery_result.id = "celery-task-id-5678"

        with patch(
            "app.domains.geo.service._get_task_dispatch_map"
        ) as mock_map:
            mock_launcher = MagicMock(return_value=mock_celery_result)
            mock_map.return_value = {TipoGeoJob.SLOPE: mock_launcher}

            result = dispatch_job(
                mock_db,
                tipo=TipoGeoJob.SLOPE,
                parametros={"dem_path": "/tmp/dem.tif", "output_path": "/tmp/slope.tif"},
            )

        # Job was created
        mock_repo.create_job.assert_called_once()
        # Task was dispatched
        mock_launcher.assert_called_once()
        # celery_task_id was stored
        mock_repo.update_job_status.assert_called_once()
        call_kwargs = mock_repo.update_job_status.call_args
        assert call_kwargs[1]["celery_task_id"] == "celery-task-id-5678"

    @patch("app.domains.geo.service.repo")
    def test_dispatch_job_unknown_tipo_still_creates_job(self, mock_repo):
        """An unmapped tipo should still create the job, just skip dispatch."""
        from app.domains.geo.service import dispatch_job

        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.id = "test-uuid"
        mock_repo.create_job.return_value = mock_job

        with patch(
            "app.domains.geo.service._get_task_dispatch_map"
        ) as mock_map:
            mock_map.return_value = {}  # empty map

            result = dispatch_job(
                mock_db,
                tipo="nonexistent_tipo",
                parametros={},
            )

        mock_repo.create_job.assert_called_once()
        # No task dispatched, so update_job_status should NOT be called
        mock_repo.update_job_status.assert_not_called()


# ---------------------------------------------------------------------------
# Task 1.3: compute_hand task signature fix
# ---------------------------------------------------------------------------


class TestComputeHandTaskSignature:
    """Verify compute_hand Celery task has correct parameters."""

    def test_task_signature_matches_processing(self):
        """Task params (minus job_id) should match processing.compute_hand."""
        from app.domains.geo.tasks import compute_hand as task_fn

        sig = inspect.signature(task_fn)
        task_params = list(sig.parameters.keys())

        # Expected: dem_path, flow_dir_path, flow_acc_path, output_path, job_id
        assert "dem_path" in task_params
        assert "flow_dir_path" in task_params
        assert "flow_acc_path" in task_params
        assert "output_path" in task_params
        assert "job_id" in task_params

        # Must NOT have the old wrong param name
        assert "drainage_path" not in task_params

    def test_task_does_not_pass_output_path_twice(self):
        """The task must call processing.compute_hand with correct 4 args."""
        from app.domains.geo.tasks import compute_hand as task_fn

        mock_processing = MagicMock()
        mock_processing.compute_hand.return_value = "/tmp/hand.tif"

        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            result = task_fn(
                dem_path="/tmp/dem.tif",
                flow_dir_path="/tmp/flow_dir.tif",
                flow_acc_path="/tmp/flow_acc.tif",
                output_path="/tmp/hand.tif",
            )

        mock_processing.compute_hand.assert_called_once_with(
            "/tmp/dem.tif",
            "/tmp/flow_dir.tif",
            "/tmp/flow_acc.tif",
            "/tmp/hand.tif",
        )
        assert result == {"output_path": "/tmp/hand.tif"}
