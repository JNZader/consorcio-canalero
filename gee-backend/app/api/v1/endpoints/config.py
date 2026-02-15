"""
Configuration Endpoints.
Endpoints para obtener configuraciones del sistema.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, List

from app import constants

router = APIRouter()


class MapConfig(BaseModel):
    center: Dict[str, float]
    zoom: int
    bounds: Dict[str, float]


class CuencaInfo(BaseModel):
    id: str
    nombre: str
    ha: int
    color: str


class AnalysisConfig(BaseModel):
    default_max_cloud: int
    default_days_back: int


class SystemConfigResponse(BaseModel):
    consorcio_area_ha: int
    consorcio_km_caminos: int
    map: MapConfig
    cuencas: List[CuencaInfo]
    analysis: AnalysisConfig


@router.get("/system", response_model=SystemConfigResponse)
async def get_system_config():
    """
    Obtener la configuracion global del sistema.

    Este endpoint retorna constantes y configuraciones necesarias
    para el funcionamiento del frontend, como coordenadas del mapa,
    datos de cuencas y parametros de analisis.
    """

    # Preparar info de cuencas
    cuencas = []
    for cid in constants.CUENCA_IDS:
        cuencas.append(
            {
                "id": cid,
                "nombre": constants.CUENCA_NOMBRES.get(cid, cid.capitalize()),
                "ha": constants.CUENCA_AREAS_HA.get(cid, 0),
                "color": constants.CUENCA_COLORS.get(cid, "#808080"),
            }
        )

    return {
        "consorcio_area_ha": constants.CONSORCIO_AREA_HA,
        "consorcio_km_caminos": constants.CONSORCIO_KM_CAMINOS,
        "map": {
            "center": {
                "lat": constants.MAP_CENTER_LAT,
                "lng": constants.MAP_CENTER_LNG,
            },
            "zoom": constants.MAP_DEFAULT_ZOOM,
            "bounds": constants.MAP_BOUNDS,
        },
        "cuencas": cuencas,
        "analysis": {
            "default_max_cloud": constants.DEFAULT_MAX_CLOUD,
            "default_days_back": constants.DEFAULT_DAYS_BACK,
        },
    }
