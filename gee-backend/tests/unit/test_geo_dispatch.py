from unittest.mock import MagicMock, patch

import pytest


def test_dispatch_job_rolls_back_when_task_queue_fails():
    """Broker/Celery failures should surface clearly and avoid stale pending jobs."""
    from app.domains.geo.models import TipoGeoJob
    from app.domains.geo.service import GeoJobDispatchError, dispatch_job

    mock_db = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "test-uuid"

    with (
        patch("app.domains.geo.service.repo") as mock_repo,
        patch("app.domains.geo.service._get_task_dispatch_map") as mock_map,
    ):
        mock_repo.create_job.return_value = mock_job
        mock_launcher = MagicMock(side_effect=ConnectionError("redis down"))
        mock_map.return_value = {TipoGeoJob.DEM_FULL_PIPELINE: mock_launcher}

        with pytest.raises(GeoJobDispatchError):
            dispatch_job(
                mock_db,
                tipo=TipoGeoJob.DEM_FULL_PIPELINE,
                parametros={"area_id": "zona_principal"},
            )

    mock_db.rollback.assert_called_once()
    mock_repo.update_job_status.assert_not_called()
