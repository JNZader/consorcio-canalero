"""Informe de área service — cache identity, caps, privacy, dispatch (T1).

The create path is the S4/S5 pipeline, in order:

1. **Resolve** the selection with PR 1's own SQL (``_ZONAS_SQL`` /
   ``_ZONAS_UNION_SQL`` from ``ficha_service``) — all-or-nothing on unknown
   ids, repaired server-side union, exactly like ``tipo=zonas``. The informe
   caps (120 zonas, S5) are applied HERE, not the ficha's 60: the ficha is a
   synchronous public compute, the informe is a bounded background job.
2. **Hash** the normalized selection: union → ``ST_SnapToGrid(1e-7)`` → WKB
   bytes ‖ sorted ids → sha256, all inside PostgreSQL so the geometry never
   crosses the wire twice (``sha256(bytea)`` is core SQL since PG 11 — no
   pgcrypto dependency).
3. **Version** the clave: the hash plus the newest ``geo_layers`` row per
   dataset the informe reads plus ``composite_zonal_stats`` recency plus
   ``version_plantilla``. A layer refresh changes the clave — that IS the
   invalidation; there is no purge.
4. **Caps** area (150 000 ha) and post-simplify vertices (20 000) over the
   RESOLVED union, then the per-user ceiling of 3 in-progress (429).
5. **Cache probe**: a completed row of THIS user with the same clave is
   returned as-is (``desde_cache=True``), no task enqueued.
6. **Dispatch**: row + outbox intent in one transaction, then the best-effort
   immediate publish (the beat task retries what it misses).

Reads are private (S11): the creator sees the row, an admin sees everything,
anybody else gets the same 404 as for a missing id.
"""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.domains.geo import ficha_errors
from app.domains.geo import ficha_service
from app.domains.geo.informe_area import errors
from app.domains.geo.informe_area.models import InformeArea
from app.domains.geo.informe_area.repository import InformeAreaRepository
from app.domains.geo.informe_area.schemas import (
    InformeAreaCreate,
    InformeAreaPreviewRequest,
    InformeAreaPreviewResponse,
    InformeAreaPreviewSubcuenca,
)
from app.shared.celery_outbox import (
    CeleryTaskKey,
    enqueue_celery_task,
    try_publish_celery_task,
)

logger = get_logger(__name__)

repo = InformeAreaRepository()

M2_POR_HA = ficha_service.M2_POR_HA

# The simplify tolerance the informe's own vertex cap is measured AFTER (S5:
# "20 000 después de simplificar"). 20 m is the same tolerance the catchment
# ETL uses, so the bound is measured against the geometry class T2 will
# actually render, not the raw dissolved perimeter.
TOLERANCIA_SIMPLIFY_M = 20.0


class SeleccionResuelta(NamedTuple):
    """Everything the create path needs from one round trip of resolution."""

    hash_seleccion: str
    area_ha: float
    vertices_simplificados: int
    nombres: list[str]
    cuencas: list[str]
    # Union GeoJSON (4326, un-snapped) — T2's static maps clip against it.
    geojson: str = ""
    # PR 3 (S4): hectares of the union OUTSIDE the consorcio zone.
    fuera_zona_ha: float = 0.0
    # PR 3 (S2): True when the union is a disjoint multipolygon.
    poligonos_separados: bool = False
    # PR 3: per-zona (id, nombre, cuenca, ha) rows for the preview's per-cuenca
    # breakdown — empty for a geometry-only selection (S3: "desglose rows may
    # be empty — totals still work").
    zonas_detalle: list[tuple[uuid.UUID, str, str, float]] = []


# Per-zone rows of the selection — PR 1's own SQL, reused verbatim so the
# informe and the ficha cannot disagree about what a zona is. The union SQL
# below is NOT ``_ZONAS_UNION_SQL`` because it must also hash and measure in
# the same pass; it is its exact union expression plus the normalization tail
# (and, since T2, it also emits the union GeoJSON the maps render).
#
# PR 3 (S3/S4): the selection is now the union of the picked zonas PLUS the
# caller-supplied geometrias (drawn / KML-imported), each repaired with
# ``ST_MakeValid`` BEFORE the union so an autointersecting polygon measures
# its true area instead of failing or flipping sign (S6's pytest). The
# geometrias travel as a JSON array; ``jsonb_array_elements`` rows go through
# ``ST_GeomFromGeoJSON`` (which reads only ``type``/``coordinates``) and a
# defensive ``ST_CollectionExtract(…, 3)`` keeps polygonal output only.
#
# ``fuera_zona_ha`` (S4: "avisa cuánto quedó fuera de la zona del consorcio")
# is the difference against the union of EVERY ``zonas_operativas`` row — the
# database's consorcio extent. DEVIATION, reported: the plan names
# ``zona_cc_ampliada``, which exists only as a GEE asset (no PostGIS table),
# and this pipeline is PostGIS-only by design (no GEE call in the informe
# path). The zonas union is a subset of the ampliada, so the figure
# OVER-reports never under-reports — the safe direction for a warning.
# It is only computed when geometrias are present: a zonas-only union is
# inside the zonas union by construction.
_SELECCION_SQL = text(
    """
    WITH seleccion AS (
        SELECT z.id AS zona_id, z.nombre AS nombre, z.cuenca AS cuenca,
               z.geometria AS geometria,
               ST_Transform(z.geometria, 32720) AS geom_32720
        FROM zonas_operativas z
        WHERE z.id = ANY(CAST(:ids AS uuid[]))
    ), entrada AS (
        SELECT ST_CollectionExtract(ST_MakeValid(ST_GeomFromGeoJSON(g.value)), 3)
                   AS geometria,
               ST_Transform(
                   ST_CollectionExtract(ST_MakeValid(ST_GeomFromGeoJSON(g.value)), 3),
                   32720
               ) AS geom_32720
        FROM jsonb_array_elements(CAST(:geometrias AS jsonb)) AS g
    ), partes AS (
        SELECT geometria, geom_32720 FROM seleccion
        UNION ALL
        SELECT geometria, geom_32720 FROM entrada
    ), unida AS (
        SELECT ST_CollectionExtract(ST_MakeValid(ST_Union(geometria)), 3) AS g4326,
               ST_CollectionExtract(ST_MakeValid(ST_Union(geom_32720)), 3) AS g32720
        FROM partes
    ), zona_consorcio AS (
        SELECT ST_CollectionExtract(ST_MakeValid(ST_Union(
                   ST_Transform(geometria, 32720)
               )), 3) AS g
        FROM zonas_operativas
        WHERE :con_geometrias
    ), normalizada AS (
        SELECT ST_SnapToGrid(g4326, 0.0000001) AS snap, g4326, g32720 FROM unida
    )
    SELECT encode(
               sha256(ST_AsBinary(snap) || convert_to(:ids_ordenados, 'UTF8')),
               'hex'
           ) AS hash_seleccion,
           ST_Area(g32720) / 10000.0 AS area_ha,
           ST_NPoints(ST_SimplifyPreserveTopology(g32720, :tolerancia)) AS vertices,
           ST_AsGeoJSON(g4326) AS geojson,
           COALESCE(
               ST_Area(ST_Difference(g32720, zona_consorcio.g)) / 10000.0, 0.0
           ) AS fuera_zona_ha,
           (ST_NumGeometries(ST_Multi(g4326)) > 1) AS poligonos_separados
    FROM normalizada, zona_consorcio
    """
)

# What feeds ``version_clave`` (S4: "la clave suma versiones de cada capa").
# Per dataset, the newest registered ``geo_layers`` row's ``created_at`` (the
# ETL registers a fresh row per run, so created_at IS the run identity); for
# the CHIRPS normals the ETL also stamps ``metadata_extra.version``, which
# wins when present because it is what ``get_latest_precip_normals_by_month``
# orders by. ``composite_zonal_stats.fecha_calculo`` versions the stored
# desglose figures. ``suelos_catastro`` has NO version signal anywhere in the
# schema (no updated_at, no layer row) — that gap is reported, not papered
# over with a lie like max(id).
_VERSIONES_SQL = text(
    """
    SELECT
        (SELECT max(created_at)::text FROM geo_layers WHERE tipo = 'flood_risk')
            AS flood_risk,
        (SELECT max(created_at)::text FROM geo_layers WHERE tipo = 'drainage_need')
            AS drainage_need,
        (SELECT max(COALESCE(metadata_extra->>'version', created_at::text))
             FROM geo_layers WHERE tipo = 'precip_normal') AS precip_normal,
        (SELECT max(fecha_calculo)::text FROM composite_zonal_stats
             WHERE tipo = 'flood_risk') AS composite
    """
)


def resolver_seleccion(
    db: Session,
    zona_ids: list[uuid.UUID],
    geometrias: list[dict[str, Any]] | None = None,
    *,
    aplicar_caps: bool = True,
) -> SeleccionResuelta:
    """Resolve, hash and measure a MIXED selection under the INFORME caps (S5).

    ``zona_ids`` and ``geometrias`` may each be empty but not both. The
    geometries are repaired server-side (``ST_MakeValid``, S4) and unioned
    with the zonas; the hash covers the RESOLVED union, so two selections
    with the same union share a cache clave regardless of how they were
    assembled (zonas vs drawn vs KML).

    ``aplicar_caps=False`` is the preview path: the same measurement without
    the 422s, so an over-cap selection gets ANSWERED (with ``aviso_cap``)
    instead of rejected — the same contract ``ficha_service.preview_zonas``
    applies on its side of the fence.

    Raises the ficha's own coded errors — 404 ``zona_no_encontrada`` for any
    missing id (all-or-nothing), 422 ``cap_excedido`` for the 120
    zonas-equivalent bound, the 150 000 ha area bound and the 20 000
    post-simplify vertex bound — so the informe's failures read exactly like
    the ficha's.
    """
    geometrias = geometrias or []
    ids_unicos = list(dict.fromkeys(zona_ids))
    if len(ids_unicos) != len(zona_ids):
        raise ficha_errors.geometria_invalida("zona_ids contiene ids duplicados")

    with ficha_service._traducir_fallas_db():  # noqa: SLF001 — PR 1 reuse (S12)
        filas = db.execute(
            ficha_service._ZONAS_SQL,  # noqa: SLF001 — PR 1 reuse (S12)
            {"ids": [str(z) for z in ids_unicos], "cuencas": []},
        ).all()

    encontradas = {fila.zona_id for fila in filas}
    faltantes = [z for z in ids_unicos if z not in encontradas]
    if faltantes:
        raise ficha_service.zonas_no_encontradas(faltantes)

    if len(filas) + len(geometrias) > settings.informe_area_max_zonas:
        raise ficha_errors.cap_excedido(
            "subcuencas",
            float(settings.informe_area_max_zonas),
            float(len(filas) + len(geometrias)),
        )

    ids_ordenados = ",".join(sorted(str(z) for z in ids_unicos))
    with ficha_service._traducir_fallas_db():  # noqa: SLF001 — PR 1 reuse (S12)
        fila = db.execute(
            _SELECCION_SQL,
            {
                "ids": [str(z) for z in ids_unicos],
                "ids_ordenados": ids_ordenados,
                "geometrias": json.dumps(geometrias, separators=(",", ":")),
                "con_geometrias": bool(geometrias),
                "tolerancia": TOLERANCIA_SIMPLIFY_M,
            },
        ).one()

    area_ha = float(fila.area_ha or 0.0)
    if area_ha <= 0.0:
        raise ficha_errors.geometria_invalida(
            "la union de la seleccion quedo vacia o sin area tras repararla"
        )
    if aplicar_caps:
        if area_ha > settings.informe_area_max_ha:
            raise ficha_errors.cap_excedido("area_ha", settings.informe_area_max_ha, area_ha)
        if int(fila.vertices or 0) > settings.informe_area_max_vertices:
            raise ficha_errors.cap_excedido(
                "vertices",
                float(settings.informe_area_max_vertices),
                float(fila.vertices),
            )

    return SeleccionResuelta(
        hash_seleccion=fila.hash_seleccion,
        area_ha=area_ha,
        vertices_simplificados=int(fila.vertices or 0),
        nombres=[f.nombre for f in filas],
        cuencas=sorted({f.cuenca for f in filas}),
        geojson=fila.geojson or "",
        fuera_zona_ha=max(0.0, float(fila.fuera_zona_ha or 0.0)),
        poligonos_separados=bool(fila.poligonos_separados),
        zonas_detalle=[(f.zona_id, f.nombre, f.cuenca, float(f.ha or 0.0)) for f in filas],
    )


def previsualizar(db: Session, payload: InformeAreaPreviewRequest) -> InformeAreaPreviewResponse:
    """Geometry-only measurement of a MIXED selection — the Revisar step (S2/S4).

    Sibling of ``ficha_service.preview_zonas`` on the informe side of the
    fence: same "answer, don't reject" contract (``aplicar_caps=False`` — an
    over-cap selection gets ``aviso_cap`` instead of a 422, because every
    selection generates through the background path since PR 2), plus the two
    PR 3 avisos: ``fuera_zona_ha`` (parts outside the consorcio zone) and
    ``poligonos_separados`` (a disjoint selection).

    No rate limiter on the route (documented there): the create throttle is
    about ETL-style cost, this is authenticated, statement-timeout-bounded
    PostGIS work per selection change. No audit row either — unlike the
    PUBLIC ficha preview, this route is ``current_active_user``-only and the
    Ley 25.326 trace the ficha preview carries is about anonymous traffic.
    """
    seleccion = resolver_seleccion(
        db, list(payload.zona_ids), payload.geometrias, aplicar_caps=False
    )
    cap_ha = ficha_service.area_cap_ha("zonas")
    return InformeAreaPreviewResponse(
        area_total_ha=round(seleccion.area_ha, 4),
        area_total_ha_geodesica=round(
            ficha_service._area_geodesica_ha(seleccion.geojson),  # noqa: SLF001 — PR 1 reuse
            4,
        )
        if seleccion.geojson
        else 0.0,
        subcuencas=[
            InformeAreaPreviewSubcuenca(id=zona_id, nombre=nombre, cuenca=cuenca, ha=round(ha, 4))
            for zona_id, nombre, cuenca, ha in seleccion.zonas_detalle
        ],
        cantidad_geometrias=len(payload.geometrias),
        fuera_zona_ha=round(seleccion.fuera_zona_ha, 4),
        poligonos_separados=seleccion.poligonos_separados,
        aviso_cap=seleccion.area_ha > cap_ha,
    )


# Stored drainage-need high-risk hectares per zone — the same rows
# ``_ALTO_CRITICO_SQL`` reads for flood_risk in the ficha (the DEM pipeline
# writes both tipos through ``extract_composite_zonal_stats``), read here so
# the PDF's section 3 can carry the same per-subcuenca structure as section 2
# without touching the ficha's package.
_DRENAJE_ALTO_SQL = text(
    """
    SELECT zona_id, area_high_risk_ha
    FROM composite_zonal_stats
    WHERE tipo = 'drainage_need' AND zona_id = ANY(CAST(:ids AS uuid[]))
    """
)


def pct_drenaje_por_zona(
    db: Session, zonas: list[tuple[uuid.UUID, float]]
) -> dict[uuid.UUID, float]:
    """Per-zone drainage Alto+Crítico share from stored composite rows.

    Same clamp and same None-means-absent contract as the ficha's
    ``pct_alto_critico``: stored ha over the zone's own ha, clamped to
    [0, 100]; zones without a stored row are simply absent.
    """
    ids = [str(zona_id) for zona_id, _ha in zonas]
    with ficha_service._traducir_fallas_db():  # noqa: SLF001 — PR 1 reuse (S12)
        filas = db.execute(_DRENAJE_ALTO_SQL, {"ids": ids}).all()
    ha_por_id = dict(zonas)
    return {
        fila.zona_id: round(
            min(100.0, max(0.0, float(fila.area_high_risk_ha) / ha_por_id[fila.zona_id] * 100.0)), 2
        )
        for fila in filas
        if fila.area_high_risk_ha is not None and ha_por_id.get(fila.zona_id, 0.0) > 0.0
    }


def calcular_version_clave(db: Session, hash_seleccion: str) -> str:
    """hash_seleccion + per-layer versions + version_plantilla (S4)."""
    with ficha_service._traducir_fallas_db():  # noqa: SLF001 — PR 1 reuse (S12)
        fila = db.execute(_VERSIONES_SQL).one()
    partes = [
        hash_seleccion,
        f"plantilla={settings.informe_area_version_plantilla}",
        f"flood_risk={fila.flood_risk or '-'}",
        f"drainage_need={fila.drainage_need or '-'}",
        f"precip_normal={fila.precip_normal or '-'}",
        f"composite={fila.composite or '-'}",
    ]
    return "|".join(partes)


def crear_informe(
    db: Session,
    payload: InformeAreaCreate,
    *,
    usuario_id: uuid.UUID,
) -> tuple[InformeArea, bool]:
    """Validate → hash → version → cache probe → dispatch. Returns (row, desde_cache)."""
    seleccion = resolver_seleccion(db, payload.zona_ids, payload.geometrias)
    version_clave = calcular_version_clave(db, seleccion.hash_seleccion)

    en_curso = repo.contar_en_curso(db, usuario_id)
    if en_curso >= settings.informe_area_max_en_curso:
        raise errors.limite_en_curso(settings.informe_area_max_en_curso)

    cacheado = repo.buscar_completado(db, usuario_id=usuario_id, version_clave=version_clave)
    if cacheado is not None:
        return cacheado, True

    task_id = uuid.uuid4()
    row = repo.crear(
        db,
        usuario_id=usuario_id,
        nombre=payload.nombre,
        hash_seleccion=seleccion.hash_seleccion,
        version_clave=version_clave,
        parametros={
            "zona_ids": [str(z) for z in payload.zona_ids],
            # PR 3: the geometrias ride in parametros so the task re-resolves
            # the SAME union (the row is the only durable copy of a drawn or
            # imported polygon — there is no zonas_operativas row behind it).
            "geometrias": payload.geometrias,
            "desglose": payload.desglose,
        },
        vence_at=datetime.now(timezone.utc) + timedelta(days=settings.informe_area_retencion_dias),
        celery_task_id=str(task_id),
    )
    outbox = enqueue_celery_task(
        db,
        celery_task_id=task_id,
        task_key=CeleryTaskKey.INFORME_AREA,
        task_kwargs={"informe_id": str(row.id)},
    )
    db.commit()

    try:
        publicado = try_publish_celery_task(outbox.id)
    except Exception as exc:  # noqa: BLE001 — publication is best-effort, never fatal
        publicado = False
        logger.error(
            "informe_area.publicacion_inmediata_fallo",
            informe_id=str(row.id),
            error_type=type(exc).__name__,
        )
    if not publicado:
        logger.info("informe_area.publicacion_deferida", informe_id=str(row.id))
    db.refresh(row)
    return row, False


def _es_admin(usuario: Any) -> bool:
    rol = getattr(usuario, "role", None)
    from app.auth.models import UserRole  # lazy: models import at call time

    return rol == UserRole.ADMIN


def obtener_informe(db: Session, informe_id: uuid.UUID, *, usuario: Any) -> InformeArea:
    """Creator or admin; anybody else gets the missing-id 404 (S11)."""
    row = repo.obtener(db, informe_id)
    if row is None:
        raise errors.informe_no_encontrado()
    if row.usuario_id != usuario.id and not _es_admin(usuario):
        raise errors.informe_no_encontrado()
    return row


def listar_informes(db: Session, *, usuario: Any) -> tuple[list[InformeArea], int]:
    """Own rows; admin sees all (S11)."""
    if _es_admin(usuario):
        return repo.listar(db)
    return repo.listar(db, usuario_id=usuario.id)


def _nombre_archivo(nombre: str) -> tuple[str, str]:
    """(ascii fallback, utf-8 filename) for the Content-Disposition header.

    Spanish names carry accents the ASCII fallback flattens; the ``filename*``
    half keeps the original spelling for clients that honor RFC 5987.
    """
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", plano).strip("-").lower() or "informe-area"
    ascii_name = f"informe-{slug[:60]}.pdf"
    utf8_name = quote(f"{nombre.strip() or 'informe-area'}.pdf")
    return ascii_name, utf8_name


def descargar_pdf(db: Session, informe_id: uuid.UUID, *, usuario: Any) -> tuple[bytes, str]:
    """Return ``(pdf_bytes, content_disposition_filename)`` for a completed row.

    Privacy first, then state: pending/running → 409 en progreso; failed →
    409 with the stored readable reason; completed with bytes → the PDF;
    completed WITHOUT bytes (a row force-completed before the renderer ran,
    or a T1-era row) → the typed 503, never a fabricated empty document.
    """
    row = obtener_informe(db, informe_id, usuario=usuario)
    estado = row.estado.value if hasattr(row.estado, "value") else str(row.estado)
    if estado == "pending" or estado == "running":
        raise errors.pdf_en_progreso()
    if estado == "failed":
        raise errors.informe_fallido(row.error)
    if not row.pdf_bytes:
        raise errors.pdf_no_disponible()
    ascii_name, utf8_name = _nombre_archivo(row.nombre)
    return bytes(
        row.pdf_bytes
    ), f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
