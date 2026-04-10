
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.intelligence.router_support import (
    build_baseline_by_zona,
    build_dashboard_response,
    build_suggestion_summary_payload,
    get_latest_runoff_layers,
    list_suggestions_for_batch,
    load_zona_payloads,
    paginated_response,
    serialize_comparison_items,
    serialize_composite_stats,
    serialize_suggestion_page,
    task_response,
)
from app.domains.geo.intelligence.schemas import (
    AlertaResponse,
    BasinRiskRankingResponse,
    CanalSuggestionResponse,
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
    from app.domains.geo.intelligence import service as intel_service
    return intel_service
def _get_repo() -> IntelligenceRepository:
    return IntelligenceRepository()
def _require_operator():
    from app.auth import require_admin_or_operator
    return require_admin_or_operator
def _require_admin():
    from app.auth import require_admin
    return require_admin

# MATERIALIZED VIEW REFRESH
@router.post("/refresh-views", response_model=dict)
def refresh_views(
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_admin()),
):
    results = repo.refresh_materialized_views(db)
    return {"status": "refreshed", "views": results}

# DASHBOARD
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
    if not use_mv:
        return _get_intel_service().get_dashboard(db)

    stats = repo.get_dashboard_stats(db)
    repo.get_alertas_resumen(db)

    if not stats:
        # Mat view is empty (never refreshed) — fall back to live
        return _get_intel_service().get_dashboard(db)

    hci_all, _ = repo.get_hci_por_zona(db, page=1, limit=10000)
    return build_dashboard_response(stats, hci_all)

# HCI — Hydric Criticality Index
@router.post("/hci/calculate", response_model=CriticidadResponse)
def calculate_hci(
    payload: CriticidadRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
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
    if use_mv:
        items, total = repo.get_hci_por_zona(
            db, page=page, limit=limit, cuenca_filter=cuenca
        )
        return paginated_response(items, total=total, page=page, limit=limit)

    hci_items, total = repo.get_indices_hidricos(
        db, zona_id=zona_id, page=page, limit=limit
    )
    return paginated_response(
        [IndiceHidricoResponse.model_validate(i) for i in hci_items],
        total=total,
        page=page,
        limit=limit,
    )

# CONFLICT POINTS
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
    items, total = repo.get_conflictos(
        db, tipo_filter=tipo, severidad_filter=severidad, page=page, limit=limit
    )
    return paginated_response(
        [PuntoConflictoResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        limit=limit,
    )
@router.post("/conflictos/detectar", response_model=dict)
def detect_conflictos(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    from app.domains.geo.intelligence.tasks import task_detect_all_conflicts

    task = task_detect_all_conflicts.delay()
    return task_response(task)

# RUNOFF SIMULATION
@router.post("/escorrentia", response_model=EscorrentiaResponse)
def run_escorrentia(
    payload: EscorrentiaRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    flow_dir_layer, flow_acc_layer = get_latest_runoff_layers(db)

    result = _get_intel_service().run_runoff_simulation(
        db,
        punto=tuple(payload.punto_inicio),
        lluvia_mm=payload.lluvia_mm,
        flow_dir_path=flow_dir_layer.archivo_path,
        flow_acc_path=flow_acc_layer.archivo_path,
    )
    return result

# OPERATIONAL ZONES
@router.get("/zonas", response_model=dict)
def list_zonas(
    cuenca: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    items, total = repo.get_zonas(db, page=page, limit=limit, cuenca_filter=cuenca)
    return paginated_response(
        [ZonaOperativaResponse.model_validate(z) for z in items],
        total=total,
        page=page,
        limit=limit,
    )
@router.post("/zonas/generar", response_model=dict)
def generate_zonas(
    payload: ZonificacionRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    from app.domains.geo.intelligence.tasks import task_generate_zonification

    task = task_generate_zonification.delay(
        str(payload.dem_layer_id), payload.threshold
    )
    return task_response(task)
@router.post("/hci/batch", response_model=dict)
def batch_calculate_hci(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    from app.domains.geo.intelligence.tasks import task_calculate_hci_all_zones

    task = task_calculate_hci_all_zones.delay()
    return task_response(task)

# CANAL PRIORITY
@router.get("/canales/prioridad", response_model=dict)
def get_canal_priorities(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    # Placeholder: in production this would use cached results
    return {
        "items": [],
        "message": "Use POST /geo/intelligence/canales/prioridad/calcular to compute",
    }

# ROAD RISK
@router.get("/caminos/riesgo", response_model=dict)
def get_road_risks(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    return {
        "items": [],
        "message": "Use POST /geo/intelligence/caminos/riesgo/calcular to compute",
    }

# ALERTS
@router.get("/alertas", response_model=dict)
def list_alertas(
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
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
    result = _get_intel_service().check_alerts(db)
    return result
@router.post("/alertas/{alerta_id}/desactivar", response_model=AlertaResponse)
def deactivate_alerta(
    alerta_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    alerta = repo.deactivate_alerta(db, alerta_id)
    if alerta is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    db.commit()
    return alerta

# COMPOSITE ANALYSIS
@router.post("/composite/analyze", response_model=dict)
def trigger_composite_analysis(
    payload: CompositeAnalysisRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    from app.domains.geo.tasks import composite_analysis_task

    task = composite_analysis_task.delay(
        area_id=payload.area_id,
        weights_flood=payload.weights_flood,
        weights_drainage=payload.weights_drainage,
    )
    return task_response(task)
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
    stats = repo.get_composite_stats_by_area(db, area_id=area_id, tipo=tipo)

    if not stats:
        raise HTTPException(
            status_code=404,
            detail=f"Composite analysis not yet computed for area '{area_id}'",
        )

    items = serialize_composite_stats(stats)
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
    zona_dicts, zona_meta = load_zona_payloads(repo, db)
    baseline_by_zona = build_baseline_by_zona(
        area_id,
        tipo,
        area_dir=area_dir,
        current_stats=current_stats,
        zona_dicts=zona_dicts,
    )
    if tipo == "drainage_need" and not baseline_by_zona:
        return CompositeComparisonResponse(
            area_id=area_id, tipo=tipo, items=[], total=0
        )
    items = serialize_comparison_items(current_stats, baseline_by_zona, zona_meta, tipo)
    return CompositeComparisonResponse(
        area_id=area_id, tipo=tipo, items=items, total=len(items)
    )

# CANAL SUGGESTIONS

suggestions_router = APIRouter(prefix="/suggestions", tags=["Canal Suggestions"])

@suggestions_router.post("/analyze", status_code=202, response_model=dict)
def trigger_canal_analysis(
    _user=Depends(_require_operator()),
):
    from app.domains.geo.intelligence.tasks import run_canal_analysis

    task = run_canal_analysis.delay()
    return task_response(task)

@suggestions_router.get("/results", response_model=dict)
def get_suggestion_results(
    tipo: Optional[str] = Query(
        default=None,
        description="Filter by tipo: hotspot, gap, route, maintenance, bottleneck",
    ),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    latest_batch = repo.get_latest_batch(db)
    if latest_batch is None:
        return serialize_suggestion_page(
            items=[], total=0, page=page, limit=limit, batch_id=None
        )

    items, total = list_suggestions_for_batch(
        db=db,
        repo=repo,
        batch_id=latest_batch,
        tipo=tipo,
        page=page,
        limit=limit,
    )
    return serialize_suggestion_page(
        items=items,
        total=total,
        page=page,
        limit=limit,
        batch_id=latest_batch,
    )

@suggestions_router.get("/results/{batch_id}", response_model=dict)
def get_suggestion_results_by_batch(
    batch_id: uuid.UUID,
    tipo: Optional[str] = Query(
        default=None,
        description="Filter by tipo: hotspot, gap, route, maintenance, bottleneck",
    ),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    items, total = list_suggestions_for_batch(
        db=db,
        repo=repo,
        batch_id=batch_id,
        tipo=tipo,
        page=page,
        limit=limit,
    )

    if total == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No results found for batch {batch_id}",
        )

    return serialize_suggestion_page(
        items=items,
        total=total,
        page=page,
        limit=limit,
        batch_id=batch_id,
    )

@suggestions_router.get("/summary", response_model=dict)
def get_suggestion_summary(
    batch_id: Optional[uuid.UUID] = Query(
        default=None,
        description="Specific batch to summarize. Defaults to latest.",
    ),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    summary = repo.get_summary(db, batch_id=batch_id)
    if summary is None:
        return {
            "batch_id": None,
            "total_suggestions": 0,
            "by_tipo": {},
            "top_per_tipo": {},
        }

    return build_suggestion_summary_payload(summary, repo, db)

router.include_router(suggestions_router)
