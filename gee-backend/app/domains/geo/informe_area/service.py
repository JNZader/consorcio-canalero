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

import base64
import json
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
#
# PR 5 (#738): the share is ``ha_alto + ha_critico`` — the legend's own
# Alto+Crítico area (50–70 + ≥70 for drainage_need). Both must be non-NULL:
# rows written before the recompute carry the legacy figure only and a
# partial read would mix two threshold regimes in one table.
_ALTO_CRITICO_HA_SQL = text(
    """
    SELECT zona_id, ha_alto, ha_critico
    FROM composite_zonal_stats
    WHERE tipo = :tipo AND zona_id = ANY(CAST(:ids AS uuid[]))
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


def pct_alto_critico_por_zona(
    db: Session, zonas: list[tuple[uuid.UUID, float]], tipo: str
) -> dict[uuid.UUID, float]:
    """Per-zone Alto+Crítico share from the stored legend-derived columns.

    Same clamp and same None-means-absent contract as the ficha's
    ``pct_alto_critico``: stored ``ha_alto + ha_critico`` over the zone's own
    ha, clamped to [0, 100]; zones without a stored row — or whose row
    predates the #738 recompute (NULL columns) — are simply absent, never a
    confident 0 %.
    """
    ids = [str(zona_id) for zona_id, _ha in zonas]
    with ficha_service._traducir_fallas_db():  # noqa: SLF001 — PR 1 reuse (S12)
        filas = db.execute(_ALTO_CRITICO_HA_SQL, {"ids": ids, "tipo": tipo}).all()
    ha_por_id = dict(zonas)
    resultado: dict[uuid.UUID, float] = {}
    for fila in filas:
        if fila.ha_alto is None or fila.ha_critico is None:
            continue
        if ha_por_id.get(fila.zona_id, 0.0) <= 0.0:
            continue
        alto_critico = float(fila.ha_alto) + float(fila.ha_critico)
        resultado[fila.zona_id] = round(
            min(100.0, max(0.0, alto_critico / ha_por_id[fila.zona_id] * 100.0)), 2
        )
    return resultado


def pct_drenaje_por_zona(
    db: Session, zonas: list[tuple[uuid.UUID, float]]
) -> dict[uuid.UUID, float]:
    """Per-zone drainage Alto+Crítico share from stored composite rows."""
    return pct_alto_critico_por_zona(db, zonas, "drainage_need")


# ── Validación de flood_risk con eventos ancla (PR 5, S4) ────────────────────

#: The whole validation table — rows are per (event, class) for the WHOLE
#: consorcio zone, so no per-selection clip exists or is invented: the
#: section presents the index's zone-scale calibration as zone-scale evidence.
_VALIDACION_SQL = text(
    """
    SELECT evento_key, fecha, clase, ha_clase, ha_con_agua, pct_con_agua,
           lluvia_30d_mm, sensor, escena_id, version_flood_risk
    FROM riesgo_validacion_evento
    ORDER BY fecha, evento_key
    """
)


def riesgo_validacion_dataset(db: Session) -> dict[str, Any] | None:
    """Section 2's validation dataset: observed water per class, per event.

    ``None`` (→ the section omits the table) when the table is missing or
    empty — a deployment without the calibration ETL still gets its informe.
    Any other DB failure also degrades to ``None``: the validation is a
    REPORTED layer, never a hard dependency of the job (same contract as the
    IDECOR reads, including the SAVEPOINT so a missing table cannot poison
    the task's transaction).
    """
    try:
        if (
            db.execute(text("SELECT to_regclass('riesgo_validacion_evento')")).scalar_one_or_none()
            is None
        ):
            return None
        with db.begin_nested():
            filas = db.execute(_VALIDACION_SQL).all()
    except SQLAlchemyError:
        logger.warning("informe_area.riesgo_validacion_no_disponible", exc_info=True)
        return None
    if not filas:
        return None

    eventos: dict[str, dict[str, Any]] = {}
    for fila in filas:
        clave = str(fila.evento_key)
        evento = eventos.setdefault(
            clave,
            {
                "evento_key": clave,
                "fecha": str(fila.fecha),
                "sensor": str(fila.sensor),
                "escena": str(fila.escena_id),
                "lluvia_30d_mm": (
                    float(fila.lluvia_30d_mm) if fila.lluvia_30d_mm is not None else None
                ),
                "clases": {},
            },
        )
        evento["clases"][str(fila.clase)] = {
            "ha_clase": float(fila.ha_clase),
            "ha_con_agua": float(fila.ha_con_agua),
            "pct_con_agua": float(fila.pct_con_agua),
        }
    lista = sorted(eventos.values(), key=lambda e: e["fecha"])
    return {
        "eventos": lista,
        "version_flood_risk": str(filas[0].version_flood_risk),
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


# ── Canales (PR 4, S5) ───────────────────────────────────────────────────────

#: Kilómetros of curated canals INSIDE the selection, by estado. The clip
#: is measured in EPSG:32720 (the informe/ficha length standard) and
#: collection-extracted to lines so a boundary-touching polygon can never
#: contribute a point/line artifact. Source: ``canal_consorcio`` — the
#: curated base the system loads (60 canales: 41 relevados + 19
#: propuestos) — NOT ``canal_network``: that table is the pgRouting edge
#: topology the DEM burn reads, it carries no ``estado`` and nothing in
#: this codebase populates it.
_CANALES_KM_SQL = text(
    """
    WITH sel AS (
        SELECT ST_MakeValid(ST_GeomFromGeoJSON(:geojson)) AS g4326,
               ST_Transform(ST_MakeValid(ST_GeomFromGeoJSON(:geojson)), 32720) AS g32720
    )
    SELECT c.estado AS estado,
           sum(ST_Length(ST_CollectionExtract(
               ST_Intersection(ST_Transform(c.geom, 32720), sel.g32720), 2))) / 1000.0 AS km
    FROM canal_consorcio c, sel
    WHERE ST_Intersects(c.geom, sel.g4326)
    GROUP BY c.estado
    """
)

#: Road crossings inside the selection, split by the table's own tipo
#: (``canal`` = canal/road crossing, ``flujo_natural`` = drainage/road).
_CRUCES_SQL = text(
    """
    SELECT tipo, count(*) AS n
    FROM cruce_camino, (SELECT ST_MakeValid(ST_GeomFromGeoJSON(:geojson)) AS g) sel
    WHERE ST_Intersects(geometria, sel.g)
    GROUP BY tipo
    """
)

#: Detected conflict points inside the selection, by severidad.
_CONFLICTOS_SQL = text(
    """
    SELECT severidad, count(*) AS n
    FROM puntos_conflicto, (SELECT ST_MakeValid(ST_GeomFromGeoJSON(:geojson)) AS g) sel
    WHERE ST_Intersects(geometria, sel.g)
    GROUP BY severidad
    """
)

#: Same clip per zone — the per-subcuenca km breakdown (S10) in one query.
_CANALES_ZONAS_SQL = text(
    """
    WITH z AS (
        SELECT id AS zona_id,
               geometria AS g4326,
               ST_Transform(ST_MakeValid(geometria), 32720) AS g32720
        FROM zonas_operativas
        WHERE id = ANY(CAST(:ids AS uuid[]))
    )
    SELECT z.zona_id AS zona_id, c.estado AS estado,
           sum(ST_Length(ST_CollectionExtract(
               ST_Intersection(ST_Transform(c.geom, 32720), z.g32720), 2))) / 1000.0 AS km
    FROM canal_consorcio c, z
    WHERE ST_Intersects(c.geom, z.g4326)
    GROUP BY z.zona_id, c.estado
    """
)


def canales_dataset(db: Session, geojson_4326: str, area_ha: float) -> dict[str, Any] | None:
    """Section 7's dataset: km relevados/propuestos, cruces, conflictos.

    ``None`` → «sin datos» (S7) when the canal tables cannot be read. An
    EMPTY system (no canals near the selection) is REAL data: km 0,0 with
    the honest zero rows, never a None.
    """
    try:
        with db.begin_nested():
            km_filas = db.execute(_CANALES_KM_SQL, {"geojson": geojson_4326}).all()
    except SQLAlchemyError:
        logger.warning("informe_area.canales_no_disponible", exc_info=True)
        return None
    km_por_estado = {str(f.estado): round(float(f.km or 0.0), 2) for f in km_filas}
    km_relevados = km_por_estado.get("relevado", 0.0)
    km_propuestos = km_por_estado.get("propuesto", 0.0)
    km_total = km_relevados + km_propuestos

    cruces: dict[str, int] = {}
    conflictos: dict[str, int] = {}
    try:
        with db.begin_nested():
            for fila in db.execute(_CRUCES_SQL, {"geojson": geojson_4326}).all():
                cruces[str(fila.tipo)] = int(fila.n)
    except SQLAlchemyError:
        cruces = {}
    try:
        with db.begin_nested():
            for fila in db.execute(_CONFLICTOS_SQL, {"geojson": geojson_4326}).all():
                conflictos[str(fila.severidad)] = int(fila.n)
    except SQLAlchemyError:
        conflictos = {}

    return {
        "km_relevados": km_relevados,
        "km_propuestos": km_propuestos,
        "km_total": round(km_total, 2),
        "km_por_mil_ha": round(km_total / (area_ha / 1000.0), 2) if area_ha > 0 else None,
        "cruces_camino": cruces,
        "puntos_conflicto": conflictos,
        "sin_datos": km_total <= 0.0 and not cruces and not conflictos,
    }


def canales_por_zona(
    db: Session, zonas: list[tuple[uuid.UUID, str, float]]
) -> dict[str, dict[str, Any]]:
    """Per-zone km by estado + km per 1.000 ha (S10). Absent = no canal."""
    ids = [str(zona_id) for zona_id, _n, _ha in zonas]
    try:
        with db.begin_nested():
            filas = db.execute(_CANALES_ZONAS_SQL, {"ids": ids}).all()
    except SQLAlchemyError:
        logger.warning("informe_area.canales_zonas_no_disponible", exc_info=True)
        return {}
    ha_por_id = {str(zona_id): ha for zona_id, _n, ha in zonas}
    acumulado: dict[str, dict[str, float]] = {}
    for fila in filas:
        clave = str(fila.zona_id)
        zona = acumulado.setdefault(clave, {"km_relevados": 0.0, "km_propuestos": 0.0})
        if str(fila.estado) == "relevado":
            zona["km_relevados"] += float(fila.km or 0.0)
        elif str(fila.estado) == "propuesto":
            zona["km_propuestos"] += float(fila.km or 0.0)
    return {
        clave: {
            "km_relevados": round(valores["km_relevados"], 2),
            "km_propuestos": round(valores["km_propuestos"], 2),
            "km_total": round(valores["km_relevados"] + valores["km_propuestos"], 2),
            "km_por_mil_ha": (
                round(
                    (valores["km_relevados"] + valores["km_propuestos"])
                    / (ha_por_id[clave] / 1000.0),
                    2,
                )
                if ha_por_id.get(clave, 0.0) > 0
                else None
            ),
        }
        for clave, valores in acumulado.items()
    }


# ── Imágenes de eventos ancla (PR 4, S6) ─────────────────────────────────────

#: The three curated flood anchors the plan names (2015/2017/2025). Read
#: from the catalog lluvia_ext_002 seeded — never hardcoded a second time.
_EVENTOS_ANCLA_SQL = text(
    """
    SELECT event_key, start_date, curated_payload
    FROM rainfall_extreme_event
    WHERE provenance = 'curated'
    ORDER BY start_date
    """
)

#: Best imagery candidate per event: slot='ranked', rank 1 wins.
_CANDIDATO_ANCLA_SQL = text(
    """
    SELECT DISTINCT ON (event_key)
           event_key, sensor, scene_id, scene_date, cloud_pct
    FROM rainfall_event_imagery_candidate
    WHERE slot = 'ranked'
    ORDER BY event_key, rank
    """
)

#: False-color band triplets (NIR-SWIR1-Rojo — water absorbs SWIR1, so
#: flooded vegetation/soil reads dark against red vegetation): the S2
#: surface-reflectance scale the house VIS_PRESETS uses, and the Landsat
#: TOA reflectance ceiling the explorer pins for those collections.
_BANDAS_FALSO_COLOR: dict[str, tuple[list[str], float]] = {
    "sentinel1": (["VV", "VH", "VV"], 0.5),  # SAR falso color: agua = oscura en VV (especular)
    "sentinel2": (["B8", "B11", "B4"], 3000.0),
    "landsat9": (["B5", "B6", "B4"], 0.35),
    "landsat8": (["B5", "B6", "B4"], 0.35),
    "landsat7": (["B4", "B5", "B3"], 0.35),
    "landsat5": (["B4", "B5", "B3"], 0.35),
}

#: Thumbnail budget (S6 «miniatura»; GEE caps thumbnails at 1024 px —
#: 768 keeps every one of the three requests comfortably inside quota).
MINIATURA_PX = 768


def miniatura_falso_color_impl(
    *,
    scene_id: str,
    sensor: str,
    region_geojson: dict[str, Any],
    ee_module: Any,
    requests_module: Any,
    dimension_px: int = MINIATURA_PX,
) -> bytes:
    """PNG bytes of one scene in NIR-SWIR1-Rojo, clipped to the selection.

    Raises on anything (unknown sensor, GEE error, HTTP failure) — the
    caller degrades that event to «sin datos», never fails the report.
    """
    bandas, maximo = _BANDAS_FALSO_COLOR[sensor]
    region = ee_module.Geometry(geometry=region_geojson, geodesic=False)
    imagen = ee_module.Image(scene_id).select(bandas).clip(region)
    url = imagen.getThumbURL(
        {
            "bands": bandas,
            "min": 0,
            "max": maximo,
            "dimensions": dimension_px,
            "region": region,
            "format": "png",
        }
    )
    respuesta = requests_module.get(url, timeout=90)
    respuesta.raise_for_status()
    return respuesta.content


def _miniatura_por_defecto(scene_id: str, sensor: str, region_geojson: dict[str, Any]) -> bytes:
    """The production fetcher: lazy ee import + the geo-worker's requests."""
    import ee
    import requests

    return miniatura_falso_color_impl(
        scene_id=scene_id,
        sensor=sensor,
        region_geojson=region_geojson,
        ee_module=ee,
        requests_module=requests,
    )


def imagenes_eventos_ancla(
    db: Session,
    union_geojson: dict[str, Any],
    *,
    fetch_miniatura: Any = None,
) -> list[dict[str, Any]]:
    """One row per curated anchor event, PNG bytes attached when GEE answered.

    Every failure is per-event: an event without a candidate, an unknown
    sensor or a GEE error yields ``png=None`` (the section prints «sin
    datos» for it) and the report keeps going (S7). The union geometry is
    simplified for the clip — a thumbnail loses nothing at ~100 m and
    EE rejects overly complex regions.
    """
    fetch = fetch_miniatura or _miniatura_por_defecto
    try:
        with db.begin_nested():
            eventos = db.execute(_EVENTOS_ANCLA_SQL).all()
    except SQLAlchemyError:
        logger.warning("informe_area.eventos_ancla_no_disponibles", exc_info=True)
        return []
    if not eventos:
        return []
    try:
        with db.begin_nested():
            candidatos = {fila.event_key: fila for fila in db.execute(_CANDIDATO_ANCLA_SQL).all()}
    except SQLAlchemyError:
        logger.warning("informe_area.candidatos_ancla_no_disponibles", exc_info=True)
        candidatos = {}

    region = json.loads(json.dumps(union_geojson))  # defensive copy: ee must not see a mutated dict

    filas: list[dict[str, Any]] = []
    for evento in eventos:
        fila: dict[str, Any] = {
            "event_key": str(evento.event_key),
            "fecha": str(evento.start_date),
            "nombre": (evento.curated_payload or {}).get("name") or str(evento.event_key),
            "sensor": None,
            "escena": None,
            "nubes_pct": None,
            "png": None,
        }
        candidato = candidatos.get(str(evento.event_key))
        if candidato is None:
            filas.append(fila)
            continue
        fila.update(
            {
                "sensor": str(candidato.sensor),
                "escena": str(candidato.scene_id),
                "nubes_pct": candidato.cloud_pct,
            }
        )
        try:
            fila["png"] = fetch(str(candidato.scene_id), str(candidato.sensor), region)
        except Exception:  # noqa: BLE001 — GEE degradation is the contract (S7)
            logger.warning(
                "informe_area.miniatura_fallo",
                event_key=str(evento.event_key),
                scene=str(candidato.scene_id),
                exc_info=True,
            )
        filas.append(fila)
    return filas


# ── PR 6: paquete de campo + KMZ + token público (S3/S4/S5) ──────────────────

#: Basemap threshold (S4: "para áreas chicas… con imagen de fondo; para
#: áreas grandes, un PMTiles"). 30 000 ha ≈ 300 km² — a typical consorcio
#: subcuenca group sits under it. Above it the fixed 768 px Sentinel-2
#: thumbnail is >60 m/px (useless for parcel orientation) AND the plan's
#: answer for that size is PMTiles — which is NOT buildable in the backend
#: container (no tippecanoe binary, no pmtiles package; verified PR 6).
#: Documented degradation: the package still ships every vector class, the
#: basemap is dropped, and a nota says so — never a silent failure.
AREA_CAMPO_BASEMAP_MAX_HA = 30_000.0

#: S9 acceptance target for one subcuenca's package. Exceeding it is logged
#: and recorded in ``resultado['campo']``/package ``notas`` — the field map
#: still works with heavier vectors, so it is a budget, not a gate.
CAMPO_PAQUETE_MAX_BYTES = 15_000_000

#: Soils polygons for the campo themes: simplify tolerance in METRES,
#: converted to degrees at the clip's latitude inside the helper.
_TOLERANCIA_SUELOS_M = 15.0

_SUELOS_GEOMETRIAS_SQL = text(
    """
    WITH sel AS (SELECT ST_GeomFromGeoJSON(:geojson) AS g4326)
    SELECT s.clase,
           ST_AsGeoJSON(ST_Force2D(ST_CollectionExtract(
               ST_Intersection(ST_MakeValid(s.geometria), ST_MakeValid(sel.g4326)), 3)
           )) AS geo
    FROM idecor_suelos_50mil s, sel
    WHERE ST_Intersects(s.geometria, sel.g4326)
    """
)


def url_campo(token: str) -> str:
    """The URL the PDF-cover QR encodes (S5/S7).

    Public base comes from ``settings.frontend_url`` (the deploy's own front
    origin, default localhost for dev) — no new config surface, the same
    field the auth emails already trust for links back into the app.
    """
    base = (settings.frontend_url or "http://localhost:5173").rstrip("/")
    return f"{base}/campo/{token}"


def suelos_geometrias_clase(db: Session, geojson_4326: str) -> list[dict[str, Any]] | None:
    """Soils units clipped to the selection, dissolved per class (PR 6).

    ``None`` when the IDECOR table is absent/empty — the same degrade-not-
    fail contract as ``suelos_idecor_dataset``. Each class carries ONE
    (multi)polygon — ``unary_union`` of its units, simplified ~15 m — so the
    KMZ placemark and the package JSON stay payload-bounded.
    """
    try:
        with db.begin_nested():
            filas = db.execute(_SUELOS_GEOMETRIAS_SQL, {"geojson": geojson_4326}).all()
    except SQLAlchemyError:
        logger.warning("informe_area.suelos_geometrias_no_disponible", exc_info=True)
        return None

    from shapely.geometry import shape
    from shapely.ops import unary_union

    por_clase: dict[str, list[Any]] = {}
    for fila in filas:
        clase = (fila.clase or "").strip() or "sin clasificar"
        try:
            por_clase.setdefault(clase, []).append(shape(json.loads(fila.geo)))
        except (ValueError, TypeError):
            continue  # a malformed unit never fails the theme
    if not por_clase:
        return []

    # Metres → degrees is latitude-dependent, but simplify tolerance is a
    # rendering budget, not a measurement: the mid-latitude constant is
    # honest at these scales (all consorcio selections sit near -33°).
    tol_deg = _TOLERANCIA_SUELOS_M / 111_320.0

    clases: list[dict[str, Any]] = []
    for clase, geoms in sorted(por_clase.items()):
        disuelta = unary_union(geoms).simplify(tol_deg, preserve_topology=True)
        clases.append({"clase": clase, "geometrias": [disuelta.__geo_interface__]})
    return clases


def construir_paquete_campo(
    *,
    nombre: str,
    generado_el: str,
    vence_at: str,
    area_ha: float,
    seleccion_geojson: dict[str, Any],
    subcuencas: list[dict[str, Any]],
    temas: list[dict[str, Any]],
    basemap: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the offline field package (S4) — PURE, no db/GEE.

    ``temas`` items are ``{"clave", "titulo", "clases": [{clase, color,
    geometrias}]}`` — the same vectorized pieces the KMZ and the PDF maps
    consumed, so the phone's map cannot disagree with the report.
    ``basemap`` is ``{"png", "bounds", "fecha", "sensor"}`` or ``None``;
    the >30 000 ha degradation drops it here (and says why) so the
    threshold has exactly one home.
    """
    notas: list[str] = []
    basemap_out: dict[str, Any] | None = None
    if basemap and basemap.get("png"):
        if area_ha <= AREA_CAMPO_BASEMAP_MAX_HA:
            west, south, east, north = basemap["bounds"]
            basemap_out = {
                "imagen": (
                    "data:image/png;base64,"
                    + base64.b64encode(bytes(basemap["png"])).decode("ascii")
                ),
                "bounds": [west, south, east, north],
                "fecha": basemap.get("fecha"),
                "sensor": basemap.get("sensor"),
                "descripcion": (
                    "Imagen satelital del evento ancla más reciente con datos "
                    "(falso color NIR-SWIR1-rojo); fondo de orientación, no "
                    "cartografía oficial."
                ),
            }
        else:
            notas.append(
                "Área mayor a 30.000 ha: el paquete se entrega sin imagen de "
                "fondo (la resolución de la miniatura no aporta a esa escala). "
                "Los polígonos de clase y los límites están completos."
            )
    else:
        notas.append(
            "Sin imagen satelital de fondo para esta selección (el evento ancla "
            "más reciente no tuvo miniatura). Los polígonos de clase y los "
            "límites están completos."
        )

    return {
        "version": 1,
        "nombre": nombre,
        "generado_el": generado_el,
        "vence_at": vence_at,
        "area_ha": round(float(area_ha), 4),
        # límites: la selección + las subcuencas, GeoJSON 4326 crudo.
        "limites": {
            "seleccion": seleccion_geojson,
            "subcuencas": [
                {"nombre": str(z.get("nombre") or ""), "geometry": z.get("geojson")}
                for z in subcuencas
                if z.get("geojson")
            ],
        },
        # temas: {clave: {titulo, clases:[{clase, color, geometrias}]}} — la
        # leyenda vive inline (clase + color), un solo lugar que leer.
        "temas": {
            str(tema["clave"]): {
                "titulo": str(tema.get("titulo") or tema["clave"]),
                "clases": [
                    {
                        "clase": str(c["clase"]),
                        "color": str(c.get("color") or "#808080"),
                        "geometrias": list(c.get("geometrias") or []),
                    }
                    for c in tema.get("clases") or []
                ],
            }
            for tema in temas
        },
        "basemap": basemap_out,
        "notas": notas,
    }


def serializar_paquete_campo(paquete: dict[str, Any]) -> bytes:
    """Compact UTF-8 JSON — the bytes the row stores and the route serves."""
    return json.dumps(paquete, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def descargar_kmz(db: Session, informe_id: uuid.UUID, *, usuario: Any) -> tuple[bytes, str]:
    """Same privacy ladder as ``descargar_pdf``, for the KMZ (S3)."""
    row = obtener_informe(db, informe_id, usuario=usuario)
    estado = row.estado.value if hasattr(row.estado, "value") else str(row.estado)
    if estado == "pending" or estado == "running":
        raise errors.pdf_en_progreso()
    if estado == "failed":
        raise errors.informe_fallido(row.error)
    if not row.kmz_bytes:
        raise errors.kmz_no_disponible()
    ascii_name, utf8_name = _nombre_archivo_kmz(row.nombre)
    return bytes(
        row.kmz_bytes
    ), f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"


def _nombre_archivo_kmz(nombre: str) -> tuple[str, str]:
    """Content-Disposition filenames for the KMZ (see ``_nombre_archivo``)."""
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", plano).strip("-").lower() or "informe-area"
    ascii_name = f"informe-{slug[:60]}.kmz"
    utf8_name = quote(f"{nombre.strip() or 'informe-area'}.kmz")
    return ascii_name, utf8_name


def paquete_campo_por_token(db: Session, token: str) -> bytes:
    """The PUBLIC campo route's read (S5): token → package bytes.

    404 for anything unanswerable (unknown token, deleted row = revoked,
    still pending, degraded run without a package) — a public surface gets
    ONE status for all of those, or it becomes an oracle. 410 only for the
    row that is present but past ``vence_at``: the phone that scanned the QR
    deserves to know the map expired, not that it "doesn't exist".
    """
    if not token or len(token) > 64:
        raise errors.campo_token_invalido()
    row = repo.obtener_por_token(db, token)
    if row is None:
        raise errors.campo_token_invalido()
    if row.vence_at and row.vence_at < datetime.now(timezone.utc):
        raise errors.campo_vencido()
    estado = row.estado.value if hasattr(row.estado, "value") else str(row.estado)
    if estado != "completed" or not row.campo_paquete:
        raise errors.campo_token_invalido()
    return bytes(row.campo_paquete)
