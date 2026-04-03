"""Orchestration service for canal network analysis suggestions.

Runs 5 analyses in sequence (hotspots, gaps, routes, bottlenecks,
maintenance priority), persists all results as CanalSuggestion records
grouped by a shared batch_id, and returns a summary.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping as shapely_mapping
from sqlalchemy.orm import Session

from app.domains.geo.intelligence.calculations import (
    compute_maintenance_priority,
    detect_coverage_gaps,
    rank_canal_hotspots,
    suggest_canal_routes,
)
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.models import TipoGeoLayer
from app.domains.geo.repository import GeoRepository

logger = structlog.get_logger(__name__)


def run_full_analysis(db: Session) -> dict[str, Any]:
    """Orchestrate all 5 canal network analyses and persist results.

    Execution order:
      1. Hotspots (raster sampling along canal segments)
      2. Gaps (HCI + distance to canals)
      3. Routes (least-cost paths from gap centroids)
      4. Bottlenecks (betweenness centrality on canal graph)
      5. Maintenance priority (composite of all factors)

    Args:
        db: Database session.

    Returns:
        Dict with batch_id and counts per suggestion tipo.
    """
    intel_repo = IntelligenceRepository()
    geo_repo = GeoRepository()

    batch_id = uuid.uuid4()
    all_suggestions: list[dict[str, Any]] = []

    # ── Load shared data ─────────────────────────────────────────────
    # Canal network geometries from DB (canal_network table via routing)
    canal_geometries = _load_canal_geometries(db)

    # Raster paths from GeoLayer
    flow_acc_path = _get_layer_path(db, geo_repo, TipoGeoLayer.FLOW_ACC)
    slope_path = _get_layer_path(db, geo_repo, TipoGeoLayer.SLOPE)

    # Zone geometries + HCI scores
    zones = _load_zones(db, intel_repo)
    hci_scores = _load_hci_scores(db, intel_repo)

    # Conflict counts per node (for maintenance priority)
    conflict_counts = _load_conflict_counts(db, intel_repo)

    # ── Phase 1: Hotspots ────────────────────────────────────────────
    hotspot_results: list[dict] = []
    if canal_geometries and flow_acc_path:
        try:
            hotspot_results = rank_canal_hotspots(
                canal_geometries, flow_acc_path, num_points=20
            )
            for h in hotspot_results:
                all_suggestions.append(
                    _to_suggestion(batch_id, "hotspot", h["score"], h)
                )
            logger.info("suggestions.hotspots", count=len(hotspot_results))
        except Exception:
            logger.error("suggestions.hotspots_failed", exc_info=True)
    else:
        logger.warning(
            "suggestions.hotspots_skipped",
            reason="Missing canal geometries or flow_acc raster",
        )

    # ── Phase 2: Gaps ────────────────────────────────────────────────
    gap_results: list[dict] = []
    if zones and canal_geometries:
        try:
            gap_results = detect_coverage_gaps(
                zones, hci_scores, canal_geometries, threshold_km=2.0
            )
            for g in gap_results:
                score = _gap_severity_to_score(g.get("severity", "moderado"))
                all_suggestions.append(
                    _to_suggestion(batch_id, "gap", score, g)
                )
            logger.info("suggestions.gaps", count=len(gap_results))
        except Exception:
            logger.error("suggestions.gaps_failed", exc_info=True)
    else:
        logger.warning(
            "suggestions.gaps_skipped",
            reason="Missing zones or canal geometries",
        )

    # ── Phase 3: Routes ──────────────────────────────────────────────
    route_results: list[dict] = []
    if gap_results and canal_geometries and slope_path:
        try:
            route_results = suggest_canal_routes(
                gap_results, canal_geometries, slope_path
            )
            for r in route_results:
                if r.get("status") != "ok":
                    continue
                cost = r.get("estimated_cost") or 0.0
                # Invert cost into a 0-100 score (lower cost = higher score)
                score = max(100.0 - min(cost / 100.0, 100.0), 0.0)
                all_suggestions.append(
                    _to_suggestion(batch_id, "route", round(score, 2), r)
                )
            logger.info(
                "suggestions.routes",
                count=len([r for r in route_results if r.get("status") == "ok"]),
            )
        except Exception:
            logger.error("suggestions.routes_failed", exc_info=True)
    else:
        logger.warning(
            "suggestions.routes_skipped",
            reason="No gaps, canals, or slope raster",
        )

    # ── Phase 4: Bottlenecks ─────────────────────────────────────────
    centrality_scores: dict[int, float] = {}
    try:
        from app.domains.geo.routing import betweenness_centrality

        bottleneck_results = betweenness_centrality(db, limit=100)
        for b in bottleneck_results:
            node_id = b["node_id"]
            centrality = b["centrality"]
            centrality_scores[node_id] = centrality
            all_suggestions.append(
                _to_suggestion(
                    batch_id,
                    "bottleneck",
                    round(centrality * 100, 2),
                    b,
                )
            )
        logger.info("suggestions.bottlenecks", count=len(bottleneck_results))
    except Exception:
        logger.error("suggestions.bottlenecks_failed", exc_info=True)

    # ── Phase 5: Maintenance priority ────────────────────────────────
    # Build flow_acc_scores from hotspot results (keyed by segment_index)
    flow_acc_scores: dict[int, float] = {}
    for h in hotspot_results:
        seg_idx = h.get("segment_index")
        if seg_idx is not None:
            flow_acc_scores[seg_idx] = h.get("flow_acc_mean", 0.0)

    if centrality_scores or flow_acc_scores or hci_scores or conflict_counts:
        try:
            maint_results = compute_maintenance_priority(
                centrality_scores=centrality_scores,
                flow_acc_scores=flow_acc_scores,
                hci_scores=hci_scores,
                conflict_counts=conflict_counts,
            )
            for m in maint_results:
                all_suggestions.append(
                    _to_suggestion(
                        batch_id,
                        "maintenance",
                        round(m["composite_score"] * 100, 2),
                        m,
                    )
                )
            logger.info("suggestions.maintenance", count=len(maint_results))
        except Exception:
            logger.error("suggestions.maintenance_failed", exc_info=True)

    # ── Persist ──────────────────────────────────────────────────────
    if all_suggestions:
        inserted = intel_repo.insert_suggestions_batch(db, all_suggestions)
        db.commit()
        logger.info("suggestions.persisted", batch_id=str(batch_id), count=inserted)
    else:
        logger.warning("suggestions.empty_batch", batch_id=str(batch_id))

    # ── Summary ──────────────────────────────────────────────────────
    counts: dict[str, int] = {}
    for s in all_suggestions:
        tipo = s["tipo"]
        counts[tipo] = counts.get(tipo, 0) + 1

    return {
        "batch_id": batch_id,
        "total_suggestions": len(all_suggestions),
        "by_tipo": counts,
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _to_suggestion(
    batch_id: uuid.UUID,
    tipo: str,
    score: float,
    data: dict,
) -> dict[str, Any]:
    """Map an analysis result to a CanalSuggestion insert dict."""
    geom = data.get("geometry")
    geom_wkb = None
    if geom is not None:
        try:
            from geoalchemy2.shape import from_shape
            from shapely.geometry import shape as shapely_shape

            if isinstance(geom, dict):
                geom_wkb = from_shape(shapely_shape(geom), srid=4326)
            else:
                geom_wkb = from_shape(geom, srid=4326)
        except Exception:
            geom_wkb = None

    # Strip geometry from metadata to avoid duplication
    metadata = {k: v for k, v in data.items() if k != "geometry"}

    return {
        "tipo": tipo,
        "geometry": geom_wkb,
        "score": score,
        "metadata_": metadata,
        "batch_id": batch_id,
    }


def _get_layer_path(
    db: Session, geo_repo: GeoRepository, tipo: TipoGeoLayer
) -> str | None:
    """Get the file path for the latest GeoLayer of a given type."""
    layers, _ = geo_repo.get_layers(db, tipo_filter=tipo, page=1, limit=1)
    if layers and layers[0].archivo_path:
        return layers[0].archivo_path
    return None


def _load_canal_geometries(db: Session) -> list[dict]:
    """Load canal network geometries from the canal_network table."""
    from sqlalchemy import text

    try:
        rows = db.execute(
            text("""
                SELECT id, ST_AsGeoJSON(the_geom)::json AS geometry
                FROM canal_network
                WHERE the_geom IS NOT NULL
                LIMIT 5000;
            """)
        ).fetchall()

        return [
            {"id": r.id, "geometry": r.geometry}
            for r in rows
            if r.geometry is not None
        ]
    except Exception:
        logger.warning("suggestions.canal_geom_load_failed", exc_info=True)
        return []


def _load_zones(db: Session, intel_repo: IntelligenceRepository) -> list[dict]:
    """Load operational zone geometries for gap detection."""
    try:
        zonas, _ = intel_repo.get_zonas(db, page=1, limit=10000)
        result = []
        for z in zonas:
            try:
                geom = to_shape(z.geometria)
                result.append({
                    "id": str(z.id),
                    "geometry": shapely_mapping(geom),
                    "nombre": z.nombre,
                    "cuenca": z.cuenca,
                })
            except Exception:
                continue
        return result
    except Exception:
        logger.warning("suggestions.zones_load_failed", exc_info=True)
        return []


def _load_hci_scores(
    db: Session, intel_repo: IntelligenceRepository
) -> dict[str, float]:
    """Load latest HCI scores keyed by zone_id string."""
    from sqlalchemy import func, select

    from app.domains.geo.intelligence.models import IndiceHidrico

    try:
        # Subquery: latest HCI per zone
        latest = (
            select(
                IndiceHidrico.zona_id,
                func.max(IndiceHidrico.fecha_calculo).label("max_fecha"),
            )
            .group_by(IndiceHidrico.zona_id)
            .subquery()
        )
        stmt = (
            select(IndiceHidrico.zona_id, IndiceHidrico.indice_final)
            .join(
                latest,
                (IndiceHidrico.zona_id == latest.c.zona_id)
                & (IndiceHidrico.fecha_calculo == latest.c.max_fecha),
            )
        )
        rows = db.execute(stmt).all()
        return {str(r.zona_id): float(r.indice_final) for r in rows}
    except Exception:
        logger.warning("suggestions.hci_load_failed", exc_info=True)
        return {}


def _load_conflict_counts(
    db: Session, intel_repo: IntelligenceRepository
) -> dict[int, int]:
    """Load conflict counts (total per type) as a simple dict.

    Since conflicts don't map 1:1 to canal nodes, we return a
    global count that the maintenance priority function can use.
    """
    from sqlalchemy import func, select

    from app.domains.geo.intelligence.models import PuntoConflicto

    try:
        total = db.execute(
            select(func.count()).select_from(PuntoConflicto)
        ).scalar_one()
        # Return as a single-entry dict; maintenance priority
        # redistributes weights when data is sparse
        if total > 0:
            return {0: total}
        return {}
    except Exception:
        logger.warning("suggestions.conflicts_load_failed", exc_info=True)
        return {}


def _gap_severity_to_score(severity: str) -> float:
    """Convert gap severity level to a 0-100 score."""
    return {
        "critico": 95.0,
        "alto": 75.0,
        "moderado": 50.0,
    }.get(severity, 50.0)
