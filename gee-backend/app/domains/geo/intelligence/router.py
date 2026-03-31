"""FastAPI router for the operational intelligence sub-module.

All endpoints are under /geo/intelligence and require operator role.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.intelligence.schemas import (
    AlertaResponse,
    BasinRiskRankingResponse,
    CompositeComparisonItemResponse,
    CompositeComparisonResponse,
    CompositeAnalysisRequest,
    CompositeZonalStatsResponse,
    CriticidadRequest,
    CriticidadResponse,
    DashboardInteligente,
    EscorrentiaRequest,
    EscorrentiaResponse,
    IndiceHidricoResponse,
    PuntoConflictoResponse,
    ZonaOperativaResponse,
    ZonificacionRequest,
)
logger = get_logger(__name__)

router = APIRouter(tags=["Intelligence"])


def _get_intel_service():
    """Lazy import to avoid loading geopandas at startup."""
    from app.domains.geo.intelligence import service as intel_service
    return intel_service


def _get_repo() -> IntelligenceRepository:
    return IntelligenceRepository()


def _require_operator():
    """Return the operator dependency at call time (lazy import)."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _require_admin():
    """Return the admin dependency at call time (lazy import)."""
    from app.auth import require_admin

    return require_admin


# ──────────────────────────────────────────────
# MATERIALIZED VIEW REFRESH
# ──────────────────────────────────────────────


@router.post("/refresh-views", response_model=dict)
def refresh_views(
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_admin()),
):
    """Refresh all geo materialized views. Admin only."""
    results = repo.refresh_materialized_views(db)
    return {"status": "refreshed", "views": results}


# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────


@router.get("/dashboard", response_model=DashboardInteligente)
def get_dashboard(
    use_mv: bool = Query(
        default=True,
        description="Use materialized view for faster response",
    ),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Get the aggregated operational intelligence dashboard.

    When use_mv=True (default), reads from mv_dashboard_geo_stats and
    mv_alertas_resumen for fast, pre-computed results. Set use_mv=False
    to compute live from source tables.
    """
    if not use_mv:
        return _get_intel_service().get_dashboard(db)

    stats = repo.get_dashboard_stats(db)
    alertas = repo.get_alertas_resumen(db)

    if not stats:
        # Mat view is empty (never refreshed) — fall back to live
        return _get_intel_service().get_dashboard(db)

    # Build zonas_por_nivel from mv_hci_por_zona counts
    hci_all, _ = repo.get_hci_por_zona(db, page=1, limit=10000)
    zonas_por_nivel: dict[str, int] = {"bajo": 0, "medio": 0, "alto": 0, "critico": 0}
    for row in hci_all:
        nivel = row.get("nivel_riesgo", "")
        if nivel in zonas_por_nivel:
            zonas_por_nivel[nivel] += 1

    total_zonas = stats.get("total_zonas_operativas", 0)
    at_risk = (
        zonas_por_nivel.get("medio", 0)
        + zonas_por_nivel.get("alto", 0)
        + zonas_por_nivel.get("critico", 0)
    )
    pct_risk = (at_risk / total_zonas * 100.0) if total_zonas > 0 else 0.0

    return {
        "porcentaje_area_riesgo": round(pct_risk, 2),
        "canales_criticos": 0,
        "caminos_vulnerables": 0,
        "conflictos_activos": stats.get("total_conflictos", 0),
        "alertas_activas": stats.get("total_alertas_activas", 0),
        "zonas_por_nivel": zonas_por_nivel,
        "evolucion_temporal": [],
    }


# ──────────────────────────────────────────────
# HCI — Hydric Criticality Index
# ──────────────────────────────────────────────


@router.post("/hci/calculate", response_model=CriticidadResponse)
def calculate_hci(
    payload: CriticidadRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Calculate the Hydric Criticality Index for a zone."""
    try:
        result = _get_intel_service().calculate_hci_for_zone(
            db,
            payload.zona_id,
            pendiente_media=payload.pendiente_media,
            acumulacion_media=payload.acumulacion_media,
            twi_medio=payload.twi_medio,
            proximidad_canal_m=payload.proximidad_canal_m,
            historial_inundacion=payload.historial_inundacion,
            pesos=payload.pesos,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/hci", response_model=dict)
def list_hci(
    zona_id: Optional[uuid.UUID] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    use_mv: bool = Query(
        default=False,
        description="Use mv_hci_por_zona (latest per zone, no zone_id filter)",
    ),
    cuenca: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """List HCI results with optional zone filter.

    When use_mv=True, reads from mv_hci_por_zona which returns only the
    latest HCI per zone (ignores zona_id filter, supports cuenca filter).
    """
    if use_mv:
        items, total = repo.get_hci_por_zona(
            db, page=page, limit=limit, cuenca_filter=cuenca
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        }

    items, total = repo.get_indices_hidricos(
        db, zona_id=zona_id, page=page, limit=limit
    )
    return {
        "items": [IndiceHidricoResponse.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


# ──────────────────────────────────────────────
# CONFLICT POINTS
# ──────────────────────────────────────────────


@router.get("/conflictos", response_model=dict)
def list_conflictos(
    tipo: Optional[str] = Query(default=None),
    severidad: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """List detected conflict points."""
    items, total = repo.get_conflictos(
        db, tipo_filter=tipo, severidad_filter=severidad, page=page, limit=limit
    )
    return {
        "items": [PuntoConflictoResponse.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/conflictos/detectar", response_model=dict)
def detect_conflictos(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Dispatch conflict detection as a background Celery task.

    Loads canal/road/drainage data from GEE assets and GeoLayers,
    then detects intersection points filtered by flow accumulation and slope.
    """
    from app.domains.geo.intelligence.tasks import task_detect_all_conflicts

    task = task_detect_all_conflicts.delay()
    return {"task_id": task.id, "status": "submitted"}


# ──────────────────────────────────────────────
# RUNOFF SIMULATION
# ──────────────────────────────────────────────


@router.post("/escorrentia", response_model=EscorrentiaResponse)
def run_escorrentia(
    payload: EscorrentiaRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Run runoff simulation from a starting point.

    Requires pre-computed flow direction and flow accumulation rasters.
    """
    # Find the latest flow_dir and flow_acc layers
    from app.domains.geo.repository import GeoRepository
    from app.domains.geo.models import TipoGeoLayer

    geo_repo = GeoRepository()
    flow_dir_layers, _ = geo_repo.get_layers(
        db, tipo_filter=TipoGeoLayer.FLOW_DIR, page=1, limit=1
    )
    flow_acc_layers, _ = geo_repo.get_layers(
        db, tipo_filter=TipoGeoLayer.FLOW_ACC, page=1, limit=1
    )

    if not flow_dir_layers or not flow_acc_layers:
        raise HTTPException(
            status_code=400,
            detail="Se requieren capas de flow_dir y flow_acc procesadas previamente",
        )

    result = _get_intel_service().run_runoff_simulation(
        db,
        punto=tuple(payload.punto_inicio),
        lluvia_mm=payload.lluvia_mm,
        flow_dir_path=flow_dir_layers[0].archivo_path,
        flow_acc_path=flow_acc_layers[0].archivo_path,
    )
    return result


# ──────────────────────────────────────────────
# OPERATIONAL ZONES
# ──────────────────────────────────────────────


@router.get("/zonas", response_model=dict)
def list_zonas(
    cuenca: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """List operational zones."""
    items, total = repo.get_zonas(db, page=page, limit=limit, cuenca_filter=cuenca)
    return {
        "items": [ZonaOperativaResponse.model_validate(z) for z in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/zonas/generar", response_model=dict)
def generate_zonas(
    payload: ZonificacionRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Dispatch zone generation from DEM as a background Celery task."""
    from app.domains.geo.intelligence.tasks import task_generate_zonification

    task = task_generate_zonification.delay(str(payload.dem_layer_id), payload.threshold)
    return {"task_id": task.id, "status": "submitted"}


@router.post("/hci/batch", response_model=dict)
def batch_calculate_hci(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Dispatch batch HCI calculation for all zones as a background Celery task.

    Extracts per-zone raster statistics from slope, flow_acc, and TWI layers
    and calculates HCI for every operational zone.
    """
    from app.domains.geo.intelligence.tasks import task_calculate_hci_all_zones

    task = task_calculate_hci_all_zones.delay()
    return {"task_id": task.id, "status": "submitted"}


# ──────────────────────────────────────────────
# CANAL PRIORITY
# ──────────────────────────────────────────────


@router.get("/canales/prioridad", response_model=dict)
def get_canal_priorities(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Get canal priority ranking.

    Returns a pre-computed ranking or triggers computation.
    """
    # Placeholder: in production this would use cached results
    return {
        "items": [],
        "message": "Use POST /geo/intelligence/canales/prioridad/calcular to compute",
    }


# ──────────────────────────────────────────────
# ROAD RISK
# ──────────────────────────────────────────────


@router.get("/caminos/riesgo", response_model=dict)
def get_road_risks(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Get road risk ranking.

    Returns a pre-computed ranking or triggers computation.
    """
    return {
        "items": [],
        "message": "Use POST /geo/intelligence/caminos/riesgo/calcular to compute",
    }


# ──────────────────────────────────────────────
# ALERTS
# ──────────────────────────────────────────────


@router.get("/alertas", response_model=dict)
def list_alertas(
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """List active geo-alerts."""
    alertas = repo.get_alertas_activas(db)
    return {
        "items": [AlertaResponse.model_validate(a) for a in alertas],
        "total": len(alertas),
    }


@router.post("/alertas/evaluar", response_model=dict)
def evaluate_alertas(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Evaluate alert conditions and create new alerts if thresholds are exceeded."""
    result = _get_intel_service().check_alerts(db)
    return result


@router.post("/alertas/{alerta_id}/desactivar", response_model=AlertaResponse)
def deactivate_alerta(
    alerta_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Deactivate (dismiss) an active alert."""
    alerta = repo.deactivate_alerta(db, alerta_id)
    if alerta is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    db.commit()
    return alerta


# ──────────────────────────────────────────────
# COMPOSITE ANALYSIS
# ──────────────────────────────────────────────


@router.post("/composite/analyze", response_model=dict)
def trigger_composite_analysis(
    payload: CompositeAnalysisRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Dispatch composite analysis (flood risk + drainage need) as a Celery task.

    Requires a completed DEM pipeline for the given area_id.
    Returns the job_id to poll for progress.
    """
    from app.domains.geo.tasks import composite_analysis_task

    task = composite_analysis_task.delay(
        area_id=payload.area_id,
        weights_flood=payload.weights_flood,
        weights_drainage=payload.weights_drainage,
    )
    return {"task_id": task.id, "status": "submitted"}


@router.get("/composite/stats/{area_id}", response_model=BasinRiskRankingResponse)
def get_composite_stats(
    area_id: str,
    tipo: Optional[str] = Query(
        default=None,
        description="Filter by composite type: flood_risk or drainage_need",
    ),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Get composite zonal stats for an area, ranked by mean risk score DESC.

    Returns per-basin statistics from the latest composite analysis.
    Optionally filter by tipo (flood_risk or drainage_need).
    """
    stats = repo.get_composite_stats_by_area(db, area_id=area_id, tipo=tipo)

    if not stats:
        raise HTTPException(
            status_code=404,
            detail=f"Composite analysis not yet computed for area '{area_id}'",
        )

    items = []
    for s in stats:
        item = CompositeZonalStatsResponse.model_validate(s)
        # Enrich with zona nombre from relationship
        if s.zona:
            item.zona_nombre = s.zona.nombre
            item.cuenca = s.zona.cuenca
            item.superficie_ha = s.zona.superficie_ha
        items.append(item)

    return BasinRiskRankingResponse(items=items, total=len(items))


@router.get("/composite/compare/{area_id}", response_model=CompositeComparisonResponse)
def compare_composite_stats(
    area_id: str,
    tipo: str = Query(
        default="drainage_need",
        description="Comparison type. Currently meaningful for drainage_need.",
    ),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Compare current composite stats against a baseline without real channels.

    For `drainage_need`, the baseline is recomputed from the DEM-derived
    `drainage.geojson` only, excluding `drainage_combined.geojson`.
    Flood risk does not depend on the merged real waterways, so its baseline
    is identical to the current result and the delta will be 0.
    """
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping as shapely_mapping

    from app.domains.geo.repository import GeoRepository

    geo_repo = GeoRepository()
    current_stats = repo.get_composite_stats_by_area(db, area_id=area_id, tipo=tipo)
    if not current_stats:
        raise HTTPException(
            status_code=404,
            detail=f"Composite analysis not yet computed for area '{area_id}'",
        )

    hand_layers, _ = geo_repo.get_layers(
        db, area_id_filter=area_id, tipo_filter="hand", limit=1
    )
    if not hand_layers:
        raise HTTPException(
            status_code=404,
            detail=f"No HAND layer found for area '{area_id}'. Run the DEM pipeline first.",
        )
    area_dir = Path(hand_layers[0].archivo_path).parent

    zonas, _ = repo.get_zonas(db, page=1, limit=10000)
    zona_dicts: list[dict] = []
    zona_meta: dict = {}
    for z in zonas:
        try:
            geom_shapely = to_shape(z.geometria)
            zona_dicts.append({
                "id": z.id,
                "nombre": z.nombre,
                "geometry": shapely_mapping(geom_shapely),
            })
            zona_meta[z.id] = {
                "nombre": z.nombre,
                "cuenca": z.cuenca,
                "superficie_ha": z.superficie_ha,
            }
        except Exception:
            logger.warning(
                "composite_compare.zona_geom_error",
                zona_id=str(z.id),
                exc_info=True,
            )

    baseline_by_zona: dict = {}
    if tipo == "drainage_need":
        try:
            from app.domains.geo import composites

            auto_drainage_path = area_dir / "drainage.geojson"
            if not auto_drainage_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"No auto drainage network found for area '{area_id}'",
                )
            with TemporaryDirectory(prefix="composite-compare-") as tmpdir:
                tmp = Path(tmpdir)
                for filename in ["flow_acc.tif", "hand.tif", "tpi.tif", "drainage.geojson"]:
                    (tmp / filename).symlink_to(area_dir / filename)

                baseline_raster = str(tmp / "drainage_need_baseline.tif")
                composites.compute_drainage_need(str(tmp), baseline_raster)
                baseline_stats = composites.extract_composite_zonal_stats(
                    baseline_raster,
                    zona_dicts,
                    tipo,
                )
                baseline_by_zona = {item["zona_id"]: item for item in baseline_stats}
        except ModuleNotFoundError:
            logger.warning(
                "composite_compare.unavailable_missing_raster_stack",
                area_id=area_id,
                tipo=tipo,
            )
            return CompositeComparisonResponse(area_id=area_id, tipo=tipo, items=[], total=0)
    else:
        for item in current_stats:
            baseline_by_zona[item.zona_id] = {
                "zona_id": item.zona_id,
                "mean_score": item.mean_score,
                "area_high_risk_ha": item.area_high_risk_ha,
            }

    items: list[CompositeComparisonItemResponse] = []
    for stat in current_stats:
        baseline = baseline_by_zona.get(stat.zona_id)
        if not baseline:
            continue
        meta = zona_meta.get(stat.zona_id, {})
        items.append(
            CompositeComparisonItemResponse(
                zona_id=stat.zona_id,
                zona_nombre=meta.get("nombre"),
                cuenca=meta.get("cuenca"),
                superficie_ha=meta.get("superficie_ha"),
                tipo=tipo,
                current_mean_score=stat.mean_score,
                baseline_mean_score=float(baseline["mean_score"]),
                delta_mean_score=stat.mean_score - float(baseline["mean_score"]),
                current_area_high_risk_ha=stat.area_high_risk_ha,
                baseline_area_high_risk_ha=float(baseline["area_high_risk_ha"]),
                delta_area_high_risk_ha=stat.area_high_risk_ha - float(baseline["area_high_risk_ha"]),
            )
        )

    items.sort(key=lambda item: abs(item.delta_mean_score), reverse=True)
    return CompositeComparisonResponse(area_id=area_id, tipo=tipo, items=items, total=len(items))
