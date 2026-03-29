"""
Integration test for composite_analysis_task (Celery task).

Since the full task depends on DB, Celery, GEE worker, and PostGIS,
we mock the heavy infrastructure and verify the task orchestrates
the composites module functions in the correct order.

Tests:
  - Task calls compute_flood_risk then compute_drainage_need
  - Task registers GeoLayer records for both composites
  - Task calls extract_composite_zonal_stats for both composites
  - Task updates job status through the lifecycle
  - Task handles missing prerequisite layers gracefully
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# The composite_analysis_task imports IntelligenceRepository, to_shape, and
# shapely_mapping locally inside the function body. We cannot patch them on
# the tasks module. Instead, we inject mocks into the source modules so the
# local imports find them.
# ---------------------------------------------------------------------------


def _setup_mock_intelligence_module():
    """Ensure app.domains.geo.intelligence.repository is importable with a mock."""
    mock_repo_cls = MagicMock()
    mock_repo_instance = MagicMock()
    mock_repo_instance.get_zonas.return_value = ([], 0)
    mock_repo_cls.return_value = mock_repo_instance

    mock_module = MagicMock()
    mock_module.IntelligenceRepository = mock_repo_cls

    # Also mock the models module for CompositeZonalStats
    mock_models = MagicMock()

    return mock_repo_cls, mock_repo_instance, mock_module, mock_models


@pytest.fixture()
def mock_infrastructure(tmp_path):
    """Mock all infrastructure deps: DB, Celery, repositories."""
    patches = {}

    # Mock _get_db to return a mock session
    mock_db = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.close = MagicMock()
    mock_db.add_all = MagicMock()

    p_get_db = patch("app.domains.geo.tasks._get_db", return_value=mock_db)
    patches["_get_db"] = p_get_db

    # Mock _update_job
    p_update_job = patch("app.domains.geo.tasks._update_job")
    patches["_update_job"] = p_update_job

    # Mock _register_layer
    p_register_layer = patch(
        "app.domains.geo.tasks._register_layer",
        return_value=str(uuid.uuid4()),
    )
    patches["_register_layer"] = p_register_layer

    # Mock _convert_to_cog_safe
    p_cog = patch(
        "app.domains.geo.tasks._convert_to_cog_safe",
        return_value="/tmp/fake_cog.tif",
    )
    patches["_convert_to_cog"] = p_cog

    # Mock _run_step to just call the function
    def run_step_passthrough(job_id, step_name, fn, args, kwargs=None):
        kwargs = kwargs or {}
        return fn(*args, **kwargs)

    p_run_step = patch(
        "app.domains.geo.tasks._run_step",
        side_effect=run_step_passthrough,
    )
    patches["_run_step"] = p_run_step

    # Mock repo
    mock_repo = MagicMock()
    p_repo = patch("app.domains.geo.tasks.repo", mock_repo)
    patches["repo"] = p_repo

    # Mock intelligence modules (local imports in task body)
    mock_intel_cls, mock_intel_instance, mock_intel_module, mock_intel_models = (
        _setup_mock_intelligence_module()
    )

    intel_repo_key = "app.domains.geo.intelligence.repository"
    intel_models_key = "app.domains.geo.intelligence.models"

    # Inject mock modules into sys.modules so local imports find them
    original_intel_repo = sys.modules.get(intel_repo_key)
    original_intel_models = sys.modules.get(intel_models_key)
    mock_intel_module.IntelligenceRepository = mock_intel_cls
    sys.modules[intel_repo_key] = mock_intel_module
    sys.modules[intel_models_key] = mock_intel_models

    # Mock geoalchemy2.shape.to_shape and shapely.geometry.mapping
    p_to_shape = patch("geoalchemy2.shape.to_shape", return_value=MagicMock())
    patches["to_shape"] = p_to_shape

    started = {k: v.start() for k, v in patches.items()}

    yield {
        "db": mock_db,
        "update_job": started["_update_job"],
        "register_layer": started["_register_layer"],
        "convert_to_cog": started["_convert_to_cog"],
        "run_step": started["_run_step"],
        "repo": started["repo"],
        "intel_cls": mock_intel_cls,
        "intel_instance": mock_intel_instance,
        "intel_models": mock_intel_models,
    }

    for p in patches.values():
        p.stop()

    # Restore original sys.modules
    if original_intel_repo is not None:
        sys.modules[intel_repo_key] = original_intel_repo
    else:
        sys.modules.pop(intel_repo_key, None)
    if original_intel_models is not None:
        sys.modules[intel_models_key] = original_intel_models
    else:
        sys.modules.pop(intel_models_key, None)


def _setup_area(tmp_path: Path) -> Path:
    """Create area dir with all prerequisite files."""
    area_dir = tmp_path / "test_area"
    area_dir.mkdir(exist_ok=True)
    for f in ["hand.tif", "twi.tif", "flow_acc.tif", "slope.tif", "drainage.tif"]:
        (area_dir / f).touch()
    return area_dir


def _setup_composites_mock(area_dir: Path) -> MagicMock:
    """Create mock composites module."""
    mock_composites = MagicMock()
    mock_composites.compute_flood_risk.return_value = str(area_dir / "flood_risk.tif")
    mock_composites.compute_drainage_need.return_value = str(area_dir / "drainage_need.tif")
    mock_composites.extract_composite_zonal_stats.return_value = []
    mock_composites.DEFAULT_FLOOD_WEIGHTS = {
        "twi": 0.35, "hand": 0.25, "flow_acc": 0.25, "slope": 0.15,
    }
    mock_composites.DEFAULT_DRAINAGE_WEIGHTS = {
        "flow_acc": 0.30, "twi": 0.25, "hand": 0.25, "dist_drainage": 0.20,
    }
    return mock_composites


class TestCompositeAnalysisTaskOrchestration:
    """Verify the task calls composites functions in correct order."""

    @patch("app.domains.geo.tasks._get_composites")
    def test_calls_flood_risk_then_drainage_need(
        self, mock_get_composites, mock_infrastructure, tmp_path
    ):
        """Task must call compute_flood_risk BEFORE compute_drainage_need."""
        from app.domains.geo.tasks import composite_analysis_task

        area_dir = _setup_area(tmp_path)
        mock_infrastructure["repo"].get_layers.return_value = (
            [MagicMock(archivo_path=str(area_dir / "hand.tif"))], 1,
        )
        mock_composites = _setup_composites_mock(area_dir)
        mock_get_composites.return_value = mock_composites

        job_id = str(uuid.uuid4())
        result = composite_analysis_task(area_id="test-area", job_id=job_id)

        assert result["status"] == "completed"
        mock_composites.compute_flood_risk.assert_called_once()
        mock_composites.compute_drainage_need.assert_called_once()

        # Verify order via _run_step call sequence
        flood_idx = drain_idx = None
        for i, c in enumerate(mock_infrastructure["run_step"].call_args_list):
            if c[0][1] == "compute_flood_risk":
                flood_idx = i
            elif c[0][1] == "compute_drainage_need":
                drain_idx = i

        assert flood_idx is not None, "compute_flood_risk not called via _run_step"
        assert drain_idx is not None, "compute_drainage_need not called via _run_step"
        assert flood_idx < drain_idx, "flood_risk must be called before drainage_need"

    @patch("app.domains.geo.tasks._get_composites")
    def test_registers_geo_layers_for_both_composites(
        self, mock_get_composites, mock_infrastructure, tmp_path
    ):
        """Task must register GeoLayer records for FLOOD_RISK and DRAINAGE_NEED."""
        from app.domains.geo.tasks import composite_analysis_task
        from app.domains.geo.models import TipoGeoLayer

        area_dir = _setup_area(tmp_path)
        mock_infrastructure["repo"].get_layers.return_value = (
            [MagicMock(archivo_path=str(area_dir / "hand.tif"))], 1,
        )
        mock_composites = _setup_composites_mock(area_dir)
        mock_get_composites.return_value = mock_composites

        composite_analysis_task(area_id="test-area", job_id=str(uuid.uuid4()))

        register_calls = mock_infrastructure["register_layer"].call_args_list
        assert len(register_calls) == 2

        tipos = [c.kwargs.get("tipo") for c in register_calls]
        assert TipoGeoLayer.FLOOD_RISK in tipos
        assert TipoGeoLayer.DRAINAGE_NEED in tipos

    @patch("app.domains.geo.tasks._get_composites")
    def test_extracts_zonal_stats_for_both_composites(
        self, mock_get_composites, mock_infrastructure, tmp_path
    ):
        """When zonas exist, zonal stats are extracted for both composites."""
        from app.domains.geo.tasks import composite_analysis_task

        area_dir = _setup_area(tmp_path)
        mock_infrastructure["repo"].get_layers.return_value = (
            [MagicMock(archivo_path=str(area_dir / "hand.tif"))], 1,
        )

        mock_composites = _setup_composites_mock(area_dir)
        mock_composites.extract_composite_zonal_stats.return_value = [
            {
                "zona_id": "z1", "tipo": "flood_risk",
                "mean_score": 50.0, "max_score": 80.0, "p90_score": 70.0,
                "area_high_risk_ha": 10.0, "weights_used": None,
            },
        ]
        mock_get_composites.return_value = mock_composites

        # Set up zonas
        mock_zona = MagicMock()
        mock_zona.id = uuid.uuid4()
        mock_zona.nombre = "Zona 1"
        mock_infrastructure["intel_instance"].get_zonas.return_value = ([mock_zona], 1)

        composite_analysis_task(area_id="test-area", job_id=str(uuid.uuid4()))

        assert mock_composites.extract_composite_zonal_stats.call_count == 2
        call_tipos = [
            c[0][2] for c in mock_composites.extract_composite_zonal_stats.call_args_list
        ]
        assert "flood_risk" in call_tipos
        assert "drainage_need" in call_tipos


class TestCompositeAnalysisTaskJobLifecycle:
    """Verify job status updates through the task lifecycle."""

    @patch("app.domains.geo.tasks._get_composites")
    def test_job_status_progression(
        self, mock_get_composites, mock_infrastructure, tmp_path
    ):
        """Job must go: RUNNING -> progress updates -> COMPLETED."""
        from app.domains.geo.tasks import composite_analysis_task
        from app.domains.geo.models import EstadoGeoJob

        area_dir = _setup_area(tmp_path)
        mock_infrastructure["repo"].get_layers.return_value = (
            [MagicMock(archivo_path=str(area_dir / "hand.tif"))], 1,
        )
        mock_composites = _setup_composites_mock(area_dir)
        mock_get_composites.return_value = mock_composites

        job_id = str(uuid.uuid4())
        composite_analysis_task(area_id="test-area", job_id=job_id)

        update_calls = mock_infrastructure["update_job"].call_args_list

        # First call: RUNNING status
        first_call = update_calls[0]
        assert first_call == call(job_id, estado=EstadoGeoJob.RUNNING, progreso=0)

        # Last call: COMPLETED status
        last_call = update_calls[-1]
        last_kwargs = last_call.kwargs if last_call.kwargs else {}
        # _update_job is called with positional + keyword args
        assert last_kwargs.get("estado") == EstadoGeoJob.COMPLETED or (
            len(last_call.args) > 1 and last_call.args[1] == EstadoGeoJob.COMPLETED
        )

    @patch("app.domains.geo.tasks._get_composites")
    def test_missing_prerequisite_fails_job(
        self, mock_get_composites, mock_infrastructure, tmp_path
    ):
        """If prerequisite layers are missing, task raises and marks job as FAILED."""
        from app.domains.geo.tasks import composite_analysis_task
        from app.domains.geo.models import EstadoGeoJob

        area_dir = tmp_path / "empty_area"
        area_dir.mkdir()
        # No prerequisite files created

        mock_infrastructure["repo"].get_layers.return_value = (
            [MagicMock(archivo_path=str(area_dir / "hand.tif"))], 1,
        )
        mock_get_composites.return_value = MagicMock()

        job_id = str(uuid.uuid4())
        with pytest.raises(FileNotFoundError, match="Missing prerequisite layers"):
            composite_analysis_task(area_id="test-area", job_id=job_id)

        # Job must be marked as FAILED
        failed_calls = [
            c for c in mock_infrastructure["update_job"].call_args_list
            if c.kwargs.get("estado") == EstadoGeoJob.FAILED
        ]
        assert len(failed_calls) > 0, "Job must be marked FAILED on prerequisite error"
