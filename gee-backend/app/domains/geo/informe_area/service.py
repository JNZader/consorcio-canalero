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
from typing import Any, NamedTuple, Sequence
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
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
# desglose figures. PR 4 adds the IDECOR soils download stamp: a re-run of
# the ETL changes the clave, which is the layer-refresh invalidation for a
# table that lives outside ``geo_layers``.
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

#: The IDECOR soils stamp is a SEPARATE statement guarded in Python: a
#: ``CASE WHEN to_regclass(...)`` inside one SQL string does NOT protect
#: anything, because PostgreSQL resolves every table reference at plan
#: time regardless of which branch runs. The table is created by this PR's
#: migration, and the box applies migrations manually — the create path
#: must keep working on a database that does not have it yet.
_VERSIONES_SUELOS_SQL = text("SELECT max(fecha_de_bajada)::text FROM idecor_suelos_50mil")
_TABLA_SUELOS_IDECOR = "idecor_suelos_50mil"

#: Same guarded stamp for the cobertura rasters (S4): a re-run of the ETL
#: re-downloads and re-registers, and the clave must move with it.
_VERSIONES_COBERTURA_SQL = text("SELECT max(fecha_de_bajada)::text FROM idecor_cobertura_raster")
_TABLA_COBERTURA = "idecor_cobertura_raster"


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


# ── Suelos IDECOR 1:50.000 (PR 4, S3) ────────────────────────────────────────

#: Clipped hectares per carta unit + the unit's own attributes. The
#: intersection is measured in EPSG:32720 (the informe/ficha area standard),
#: polygons repaired and collection-extracted so a sliver can never
#: contribute a line/point artifact to the area sum.
_SUELOS_IDECOR_SQL = text(
    """
    WITH sel AS (SELECT ST_GeomFromGeoJSON(:geojson) AS g4326),
    fila AS (
        SELECT s.id, s.simbolo, s.clase, s.cu, s.ip, s.au_1m, s.au_2m,
               s.serie_1, s.porc_1, s.serie_2, s.porc_2,
               s.serie_3, s.porc_3, s.serie_4, s.porc_4,
               s.nombre, s.tipo_unida, s.pdf_simbolo,
               ST_Area(ST_CollectionExtract(
                   ST_Intersection(ST_Transform(ST_MakeValid(s.geometria), 32720),
                                   ST_Transform(ST_MakeValid(sel.g4326), 32720)), 3)
               ) / 10000.0 AS ha
        FROM idecor_suelos_50mil s, sel
        WHERE ST_Intersects(s.geometria, sel.g4326)
    )
    SELECT * FROM fila WHERE ha > 0.00001
    """
)

#: Same clip, one geometry parameter per zone — the per-subcuenca breakdown
#: (S10) resolved in ONE round trip instead of one query per zone.
_SUELOS_IDECOR_ZONAS_SQL = text(
    """
    WITH z AS (
        SELECT id AS zona_id, geometria FROM zonas_operativas
        WHERE id = ANY(CAST(:ids AS uuid[]))
    ),
    fila AS (
        SELECT z.zona_id, s.clase, s.ip,
               ST_Area(ST_CollectionExtract(
                   ST_Intersection(ST_Transform(ST_MakeValid(s.geometria), 32720),
                                   ST_Transform(ST_MakeValid(z.geometria), 32720)), 3)
               ) / 10000.0 AS ha
        FROM idecor_suelos_50mil s, z
        WHERE ST_Intersects(s.geometria, z.geometria)
    )
    SELECT * FROM fila WHERE ha > 0.00001
    """
)


def _series_unidad(fila: Any) -> str | None:
    """«SERIE 90 %; OTRA 10 %» — the populated (serie, porc) pairs of a unit."""
    partes = []
    for n in (1, 2, 3, 4):
        serie = getattr(fila, f"serie_{n}")
        if not serie:
            continue
        porc = getattr(fila, f"porc_{n}")
        partes.append(f"{serie} {porc} %" if porc is not None else serie)
    return "; ".join(partes) if partes else None


def _agregar_por_unidad(
    filas: Sequence[Any], area_ha: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float | None]:
    """Rows → (unidades sorted by ha, roman-class aggregate, area-weighted IP).

    Multi-part units arrive as several rows sharing one ``simbolo``; they
    pool BEFORE any percentage exists, exactly like the ficha pools
    capability prefixes. The IP mean is area-weighted over rows that carry
    an IP; rows without one join no denominator (the honest mean of what
    was measured, never a zero-pulled average).
    """
    por_simbolo: dict[str, dict[str, Any]] = {}
    por_clase: dict[str, float] = {}
    ip_ha = 0.0
    ip_suma = 0.0
    for fila in filas:
        ha = float(fila.ha)
        unidad = por_simbolo.setdefault(
            str(fila.simbolo),
            {
                "simbolo": str(fila.simbolo),
                "clase": fila.clase,
                "cu": fila.cu,
                "ip": fila.ip,
                "au_1m": fila.au_1m,
                "au_2m": fila.au_2m,
                "nombre": fila.nombre,
                "tipo_unida": fila.tipo_unida,
                "pdf_simbolo": fila.pdf_simbolo,
                "series": _series_unidad(fila),
                "ha": 0.0,
            },
        )
        unidad["ha"] = round(unidad["ha"] + ha, 4)
        clase = (fila.clase or "").strip() or "sin clasificar"
        por_clase[clase] = por_clase.get(clase, 0.0) + ha
        if fila.ip is not None:
            ip_ha += ha
            ip_suma += ha * float(fila.ip)

    unidades = sorted(por_simbolo.values(), key=lambda u: -u["ha"])
    for unidad in unidades:
        unidad["pct"] = round(unidad["ha"] / area_ha * 100.0, 2) if area_ha > 0 else 0.0

    clases = [
        {
            "clase": clase,
            "ha": round(ha, 4),
            "pct": round(ha / area_ha * 100.0, 2) if area_ha > 0 else 0.0,
        }
        for clase, ha in sorted(por_clase.items())
    ]
    ip_ponderado = round(ip_suma / ip_ha, 1) if ip_ha > 0 else None
    return unidades, clases, ip_ponderado


def suelos_idecor_dataset(db: Session, geojson_4326: str, area_ha: float) -> dict[str, Any] | None:
    """Section 4's dataset: per-unit hectares + class aggregate + weighted IP.

    ``None`` (→ the section renders «sin datos», S7) when the table is
    missing or empty — a deployment without the IDECOR ETL still gets its
    informe. Any other DB failure also degrades to ``None``: the soils
    cartography is a REPORTED layer, never a hard dependency of the job.
    The read runs inside a SAVEPOINT — PostgreSQL poisons the whole
    transaction on the first error, so swallowing the exception alone
    would leave an aborted session for every later query of the task.
    """
    try:
        with db.begin_nested():
            filas = db.execute(_SUELOS_IDECOR_SQL, {"geojson": geojson_4326}).all()
    except SQLAlchemyError:
        logger.warning("informe_area.suelos_idecor_no_disponible", exc_info=True)
        return None
    if not filas:
        return None

    unidades, clases, ip_ponderado = _agregar_por_unidad(filas, area_ha)
    cubierto_ha = sum(u["ha"] for u in unidades)
    residual_ha = max(0.0, area_ha - cubierto_ha)
    ratio = min(1.0, cubierto_ha / area_ha) if area_ha > 0 else 0.0
    if cubierto_ha <= 0:
        cobertura = "sin_cobertura"
    elif ratio >= 0.99:
        cobertura = "total"
    else:
        cobertura = "parcial"
    return {
        "cobertura": cobertura,
        "cobertura_ratio": round(ratio, 4),
        "clases": clases,
        "unidades": unidades,
        "ip_ponderado": ip_ponderado,
        "sin_cobertura_ha": round(residual_ha, 4),
    }


def suelos_idecor_por_zona(
    db: Session, zonas: list[tuple[uuid.UUID, float]]
) -> dict[str, dict[str, Any]]:
    """Per-zone coverage / dominant class / weighted IP (S10 breakdown).

    Zones whose intersecting area is zero stay ABSENT — the PDF shows «—»,
    never a fabricated 0 % coverage.
    """
    ids = [str(zona_id) for zona_id, _ha in zonas]
    try:
        with db.begin_nested():
            filas = db.execute(_SUELOS_IDECOR_ZONAS_SQL, {"ids": ids}).all()
    except SQLAlchemyError:
        logger.warning("informe_area.suelos_idecor_zonas_no_disponible", exc_info=True)
        return {}

    acumulado: dict[str, dict[str, Any]] = {}
    for fila in filas:
        clave = str(fila.zona_id)
        zona = acumulado.setdefault(clave, {"clases": {}, "ip_ha": 0.0, "ip_suma": 0.0})
        clase = (fila.clase or "").strip() or "sin clasificar"
        zona["clases"][clase] = zona["clases"].get(clase, 0.0) + float(fila.ha)
        if fila.ip is not None:
            zona["ip_ha"] += float(fila.ha)
            zona["ip_suma"] += float(fila.ha) * float(fila.ip)

    ha_por_id = {str(zona_id): ha for zona_id, ha in zonas}
    resultado: dict[str, dict[str, Any]] = {}
    for clave, zona in acumulado.items():
        ha_zona = ha_por_id.get(clave, 0.0)
        cubierto = sum(zona["clases"].values())
        dominante = max(zona["clases"], key=lambda c: (zona["clases"][c], c))
        resultado[clave] = {
            "clase_dominante": dominante,
            "ip_ponderado": (
                round(zona["ip_suma"] / zona["ip_ha"], 1) if zona["ip_ha"] > 0 else None
            ),
            "cobertura_pct": round(min(100.0, cubierto / ha_zona * 100.0), 2)
            if ha_zona > 0
            else None,
        }
    return resultado


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
        suelos_idecor: str | None = None
        if (
            db.execute(
                text("SELECT to_regclass(:tabla)"), {"tabla": _TABLA_SUELOS_IDECOR}
            ).scalar_one_or_none()
            is not None
        ):
            suelos_idecor = db.execute(_VERSIONES_SUELOS_SQL).scalar()
        cobertura_idecor: str | None = None
        if (
            db.execute(
                text("SELECT to_regclass(:tabla)"), {"tabla": _TABLA_COBERTURA}
            ).scalar_one_or_none()
            is not None
        ):
            cobertura_idecor = db.execute(_VERSIONES_COBERTURA_SQL).scalar()
    partes = [
        hash_seleccion,
        f"plantilla={settings.informe_area_version_plantilla}",
        f"flood_risk={fila.flood_risk or '-'}",
        f"drainage_need={fila.drainage_need or '-'}",
        f"precip_normal={fila.precip_normal or '-'}",
        f"composite={fila.composite or '-'}",
        f"suelos_idecor={suelos_idecor or '-'}",
        f"cobertura_idecor={cobertura_idecor or '-'}",
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


# ── Cobertura IDECOR (PR 4, S4) ──────────────────────────────────────────────

#: Registered raster rows: uso (1) + estivales (3), newest per capa. The
#: table is this PR's own registration surface (see the migration's
#: docstring for why not ``geo_layers``).
_COBERTURAS_SQL = text(
    """
    SELECT capa, tipo, campania, archivo_path, leyenda
    FROM idecor_cobertura_raster
    ORDER BY tipo, campania
    """
)


def _leer_capas_cobertura(db: Session) -> list[dict[str, Any]] | None:
    """Registered rows, or ``None`` when the table is missing/empty (S7).

    Savepoint for the same reason as the suelos read: a missing table
    must degrade the section, not poison the task's transaction.
    """
    try:
        with db.begin_nested():
            filas = db.execute(_COBERTURAS_SQL).all()
    except SQLAlchemyError:
        logger.warning("informe_area.cobertura_no_disponible", exc_info=True)
        return None
    if not filas:
        return None
    return [
        {
            "capa": f.capa,
            "tipo": f.tipo,
            "campania": f.campania,
            "archivo_path": f.archivo_path,
            "leyenda": f.leyenda or [],
        }
        for f in filas
    ]


def _breaks_de_leyenda(leyenda: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Legend entries → half-open bins centered on each class code.

    ``extract_zonal_profile`` bins on ``[min, max)`` with the last bin
    closed; ±0.5 around integer codes puts 255 (uso nodata) and NaN
    (estival nodata) outside every bin, which is exactly the intent.
    """
    return [
        {
            "label": str(entrada["etiqueta"]),
            "min": float(entrada["codigo"]) - 0.5,
            "max": float(entrada["codigo"]) + 0.5,
        }
        for entrada in leyenda
    ]


def _perfil_por_clase(
    ruta: str,
    leyenda: list[dict[str, Any]],
    geom4326: dict[str, Any],
    area_m2: float,
) -> tuple[list[dict[str, Any]], str, float]:
    """(clases ordenadas por ha, cobertura, cobertura_ratio) for one cover."""
    from app.domains.geo.composites import extract_zonal_profile

    perfil = extract_zonal_profile(
        ruta,
        geom4326,
        geom_crs="EPSG:4326",
        breaks=_breaks_de_leyenda(leyenda),
        geom_area_m2=area_m2,
    )
    clases: list[dict[str, Any]] = [
        {"clase": str(b["label"]), "ha": float(b["ha"]), "pct": float(b["pct"])}
        for b in perfil["bins"]
        if b["pixels"] > 0
    ]
    clases.sort(key=lambda c: -float(c["ha"]))
    return clases, str(perfil["coverage"]), float(perfil["coverage_ratio"])
    return clases, str(perfil["coverage"]), float(perfil["coverage_ratio"])


def _recurrencia_estivales(
    estivales: list[dict[str, Any]], geom4326: dict[str, Any]
) -> dict[str, float] | None:
    """Hectareas con cultivo estival en 3 / 2 / 1 / 0 campañas (pixel-exacto).

    The ETL downloads every estival cover onto the SAME 10 m grid, so the
    three reads stack without resampling: a pixel counts for a campaign
    when it is not nodata there (NaN = sin cultivo estival). The
    selection is rasterized once onto that grid; each cell contributes
    its whole 0,01 ha — at 10 m against selections of thousands of ha the
    boundary error sits far below S7's ±0,1 % reconciliation budget.
    """
    if len(estivales) < 3:
        return None
    try:
        import numpy as np
        import rasterio
        from pyproj import Transformer
        from rasterio.features import rasterize
        from shapely.geometry import shape
        from shapely.ops import transform as shapely_transform
    except Exception:  # noqa: BLE001 — worker deps; tests inject their own grids
        return None

    try:
        with rasterio.open(estivales[0]["archivo_path"]) as ref:
            grid_transform = ref.transform
            ancho, alto = ref.width, ref.height
            presentes = np.zeros((alto, ancho), dtype="uint8")
            for capa in estivales:
                with rasterio.open(capa["archivo_path"]) as src:
                    if src.width != ancho or src.height != alto:
                        logger.warning(
                            "informe_area.cobertura_grillas_desalineadas", capa=capa["capa"]
                        )
                        return None
                    # The estival covers carry NaN values WITHOUT a nodata
                    # tag (verified live: rasterio reports nodata=None), so
                    # ``read(masked=True)`` would mask nothing — validity is
                    # finiteness itself. Same rule ``extract_zonal_profile``
                    # applies (~np.isnan) for the per-class tables.
                    datos = src.read(1)
                    presentes += np.isfinite(datos).astype("uint8")
    except Exception:  # noqa: BLE001 — a missing/unreadable file degrades
        logger.warning(
            "informe_area.cobertura_archivo_ilegible", rutas=[c["archivo_path"] for c in estivales]
        )
        return None

    reproj = Transformer.from_crs("EPSG:4326", "EPSG:22174", always_xy=True)
    geom_22174 = shapely_transform(reproj.transform, shape(geom4326))
    mascara = rasterize(
        [(geom_22174, 1)],
        out_shape=(alto, ancho),
        transform=grid_transform,
        fill=0,
        dtype="uint8",
        all_touched=False,
    ).astype(bool)

    dentro = presentes[mascara]
    area_px_ha = 100.0 / 10_000.0  # 10 m × 10 m
    return {
        f"{n}_campanias_ha": round(float((dentro == n).sum()) * area_px_ha, 2) for n in (3, 2, 1, 0)
    }


def cobertura_dataset(
    db: Session, geom4326: dict[str, Any], area_m2: float
) -> dict[str, Any] | None:
    """Section 5's dataset: uso classes, estival campaigns, summer recurrence.

    ``None`` → «sin datos» (S7). Percentages are over the selection's
    whole area; the builder's residual row reconciles each table.
    """
    capas = _leer_capas_cobertura(db)
    if capas is None:
        return None
    usos = [c for c in capas if c["tipo"] == "cobertura_uso"]
    estivales = [c for c in capas if c["tipo"] == "cobertura_estival"]
    if not usos:
        return None

    try:
        uso = usos[0]
        clases, cobertura, cobertura_ratio = _perfil_por_clase(
            uso["archivo_path"], uso["leyenda"], geom4326, area_m2
        )
        por_clase = {c["clase"]: c for c in clases}
        # % «Cuerpo de agua estacional» (código 9, S4): resolved from the
        # STORED legend by label — never by hardcoded code or position,
        # because the estival codings differ between campaigns.
        etiqueta_agua = next(
            (
                str(e["etiqueta"])
                for e in uso["leyenda"]
                if "agua estacional" in str(e["etiqueta"]).lower()
            ),
            None,
        )
        pct_agua = por_clase[etiqueta_agua]["pct"] if etiqueta_agua in por_clase else None

        area_ha = area_m2 / 10_000.0
        campanias = []
        for capa in estivales:
            clases_c, _cob, _ratio = _perfil_por_clase(
                capa["archivo_path"], capa["leyenda"], geom4326, area_m2
            )
            cultivado = sum(c["ha"] for c in clases_c)
            campanias.append(
                {
                    "capa": capa["capa"],
                    "campania": capa["campania"],
                    "clases": clases_c,
                    "ha_cultivo": round(cultivado, 2),
                    "pct_cultivo": round(cultivado / area_ha * 100.0, 2) if area_ha > 0 else 0.0,
                }
            )

        return {
            "cobertura": cobertura,
            "cobertura_ratio": cobertura_ratio,
            "clases": clases,
            "etiqueta_agua_estacional": etiqueta_agua,
            "pct_agua_estacional": pct_agua,
            "campanias": campanias,
            "recurrencia": _recurrencia_estivales(estivales, geom4326),
        }
    except Exception:  # noqa: BLE001 — IDECOR is a reported layer, never fatal
        logger.warning("informe_area.cobertura_fallo", exc_info=True)
        return None


def cobertura_por_zona(
    db: Session,
    zonas: list[tuple[uuid.UUID, str, str]],
) -> dict[str, dict[str, float | None]]:
    """Per-zone % cultivo (uso, clases de «Cultivo») y % soja (última campaña).

    ``zonas`` carries ``(zona_id, nombre, geojson_4326)`` — the task
    already resolved those geometries for the maps, so no re-query. Label
    matching (not codes) keeps working when a campaign's coding differs.
    Degrades to ``{}`` like every IDECOR read (S7).
    """
    capas = _leer_capas_cobertura(db)
    if capas is None:
        return {}
    usos = [c for c in capas if c["tipo"] == "cobertura_uso"]
    estivales = [c for c in capas if c["tipo"] == "cobertura_estival"]
    if not usos:
        return {}

    def _pct(clases: list[dict[str, Any]], claves: tuple[str, ...]) -> float | None:
        pct = sum(
            float(c["pct"]) for c in clases if any(clave in c["clase"].lower() for clave in claves)
        )
        return round(pct, 2) if pct > 0 else None

    uso = usos[0]
    estival = estivales[-1] if estivales else None
    resultado: dict[str, dict[str, float | None]] = {}
    try:
        for zona_id, _nombre, geojson in zonas:
            clases_uso, _cob, _ratio = _perfil_por_clase(
                uso["archivo_path"], uso["leyenda"], json.loads(geojson), 0.0
            )
            fila: dict[str, float | None] = {
                "pct_cultivo": _pct(clases_uso, ("cultivo",)),
            }
            if estival is not None:
                clases_est, _cob_e, _ratio_e = _perfil_por_clase(
                    estival["archivo_path"], estival["leyenda"], json.loads(geojson), 0.0
                )
                fila["pct_soja"] = _pct(clases_est, ("soja",))
            resultado[str(zona_id)] = fila
    except Exception:  # noqa: BLE001 — reported layer, never fatal
        logger.warning("informe_area.cobertura_zonas_fallo", exc_info=True)
        return {}
    return resultado
