"""Advanced geo analysis, temporal, hydrology, routing and STAC endpoints."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.exceptions import AppException, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.intelligence.models import ZonaOperativa
from app.domains.geo.models import GeoLayer
from app.domains.geo.router_common import _require_operator

logger = get_logger(__name__)
router = APIRouter(tags=["Geo Processing"])

# ── Zonal Statistics ──────────────────────────────────────────────


class ZonalStatsRequest(BaseModel):
    """Request body for zonal statistics computation."""

    layer_tipo: str = Field(
        ...,
        description="GeoLayer type to use as raster (e.g. slope, twi, hand, flow_acc)",
    )
    zona_source: str = Field(
        default="zonas_operativas",
        description="Source table for zones: zonas_operativas, assets, or denuncias",
    )
    area_id: str | None = Field(
        default=None,
        description="Filter GeoLayer by area_id",
    )
    stats: list[str] | None = Field(
        default=None,
        description="Statistics to compute (default: min, max, mean, std, median, count, sum)",
    )


@router.post("/zonal-stats")
def compute_zonal_statistics(
    body: ZonalStatsRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Compute raster statistics per zone geometry.

    Crosses a raster layer (from the DEM pipeline) with vector zones
    (zonas_operativas, assets, or denuncias) and returns per-zone stats.
    """
    from geoalchemy2.functions import ST_AsText

    # 1. Find the raster layer
    layer = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == body.layer_tipo)
        .order_by(GeoLayer.created_at.desc())
    )
    if body.area_id:
        layer = layer.filter(GeoLayer.area_id == body.area_id)
    layer = layer.first()

    if not layer:
        raise NotFoundError(f"No GeoLayer found for tipo={body.layer_tipo}")

    # Prefer COG path if available
    raster_path = layer.archivo_path
    if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
        cog = layer.metadata_extra["cog_path"]
        if Path(cog).exists():
            raster_path = cog

    if not Path(raster_path).exists():
        raise AppException(
            message=f"Raster file not found: {raster_path}",
            code="RASTER_NOT_FOUND",
            status_code=404,
        )

    # 2. Fetch zone geometries from PostGIS
    if body.zona_source == "zonas_operativas":
        rows = db.query(
            ZonaOperativa.id,
            ST_AsText(ZonaOperativa.geometria),
            ZonaOperativa.nombre,
        ).all()
    elif body.zona_source == "assets":
        from app.domains.infraestructura.models import Asset

        rows = (
            db.query(
                Asset.id,
                ST_AsText(Asset.geom),
                Asset.nombre,
            )
            .filter(Asset.geom.isnot(None))
            .all()
        )
    elif body.zona_source == "denuncias":
        from app.domains.denuncias.models import Denuncia

        rows = (
            db.query(
                Denuncia.id,
                ST_AsText(Denuncia.geom),
                Denuncia.tipo,
            )
            .filter(Denuncia.geom.isnot(None))
            .all()
        )
    else:
        raise AppException(
            message=f"Invalid zona_source: {body.zona_source}",
            code="INVALID_ZONA_SOURCE",
            status_code=400,
        )

    if not rows:
        return {"results": [], "count": 0, "raster": body.layer_tipo}

    # 3. Compute zonal stats
    from app.domains.geo.zonal_stats import compute_stats_for_zones

    zone_data = [(str(r[0]), r[1], r[2]) for r in rows]
    results = compute_stats_for_zones(zone_data, raster_path, body.stats)

    return {
        "results": results,
        "count": len(results),
        "raster": body.layer_tipo,
        "zona_source": body.zona_source,
    }


# ── Flood Risk Assessment ─────────────────────────────────────────


@router.get("/flood-risk/zona/{zona_id}")
def get_zona_flood_risk(
    zona_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Compute comprehensive flood risk score for a zona operativa.

    Combines HAND, TWI, flow accumulation, and slope from the DEM
    pipeline into a single risk assessment. Returns individual metrics
    and a composite risk level.
    """
    from geoalchemy2.functions import ST_AsText

    # Get zona geometry
    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona operativa not found: {zona_id}")

    # Get raster layers
    layers_needed = ["hand", "twi", "flow_acc", "slope"]
    raster_paths = {}
    for tipo in layers_needed:
        layer = (
            db.query(GeoLayer)
            .filter(GeoLayer.tipo == tipo)
            .order_by(GeoLayer.created_at.desc())
            .first()
        )
        if layer:
            path = layer.archivo_path
            if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
                cog = layer.metadata_extra["cog_path"]
                if Path(cog).exists():
                    path = cog
            if Path(path).exists():
                raster_paths[tipo] = path

    if not raster_paths:
        raise AppException(
            message="No raster layers available for risk calculation",
            code="NO_RASTERS",
            status_code=404,
        )

    # Get zone geometry as WKT
    from sqlalchemy import select

    zona_wkt = db.execute(
        select(ST_AsText(ZonaOperativa.geometria)).where(ZonaOperativa.id == zona_id)
    ).scalar()

    # Compute zonal stats for each available layer
    from app.domains.geo.zonal_stats import compute_stats_for_zones

    zone_data = [(str(zona.id), zona_wkt, zona.nombre)]
    metrics = {}

    for tipo, path in raster_paths.items():
        try:
            stats = compute_stats_for_zones(
                zone_data, path, ["mean", "max", "min", "median", "count"]
            )
            if stats and stats[0].get("count", 0) > 0:
                metrics[tipo] = {
                    "mean": stats[0].get("mean"),
                    "max": stats[0].get("max"),
                    "min": stats[0].get("min"),
                    "median": stats[0].get("median"),
                }
        except Exception as exc:
            logger.warning("flood_risk.zonal_stats_failed", tipo=tipo, error=str(exc))

    # Compute composite risk score (0-100)
    risk_score = 0
    risk_factors = []

    if "hand" in metrics and metrics["hand"]["mean"] is not None:
        hand_mean = metrics["hand"]["mean"]
        if hand_mean < 0.5:
            risk_score += 40
            risk_factors.append("HAND muy bajo (<0.5m): zona extremadamente baja")
        elif hand_mean < 1.0:
            risk_score += 30
            risk_factors.append("HAND bajo (<1m): zona baja, susceptible a inundación")
        elif hand_mean < 2.0:
            risk_score += 15
            risk_factors.append("HAND moderado (<2m)")

    if "twi" in metrics and metrics["twi"]["mean"] is not None:
        twi_mean = metrics["twi"]["mean"]
        if twi_mean > 14:
            risk_score += 30
            risk_factors.append("TWI alto (>14): alta acumulación de agua")
        elif twi_mean > 11:
            risk_score += 20
            risk_factors.append("TWI moderado (>11): acumulación moderada")
        elif twi_mean > 8:
            risk_score += 5

    if "flow_acc" in metrics and metrics["flow_acc"]["max"] is not None:
        fa_max = metrics["flow_acc"]["max"]
        if fa_max > 100000:
            risk_score += 20
            risk_factors.append("Flow accumulation extremo: recibe mucha agua upstream")
        elif fa_max > 10000:
            risk_score += 10
            risk_factors.append("Flow accumulation alto")

    if "slope" in metrics and metrics["slope"]["mean"] is not None:
        slope_mean = metrics["slope"]["mean"]
        if slope_mean < 0.3:
            risk_score += 10
            risk_factors.append("Pendiente muy baja (<0.3°): agua no drena")
        elif slope_mean < 0.5:
            risk_score += 5

    risk_score = min(risk_score, 100)
    risk_level = (
        "critico"
        if risk_score >= 70
        else "alto"
        if risk_score >= 50
        else "moderado"
        if risk_score >= 30
        else "bajo"
    )

    return {
        "zona": {
            "id": str(zona.id),
            "nombre": zona.nombre,
            "cuenca": zona.cuenca,
            "superficie_ha": zona.superficie_ha,
        },
        "risk_score": risk_score,
        "risk_level": risk_level,
        "metrics": metrics,
        "risk_factors": risk_factors,
        "layers_used": list(raster_paths.keys()),
    }
