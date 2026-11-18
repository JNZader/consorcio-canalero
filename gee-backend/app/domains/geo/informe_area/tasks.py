"""Celery tasks for the informe de área: generation + daily retention sweep.

Published through the transactional outbox (``CeleryTaskKey.INFORME_AREA``),
so the enqueue is atomic with the row and the beat publisher retries broker
failures. Queue: ``geo`` — the GDAL worker that T2's raster/Pillow rendering
needs anyway; the T1 compute itself is PostGIS + stored-data reads.

State machine (S8): pending → running → completed / failed, with ``progreso``
bumps the UI polls. Every transition is a compare-and-set, so a duplicate
delivery of the same logical task (the outbox's at-least-once contract)
either skips cleanly or loses the race — never resurrects a finished row.

The compute reuses PR 1 wholesale (S12): the zonas resolver SQL for the
selection, ``_desglose_zonas`` for the per-zone rows from
``composite_zonal_stats`` / ``suelos_catastro`` / the CHIRPS annual normal,
and the ``legacy70`` threshold tag until #738. NO raster is recomputed —
reading registered products is the whole latency budget (S6).

GEE degradation (S8): nothing here calls GEE yet. T2's Sentinel-2 miniature
will append to ``resultado["degradado"]`` instead of failing the report; a
HARD failure (anything raised below) leaves ``estado=failed`` with a readable
one-line reason in ``error`` — the traceback goes to the log, not the user.
"""

from __future__ import annotations

import uuid

import structlog

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.domains.geo.models import EstadoGeoJob

logger = structlog.get_logger(__name__)

# Progreso milestones: the UI shows a determinate bar from the moment the
# task starts, so "pending forever" is distinguishable from "never picked up".
PROGRESO_INICIO = 10
PROGRESO_RESUELTO = 40
PROGRESO_DESGLOSE = 80
PROGRESO_FINAL = 100


@celery_app.task(queue="geo", name="geo.informe_area.generar")
def generar_informe_area(informe_id: str) -> dict:
    """Resolve → desglose → store. Idempotent under duplicate delivery."""
    from app.domains.geo import ficha_service
    from app.domains.geo.informe_area import service
    from app.domains.geo.informe_area.repository import InformeAreaRepository

    repo = InformeAreaRepository()
    db = SessionLocal()
    try:
        row = repo.obtener(db, uuid.UUID(informe_id))
        if row is None:
            logger.warning("informe_area.fila_ausente", informe_id=informe_id)
            return {"informe_id": informe_id, "estado": "skipped"}

        if not repo.actualizar_estado_if_actual(
            db,
            row.id,
            expected_estado=EstadoGeoJob.PENDING,
            estado=EstadoGeoJob.RUNNING,
            progreso=PROGRESO_INICIO,
        ):
            logger.info("informe_area.ya_no_pending", informe_id=informe_id)
            return {"informe_id": informe_id, "estado": "skipped"}

        try:
            parametros = row.parametros or {}
            zona_ids = [uuid.UUID(z) for z in parametros.get("zona_ids", [])]
            con_desglose = bool(parametros.get("desglose", True))

            seleccion = service.resolver_seleccion(db, zona_ids)

            desglose: list[dict] | None = None
            umbral: str | None = None
            if con_desglose and zona_ids:
                filas_zonas = db.execute(
                    ficha_service._ZONAS_SQL,  # noqa: SLF001 — PR 1 reuse (S12)
                    {"ids": [str(z) for z in zona_ids], "cuencas": []},
                ).all()
                zonas = [
                    ficha_service.ZonaResuelta(
                        zona_id=f.zona_id,
                        nombre=f.nombre,
                        cuenca=f.cuenca,
                        ha=float(f.ha or 0.0),
                        g4326=f.g4326,
                    )
                    for f in filas_zonas
                ]
                repo.actualizar_estado_if_actual(
                    db,
                    row.id,
                    expected_estado=EstadoGeoJob.RUNNING,
                    progreso=PROGRESO_RESUELTO,
                )
                filas_desglose, umbral = ficha_service._desglose_zonas(  # noqa: SLF001
                    db, zonas
                )
                desglose = [fila.model_dump(mode="json") for fila in filas_desglose]

            resultado = {
                "area_ha": round(seleccion.area_ha, 4),
                "zonas": len(zona_ids),
                "cuencas": seleccion.cuencas,
                "vertices_simplificados": seleccion.vertices_simplificados,
                "desglose": desglose,
                "umbral_alto_critico": umbral,
                # GEE-dependent pieces land in T2 (Sentinel-2 miniature);
                # each degradation is APPENDED here, never fails the report.
                "degradado": [],
            }

            if not repo.actualizar_estado_if_actual(
                db,
                row.id,
                expected_estado=EstadoGeoJob.RUNNING,
                estado=EstadoGeoJob.COMPLETED,
                progreso=PROGRESO_FINAL,
                resultado=resultado,
                error=None,
            ):
                logger.warning("informe_area.cas_perdido_al_completar", informe_id=informe_id)
                return {"informe_id": informe_id, "estado": "skipped"}
            logger.info(
                "informe_area.completado",
                informe_id=informe_id,
                area_ha=resultado["area_ha"],
                zonas=resultado["zonas"],
            )
            return {"informe_id": informe_id, "estado": "completed"}
        except Exception as exc:  # noqa: BLE001 — the failure path IS the contract (S8)
            razon = f"{type(exc).__name__}: {exc}".strip()
            logger.error("informe_area.fallo", informe_id=informe_id, exc_info=True)
            repo.actualizar_estado_if_actual(
                db,
                row.id,
                expected_estado=EstadoGeoJob.RUNNING,
                estado=EstadoGeoJob.FAILED,
                progreso=0,
                error=razon,
            )
            return {"informe_id": informe_id, "estado": "failed", "error": razon}
    finally:
        db.close()


@celery_app.task(queue="geo", name="geo.informe_area.limpiar_vencidos")
def limpiar_informes_vencidos() -> dict:
    """Daily retention sweep (S11): delete rows past their ``vence_at``.

    Runs via Celery Beat; the schedule entry lives with the rest of the beat
    table in ``app/core/celery_app.py`` (see the T1 report — the wiring is a
    documented follow-up outside this package's allowed surfaces). The task
    itself is complete and directly invokable, which is how its test runs.
    """
    from app.domains.geo.informe_area.repository import InformeAreaRepository

    db = SessionLocal()
    try:
        borrados = InformeAreaRepository().borrar_vencidos(db)
        logger.info("informe_area.limpieza", borrados=borrados)
        return {"borrados": borrados}
    finally:
        db.close()
