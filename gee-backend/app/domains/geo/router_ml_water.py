"""Machine-learning prediction and water-detection endpoints."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.domains.geo.intelligence.models import ZonaOperativa
from app.domains.geo.models import GeoLayer
from app.domains.geo.router_common import _require_operator

router = APIRouter(tags=["Geo Processing"])

# ── ML: Flood Prediction ──────────────────────────────────────────


@router.get("/ml/flood-prediction/zona/{zona_id}")
def predict_flood_ml(
    zona_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """ML-based flood probability prediction for a zona operativa.

    Combines DEM features (HAND, TWI, slope, flow_acc) with water
    detection data into a weighted model that outputs flood probability
    (0-1) and risk level. Model weights can be trained from historical
    flood events via POST /ml/flood-prediction/train.
    """
    from geoalchemy2.functions import ST_AsText
    from sqlalchemy import select

    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona not found: {zona_id}")

    # Get raster stats for features
    zona_wkt = db.execute(
        select(ST_AsText(ZonaOperativa.geometria)).where(ZonaOperativa.id == zona_id)
    ).scalar()

    from app.domains.geo.zonal_stats import compute_stats_for_zones

    zone_data = [(str(zona.id), zona_wkt, zona.nombre)]

    features = {
        "zona_id": str(zona.id),
        "zona_name": zona.nombre,
    }

    layer_stats = {}
    for tipo in ["hand", "twi", "slope", "flow_acc"]:
        layer = (
            db.query(GeoLayer)
            .filter(GeoLayer.tipo == tipo)
            .order_by(GeoLayer.created_at.desc())
            .first()
        )
        if not layer:
            continue

        path = layer.archivo_path
        if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
            cog = layer.metadata_extra["cog_path"]
            if Path(cog).exists():
                path = cog

        if not Path(path).exists():
            continue

        try:
            stats = compute_stats_for_zones(
                zone_data, path, ["mean", "max", "min", "count"]
            )
            if stats and stats[0].get("count", 0) > 0:
                layer_stats[tipo] = stats[0]
        except Exception:
            pass

    # Map to model features
    if "hand" in layer_stats:
        features["hand_mean"] = layer_stats["hand"].get("mean", 0) or 0
        features["hand_min"] = layer_stats["hand"].get("min", 0) or 0
    if "twi" in layer_stats:
        features["twi_mean"] = layer_stats["twi"].get("mean", 0) or 0
        features["twi_max"] = layer_stats["twi"].get("max", 0) or 0
    if "slope" in layer_stats:
        features["slope_mean"] = layer_stats["slope"].get("mean", 0) or 0
    if "flow_acc" in layer_stats:
        features["flow_acc_max"] = layer_stats["flow_acc"].get("max", 0) or 0
        features["flow_acc_mean"] = layer_stats["flow_acc"].get("mean", 0) or 0

    from app.domains.geo.ml.flood_prediction import predict_flood_for_zone

    prediction = predict_flood_for_zone(features)

    return {
        "zona": {"id": str(zona.id), "nombre": zona.nombre, "cuenca": zona.cuenca},
        "features": features,
        **prediction,
    }


@router.get("/ml/flood-prediction/all-zones")
def predict_flood_all_zones(
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Run flood prediction for ALL zonas operativas.

    Returns a ranked list of zones by flood probability, useful for
    prioritizing maintenance and emergency planning.
    """
    from geoalchemy2.functions import ST_AsText
    from sqlalchemy import select

    zonas = db.query(ZonaOperativa).all()
    if not zonas:
        return {"zones": [], "count": 0}

    # Load raster layers once
    raster_paths = {}
    for tipo in ["hand", "twi", "slope", "flow_acc"]:
        layer = (
            db.query(GeoLayer)
            .filter(GeoLayer.tipo == tipo)
            .order_by(GeoLayer.created_at.desc())
            .first()
        )
        if not layer:
            continue
        path = layer.archivo_path
        if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
            cog = layer.metadata_extra["cog_path"]
            if Path(cog).exists():
                path = cog
        if Path(path).exists():
            raster_paths[tipo] = path

    from app.domains.geo.zonal_stats import compute_stats_for_zones
    from app.domains.geo.ml.flood_prediction import FloodModel, ZoneFeatures

    model = FloodModel.load()
    results = []

    for zona in zonas:
        zona_wkt = db.execute(
            select(ST_AsText(ZonaOperativa.geometria)).where(
                ZonaOperativa.id == zona.id
            )
        ).scalar()

        zone_data = [(str(zona.id), zona_wkt, zona.nombre)]
        features = ZoneFeatures(zona_id=str(zona.id), zona_name=zona.nombre)

        for tipo, path in raster_paths.items():
            try:
                stats = compute_stats_for_zones(
                    zone_data, path, ["mean", "max", "min", "count"]
                )
                if stats and stats[0].get("count", 0) > 0:
                    s = stats[0]
                    if tipo == "hand":
                        features.hand_mean = s.get("mean", 0) or 0
                        features.hand_min = s.get("min", 0) or 0
                    elif tipo == "twi":
                        features.twi_mean = s.get("mean", 0) or 0
                        features.twi_max = s.get("max", 0) or 0
                    elif tipo == "slope":
                        features.slope_mean = s.get("mean", 0) or 0
                    elif tipo == "flow_acc":
                        features.flow_acc_max = s.get("max", 0) or 0
                        features.flow_acc_mean = s.get("mean", 0) or 0
            except Exception:
                pass

        prediction = model.predict(features)
        results.append(
            {
                "zona_id": str(zona.id),
                "zona_name": zona.nombre,
                "cuenca": zona.cuenca,
                "superficie_ha": zona.superficie_ha,
                "probability": prediction["probability"],
                "risk_level": prediction["risk_level"],
            }
        )

    # Sort by probability descending
    results.sort(key=lambda r: r["probability"], reverse=True)

    return {
        "zones": results,
        "count": len(results),
        "model_version": model.version,
        "layers_used": list(raster_paths.keys()),
    }


@router.get("/ml/model-info")
def get_ml_model_info():
    """Get information about available ML models."""
    from app.domains.geo.ml.flood_prediction import FloodModel
    from app.domains.geo.ml.water_segmentation import UNetStrategy

    flood_model = FloodModel.load()
    unet = UNetStrategy()

    return {
        "flood_prediction": {
            "version": flood_model.version,
            "weights": flood_model.weights,
            "bias": flood_model.bias,
            "trained": "trained" in flood_model.version,
        },
        "water_segmentation": {
            "strategies": ["ndwi", "unet"],
            "unet_model_available": unet.model_available,
            "unet_model_path": str(unet.MODEL_DIR / unet.MODEL_FILE),
        },
    }


# ── Water Detection ───────────────────────────────────────────────


class WaterDetectionRequest(BaseModel):
    """Request for water detection on a zona operativa."""

    zona_id: uuid.UUID
    target_date: str = Field(..., description="Target date YYYY-MM-DD")
    days_window: int = Field(default=15, ge=1, le=60)
    cloud_cover_max: int = Field(default=20, ge=0, le=100)


class WaterMultiDateRequest(BaseModel):
    """Request for multi-date water detection."""

    zona_id: uuid.UUID
    dates: list[str] = Field(..., description="List of target dates YYYY-MM-DD")
    cloud_cover_max: int = Field(default=20, ge=0, le=100)


@router.post("/water-detection/detect")
def detect_water(
    body: WaterDetectionRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Detect water bodies in a zona operativa using Sentinel-2 NDWI.

    Finds the best available Sentinel-2 image near the target date and
    classifies pixels into water/wet/dry based on NDWI thresholds.
    Returns area statistics in hectares and percentages.

    NOTE: This calls GEE and can take 15-30s.
    """
    from geoalchemy2.functions import ST_AsGeoJSON
    from sqlalchemy import select

    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == body.zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona not found: {body.zona_id}")

    geojson_str = db.execute(
        select(ST_AsGeoJSON(ZonaOperativa.geometria)).where(
            ZonaOperativa.id == body.zona_id
        )
    ).scalar()

    import json

    geometry = json.loads(geojson_str)

    from app.domains.geo.water_detection import detect_water_from_gee

    result = detect_water_from_gee(
        geometry_geojson=geometry,
        target_date=body.target_date,
        days_window=body.days_window,
        cloud_cover_max=body.cloud_cover_max,
    )

    return {"zona": {"id": str(zona.id), "nombre": zona.nombre}, **result}


@router.post("/water-detection/multi-date")
def detect_water_multi(
    body: WaterMultiDateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Run water detection for multiple dates to track water level changes.

    Returns per-date results and a change summary between first and last date.

    NOTE: Each date calls GEE — total time ≈ 15-30s × number of dates.
    """
    from geoalchemy2.functions import ST_AsGeoJSON
    from sqlalchemy import select

    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == body.zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona not found: {body.zona_id}")

    geojson_str = db.execute(
        select(ST_AsGeoJSON(ZonaOperativa.geometria)).where(
            ZonaOperativa.id == body.zona_id
        )
    ).scalar()

    import json

    geometry = json.loads(geojson_str)

    from app.domains.geo.water_detection import detect_water_multi_date

    result = detect_water_multi_date(
        geometry_geojson=geometry,
        dates=body.dates,
        cloud_cover_max=body.cloud_cover_max,
    )

    return {"zona": {"id": str(zona.id), "nombre": zona.nombre}, **result}
