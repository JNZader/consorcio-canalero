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
``composite_zonal_stats`` / ``suelos_catastro`` / the CHIRPS annual normal.
PR 5 (#738) switches the threshold tag to ``leyenda-55`` and OVERRIDES the
per-zone % Alto+Crítico with the legend-derived ``ha_alto + ha_critico``
read, so no legacy-70 figure can appear under the new label. NO raster is
recomputed — reading registered products is the whole latency budget (S6).

PR 5 also adds the flood_risk validation dataset (S4): observed water per
class on the anchor events (``riesgo_validacion_evento``, zone scale),
rendered in section 2 when the calibration ETL has loaded rows.

T2 appends the render pipeline on top of the same stored reads:
``_raster_dataset`` / ``_suelos_dataset`` / ``_precipitacion_dataset`` shape
the PDF's sections, ``mapas`` paints the static maps (S7 — white background,
NEVER Esri) and ``build_informe_area_pdf`` lays out the 7 sections (S6). The
bytes land in ``informes_area.pdf_bytes`` (bytea) inside the SAME completion
compare-and-set, so a row is never ``completed`` without its PDF.

GEE degradation (S8): the ONLY GEE dependency is the S6 anchor-event
miniature (NIR-SWIR1-red thumbnails of dated scenes picked by the imagery
shortlist). Every failure there appends to ``resultado["degradado"]`` and
renders «sin datos» for that event — a report never fails on GEE; a
map-render failure degrades the same way. A HARD failure (anything raised
below) leaves ``estado=failed`` with a readable one-line reason in
``error`` — the traceback goes to the log, not the user.

PR 6 appends the field exports to the SAME completion transaction: the KMZ
(S3 — vectorized class themes + georeferenced anchor imagery, one theme
visible at a time via radioFolder) and the offline campo package (S4 — the
same vectors + límites + leyenda + a Sentinel-2 basemap, target ≤ 15 MB).
Both degrade per-piece like a map does; the row is never ``completed``
without its PDF, but it CAN complete without a KMZ or package (each says so
in ``degradado`` / ``resultado["campo"]``).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.core.celery_app import celery_app
from app.core.exceptions import sanitize_error_message
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

_INTERNAL_ERROR_MARKERS = (
    "select ",
    "insert ",
    "update ",
    "delete ",
    "postgresql://",
    "postgres://",
    "redis://",
    "psycopg",
    "sqlalchemy",
)


def _sanitizar_error_informe(exc: Exception) -> str:
    """Strip SQL/DSN/filesystem details before storing in user-visible InformeArea.error."""
    lowered = str(exc).lower()
    default_msg = "Error interno al generar el informe"
    if any(marker in lowered for marker in _INTERNAL_ERROR_MARKERS):
        safe_detail = default_msg
    else:
        safe_detail = sanitize_error_message(exc, default_message=default_msg)
    return f"{type(exc).__name__}: {safe_detail}".strip()


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

    # Suelos: section 4 reads the IDECOR 1:50.000 cartography (PR 4, S3).
    # The row exists only when the ETL actually ran — the same "absent from
    # this deployment is absent from the table" rule as every other row.
    if (
        db.execute(text("SELECT to_regclass('idecor_suelos_50mil')")).scalar_one_or_none()
        is not None
    ):
        fecha_suelos = db.execute(
            text("SELECT max(fecha_de_bajada)::date::text FROM idecor_suelos_50mil")
        ).scalar_one_or_none()
        if fecha_suelos:
            fuentes.append(
                {
                    "capa": "Suelos 1:50.000 (IDECOR)",
                    "fecha": str(fecha_suelos),
                    "resolucion": "vectorial · escala 1:50.000",
                    "origen": (
                        "IDECOR · carta_suelo_50mil_2025 (WFS) · INTA series · licencia CC BY 4.0"
                    ),
                }
            )

    # Cobertura y cultivos (S4): uso 2024/2025 + campañas estivales, one
    # Fuentes row per registered raster family (same date, same source).
    if (
        db.execute(text("SELECT to_regclass('idecor_cobertura_raster')")).scalar_one_or_none()
        is not None
    ):
        filas_cob = db.execute(
            text(
                "SELECT tipo, max(fecha_de_bajada)::date::text AS fecha, count(*) "
                "FROM idecor_cobertura_raster GROUP BY tipo"
            )
        ).all()
        etiquetas = {
            "cobertura_uso": ("Cobertura y uso del suelo (IDECOR)", "10 m · 21 clases"),
            "cobertura_estival": ("Cultivos estivales (IDECOR/INTA)", "10 m · 3 campañas"),
        }
        for fila in filas_cob:
            etiqueta, resolucion = etiquetas.get(str(fila.tipo), (str(fila.tipo), "10 m"))
            fuentes.append(
                {
                    "capa": etiqueta,
                    "fecha": str(fila.fecha),
                    "resolucion": resolucion,
                    "origen": "IDECOR · Mapas Córdoba (WCS/WMS) · licencia CC BY 4.0",
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

        informe_uuid = row.id
        if not repo.actualizar_estado_if_actual(
            db,
            informe_uuid,
            expected_estado=EstadoGeoJob.PENDING,
            estado=EstadoGeoJob.RUNNING,
            progreso=PROGRESO_INICIO,
        ):
            logger.info("informe_area.ya_no_pending", informe_id=informe_id)
            return {"informe_id": informe_id, "estado": "skipped"}

        try:
            parametros = row.parametros or {}
            zona_ids = [uuid.UUID(z) for z in parametros.get("zona_ids", [])]
            # PR 3 (S3): the mixed selection's caller-supplied geometries
            # (drawn / KML-imported), stored in parametros at create time —
            # the row is their only durable copy. A geometry-only selection
            # has zona_ids == [] and that is VALID: the union carries the
            # report, the desglose rows are simply empty.
            geometrias = [g for g in (parametros.get("geometrias") or []) if isinstance(g, dict)]
            con_desglose = bool(parametros.get("desglose", True))

            seleccion = service.resolver_seleccion(db, zona_ids, geometrias)
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
            # PR 5 (#738): every % Alto+Crítico figure this informe renders —
            # the Resumen KPI (raster classes) and the per-subcuenca table —
            # counts from the legend's Alto edge (55), so the tag says so.
            # The ficha's own desglose helper still returns its stored-column
            # figure; the rows are OVERRIDDEN here with the legend-derived
            # ha_alto + ha_critico read, which is NULL-aware: a row that
            # predates the recompute reports «—», never a legacy-70 figure
            # wearing the new label.
            umbral: str | None = "leyenda-55"
            if con_desglose and zona_ids:
                filas_desglose, _umbral_ficha = ficha_service._desglose_zonas(  # noqa: SLF001
                    db, zonas
                )
                # str keys — desglose items are model_dump(mode="json"), so
                # zona_id arrives as a string (same conversion pct_drenaje
                # applies below).
                pct_riesgo_leyenda = {
                    str(k): v
                    for k, v in service.pct_alto_critico_por_zona(
                        db, [(z.zona_id, z.ha) for z in zonas], "flood_risk"
                    ).items()
                }
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
                    item["pct_alto_critico"] = pct_riesgo_leyenda.get(item["zona_id"])
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
            # Section 4's data (S3): IDECOR 1:50.000 cartography. The
            # dataset itself degrades to None on a missing/failed table
            # (S7 — «sin datos», the report never fails); the ficha's
            # suelos_cu no longer feeds the informe, and the desglose's
            # clase_suelo_dominante (suelos_catastro) stays as PR 1 built
            # it — PR 3 owns that surface.
            suelos = service.suelos_idecor_dataset(db, seleccion.geojson, seleccion.area_ha)
            if suelos is not None:
                suelos["por_zona"] = service.suelos_idecor_por_zona(
                    db, [(z.zona_id, z.ha) for z in zonas]
                )
            # Cobertura y cultivos (S4): uso 2024/2025 + 3 campañas
            # estivales + recurrencia. Degrades to None → «sin datos».
            cobertura = service.cobertura_dataset(db, union_geom, area_m2)
            if cobertura is not None:
                cobertura["por_zona"] = service.cobertura_por_zona(
                    db, [(z.zona_id, z.nombre, z.g4326, float(z.ha or 0.0)) for z in zonas]
                )
            # Canales (S5): km relevados/propuestos clip por el área +
            # cruces y conflictos. None → «sin datos»; ceros son reales.
            canales = service.canales_dataset(db, seleccion.geojson, seleccion.area_ha)
            if canales is not None:
                canales["por_zona"] = service.canales_por_zona(
                    db, [(z.zona_id, z.nombre, z.ha) for z in zonas]
                )
            # Imágenes de los eventos ancla (S6): miniaturas GEE falso
            # color NIR-SWIR1-R recortadas al área. Cada fallo es por
            # evento (png=None → «sin datos»), el informe no falla (S7).
            degradado: list[str] = []
            imagenes = service.imagenes_eventos_ancla(db, union_geom)
            for imagen in imagenes:
                if imagen.get("png") is None:
                    degradado.append(f"miniatura sin datos: {imagen.get('nombre')}")
            # Validación de flood_risk (PR 5, S4): agua observada por clase en
            # los eventos ancla, a escala de la zona del consorcio. None → the
            # section omits the table (ETL not run here).
            riesgo_validacion = service.riesgo_validacion_dataset(db)
            lluvia = ficha_service._precipitacion_dataset(  # noqa: SLF001
                db, union_geom, area_m2
            ).model_dump()

            # ── static maps (S7: white background, NEVER Esri) ────────────
            from app.domains.geo.informe_area import mapas

            zonas_geo = [{"nombre": z.nombre, "geojson": json.loads(z.g4326)} for z in zonas]
            mapas_bytes: dict[str, bytes] = {}

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

            for ds in (riesgo, drenaje, suelos, cobertura, lluvia):
                if ds is not None:
                    ds["area_ha"] = seleccion.area_ha

            datos = {
                "nombre": row.nombre,
                "generado_el": datetime.now(timezone.utc).isoformat(),
                "area_ha": round(seleccion.area_ha, 4),
                "cantidad_zonas": len(zona_ids),
                "cuencas": seleccion.cuencas,
                # PR 6 (S7): the cover QR encodes the campo URL — the token
                # was minted at create time, so the URL is known before render.
                "campo_url": service.url_campo(row.token_publico),
                "riesgo": riesgo,
                "drenaje": drenaje,
                "suelos": suelos,
                "cobertura": cobertura,
                "canales": canales,
                "imagenes": imagenes,
                "lluvia": lluvia,
                "desglose": desglose,
                "umbral_alto_critico": umbral,
                "riesgo_validacion": riesgo_validacion,
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

            # ── PR 6: KMZ + paquete de campo (S3/S4) ────────────────────
            # Themes are vectorized from the SAME rasters the PDF's maps
            # painted (vectorize_zonal_classes), so Google Earth and the
            # phone cannot disagree with the report.
            from shapely.geometry import shape

            from app.domains.geo.class_breaks import RANGE_CONFIGS
            from app.domains.geo.composites import vectorize_zonal_classes
            from app.domains.geo.informe_area import kmz as kmz_export

            bounds_union = shape(union_geom).bounds  # (w, s, e, n) 4326

            datasets_clase = {"flood_risk": riesgo, "drainage_need": drenaje}
            temas_campo: list[dict[str, Any]] = []
            for tipo, clave, titulo in (
                ("flood_risk", "riesgo", "Riesgo hídrico"),
                ("drainage_need", "drenaje", "Necesidad de drenaje"),
            ):
                if datasets_clase[tipo].get("cobertura") == "sin_cobertura":
                    continue
                ruta = ficha_service._raster_path(db, tipo)  # noqa: SLF001
                if not ruta:
                    continue
                try:
                    vectorizado = vectorize_zonal_classes(
                        ruta, union_geom, RANGE_CONFIGS.get(tipo) or []
                    )
                except Exception:  # noqa: BLE001 — a theme degrades, never fails
                    logger.warning("informe_area.vectorizado_fallo", tipo=tipo, exc_info=True)
                    degradado.append(f"vectorizado de {tipo} no generado")
                    continue
                colores = {str(b["label"]): str(b["color"]) for b in RANGE_CONFIGS.get(tipo) or []}
                clases = [
                    {
                        "clase": str(f["clase"]),
                        "color": colores.get(str(f["clase"]), "#808080"),
                        "geometrias": [f["geometry"]],
                    }
                    for f in vectorizado
                    if f.get("geometry")
                ]
                if clases:
                    temas_campo.append({"clave": clave, "titulo": titulo, "clases": clases})

            try:
                suelos_geo = service.suelos_geometrias_clase(db, seleccion.geojson)
            except Exception:  # noqa: BLE001
                suelos_geo = None
            if suelos_geo:
                temas_campo.append(
                    {
                        "clave": "suelos",
                        "titulo": "Suelos (IDECOR 1:50.000)",
                        "clases": [
                            {
                                "clase": c["clase"],
                                "color": kmz_export.color_suelo(c["clase"], i),
                                "geometrias": c["geometrias"],
                            }
                            for i, c in enumerate(suelos_geo)
                        ],
                    }
                )

            # KMZ (S3): one folder per theme + georeferenced anchor imagery.
            kmz_bytes: bytes | None = None
            try:
                temas_kmz = [
                    kmz_export.TemaKmz(
                        titulo=t["titulo"],
                        clases=[
                            kmz_export.ClaseKmz(
                                clase=c["clase"],
                                color=c["color"],
                                geometrias=c["geometrias"],
                            )
                            for c in t["clases"]
                        ],
                    )
                    for t in temas_campo
                ]
                imagenes_kmz = [
                    kmz_export.ImagenKmz(
                        titulo=f"Imagen {i['fecha']} — {i['nombre']}",
                        png=i["png"],
                        bounds=bounds_union,
                    )
                    for i in imagenes
                    if i.get("png")
                ]
                kmz_bytes = kmz_export.construir_kmz_informe(
                    nombre=row.nombre,
                    seleccion_geojson=union_geom,
                    subcuencas=zonas_geo,
                    temas=temas_kmz,
                    imagenes=imagenes_kmz,
                )
            except Exception:  # noqa: BLE001 — the KMZ degrades like a map
                logger.warning("informe_area.kmz_fallo", informe_id=informe_id, exc_info=True)
                degradado.append("KMZ no generado")

            # Paquete de campo (S4): vectors + límites + leyenda + basemap.
            campo_bytes: bytes | None = None
            campo_notas: list[str] = []
            campo_basemap = False
            try:
                con_png = [i for i in imagenes if i.get("png") is not None]
                basemap: dict[str, Any] | None = None
                if con_png:
                    # imagenes comes ORDER BY start_date: the LAST row with a
                    # PNG is the latest scene. Prefer a Sentinel-2 one (S4
                    # names Sentinel-2; the anchors may carry Landsat).
                    s2 = [i for i in con_png if str(i.get("sensor")) == "sentinel2"]
                    elegida = (s2 or con_png)[-1]
                    basemap = {
                        "png": elegida["png"],
                        "bounds": bounds_union,
                        "fecha": elegida.get("fecha"),
                        "sensor": elegida.get("sensor"),
                    }
                paquete = service.construir_paquete_campo(
                    nombre=row.nombre,
                    generado_el=str(datos["generado_el"]),
                    vence_at=row.vence_at.isoformat(),
                    area_ha=seleccion.area_ha,
                    seleccion_geojson=union_geom,
                    subcuencas=zonas_geo,
                    temas=temas_campo,
                    basemap=basemap,
                )
                campo_bytes = service.serializar_paquete_campo(paquete)
                campo_notas = list(paquete.get("notas") or [])
                campo_basemap = paquete.get("basemap") is not None
                if len(campo_bytes) > service.CAMPO_PAQUETE_MAX_BYTES:
                    logger.warning(
                        "informe_area.paquete_grande",
                        informe_id=informe_id,
                        bytes=len(campo_bytes),
                    )
            except Exception:  # noqa: BLE001 — the package degrades, report lives
                logger.warning("informe_area.paquete_fallo", informe_id=informe_id, exc_info=True)
                degradado.append("paquete de campo no generado")

            resultado = {
                "area_ha": round(seleccion.area_ha, 4),
                "zonas": len(zona_ids),
                "geometrias": len(geometrias),
                "fuera_zona_ha": round(seleccion.fuera_zona_ha, 4),
                "cuencas": seleccion.cuencas,
                "vertices_simplificados": seleccion.vertices_simplificados,
                "desglose": desglose,
                "umbral_alto_critico": umbral,
                "riesgo_validacion": (
                    {
                        "eventos": len(riesgo_validacion["eventos"]),
                        "version_flood_risk": riesgo_validacion.get("version_flood_risk"),
                    }
                    if riesgo_validacion
                    else None
                ),
                "kpis": calcular_kpis(datos),
                "suelos_idecor": (
                    {
                        "cobertura": suelos.get("cobertura"),
                        "cobertura_ratio": suelos.get("cobertura_ratio"),
                        "unidades": len(suelos.get("unidades") or []),
                        "ip_ponderado": suelos.get("ip_ponderado"),
                    }
                    if suelos
                    else None
                ),
                "cobertura_idecor": (
                    {
                        "cobertura": cobertura.get("cobertura"),
                        "cobertura_ratio": cobertura.get("cobertura_ratio"),
                        "pct_agua_estacional": cobertura.get("pct_agua_estacional"),
                        "campanias": [
                            {"campania": c["campania"], "ha_cultivo": c["ha_cultivo"]}
                            for c in cobertura.get("campanias") or []
                        ],
                        "recurrencia": cobertura.get("recurrencia"),
                    }
                    if cobertura
                    else None
                ),
                "canales_resumen": (
                    {
                        "km_relevados": canales.get("km_relevados"),
                        "km_propuestos": canales.get("km_propuestos"),
                        "km_total": canales.get("km_total"),
                        "km_por_mil_ha": canales.get("km_por_mil_ha"),
                        "cruces_camino": canales.get("cruces_camino"),
                        "puntos_conflicto": canales.get("puntos_conflicto"),
                    }
                    if canales
                    else None
                ),
                # PNG bytes stay OUT of resultado (JSONB budget, S9): only
                # the per-event presence the UI polls for.
                "imagenes_ancla": (
                    [
                        {
                            "event_key": i["event_key"],
                            "fecha": i["fecha"],
                            "sensor": i["sensor"],
                            "con_miniatura": i.get("png") is not None,
                        }
                        for i in imagenes
                    ]
                    if imagenes
                    else []
                ),
                # GEE-dependent pieces (Sentinel-2 miniature) land later;
                # each degradation is APPENDED here, never fails the report.
                "degradado": degradado,
                # PR 6: what the campo surface needs (S5) — token + url for
                # the UI, sizes + notas for the operator. Bytes stay in
                # their own columns, never in JSONB.
                "campo": {
                    "token": row.token_publico,
                    "url": service.url_campo(row.token_publico),
                    "paquete_bytes": len(campo_bytes) if campo_bytes else None,
                    "kmz_bytes": len(kmz_bytes) if kmz_bytes else None,
                    "basemap": campo_basemap,
                    "notas": campo_notas,
                },
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
                kmz_bytes=kmz_bytes,
                campo_paquete=campo_bytes,
            ):
                logger.warning("informe_area.cas_perdido_al_completar", informe_id=informe_id)
                return {"informe_id": informe_id, "estado": "skipped"}
            logger.info(
                "informe_area.completado",
                informe_id=informe_id,
                area_ha=resultado["area_ha"],
                zonas=resultado["zonas"],
                pdf_bytes=len(pdf_bytes),
                kmz_bytes=len(kmz_bytes) if kmz_bytes else 0,
                campo_bytes=len(campo_bytes) if campo_bytes else 0,
                mapas=list(mapas_bytes),
            )
            return {"informe_id": informe_id, "estado": "completed"}
        except Exception as exc:  # noqa: BLE001 — the failure path IS the contract (S8)
            razon = _sanitizar_error_informe(exc)
            logger.error("informe_area.fallo", informe_id=informe_id, exc_info=True)
            db.rollback()
            repo.actualizar_estado_if_actual(
                db,
                informe_uuid,
                expected_estado=EstadoGeoJob.RUNNING,
                estado=EstadoGeoJob.FAILED,
                progreso=0,
                error=razon,
            )
            return {"informe_id": informe_id, "estado": "failed", "error": razon}
    finally:
        db.close()


@celery_app.task(queue="celery", name="geo.informe_area.limpiar_vencidos")
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
