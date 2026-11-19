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
from app.domains.geo.informe_area.schemas import InformeAreaCreate
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


# Per-zone rows of the selection — PR 1's own SQL, reused verbatim so the
# informe and the ficha cannot disagree about what a zona is. The union SQL
# below is NOT ``_ZONAS_UNION_SQL`` because it must also hash and measure in
# the same pass; it is its exact union expression plus the normalization tail
# (and, since T2, it also emits the union GeoJSON the maps render).
_SELECCION_SQL = text(
    """
    WITH seleccion AS (
        SELECT z.id AS zona_id, z.nombre AS nombre, z.cuenca AS cuenca,
               z.geometria AS geometria,
               ST_Transform(z.geometria, 32720) AS geom_32720
        FROM zonas_operativas z
        WHERE z.id = ANY(CAST(:ids AS uuid[]))
    ), unida AS (
        SELECT ST_CollectionExtract(ST_MakeValid(ST_Union(geometria)), 3) AS g4326,
               ST_CollectionExtract(ST_MakeValid(ST_Union(geom_32720)), 3) AS g32720
        FROM seleccion
    ), normalizada AS (
        SELECT ST_SnapToGrid(g4326, 0.0000001) AS snap, g4326, g32720 FROM unida
    )
    SELECT encode(
               sha256(ST_AsBinary(snap) || convert_to(:ids_ordenados, 'UTF8')),
               'hex'
           ) AS hash_seleccion,
           ST_Area(g32720) / 10000.0 AS area_ha,
           ST_NPoints(ST_SimplifyPreserveTopology(g32720, :tolerancia)) AS vertices,
           ST_AsGeoJSON(g4326) AS geojson
    FROM normalizada
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


def resolver_seleccion(db: Session, zona_ids: list[uuid.UUID]) -> SeleccionResuelta:
    """Resolve, hash and measure a selection under the INFORME caps (S5).

    Raises the ficha's own coded errors — 404 ``zona_no_encontrada`` for any
    missing id (all-or-nothing), 422 ``cap_excedido`` for the 120-zona bound,
    the 150 000 ha area bound and the 20 000 post-simplify vertex bound — so
    the informe's failures read exactly like the ficha's.
    """
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

    if len(filas) > settings.informe_area_max_zonas:
        raise ficha_errors.cap_excedido(
            "subcuencas",
            float(settings.informe_area_max_zonas),
            float(len(filas)),
        )

    ids_ordenados = ",".join(sorted(str(z) for z in ids_unicos))
    with ficha_service._traducir_fallas_db():  # noqa: SLF001 — PR 1 reuse (S12)
        fila = db.execute(
            _SELECCION_SQL,
            {
                "ids": [str(z) for z in ids_unicos],
                "ids_ordenados": ids_ordenados,
                "tolerancia": TOLERANCIA_SIMPLIFY_M,
            },
        ).one()

    area_ha = float(fila.area_ha or 0.0)
    if area_ha <= 0.0:
        raise ficha_errors.geometria_invalida(
            "la union de las zonas quedo vacia o sin area tras repararla"
        )
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
    seleccion = resolver_seleccion(db, payload.zona_ids)
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
