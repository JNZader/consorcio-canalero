from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.intelligence.schemas import (
    CanalSuggestionResponse,
    CompositeComparisonItemResponse,
    CompositeZonalStatsResponse,
)

SUGGESTION_TYPES = ("hotspot", "gap", "route", "maintenance", "bottleneck")


def task_response(task) -> dict[str, str]:
    return {"task_id": task.id, "status": "submitted"}


def paginated_response(
    items,
    *,
    total: int,
    page: int,
    limit: int,
    **extra,
) -> dict:
    response = {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
    }
    response.update(extra)
    return response


def build_dashboard_response(stats: dict, hci_all: list[dict]) -> dict:
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


def get_latest_runoff_layers(db: Session):
    from app.domains.geo.models import TipoGeoLayer
    from app.domains.geo.repository import GeoRepository

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
    return flow_dir_layers[0], flow_acc_layers[0]


def serialize_composite_stats(stats) -> list[CompositeZonalStatsResponse]:
    items: list[CompositeZonalStatsResponse] = []
    for stat in stats:
        item = CompositeZonalStatsResponse.model_validate(stat)
        if stat.zona:
            item.zona_nombre = stat.zona.nombre
            item.cuenca = stat.zona.cuenca
            item.superficie_ha = stat.zona.superficie_ha
        items.append(item)
    return items


def load_zona_payloads(repo: IntelligenceRepository, db: Session, logger):
    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping as shapely_mapping

    zonas, _ = repo.get_zonas(db, page=1, limit=10000)
    zona_dicts: list[dict] = []
    zona_meta: dict = {}
    for zona in zonas:
        try:
            geom_shapely = to_shape(zona.geometria)
            zona_dicts.append(
                {
                    "id": zona.id,
                    "nombre": zona.nombre,
                    "geometry": shapely_mapping(geom_shapely),
                }
            )
            zona_meta[zona.id] = {
                "nombre": zona.nombre,
                "cuenca": zona.cuenca,
                "superficie_ha": zona.superficie_ha,
            }
        except Exception:
            logger.warning(
                "composite_compare.zona_geom_error",
                zona_id=str(zona.id),
                exc_info=True,
            )
    return zona_dicts, zona_meta


def build_baseline_by_zona(
    area_id: str,
    tipo: str,
    area_dir: Path,
    current_stats,
    zona_dicts,
    logger,
):
    from tempfile import TemporaryDirectory

    baseline_by_zona: dict = {}
    if tipo != "drainage_need":
        for item in current_stats:
            baseline_by_zona[item.zona_id] = {
                "zona_id": item.zona_id,
                "mean_score": item.mean_score,
                "area_high_risk_ha": item.area_high_risk_ha,
            }
        return baseline_by_zona

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
            return {item["zona_id"]: item for item in baseline_stats}
    except ModuleNotFoundError:
        logger.warning(
            "composite_compare.unavailable_missing_raster_stack",
            area_id=area_id,
            tipo=tipo,
        )
        return {}


def serialize_comparison_items(current_stats, baseline_by_zona: dict, zona_meta: dict, tipo: str):
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
                delta_area_high_risk_ha=stat.area_high_risk_ha
                - float(baseline["area_high_risk_ha"]),
            )
        )
    items.sort(key=lambda item: abs(item.delta_mean_score), reverse=True)
    return items


def list_suggestions_for_batch(
    *,
    db: Session,
    repo: IntelligenceRepository,
    batch_id,
    tipo,
    page: int,
    limit: int,
):
    if tipo:
        return repo.get_suggestions_by_tipo(
            db, tipo, page=page, limit=limit, batch_id=batch_id
        )

    items, total = repo.get_suggestions_by_tipo(
        db, tipo="", page=page, limit=limit, batch_id=batch_id
    )
    if total > 0:
        return items, total

    from sqlalchemy import func as sa_func
    from sqlalchemy import select

    from app.domains.geo.intelligence.models import CanalSuggestion

    base = select(CanalSuggestion).where(CanalSuggestion.batch_id == batch_id)
    total = db.execute(select(sa_func.count()).select_from(base.subquery())).scalar_one()
    offset = (page - 1) * limit
    items = list(
        db.execute(base.order_by(CanalSuggestion.score.desc()).offset(offset).limit(limit))
        .scalars()
        .all()
    )
    return items, total


def serialize_suggestion_page(*, items, total: int, page: int, limit: int, batch_id):
    return paginated_response(
        [CanalSuggestionResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        limit=limit,
        batch_id=str(batch_id) if batch_id is not None else None,
    )


def build_suggestion_summary_payload(summary: dict, repo: IntelligenceRepository, db: Session):
    resolved_batch = summary["batch_id"]
    top_per_tipo: dict[str, list] = {}
    for tipo in SUGGESTION_TYPES:
        items, _ = repo.get_suggestions_by_tipo(
            db, tipo, page=1, limit=5, batch_id=resolved_batch
        )
        if items:
            top_per_tipo[tipo] = [
                CanalSuggestionResponse.model_validate(item).model_dump()
                for item in items
            ]

    return {
        "batch_id": str(resolved_batch),
        "total_suggestions": summary["total_suggestions"],
        "by_tipo": summary["by_tipo"],
        "avg_score": summary["avg_score"],
        "created_at": summary["created_at"].isoformat()
        if summary.get("created_at")
        else None,
        "top_per_tipo": top_per_tipo,
    }
