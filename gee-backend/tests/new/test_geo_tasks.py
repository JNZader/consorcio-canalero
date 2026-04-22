"""Tests for geo/tasks.py — Celery task functions with mocked processing and DB.

Covers: helper functions, individual analysis tasks, pipeline orchestration,
DEM full pipeline, composite analysis, rainfall tasks.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_celery_app():
    """Neuter the celery_app.task decorator so tasks are plain functions."""
    with patch("app.core.celery_app.celery_app") as mock_app:
        # Make @celery_app.task(...) return the original function
        mock_app.task = lambda *a, **kw: (lambda fn: fn)
        yield mock_app


@pytest.fixture
def mock_processing():
    proc = MagicMock()
    proc.compute_slope.return_value = "/out/slope.tif"
    proc.compute_aspect.return_value = "/out/aspect.tif"
    proc.compute_flow_direction.return_value = "/out/flow_dir.tif"
    proc.compute_flow_accumulation.return_value = "/out/flow_acc.tif"
    proc.compute_twi.return_value = "/out/twi.tif"
    proc.compute_hand.return_value = "/out/hand.tif"
    proc.extract_drainage_network.return_value = "/out/drainage.geojson"
    proc.compute_profile_curvature.return_value = "/out/profile_curvature.tif"
    proc.compute_tpi.return_value = "/out/tpi.tif"
    proc.classify_terrain.return_value = "/out/terrain_class.tif"
    proc.fill_sinks.return_value = "/out/dem_filled.tif"
    proc.clip_dem.return_value = "/out/dem_clipped.tif"
    proc.convert_to_cog.return_value = "/out/cog.tif"
    proc.download_dem_from_gee.return_value = "/data/geo/area1/dem_raw.tif"
    proc.delineate_basins.return_value = "/out/basins.geojson"
    proc.ensure_nodata.return_value = "/out/dem_nodata.tif"
    proc.reproject_to_utm.return_value = "/out/dem_utm.tif"
    proc.clip_to_geometry.return_value = "/out/dem_clipped.tif"
    return proc


@pytest.fixture
def mock_db():
    session = MagicMock()
    return session


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.create_job.return_value = SimpleNamespace(id=uuid.uuid4())
    repo.upsert_layer.return_value = SimpleNamespace(id=uuid.uuid4())
    repo.get_layers.return_value = (
        [SimpleNamespace(archivo_path="/data/geo/area1/output/hand.tif")],
        1,
    )
    return repo


def _reload_tasks(mock_processing, mock_db, mock_repo):
    """Import tasks module with all heavy deps mocked."""
    import importlib

    with (
        patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
        patch("app.domains.geo.tasks._get_db", return_value=mock_db),
        patch("app.domains.geo.tasks.repo", mock_repo),
    ):
        import app.domains.geo.tasks as tasks_mod

        importlib.reload(tasks_mod)
    return tasks_mod


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_update_job_calls_repo_and_commits(self, mock_db, mock_repo):
        with (
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
        ):
            from app.domains.geo.tasks import _update_job

            job_id = str(uuid.uuid4())
            _update_job(job_id, estado="running")
            mock_repo.update_job_status.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.close.assert_called_once()

    def test_update_job_closes_db_on_error(self, mock_db, mock_repo):
        mock_repo.update_job_status.side_effect = RuntimeError("boom")
        with (
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
        ):
            from app.domains.geo.tasks import _update_job

            with pytest.raises(RuntimeError):
                _update_job(str(uuid.uuid4()), estado="running")
            mock_db.close.assert_called_once()

    def test_register_layer_upserts_and_returns_id(self, mock_db, mock_repo):
        layer_id = uuid.uuid4()
        mock_repo.upsert_layer.return_value = SimpleNamespace(id=layer_id)
        with (
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
        ):
            from app.domains.geo.tasks import _register_layer

            result = _register_layer(
                nombre="slope_area1",
                tipo="slope",
                archivo_path="/out/slope.tif",
            )
            assert result == str(layer_id)
            mock_db.commit.assert_called_once()
            mock_db.close.assert_called_once()

    def test_register_layer_closes_db_on_error(self, mock_db, mock_repo):
        mock_repo.upsert_layer.side_effect = RuntimeError("db error")
        with (
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
        ):
            from app.domains.geo.tasks import _register_layer

            with pytest.raises(RuntimeError):
                _register_layer(nombre="x", tipo="x", archivo_path="/x")
            mock_db.close.assert_called_once()

    def test_convert_to_cog_safe_returns_path_on_success(self, mock_processing):
        mock_processing.convert_to_cog.return_value = "/out/cog.tif"
        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            from app.domains.geo.tasks import _convert_to_cog_safe

            result = _convert_to_cog_safe("/out/slope.tif")
            assert result == "/out/cog.tif"

    def test_convert_to_cog_safe_returns_none_on_failure(self, mock_processing):
        mock_processing.convert_to_cog.side_effect = RuntimeError("fail")
        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            from app.domains.geo.tasks import _convert_to_cog_safe

            result = _convert_to_cog_safe("/bad.tif")
            assert result is None

    def test_run_step_success(self):
        from app.domains.geo.tasks import _run_step

        fn = MagicMock(return_value="/out.tif")
        result = _run_step("job-1", "test_step", fn, ("a", "b"))
        assert result == "/out.tif"
        fn.assert_called_once_with("a", "b")

    def test_run_step_failure_raises(self):
        from app.domains.geo.tasks import _run_step

        fn = MagicMock(side_effect=ValueError("broken"))
        with pytest.raises(ValueError, match="broken"):
            _run_step("job-1", "test_step", fn, ("a",))

    def test_run_step_with_kwargs(self):
        from app.domains.geo.tasks import _run_step

        fn = MagicMock(return_value="ok")
        _run_step("job-1", "step", fn, ("a",), {"key": "val"})
        fn.assert_called_once_with("a", key="val")


# ---------------------------------------------------------------------------
# Individual analysis task tests
# ---------------------------------------------------------------------------


class TestIndividualTasks:
    """Tests for single-step Celery tasks (compute_slope, aspect, etc.)."""

    def test_compute_slope_without_job_id(self, mock_processing, mock_db, mock_repo):
        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
        ):
            from app.domains.geo.tasks import compute_slope

            result = compute_slope("/in.tif", "/out.tif")
            assert result == {"output_path": "/out/slope.tif"}
            mock_processing.compute_slope.assert_called_once_with("/in.tif", "/out.tif")

    def test_compute_slope_with_job_id(self, mock_processing, mock_db, mock_repo):
        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._update_job") as mock_update,
        ):
            from app.domains.geo.tasks import compute_slope

            job_id = str(uuid.uuid4())
            result = compute_slope("/in.tif", "/out.tif", job_id=job_id)
            assert result == {"output_path": "/out/slope.tif"}
            assert mock_update.call_count == 2  # RUNNING + COMPLETED

    def test_compute_slope_failure_updates_job(self, mock_processing, mock_db, mock_repo):
        mock_processing.compute_slope.side_effect = RuntimeError("fail")
        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._update_job") as mock_update,
        ):
            from app.domains.geo.tasks import compute_slope

            job_id = str(uuid.uuid4())
            with pytest.raises(RuntimeError):
                compute_slope("/in.tif", "/out.tif", job_id=job_id)
            # Should update to RUNNING then FAILED
            assert mock_update.call_count == 2

    def test_compute_aspect_without_job_id(self, mock_processing):
        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            from app.domains.geo.tasks import compute_aspect

            result = compute_aspect("/in.tif", "/out.tif")
            assert result == {"output_path": "/out/aspect.tif"}

    def test_compute_aspect_with_job_id(self, mock_processing):
        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._update_job") as mock_update,
        ):
            from app.domains.geo.tasks import compute_aspect

            result = compute_aspect("/in.tif", "/out.tif", job_id="j1")
            assert "output_path" in result
            assert mock_update.call_count == 2

    def test_compute_flow_direction(self, mock_processing):
        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            from app.domains.geo.tasks import compute_flow_direction

            result = compute_flow_direction("/in.tif", "/out.tif")
            assert result == {"output_path": "/out/flow_dir.tif"}

    def test_compute_flow_direction_with_job_id_failure(self, mock_processing):
        mock_processing.compute_flow_direction.side_effect = ValueError("err")
        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._update_job"),
        ):
            from app.domains.geo.tasks import compute_flow_direction

            with pytest.raises(ValueError):
                compute_flow_direction("/in.tif", "/out.tif", job_id="j1")

    def test_compute_flow_accumulation(self, mock_processing):
        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            from app.domains.geo.tasks import compute_flow_accumulation

            result = compute_flow_accumulation("/in.tif", "/out.tif")
            assert result == {"output_path": "/out/flow_acc.tif"}

    def test_compute_twi(self, mock_processing):
        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            from app.domains.geo.tasks import compute_twi

            result = compute_twi("/slope.tif", "/flow.tif", "/out.tif")
            assert result == {"output_path": "/out/twi.tif"}

    def test_compute_hand(self, mock_processing):
        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            from app.domains.geo.tasks import compute_hand

            result = compute_hand("/dem.tif", "/flow_dir.tif", "/flow_acc.tif", "/out.tif")
            assert result == {"output_path": "/out/hand.tif"}

    def test_extract_drainage_network(self, mock_processing):
        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            from app.domains.geo.tasks import extract_drainage_network

            result = extract_drainage_network("/flow_acc.tif", 1000, "/out.geojson")
            assert result == {"output_path": "/out/drainage.geojson"}

    def test_classify_terrain_without_job(self, mock_processing):
        with patch("app.domains.geo.tasks._get_processing", return_value=mock_processing):
            from app.domains.geo.tasks import classify_terrain

            result = classify_terrain("/filled.tif", "/outdir")
            assert result == {"output_path": "/out/terrain_class.tif"}

    def test_classify_terrain_with_all_inputs(self, mock_processing):
        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._update_job"),
        ):
            from app.domains.geo.tasks import classify_terrain

            result = classify_terrain(
                "/filled.tif",
                "/outdir",
                hand_path="/hand.tif",
                tpi_path="/tpi.tif",
                curvature_path="/curv.tif",
                flow_acc_path="/fa.tif",
                twi_path="/twi.tif",
                job_id="j1",
            )
            assert "output_path" in result


# ---------------------------------------------------------------------------
# DEM pipeline orchestrator
# ---------------------------------------------------------------------------


class TestProcessDemPipeline:
    def test_pipeline_without_bbox(self, mock_processing, mock_db, mock_repo, tmp_path):
        dem_path = str(tmp_path / "dem.tif")
        (tmp_path / "dem.tif").write_text("fake")
        (tmp_path / "output").mkdir()

        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
            patch("app.domains.geo.tasks._update_job"),
            patch("app.domains.geo.tasks._register_layer", return_value="layer-id"),
            patch("app.domains.geo.tasks._convert_to_cog_safe", return_value="/cog.tif"),
        ):
            from app.domains.geo.tasks import process_dem_pipeline

            result = process_dem_pipeline(
                area_id="area1",
                dem_path=dem_path,
                job_id=str(uuid.uuid4()),
            )
            assert result["status"] == "completed"
            assert "outputs" in result
            # No clip step was called
            mock_processing.clip_dem.assert_not_called()
            # fill_sinks should have been called
            mock_processing.fill_sinks.assert_called_once()

    def test_pipeline_with_bbox(self, mock_processing, mock_db, mock_repo, tmp_path):
        dem_path = str(tmp_path / "dem.tif")
        (tmp_path / "dem.tif").write_text("fake")
        (tmp_path / "output").mkdir()

        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
            patch("app.domains.geo.tasks._update_job"),
            patch("app.domains.geo.tasks._register_layer", return_value="layer-id"),
            patch("app.domains.geo.tasks._convert_to_cog_safe", return_value=None),
        ):
            from app.domains.geo.tasks import process_dem_pipeline

            result = process_dem_pipeline(
                area_id="area1",
                dem_path=dem_path,
                bbox=[0, 0, 1, 1],
                job_id=str(uuid.uuid4()),
            )
            assert result["status"] == "completed"
            mock_processing.clip_dem.assert_called_once()

    def test_pipeline_creates_job_when_none(self, mock_processing, mock_db, mock_repo, tmp_path):
        dem_path = str(tmp_path / "dem.tif")
        (tmp_path / "dem.tif").write_text("fake")

        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
            patch("app.domains.geo.tasks._update_job"),
            patch("app.domains.geo.tasks._register_layer", return_value="lid"),
            patch("app.domains.geo.tasks._convert_to_cog_safe", return_value=None),
        ):
            from app.domains.geo.tasks import process_dem_pipeline

            result = process_dem_pipeline(area_id="a1", dem_path=dem_path, job_id=None)
            assert result["status"] == "completed"
            mock_repo.create_job.assert_called_once()

    def test_pipeline_failure_updates_job_failed(self, mock_processing, mock_db, mock_repo, tmp_path):
        dem_path = str(tmp_path / "dem.tif")
        (tmp_path / "dem.tif").write_text("fake")
        mock_processing.fill_sinks.side_effect = RuntimeError("fill failed")

        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
            patch("app.domains.geo.tasks._update_job") as mock_update,
        ):
            from app.domains.geo.tasks import process_dem_pipeline

            with pytest.raises(RuntimeError, match="fill failed"):
                process_dem_pipeline(
                    area_id="a1", dem_path=dem_path, job_id=str(uuid.uuid4())
                )
            # Last call should be FAILED status
            last_call_kwargs = mock_update.call_args[1]
            assert "FAILED" in str(last_call_kwargs.get("estado", "")) or "error" in last_call_kwargs


# ---------------------------------------------------------------------------
# Download DEM from GEE
# ---------------------------------------------------------------------------


class TestDownloadDemFromGee:
    def test_success(self, mock_processing, mock_db, mock_repo, tmp_path):
        mock_gee = MagicMock()
        mock_gee.zona.geometry.return_value.getInfo.return_value = {"type": "Polygon", "coordinates": []}

        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._get_gee_service", return_value=mock_gee),
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
            patch("app.domains.geo.tasks._update_job"),
            patch("app.domains.geo.tasks._register_layer", return_value="lid"),
            patch("app.domains.geo.tasks._run_step", return_value="/data/dem.tif"),
            patch("pathlib.Path.mkdir"),
        ):
            from app.domains.geo.tasks import download_dem_from_gee_task

            result = download_dem_from_gee_task(area_id="a1", job_id=str(uuid.uuid4()))
            assert "dem_path" in result
            assert result["area_id"] == "a1"

    def test_failure_updates_job(self, mock_processing, mock_db, mock_repo):
        with (
            patch("app.domains.geo.tasks._get_gee_service", side_effect=RuntimeError("no gee")),
            patch("app.domains.geo.tasks._update_job") as mock_update,
        ):
            from app.domains.geo.tasks import download_dem_from_gee_task

            job_id = str(uuid.uuid4())
            with pytest.raises(RuntimeError):
                download_dem_from_gee_task(area_id="a1", job_id=job_id)
            # FAILED update
            assert any("FAILED" in str(c) or "error" in str(c) for c in mock_update.call_args_list)


# ---------------------------------------------------------------------------
# Delineate basins
# ---------------------------------------------------------------------------


class TestDelineateBasins:
    def test_without_store_zonas(self, mock_processing, mock_db, mock_repo):
        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
            patch("app.domains.geo.tasks._update_job"),
            patch("app.domains.geo.tasks._register_layer", return_value="lid"),
            patch("app.domains.geo.tasks._run_step", return_value="/out/basins.geojson"),
        ):
            from app.domains.geo.tasks import delineate_basins_task

            result = delineate_basins_task(
                area_id="a1",
                flow_dir_path="/out/flow_dir.tif",
                store_zonas=False,
                job_id=str(uuid.uuid4()),
            )
            assert "basins_geojson" in result
            assert result["zonas_created"] == 0

    def test_failure_updates_job(self, mock_processing, mock_db, mock_repo):
        with (
            patch("app.domains.geo.tasks._get_processing", return_value=mock_processing),
            patch("app.domains.geo.tasks._get_db", return_value=mock_db),
            patch("app.domains.geo.tasks.repo", mock_repo),
            patch("app.domains.geo.tasks._update_job") as mock_update,
            patch("app.domains.geo.tasks._run_step", side_effect=RuntimeError("fail")),
        ):
            from app.domains.geo.tasks import delineate_basins_task

            with pytest.raises(RuntimeError):
                delineate_basins_task("a1", "/fd.tif", job_id=str(uuid.uuid4()))
