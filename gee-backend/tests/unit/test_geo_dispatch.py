from unittest.mock import MagicMock, patch

import pytest


def test_dispatch_job_commits_before_publish_and_preserves_fast_worker_state():
    from app.domains.geo.models import EstadoGeoJob, TipoGeoJob
    from app.domains.geo.service import dispatch_job

    events: list[str] = []
    mock_db = MagicMock()
    mock_db.commit.side_effect = lambda: events.append("commit")
    mock_job = MagicMock()
    mock_job.id = "test-uuid"
    mock_job.estado = EstadoGeoJob.PENDING
    mock_result = MagicMock()
    mock_result.id = "celery-task-id"

    def publish(_payload):
        events.append("delay")
        mock_job.estado = EstadoGeoJob.RUNNING
        return mock_result

    with (
        patch("app.domains.geo.service.repo") as mock_repo,
        patch("app.domains.geo.service._get_task_dispatch_map") as mock_map,
    ):
        mock_repo.create_job.return_value = mock_job
        mock_launcher = MagicMock(side_effect=publish)
        mock_map.return_value = {TipoGeoJob.DEM_FULL_PIPELINE: mock_launcher}

        returned = dispatch_job(
            mock_db,
            tipo=TipoGeoJob.DEM_FULL_PIPELINE,
            parametros={"area_id": "zona_principal"},
        )

    assert returned is mock_job
    assert events == ["commit", "delay", "commit"]
    mock_repo.update_job_status.assert_called_once_with(
        mock_db,
        "test-uuid",
        celery_task_id="celery-task-id",
    )
    assert mock_job.estado == EstadoGeoJob.RUNNING


def test_dispatch_job_persists_failed_job_when_task_queue_fails():
    from app.domains.geo.models import EstadoGeoJob, TipoGeoJob
    from app.domains.geo.service import GeoJobDispatchError, dispatch_job

    events: list[str] = []
    publication_error = ConnectionError("redis down")
    mock_db = MagicMock()
    mock_db.commit.side_effect = lambda: events.append("commit")
    mock_job = MagicMock()
    mock_job.id = "test-uuid"

    def publish(_payload):
        events.append("delay")
        raise publication_error

    with (
        patch("app.domains.geo.service.repo") as mock_repo,
        patch("app.domains.geo.service._get_task_dispatch_map") as mock_map,
    ):
        mock_repo.create_job.return_value = mock_job
        mock_repo.update_job_status_if_current.return_value = True
        mock_launcher = MagicMock(side_effect=publish)
        mock_map.return_value = {TipoGeoJob.DEM_FULL_PIPELINE: mock_launcher}

        with pytest.raises(GeoJobDispatchError) as raised:
            dispatch_job(
                mock_db,
                tipo=TipoGeoJob.DEM_FULL_PIPELINE,
                parametros={"area_id": "zona_principal"},
            )

    assert raised.value.__cause__ is publication_error
    assert events == ["commit", "delay", "commit"]
    mock_repo.update_job_status_if_current.assert_called_once_with(
        mock_db,
        "test-uuid",
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.FAILED,
        error="Celery publication failed: ConnectionError: redis down",
    )
    mock_repo.update_job_status.assert_not_called()
    mock_db.rollback.assert_not_called()


def test_submit_pipeline_job_commits_before_publish_and_keeps_running_state():
    from app.domains.geo.models import EstadoGeoJob
    from app.domains.geo.service import submit_pipeline_job

    events: list[str] = []
    mock_db = MagicMock()
    mock_db.commit.side_effect = lambda: events.append("commit")
    mock_job = MagicMock()
    mock_job.id = "pipeline-job-id"
    mock_job.estado = EstadoGeoJob.PENDING
    mock_result = MagicMock()
    mock_result.id = "pipeline-task-id"

    def publish(**_kwargs):
        events.append("delay")
        mock_job.estado = EstadoGeoJob.RUNNING
        return mock_result

    with (
        patch("app.domains.geo.service.repo") as mock_repo,
        patch("app.domains.geo.tasks.process_dem_pipeline") as mock_task,
    ):
        mock_repo.create_job.return_value = mock_job
        mock_task.delay.side_effect = publish

        returned = submit_pipeline_job(
            mock_db,
            dem_path="/tmp/dem.tif",
            bbox=[1.0, 2.0, 3.0, 4.0],
            area_id="area-1",
        )

    assert returned is mock_job
    assert events == ["commit", "delay", "commit"]
    mock_task.delay.assert_called_once_with(
        area_id="area-1",
        dem_path="/tmp/dem.tif",
        bbox=[1.0, 2.0, 3.0, 4.0],
        job_id="pipeline-job-id",
    )
    mock_repo.update_job_status.assert_called_once_with(
        mock_db,
        "pipeline-job-id",
        celery_task_id="pipeline-task-id",
    )
    assert mock_job.estado == EstadoGeoJob.RUNNING


def test_submit_pipeline_job_reraises_publish_error_without_overwriting_claimed_job():
    from app.domains.geo.models import EstadoGeoJob
    from app.domains.geo.service import submit_pipeline_job

    events: list[str] = []
    publication_error = ConnectionError("redis down")
    mock_db = MagicMock()
    mock_db.commit.side_effect = lambda: events.append("commit")
    mock_job = MagicMock()
    mock_job.id = "pipeline-job-id"
    mock_job.estado = EstadoGeoJob.PENDING

    def publish(**_kwargs):
        events.append("delay")
        mock_job.estado = EstadoGeoJob.RUNNING
        raise publication_error

    with (
        patch("app.domains.geo.service.repo") as mock_repo,
        patch("app.domains.geo.tasks.process_dem_pipeline") as mock_task,
    ):
        mock_repo.create_job.return_value = mock_job
        mock_repo.update_job_status_if_current.return_value = False
        mock_task.delay.side_effect = publish

        with pytest.raises(ConnectionError) as raised:
            submit_pipeline_job(
                mock_db,
                dem_path="/tmp/dem.tif",
                area_id="area-1",
            )

    assert raised.value is publication_error
    assert events == ["commit", "delay", "commit"]
    mock_repo.update_job_status_if_current.assert_called_once_with(
        mock_db,
        "pipeline-job-id",
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.FAILED,
        error="Celery publication failed: ConnectionError: redis down",
    )
    mock_repo.update_job_status.assert_not_called()
    assert mock_job.estado == EstadoGeoJob.RUNNING
    mock_db.rollback.assert_not_called()
