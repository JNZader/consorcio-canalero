"""
Monitoring Endpoints.
Dashboard de monitoreo satelital de la cuenca.
"""

import time
from fastapi import APIRouter, HTTPException, Depends

from app.services.monitoring_service import get_monitoring_service
from app.auth import User, get_current_user
from app.core.logging import get_logger
from app.core.exceptions import get_safe_error_detail

logger = get_logger(__name__)

router = APIRouter()

# ============================================
# CACHE EN MEMORIA (TTL 5 minutos)
# ============================================
_dashboard_cache = {
    "data": None,
    "expires_at": 0,
    "ttl_seconds": 300,  # 5 minutos
}


def _get_cached_or_fetch():
    """Retorna datos cacheados o fetch fresh si expiró."""
    now = time.time()

    # Cache válido?
    if _dashboard_cache["data"] and now < _dashboard_cache["expires_at"]:
        logger.info("Monitoring dashboard: returning cached data")
        return _dashboard_cache["data"], True

    # Fetch fresh
    logger.info("Monitoring dashboard: fetching fresh data from GEE")
    monitoring = get_monitoring_service()
    summary = monitoring.get_monitoring_summary(days_back=30)

    if "error" not in summary:
        # Guardar en cache
        _dashboard_cache["data"] = summary
        _dashboard_cache["expires_at"] = now + _dashboard_cache["ttl_seconds"]

    return summary, False


@router.get("/dashboard")
async def get_dashboard_data(
    user: User = Depends(get_current_user),
):
    """
    Obtener todos los datos necesarios para el dashboard de monitoreo.

    Combina múltiples fuentes de datos en una sola respuesta:
    - Resumen de estado actual (área productiva vs problemática)
    - Alertas activas
    - Ranking de cuencas por área problemática

    Optimizado con cache de 5 minutos para evitar llamadas repetidas a GEE.
    """
    try:
        summary, from_cache = _get_cached_or_fetch()

        if "error" in summary:
            raise HTTPException(status_code=400, detail=summary["error"])

        # Extraer periodo de summary
        periodo = summary.get("periodo", {})

        return {
            "summary": summary.get("estado_general", {}),
            "clasificacion": summary.get("clasificacion", {}),
            "cuencas": {},  # No incluido para optimizar (usa ranking_cuencas)
            "ranking_cuencas": summary.get("cuencas_criticas", []),
            "alertas": summary.get("alertas", []),
            "total_alertas": summary.get("total_alertas", 0),
            "periodo": {
                "inicio": periodo.get("inicio", ""),
                "fin": periodo.get("fin", ""),
            },
            "fecha_actualizacion": summary.get("fecha_actualizacion"),
            "from_cache": from_cache,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error obteniendo datos del dashboard", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=get_safe_error_detail(e, "datos del dashboard")
        )
