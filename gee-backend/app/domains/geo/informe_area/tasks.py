"""Celery tasks for the informe de área: generation + daily retention sweep.

Published through the transactional outbox (``CeleryTaskKey.INFORME_AREA``),
so the enqueue is atomic with the row and the beat publisher retries broker
failures. Queue: ``geo`` — the GDAL worker T2's raster/Pillow rendering needs;
the compute itself is PostGIS + stored-data reads.

State machine (S8): pending → running → completed / failed, with ``progreso``
bumps the UI polls. Every transition is a compare-and-set, so a duplicate
delivery of the same logical task (the outbox's at-least-once contract)
either skips cleanly or loses the race — never resurrects a finished row.

The compute reuses PR 1 wholesale (S12): the zonas resolver SQL for the
selection, ``_desglose_zonas`` for the per-zone rows from
``composite_zonal_stats`` / ``suelos_catastro`` / the CHIRPS annual normal,
and the ``legacy70`` threshold tag until #738. NO raster is recomputed —
reading registered products is the whole latency budget (S6).

T2 appends the render pipeline on top of the same stored reads:
``_raster_dataset`` / ``_suelos_dataset`` / ``_precipitacion_dataset`` shape
the PDF's sections, ``mapas`` paints the static maps (S7 — white background,
NEVER Esri) and ``build_informe_area_pdf`` lays out the 7 sections (S6). The
bytes land in ``informes_area.pdf_bytes`` (bytea) inside the SAME completion
compare-and-set, so a row is never ``completed`` without its PDF.

GEE degradation (S8): nothing here calls GEE yet. A future Sentinel-2
miniature will append to ``resultado["degradado"]`` instead of failing the
report; a map-render failure degrades the same way today. A HARD failure
(anything raised below) leaves ``estado=failed`` with a readable one-line
reason in ``error`` — the traceback goes to the log, not the user.
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
PROGRESO_PDF = 90
PROGRESO_FINAL = 100


def _resolucion_raster(ruta: str) -> str:
    """Human resolution of a registered raster for the Fuentes table (S6 §7).

    Geographic CRS → metres-per-pixel at the raster's mid-latitude (the
    honest approximation for a provenance line); projected CRS → the map
    units themselves. Lazy rasterio import: this module is imported by the
    API-adjacent beat wiring too, not only the geo worker.
    """
    import math

    try:
        import rasterio

        with rasterio.open(ruta) as src:
            paso_x = abs(src.transform.a)
            if src.crs is not None and src.crs.is_geographic:
                lat = (src.bounds.top + src.bounds.bottom) / 2.0
                return f"~{paso_x * 111_320.0 * math.cos(math.radians(lat)):.0f} m"
            return f"{paso_x:.1f} m"
    except Exception:  # noqa: BLE001 — provenance decoration, never fatal
        return "—"


def _fuentes_informe(db, precip_fuente: str, precip_periodo: str) -> list[dict]:
    """Capa · fecha · resolución · origen rows for section 7 (S6).

    Reads what is REGISTERED (``geo_layers`` / ``composite_zonal_stats``), not
    what the pipeline constants claim — same discipline as the ficha's
    ``_precip_procedencia``. Layers absent from this deployment are absent
    from the table; nothing is invented.
    """
    from app.domains.geo.models import GeoLayer

    fuentes: list[dict] = []
    for tipo, etiqueta in (
        ("flood_risk", "Riesgo hídrico (flood_risk)"),
        ("drainage_need", "Necesidad de drenaje (drainage_need)"),
    ):
        layer = (
            db.query(GeoLayer)
            .filter(GeoLayer.tipo == tipo)
            .order_by(GeoLayer.created_at.desc(), GeoLayer.id.desc())
            .first()
        )
        if layer is None:
            continue
        fuentes.append(
            {
                "capa": etiqueta,
                "fecha": layer.created_at.date().isoformat(),
                "resolucion": _resolucion_raster(layer.archivo_path),
                "origen": f"pipeline DEM (geo_layers, {layer.fuente.value})",
            }
        )

    precip = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == "precip_normal")
        .order_by(GeoLayer.created_at.desc())
        .first()
    )
    if precip is not None:
        fuentes.append(
            {
                "capa": "Normales de precipitación (CHIRPS)",
                "fecha": precip.created_at.date().isoformat(),
                "resolucion": "~5 km (píxel)",
                "origen": f"{precip_fuente or 'CHIRPS'} · período {precip_periodo or '—'}",
            }
        )

    from sqlalchemy import text

    fecha_composite = db.execute(
        text("SELECT max(fecha_calculo)::date::text FROM composite_zonal_stats")
    ).scalar_one_or_none()
    if fecha_composite:
        fuentes.append(
            {
                "capa": "Desglose por subcuenca",
                "fecha": str(fecha_composite),
                "resolucion": "por subcuenca",
                "origen": "composite_zonal_stats (pipeline DEM)",
            }
        )

    fuentes.append(
        {
            "capa": "Suelos (capacidad de uso)",
            "fecha": "—",
            "resolucion": "vectorial",
            "origen": "catastro INTA (suelos_catastro)",
        }
    )
    return fuentes


@celery_app.task(queue="geo", name="geo.informe_area.generar")
def generar_informe_area(informe_id: str) -> dict:
    """Resolve → desglose → datasets → maps → PDF → store.

    Idempotent under duplicate delivery.
    """
    import json
    from datetime import datetime, timezone

    from app.domains.geo import ficha_errors
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
            if not seleccion.geojson:
                raise RuntimeError("la geometría de la selección no pudo resolverse")

            # Zonas rows ALWAYS: the desglose aggregates them AND both maps
            # draw their outlines — "Solo total" skips the per-zone COMPUTE,
            # not the geometry the report is drawn from.
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

            desglose: list[dict] | None = None
            umbral: str | None = None
            if con_desglose and zona_ids:
                filas_desglose, umbral = ficha_service._desglose_zonas(  # noqa: SLF001
                    db, zonas
                )
                # Same clamp/None contract as the ficha's pct_alto_critico,
                # read from the drainage composite rows so section 3 carries
                # the same per-subcuenca structure as section 2.
                pct_drenaje = {
                    str(k): v
                    for k, v in service.pct_drenaje_por_zona(
                        db, [(z.zona_id, z.ha) for z in zonas]
                    ).items()
                }
                cuenca_por_id = {str(z.zona_id): z.cuenca for z in zonas}
                desglose = []
                for fila in filas_desglose:
                    item = fila.model_dump(mode="json")
                    item["cuenca"] = cuenca_por_id.get(item["zona_id"], "—")
                    item["pct_drenaje_alto_critico"] = pct_drenaje.get(item["zona_id"])
                    desglose.append(item)
                repo.actualizar_estado_if_actual(
                    db,
                    row.id,
                    expected_estado=EstadoGeoJob.RUNNING,
                    progreso=PROGRESO_DESGLOSE,
                )

            # ── datasets for the PDF sections (PR 1 primitives, S12) ──────
            area_m2 = seleccion.area_ha * service.M2_POR_HA
            union_geom = json.loads(seleccion.geojson)

            riesgo = ficha_service._raster_dataset(  # noqa: SLF001 — PR 1 reuse (S12)
                db, "flood_risk", union_geom, area_m2
            ).model_dump()
            drenaje = ficha_service._raster_dataset(  # noqa: SLF001
                db, "drainage_need", union_geom, area_m2
            ).model_dump()
            try:
                suelos = ficha_service._suelos_dataset(  # noqa: SLF001
                    db, seleccion.geojson, seleccion.area_ha
                ).model_dump()
            except ficha_errors.FichaError:
                # Empty/uninstalled soils product: the ficha 503s (it is a
                # hard dependency THERE); the informe reports sin cobertura
                # and keeps serving the rest (S6 §6 cobertura por capa).
                suelos = None
            lluvia = ficha_service._precipitacion_dataset(  # noqa: SLF001
                db, union_geom, area_m2
            ).model_dump()

            # ── static maps (S7: white background, NEVER Esri) ────────────
            from app.domains.geo.informe_area import mapas

            zonas_geo = [{"nombre": z.nombre, "geojson": json.loads(z.g4326)} for z in zonas]
            mapas_bytes: dict[str, bytes] = {}
            degradado: list[str] = []

            ubicacion = mapas.render_mapa_ubicacion(union_geom, zonas_geo)
            if ubicacion:
                mapas_bytes["ubicacion"] = ubicacion

            for tipo, dataset in (("flood_risk", riesgo), ("drainage_need", drenaje)):
                if dataset.get("cobertura") == "sin_cobertura":
                    continue
                ruta = ficha_service._raster_path(db, tipo)  # noqa: SLF001
                if not ruta:
                    continue
                png = mapas.render_mapa_clasificado(
                    tipo, ruta, union_geom, zonas_geo, dataset.get("clases") or []
                )
                if png:
                    mapas_bytes[tipo] = png
                else:
                    degradado.append(f"mapa de {tipo} no generado")

            repo.actualizar_estado_if_actual(
                db,
                row.id,
                expected_estado=EstadoGeoJob.RUNNING,
                progreso=PROGRESO_PDF,
            )

            # ── the PDF itself (S6) ───────────────────────────────────────
            from app.shared.pdf.base import get_branding
            from app.shared.pdf.builders_informe_area import (
                build_informe_area_pdf,
                calcular_kpis,
            )

            for dataset in (riesgo, drenaje, suelos, lluvia):
                if dataset is not None:
                    dataset["area_ha"] = seleccion.area_ha

            datos = {
                "nombre": row.nombre,
                "generado_el": datetime.now(timezone.utc).isoformat(),
                "area_ha": round(seleccion.area_ha, 4),
                "cantidad_zonas": len(zona_ids),
                "cuencas": seleccion.cuencas,
                "riesgo": riesgo,
                "drenaje": drenaje,
                "suelos": suelos,
                "lluvia": lluvia,
                "desglose": desglose,
                "umbral_alto_critico": umbral,
                "degradado": degradado,
                "fuentes": _fuentes_informe(
                    db,
                    str(lluvia.get("fuente") or ""),
                    str(lluvia.get("periodo") or ""),
                ),
            }
            pdf_bytes = build_informe_area_pdf(
                datos, get_branding(db), mapas=mapas_bytes
            ).getvalue()
            if len(pdf_bytes) > 5_000_000:  # S9 budget — logged, not fatal
                logger.warning(
                    "informe_area.pdf_grande",
                    informe_id=informe_id,
                    bytes=len(pdf_bytes),
                )

            resultado = {
                "area_ha": round(seleccion.area_ha, 4),
                "zonas": len(zona_ids),
                "cuencas": seleccion.cuencas,
                "vertices_simplificados": seleccion.vertices_simplificados,
                "desglose": desglose,
                "umbral_alto_critico": umbral,
                "kpis": calcular_kpis(datos),
                # GEE-dependent pieces (Sentinel-2 miniature) land later;
                # each degradation is APPENDED here, never fails the report.
                "degradado": degradado,
            }

            if not repo.actualizar_estado_if_actual(
                db,
                row.id,
                expected_estado=EstadoGeoJob.RUNNING,
                estado=EstadoGeoJob.COMPLETED,
                progreso=PROGRESO_FINAL,
                resultado=resultado,
                error=None,
                pdf_bytes=pdf_bytes,
            ):
                logger.warning("informe_area.cas_perdido_al_completar", informe_id=informe_id)
                return {"informe_id": informe_id, "estado": "skipped"}
            logger.info(
                "informe_area.completado",
                informe_id=informe_id,
                area_ha=resultado["area_ha"],
                zonas=resultado["zonas"],
                pdf_bytes=len(pdf_bytes),
                mapas=list(mapas_bytes),
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
