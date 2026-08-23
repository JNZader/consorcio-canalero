"""The road-crossing run itself, and the read side that serves it.

Kept out of ``tasks.py`` so the protocol is testable without a broker: the Celery
task is a three-line wrapper and every property the snapshot-copy protocol exists
for is exercised against :func:`run_crossing_task` directly.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import structlog
from sqlalchemy import text

from app.domains.geo.intelligence.cruces_camino_support import (
    CopiaCorrupta,
    DemJobEnCurso,
    VarianteNoDisponible,
    calcular_desactualizado,
    copiar_rasters_a_scratch,
    corroborar_copias,
    dem_job_ocupado,
    resolver_variante_drenaje,
    verificar_dem_libre,
)

logger = structlog.get_logger(__name__)

#: Where the private copies live. Configurable because the deployment mounts
#: ``/data/geo`` and a same-filesystem copy is a great deal cheaper than one
#: across a container boundary.
SCRATCH_ROOT = os.environ.get("CRUCES_SCRATCH_ROOT", tempfile.gettempdir())

#: The five recorded parameters, and their ``system_settings`` keys.
#:
#: ONE home (category ``analisis``, alongside the pre-existing
#: ``analisis/flow_acc_threshold``), decided so that "changeable without a code
#: change" is actually true and so that what a run RECORDS cannot depend on who
#: dispatched it. A task-parameter default is still code.
PARAMETER_KEYS: dict[str, str] = {
    "acc_threshold_cells": "analisis/cruce_acc_threshold_cells",
    "min_separation_m": "analisis/cruce_min_separation_m",
    "parallel_min_angle_deg": "analisis/cruce_parallel_min_angle_deg",
    "parallel_high_angle_deg": "analisis/cruce_parallel_high_angle_deg",
    "bearing_window_m": "analisis/cruce_bearing_window_m",
}

#: Used only if a deployment has never been seeded. Kept identical to the seeds
#: in ``SettingsService._SEED_DEFAULTS`` — the settings row is the home, this is
#: the "the row is missing" answer, not a second home.
PARAMETER_FALLBACKS: dict[str, float] = {
    "acc_threshold_cells": 1000.0,
    "min_separation_m": 90.0,
    "parallel_min_angle_deg": 22.5,
    "parallel_high_angle_deg": 45.0,
    "bearing_window_m": 60.0,
}


def leer_parametros(db) -> dict[str, float]:
    """Read the five thresholds from ``system_settings``, once per run."""
    from app.domains.settings.service import SettingsService

    settings_service = SettingsService()
    return {
        name: float(settings_service.get_setting(db, key, PARAMETER_FALLBACKS[name]))
        for name, key in PARAMETER_KEYS.items()
    }


def _raster_bbox_4326(path: str) -> tuple[float, float, float, float]:
    """The raster footprint in lon/lat, for the spatial pre-filter."""
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(path) as src:
        return transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)


def _load_lines(rows: list[dict[str, Any]]):
    import geopandas as gpd
    from shapely import wkt

    if not rows:
        return gpd.GeoDataFrame({"id": [], "geometry": []}, geometry="geometry", crs=4326)
    return gpd.GeoDataFrame(
        {
            "id": [r["id"] for r in rows],
            "geometry": [wkt.loads(r["wkt"]) for r in rows],
        },
        geometry="geometry",
        crs=4326,
    )


def _frame_to_rows(gdf) -> list[dict[str, Any]]:
    """Turn the derivation's frame into insert parameters, nulls preserved."""
    import pandas as pd

    def _clean(value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return value

    rows: list[dict[str, Any]] = []
    for _, row in gdf.iterrows():
        rank = _clean(row["orden_ranking"])
        rows.append(
            {
                "tramo_ref": row["tramo_ref"],
                "tipo": row["tipo"],
                "lon": float(row.geometry.x),
                "lat": float(row.geometry.y),
                "direccion_flujo_deg": _clean(row["direccion_flujo_deg"]),
                "rumbo_camino_deg": _clean(row["rumbo_camino_deg"]),
                "lado_cruce": _clean(row["lado_cruce"]),
                "area_aporte_ha": _clean(row["area_aporte_ha"]),
                "orden_ranking": int(rank) if rank is not None else None,
                "confianza": _clean(row["confianza"]),
                "nota": _clean(row["nota"]),
                "canal_ref": _clean(row["canal_ref"]),
            }
        )
    return rows


class _ResolverPorts:
    """The two lookups :func:`resolver_variante_drenaje` needs, in one object.

    They live on two different repositories — ``get_layer_by_nombre`` on
    ``GeoRepository`` (layers are a geo-domain concern) and
    ``get_dem_resultados`` on the intelligence one — and the resolver takes a
    single collaborator so it can be driven by a fake in a test that never opens
    a database. Composing them here beats duplicating either query.
    """

    def __init__(self, geo_repo, intel_repo) -> None:
        self._geo = geo_repo
        self._intel = intel_repo

    def get_layer_by_nombre(self, db, nombre: str):
        return self._geo.get_layer_by_nombre(db, nombre)

    def get_dem_resultados(self, db, area_id: str):
        return self._intel.get_dem_resultados(db, area_id)


def run_crossing_task(
    *,
    area_id: str,
    job_id: Optional[str],
    session_factory: Callable[[], Any],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    scratch_root: Optional[str] = None,
) -> dict[str, Any]:
    """See the Celery task's docstring for the five steps and why each exists."""
    from app.domains.geo.intelligence.calculations import detectar_cruces_camino_flujo
    from app.domains.geo.intelligence.repository import IntelligenceRepository
    from app.domains.geo.models import EstadoGeoJob, TipoGeoJob
    from app.domains.geo.repository import GeoRepository

    repo = IntelligenceRepository()
    # ``geo_jobs`` bookkeeping lives on ``GeoRepository`` -- the compare-and-set
    # ``update_job_status_if_current`` is the shared fencing primitive every geo
    # task claims through, and re-implementing it here would be a second, drifting
    # copy of the one mechanism that keeps two workers off one job.
    jobs = GeoRepository()
    scratch_root = scratch_root or SCRATCH_ROOT

    # ── Step 1: pre-check, BEFORE claiming ──────────────────────────────
    # Before the claim on purpose: refusing here transitions PENDING → FAILED,
    # so there is no window in which this task owns a RUNNING row it is about to
    # abandon.
    db = session_factory()
    try:
        # The guard predicate compares against ``geo_jobs.updated_at``, which
        # the DATABASE server stamps. Taking the mark from the worker's clock
        # would make the revalidation window depend on cross-host clock skew,
        # so the mark comes from the same clock that writes the column.
        pre_check_at = db.execute(text("SELECT now()")).scalar_one()
        if job_id is None:
            job = jobs.create_job(
                db, tipo=TipoGeoJob.ROAD_FLOW_CROSSINGS.value, parametros={"area_id": area_id}
            )
            db.commit()
            job_id = str(job.id)

        if dem_job_ocupado(db, area_id):
            _fail(
                db,
                jobs,
                job_id,
                expected=EstadoGeoJob.PENDING.value,
                motivo="dem_job_running_pre_check",
                area_id=area_id,
            )
            return {"job_id": job_id, "status": "skipped", "motivo": "dem_job_running_pre_check"}

        claimed = jobs.update_job_status_if_current(
            db,
            uuid.UUID(job_id),
            expected_estado=EstadoGeoJob.PENDING.value,
            estado=EstadoGeoJob.RUNNING.value,
            progreso=0,
        )
        db.commit()
        if not claimed:
            # The row already belongs to whoever won the fence. Writing an estado
            # here would be exactly the resurrection the compare-and-set prevents.
            logger.info("cruces_camino.not_claimed", area_id=area_id, job_id=job_id)
            return {"job_id": job_id, "status": "skipped", "motivo": "fence_lost"}

    finally:
        db.close()

    scratch = None
    try:
        # Post-claim work belongs INSIDE the handlers below: an exception here
        # used to escape past a bare ``finally: db.close()`` and strand the row
        # in RUNNING for ever.
        db = session_factory()
        try:
            parametros = leer_parametros(db)
            # ── Variant resolution ──────────────────────────────────────
            # A genuinely unavailable variant is a NAMED REFUSAL, never a
            # degraded canal-only run: the bbox is ALWAYS derived from the
            # copied raster, so no run scans the whole network, and no degraded
            # result can replace the last good set.
            variante = resolver_variante_drenaje(db, _ResolverPorts(jobs, repo), area_id=area_id)
        finally:
            db.close()

        # ── Steps 2 and 3: copy, then REVALIDATE ────────────────────────
        scratch, flow_dir_copy, flow_acc_copy = copiar_rasters_a_scratch(
            variante, scratch_root=scratch_root
        )
        db = session_factory()
        try:
            verificar_dem_libre(db, area_id, desde=pre_check_at)
        finally:
            db.close()
        corroborar_copias(flow_dir_copy, flow_acc_copy)

        # ── Step 4: compute, entirely from the private copies ───────────
        db = session_factory()
        try:
            minx, miny, maxx, maxy = _raster_bbox_4326(flow_acc_copy)
            roads = _load_lines(
                repo.get_red_vial_en_bbox(db, minx=minx, miny=miny, maxx=maxx, maxy=maxy)
            )
            canals = _load_lines(
                repo.get_canales_en_bbox(db, minx=minx, miny=miny, maxx=maxx, maxy=maxy)
            )
        finally:
            db.close()

        gdf, excluidos, run_parametros = detectar_cruces_camino_flujo(
            roads, canals, flow_dir_copy, flow_acc_copy, **parametros
        )
        run_parametros["variante"] = variante.variante
        run_parametros["area_id"] = area_id

        # ── Step 5: write, in ONE transaction ───────────────────────────
        calculada_en = now()
        rows = _frame_to_rows(gdf)
        db = session_factory()
        try:
            # Recomputation IS invalidation, so an empty result legitimately
            # replaces the set — but silently emptying a populated list is the
            # one degradation an operator cannot see from "COMPLETED, cruces: 0"
            # alone. The count-before is read inside the SAME transaction (and
            # therefore under the per-area advisory lock), so the signal names
            # exactly the set this run destroyed.
            previos = len(repo.get_cruces_for_area(db, area_id)) if not rows else 0
            repo.replace_cruces_for_area(
                db,
                area_id=area_id,
                rows=rows,
                geo_job_id=uuid.UUID(job_id),
                calculada_en=calculada_en,
            )
            resultado = {
                "area_id": area_id,
                "cruces": len(rows),
                "excluidos": excluidos,
                "parametros": run_parametros,
            }
            if not rows and previos:
                resultado["reemplazo_vacio"] = {"previos": previos}
                logger.warning(
                    "cruces_camino.reemplazo_vacio",
                    area_id=area_id,
                    previos=previos,
                    job_id=job_id,
                )
            completed = jobs.update_job_status_if_current(
                db,
                uuid.UUID(job_id),
                expected_estado=EstadoGeoJob.RUNNING.value,
                estado=EstadoGeoJob.COMPLETED.value,
                progreso=100,
                resultado=resultado,
            )
            if not completed:
                db.rollback()
                logger.warning("cruces_camino.fence_lost_at_write", area_id=area_id)
                return {"job_id": job_id, "status": "skipped", "motivo": "fence_lost"}
            db.commit()
        finally:
            db.close()

        logger.info("cruces_camino.done", area_id=area_id, cruces=len(rows))
        return {"job_id": job_id, "status": "completed", **resultado}

    except VarianteNoDisponible as exc:
        motivo = f"variante_no_disponible ({exc})"
        db = session_factory()
        try:
            _fail(
                db,
                jobs,
                job_id,
                expected=EstadoGeoJob.RUNNING.value,
                motivo=motivo,
                area_id=area_id,
            )
        finally:
            db.close()
        logger.warning("cruces_camino.variante_no_disponible", area_id=area_id, detalle=str(exc))
        return {"job_id": job_id, "status": "failed", "motivo": motivo}
    except (DemJobEnCurso, CopiaCorrupta) as exc:
        db = session_factory()
        try:
            _fail(
                db,
                jobs,
                job_id,
                expected=EstadoGeoJob.RUNNING.value,
                motivo=exc.motivo,
                area_id=area_id,
            )
        finally:
            db.close()
        return {"job_id": job_id, "status": "skipped", "motivo": exc.motivo}
    except Exception:
        db = session_factory()
        try:
            _fail(
                db,
                jobs,
                job_id,
                expected=EstadoGeoJob.RUNNING.value,
                motivo="error",
                area_id=area_id,
            )
        finally:
            db.close()
        logger.error("cruces_camino.failed", area_id=area_id, exc_info=True)
        raise
    finally:
        # Even a crashed run leaks at most one area's worth of temporary rasters.
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)


def _fail(db, jobs, job_id: str, *, expected: str, motivo: str, area_id: str) -> None:
    """Compare-and-set to FAILED with a motivo naming the area and the reason."""
    from app.domains.geo.models import EstadoGeoJob

    jobs.update_job_status_if_current(
        db,
        uuid.UUID(job_id),
        expected_estado=expected,
        estado=EstadoGeoJob.FAILED.value,
        error=f"{motivo}: area {area_id}",
    )
    db.commit()


# ---------------------------------------------------------------------------
# The read side
# ---------------------------------------------------------------------------


def get_cruces_camino(db, *, area_id: str) -> dict[str, Any]:
    """The ranked list, the canal set and everything needed to read them honestly.

    ``N.º de M`` uses **M = the flujo_natural count**, never the total row count:
    canal crossings are a separately-toggled set with their own count, because a
    rank whose denominator changed with DEM coverage rather than with the network
    would be meaningless. ``calculada_en`` is always present so no operator ever
    reads a rank without knowing how old it is.

    No volume, flow rate, depth, cuneta size or return period appears anywhere in
    this payload. The capability derives a direction and a relative ordering.
    """
    from app.domains.geo.intelligence.repository import IntelligenceRepository

    repo = IntelligenceRepository()
    rows = repo.get_cruces_for_area(db, area_id)
    calculada_en = repo.get_calculada_en(db, area_id)
    resultado = repo.get_ultimo_resultado_cruces(db, area_id) or {}

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {
                "id": str(row["id"]),
                "tipo": row["tipo"],
                "tramo_ref": row["tramo_ref"],
                "canal_ref": row["canal_ref"],
                "direccion_flujo_deg": row["direccion_flujo_deg"],
                "rumbo_camino_deg": row["rumbo_camino_deg"],
                "lado_cruce": row["lado_cruce"],
                "area_aporte_ha": row["area_aporte_ha"],
                "orden_ranking": row["orden_ranking"],
                "confianza": row["confianza"],
                "nota": row["nota"],
            },
        }
        for row in rows
    ]

    parametros = resultado.get("parametros", {}) or {}
    return {
        "area_id": area_id,
        "calculada_en": calculada_en,
        "desactualizado": calcular_desactualizado(db, area_id, calculada_en),
        "total_flujo_natural": sum(1 for r in rows if r["tipo"] == "flujo_natural"),
        "total_canal": sum(1 for r in rows if r["tipo"] == "canal"),
        "features": {"type": "FeatureCollection", "features": features},
        "excluidos": resultado.get("excluidos", []) or [],
        "parametros": parametros,
        "variante": parametros.get("variante"),
        "segmentos_parcialmente_cubiertos": parametros.get("segmentos_parcialmente_cubiertos", 0),
    }


__all__ = [
    "compute_scratch_root",
    "get_cruces_camino",
    "leer_parametros",
    "run_crossing_task",
]


def compute_scratch_root() -> str:
    """Exposed so a test can assert the scratch directory is really gone."""
    return SCRATCH_ROOT
