from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.domains.geo.models import EstadoGeoJob, TipoGeoJob
from app.shared.celery_outbox import CeleryTaskKey


JOB_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OUTBOX_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


def _job_from_create(_db, **kwargs):
    return SimpleNamespace(
        id=JOB_ID,
        tipo=kwargs["tipo"],
        estado=EstadoGeoJob.PENDING,
        parametros=kwargs["parametros"],
        usuario_id=kwargs["usuario_id"],
        celery_task_id=kwargs["celery_task_id"],
    )


def test_task_key_map_covers_every_geo_job_type_exactly() -> None:
    from app.domains.geo.service import _get_task_key_map

    assert _get_task_key_map() == {
        TipoGeoJob.DEM_PIPELINE: CeleryTaskKey.PROCESS_DEM_PIPELINE,
        TipoGeoJob.SLOPE: CeleryTaskKey.COMPUTE_SLOPE,
        TipoGeoJob.ASPECT: CeleryTaskKey.COMPUTE_ASPECT,
        TipoGeoJob.FLOW_DIR: CeleryTaskKey.COMPUTE_FLOW_DIRECTION,
        TipoGeoJob.FLOW_ACC: CeleryTaskKey.COMPUTE_FLOW_ACCUMULATION,
        TipoGeoJob.TWI: CeleryTaskKey.COMPUTE_TWI,
        TipoGeoJob.HAND: CeleryTaskKey.COMPUTE_HAND,
        TipoGeoJob.DRAINAGE: CeleryTaskKey.EXTRACT_DRAINAGE_NETWORK,
        TipoGeoJob.TERRAIN_CLASS: CeleryTaskKey.CLASSIFY_TERRAIN,
        TipoGeoJob.GEE_FLOOD: CeleryTaskKey.ANALYZE_FLOOD,
        TipoGeoJob.GEE_CLASSIFICATION: CeleryTaskKey.SUPERVISED_CLASSIFICATION,
        TipoGeoJob.DEM_FULL_PIPELINE: CeleryTaskKey.RUN_FULL_DEM_PIPELINE,
        TipoGeoJob.BASIN_DELINEATION: CeleryTaskKey.DELINEATE_BASINS,
        TipoGeoJob.COMPOSITE_ANALYSIS: CeleryTaskKey.COMPOSITE_ANALYSIS,
        TipoGeoJob.ROAD_FLOW_CROSSINGS: CeleryTaskKey.COMPUTE_ROAD_FLOW_CROSSINGS,
    }


def test_dispatch_job_commits_job_and_outbox_once_before_best_effort_publish() -> None:
    from app.domains.geo.service import dispatch_job

    events: list[str] = []
    db = MagicMock()
    db.commit.side_effect = lambda: events.append("commit")
    db.refresh.side_effect = lambda _job: events.append("refresh")
    outbox = SimpleNamespace(id=OUTBOX_ID)

    with (
        patch("app.domains.geo.service.repo") as repo,
        patch("app.domains.geo.service.enqueue_celery_task") as enqueue,
        patch("app.domains.geo.service.try_publish_celery_task") as publish,
    ):

        def create_job(*args, **kwargs):
            events.append("create")
            return _job_from_create(*args, **kwargs)

        def enqueue_task(*args, **kwargs):
            events.append("enqueue")
            return outbox

        repo.create_job.side_effect = create_job
        enqueue.side_effect = enqueue_task
        publish.side_effect = lambda _outbox_id: events.append("publish") or True

        returned = dispatch_job(
            db,
            tipo=TipoGeoJob.SLOPE,
            parametros={"dem_path": "dem.tif", "output_path": "slope.tif"},
        )

    assert returned.estado == EstadoGeoJob.PENDING
    assert events == ["create", "enqueue", "commit", "refresh", "publish"]
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(returned)
    db.rollback.assert_not_called()

    create_kwargs = repo.create_job.call_args.kwargs
    task_id = uuid.UUID(create_kwargs["celery_task_id"])
    assert create_kwargs == {
        "tipo": TipoGeoJob.SLOPE,
        "parametros": {"dem_path": "dem.tif", "output_path": "slope.tif"},
        "usuario_id": None,
        "celery_task_id": str(task_id),
    }
    enqueue.assert_called_once_with(
        db,
        celery_task_id=task_id,
        task_key=CeleryTaskKey.COMPUTE_SLOPE,
        task_kwargs={
            "dem_path": "dem.tif",
            "output_path": "slope.tif",
            "job_id": str(JOB_ID),
        },
    )
    publish.assert_called_once_with(OUTBOX_ID)
    assert returned.celery_task_id == str(task_id)
    repo.update_job_status.assert_not_called()
    repo.update_job_status_if_current.assert_not_called()


def test_dispatch_job_returns_durable_pending_when_broker_is_unavailable() -> None:
    from app.domains.geo.service import dispatch_job

    db = MagicMock()
    outbox = SimpleNamespace(id=OUTBOX_ID)
    with (
        patch("app.domains.geo.service.repo") as repo,
        patch("app.domains.geo.service.enqueue_celery_task", return_value=outbox),
        patch("app.domains.geo.service.try_publish_celery_task", return_value=False) as publish,
    ):
        repo.create_job.side_effect = _job_from_create
        job = dispatch_job(
            db,
            tipo=TipoGeoJob.DEM_FULL_PIPELINE,
            parametros={"area_id": "zona_principal"},
        )

    assert job.estado == EstadoGeoJob.PENDING
    assert uuid.UUID(job.celery_task_id)
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(job)
    publish.assert_called_once_with(OUTBOX_ID)
    repo.update_job_status.assert_not_called()
    repo.update_job_status_if_current.assert_not_called()


def test_dispatch_job_contains_unexpected_immediate_publish_error() -> None:
    from app.domains.geo.service import dispatch_job

    db = MagicMock()
    outbox = SimpleNamespace(id=OUTBOX_ID)
    with (
        patch("app.domains.geo.service.repo") as repo,
        patch("app.domains.geo.service.enqueue_celery_task", return_value=outbox),
        patch(
            "app.domains.geo.service.try_publish_celery_task",
            side_effect=ConnectionError("redis password=secret"),
        ),
    ):
        repo.create_job.side_effect = _job_from_create
        job = dispatch_job(db, tipo=TipoGeoJob.ASPECT, parametros={})

    assert job.estado == EstadoGeoJob.PENDING
    db.commit.assert_called_once_with()
    repo.update_job_status_if_current.assert_not_called()


def test_dispatch_job_rolls_back_atomic_transaction_on_commit_failure() -> None:
    from app.domains.geo.service import dispatch_job

    commit_error = RuntimeError("commit failed")
    db = MagicMock()
    db.commit.side_effect = commit_error
    outbox = SimpleNamespace(id=OUTBOX_ID)

    with (
        patch("app.domains.geo.service.repo") as repo,
        patch("app.domains.geo.service.enqueue_celery_task", return_value=outbox) as enqueue,
        patch("app.domains.geo.service.try_publish_celery_task") as publish,
    ):
        repo.create_job.side_effect = _job_from_create
        with pytest.raises(RuntimeError) as raised:
            dispatch_job(db, tipo=TipoGeoJob.TWI, parametros={})

    assert raised.value is commit_error
    enqueue.assert_called_once()
    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()
    publish.assert_not_called()


def test_dispatch_job_does_not_mask_commit_error_when_rollback_also_fails() -> None:
    from app.domains.geo.service import dispatch_job

    commit_error = RuntimeError("commit failed")
    db = MagicMock()
    db.commit.side_effect = commit_error
    db.rollback.side_effect = RuntimeError("rollback failed")

    with (
        patch("app.domains.geo.service.repo") as repo,
        patch(
            "app.domains.geo.service.enqueue_celery_task",
            return_value=SimpleNamespace(id=OUTBOX_ID),
        ),
        patch("app.domains.geo.service.try_publish_celery_task") as publish,
    ):
        repo.create_job.side_effect = _job_from_create
        with pytest.raises(RuntimeError) as raised:
            dispatch_job(db, tipo=TipoGeoJob.HAND, parametros={})

    assert raised.value is commit_error
    publish.assert_not_called()


@pytest.mark.parametrize("tipo", ["not-a-job", "", object()])
def test_dispatch_job_rejects_unknown_type_before_persistence(tipo) -> None:
    from app.domains.geo.service import dispatch_job

    db = MagicMock()
    with (
        patch("app.domains.geo.service.repo") as repo,
        patch("app.domains.geo.service.enqueue_celery_task") as enqueue,
        patch("app.domains.geo.service.try_publish_celery_task") as publish,
    ):
        with pytest.raises(ValueError, match="Unsupported GeoJob type"):
            dispatch_job(db, tipo=tipo, parametros={})

    repo.create_job.assert_not_called()
    enqueue.assert_not_called()
    db.commit.assert_not_called()
    publish.assert_not_called()


def test_missing_allowlist_mapping_is_rejected_before_persistence() -> None:
    from app.domains.geo.service import dispatch_job

    db = MagicMock()
    with (
        patch("app.domains.geo.service._get_task_key_map", return_value={}),
        patch("app.domains.geo.service.repo") as repo,
        patch("app.domains.geo.service.enqueue_celery_task") as enqueue,
    ):
        with pytest.raises(ValueError, match="Unsupported GeoJob type"):
            dispatch_job(db, tipo=TipoGeoJob.SLOPE, parametros={})

    repo.create_job.assert_not_called()
    enqueue.assert_not_called()
    db.commit.assert_not_called()


def test_submit_pipeline_job_delegates_once_to_generic_outbox_producer() -> None:
    from app.domains.geo.service import submit_pipeline_job

    db = MagicMock()
    user_id = uuid.uuid4()
    expected_job = SimpleNamespace(id=JOB_ID)
    with patch("app.domains.geo.service.dispatch_job", return_value=expected_job) as dispatch:
        returned = submit_pipeline_job(
            db,
            dem_path="/tmp/dem.tif",
            bbox=[1.0, 2.0, 3.0, 4.0],
            area_id="area-1",
            user_id=user_id,
        )

    assert returned is expected_job
    dispatch.assert_called_once_with(
        db,
        tipo=TipoGeoJob.DEM_PIPELINE,
        parametros={
            "dem_path": "/tmp/dem.tif",
            "bbox": [1.0, 2.0, 3.0, 4.0],
            "area_id": "area-1",
        },
        usuario_id=user_id,
    )


@pytest.mark.parametrize(
    "module_name",
    # ``app.domains.geo.router`` used to carry an un-decorated COPY of this
    # handler and was parametrized here too. The copy is gone (it was dead code
    # that shadowed the hardened originals); ``router_core`` owns the live one.
    ["app.domains.geo.router_core"],
)
def test_geo_job_router_helpers_return_accepted_pending_without_503_translation(
    module_name: str,
) -> None:
    import importlib

    from app.domains.geo.schemas import GeoJobCreate

    module = importlib.import_module(module_name)
    db = MagicMock()
    pending = SimpleNamespace(id=JOB_ID, estado=EstadoGeoJob.PENDING)
    payload = GeoJobCreate(tipo=TipoGeoJob.SLOPE, parametros={"dem_path": "dem.tif"})

    with patch.object(module, "dispatch_job", return_value=pending) as dispatch:
        returned = module.submit_geo_job(
            payload,
            db=db,
            repo=MagicMock(),
            _user=object(),
        )

    assert returned is pending
    dispatch.assert_called_once_with(
        db,
        tipo=TipoGeoJob.SLOPE,
        parametros={"dem_path": "dem.tif"},
    )
