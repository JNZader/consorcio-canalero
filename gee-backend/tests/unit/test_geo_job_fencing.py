from __future__ import annotations

import inspect
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.domains.geo.models import EstadoGeoJob, TipoGeoJob
from app.domains.geo.repository import GeoRepository
from app.domains.geo.tasks_composite_support import composite_analysis_task_impl
from app.domains.geo.tasks_io_support import (
    delineate_basins_task_impl,
    download_dem_from_gee_task_impl,
)
from app.domains.geo.tasks_dem_support import (
    process_dem_pipeline_impl,
    run_full_dem_pipeline_impl,
)


def test_repository_compare_and_set_reports_single_atomic_claim() -> None:
    db = MagicMock()
    db.execute.return_value.rowcount = 1
    repo = GeoRepository()

    assert (
        repo.update_job_status_if_current(
            db,
            uuid.uuid4(),
            expected_estado=EstadoGeoJob.PENDING,
            estado=EstadoGeoJob.RUNNING,
            progreso=0,
        )
        is True
    )

    db.execute.return_value.rowcount = 0
    assert (
        repo.update_job_status_if_current(
            db,
            uuid.uuid4(),
            expected_estado=EstadoGeoJob.PENDING,
            estado=EstadoGeoJob.RUNNING,
        )
        is False
    )


def test_late_normal_dem_task_exits_before_creating_outputs(tmp_path) -> None:
    update_job = MagicMock(return_value=False)
    get_processing = MagicMock()

    result = process_dem_pipeline_impl(
        area_id="area-1",
        dem_path=str(tmp_path / "dem.tif"),
        bbox=None,
        job_id=str(uuid.uuid4()),
        fetch_canal_geojsons=MagicMock(return_value=[]),
        fetch_propuesta_geojsons=MagicMock(return_value=[]),
        escenario_propuestas=None,
        archive_previous_output=MagicMock(return_value=None),
        run_timestamp="20260727_000000",
        burn_canals=MagicMock(),
        burn_depth_m=10.0,
        create_geo_job=MagicMock(),
        update_job=update_job,
        run_step=MagicMock(),
        get_processing=get_processing,
        register_raster_layer=MagicMock(),
        register_layer=MagicMock(),
        tipo_geo_job=TipoGeoJob,
        tipo_geo_layer=SimpleNamespace(),
        estado_geo_job=EstadoGeoJob,
        formato_geo_layer=SimpleNamespace(),
    )

    assert result["status"] == "skipped"
    assert not (tmp_path / "output").exists()
    get_processing.assert_not_called()
    update_job.assert_called_once_with(
        result["job_id"],
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.RUNNING,
        progreso=0,
    )


def test_late_full_dem_task_exits_before_destructive_cleanup() -> None:
    update_job = MagicMock(return_value=False)
    cleanup = MagicMock()
    prepare = MagicMock()
    process = MagicMock()
    basins = MagicMock()

    result = run_full_dem_pipeline_impl(
        area_id="area-1",
        min_basin_area_ha=10.0,
        job_id=str(uuid.uuid4()),
        create_geo_job=MagicMock(),
        update_job=update_job,
        cleanup_full_dem_state=cleanup,
        prepare_full_pipeline_dem=prepare,
        process_dem_pipeline=process,
        generate_auto_basins=basins,
        tipo_geo_job=TipoGeoJob,
        estado_geo_job=EstadoGeoJob,
    )

    assert result["status"] == "skipped"
    cleanup.assert_not_called()
    prepare.assert_not_called()
    process.assert_not_called()
    basins.assert_not_called()


def test_busy_area_lock_prevents_second_full_dem_execution() -> None:
    @contextmanager
    def busy_lock(area_id: str):
        yield False

    job_id = str(uuid.uuid4())
    with (
        patch("app.domains.geo.tasks._area_execution_lock", busy_lock),
        patch("app.domains.geo.tasks._update_job") as update_job,
        patch("app.domains.geo.tasks.run_full_dem_pipeline_impl") as implementation,
    ):
        from app.domains.geo.tasks import run_full_dem_pipeline

        task = getattr(run_full_dem_pipeline, "run", run_full_dem_pipeline)
        result = task(area_id="area-1", job_id=job_id)

    assert result["status"] == "skipped"
    implementation.assert_not_called()
    update_job.assert_called_once_with(
        job_id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.FAILED,
        error="Another full DEM pipeline is already running for this area",
    )


def test_update_job_requires_an_expected_state() -> None:
    from app.domains.geo.tasks import _update_job

    assert (
        inspect.signature(_update_job).parameters["expected_estado"].default
        is inspect.Parameter.empty
    )


def test_late_simple_task_exits_before_processing() -> None:
    with (
        patch("app.domains.geo.tasks._update_job", return_value=False),
        patch("app.domains.geo.tasks._get_processing") as get_processing,
    ):
        from app.domains.geo.tasks import _run_simple_processing_task

        result = _run_simple_processing_task(
            "compute_slope",
            "input.tif",
            "output.tif",
            job_id=str(uuid.uuid4()),
        )

    assert result["status"] == "skipped"
    get_processing.assert_not_called()


def test_late_download_task_exits_before_gee_or_filesystem_work() -> None:
    get_gee_service = MagicMock()
    result = download_dem_from_gee_task_impl(
        area_id="area-1",
        job_id=str(uuid.uuid4()),
        update_job=MagicMock(return_value=False),
        get_gee_service=get_gee_service,
        run_step=MagicMock(),
        get_processing=MagicMock(),
        register_layer=MagicMock(),
        tipo_geo_layer=SimpleNamespace(),
        estado_geo_job=EstadoGeoJob,
        logger=MagicMock(),
    )

    assert result["status"] == "skipped"
    get_gee_service.assert_not_called()


def test_late_basin_task_exits_before_processing_or_database_writes() -> None:
    run_step = MagicMock()
    get_db = MagicMock()
    result = delineate_basins_task_impl(
        area_id="area-1",
        flow_dir_path="/tmp/flow.tif",
        min_area_ha=10.0,
        job_id=str(uuid.uuid4()),
        store_zonas=True,
        update_job=MagicMock(return_value=False),
        run_step=run_step,
        get_processing=MagicMock(),
        register_layer=MagicMock(),
        tipo_geo_layer=SimpleNamespace(),
        formato_geo_layer=SimpleNamespace(),
        estado_geo_job=EstadoGeoJob,
        get_db=get_db,
        logger=MagicMock(),
    )

    assert result["status"] == "skipped"
    run_step.assert_not_called()
    get_db.assert_not_called()


def test_late_composite_task_exits_before_analysis_side_effects() -> None:
    get_composites = MagicMock()
    resolve_area = MagicMock()
    result = composite_analysis_task_impl(
        area_id="area-1",
        weights_flood=None,
        weights_drainage=None,
        job_id=str(uuid.uuid4()),
        create_geo_job=MagicMock(),
        update_job=MagicMock(return_value=False),
        resolve_composite_area_dir=resolve_area,
        validate_composite_prerequisites=MagicMock(),
        run_step=MagicMock(),
        get_composites=get_composites,
        register_layer=MagicMock(),
        convert_to_cog_safe=MagicMock(),
        merge_drainage_networks_if_available=MagicMock(),
        store_composite_zonal_stats=MagicMock(),
        intel_repo=MagicMock(),
        tipo_geo_job=TipoGeoJob,
        tipo_geo_layer=SimpleNamespace(),
        estado_geo_job=EstadoGeoJob,
    )

    assert result["status"] == "skipped"
    get_composites.assert_not_called()
    resolve_area.assert_not_called()
