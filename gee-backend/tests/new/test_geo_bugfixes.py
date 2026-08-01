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
    """Verify every GeoJob type resolves to a durable outbox task key."""

    def test_task_key_map_covers_all_tipos(self):
        from app.domains.geo.models import TipoGeoJob
        from app.domains.geo.service import _get_task_key_map
        from app.shared.celery_outbox import CeleryTaskKey

        task_keys = _get_task_key_map()

        assert set(task_keys) == set(TipoGeoJob)
        assert all(isinstance(task_key, CeleryTaskKey) for task_key in task_keys.values())

    @patch("app.domains.geo.service.repo")
    def test_dispatch_job_creates_job_and_outbox(self, mock_repo):
        import uuid
        from types import SimpleNamespace

        from app.domains.geo.models import EstadoGeoJob, TipoGeoJob
        from app.domains.geo.service import dispatch_job
        from app.shared.celery_outbox import CeleryTaskKey

        mock_db = MagicMock()
        job = SimpleNamespace(
            id=uuid.uuid4(),
            tipo=TipoGeoJob.SLOPE,
            estado=EstadoGeoJob.PENDING,
            celery_task_id=None,
        )

        def create_job(_db, **kwargs):
            job.celery_task_id = kwargs["celery_task_id"]
            return job

        mock_repo.create_job.side_effect = create_job
        outbox = SimpleNamespace(id=uuid.uuid4())
        with (
            patch(
                "app.domains.geo.service.enqueue_celery_task",
                return_value=outbox,
            ) as enqueue,
            patch(
                "app.domains.geo.service.try_publish_celery_task",
                return_value=False,
            ) as publish,
        ):
            returned = dispatch_job(
                mock_db,
                tipo=TipoGeoJob.SLOPE,
                parametros={"dem_path": "/tmp/dem.tif"},
            )

        assert returned is job
        task_id = uuid.UUID(job.celery_task_id)
        enqueue.assert_called_once_with(
            mock_db,
            celery_task_id=task_id,
            task_key=CeleryTaskKey.COMPUTE_SLOPE,
            task_kwargs={"dem_path": "/tmp/dem.tif", "job_id": str(job.id)},
        )
        mock_db.commit.assert_called_once_with()
        publish.assert_called_once_with(outbox.id)
        mock_repo.update_job_status.assert_not_called()

    @patch("app.domains.geo.service.repo")
    def test_dispatch_job_unknown_tipo_fails_before_create(self, mock_repo):
        from app.domains.geo.service import dispatch_job

        mock_db = MagicMock()
        with patch("app.domains.geo.service.enqueue_celery_task") as enqueue:
            try:
                dispatch_job(mock_db, tipo="nonexistent_tipo", parametros={})
            except ValueError as error:
                assert str(error) == "Unsupported GeoJob type"
            else:
                raise AssertionError("Unknown GeoJob type must be rejected")

        mock_repo.create_job.assert_not_called()
        enqueue.assert_not_called()
        mock_db.commit.assert_not_called()


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


# ---------------------------------------------------------------------------
# Composite default weights are re-exported through the composites facade
# ---------------------------------------------------------------------------


class TestCompositeDefaultWeightsReexport:
    """``tasks_composite_support`` reads ``composites.DEFAULT_*_WEIGHTS`` when a
    composite job is enqueued without explicit weights. Those constants live in
    ``composites_support`` and MUST be re-exported by the ``composites`` facade,
    or the composite_analysis task raises ``AttributeError`` after computing
    flood_risk but before registering the layer (a real prod failure)."""

    def test_default_flood_weights_accessible_via_facade(self):
        from app.domains.geo import composites

        assert isinstance(composites.DEFAULT_FLOOD_WEIGHTS, dict)
        assert composites.DEFAULT_FLOOD_WEIGHTS

    def test_default_drainage_weights_accessible_via_facade(self):
        from app.domains.geo import composites

        assert isinstance(composites.DEFAULT_DRAINAGE_WEIGHTS, dict)
        assert composites.DEFAULT_DRAINAGE_WEIGHTS

    def test_the_exact_attribute_access_that_crashed_resolves(self):
        """Mirrors tasks_composite_support.py:79,110 with weights=None."""
        from app.domains.geo import composites

        weights_flood = None
        weights_drainage = None
        assert weights_flood or composites.DEFAULT_FLOOD_WEIGHTS
        assert weights_drainage or composites.DEFAULT_DRAINAGE_WEIGHTS
