"""
Monitoring Endpoints.
Dashboard de monitoreo satelital de la cuenca.
"""

import asyncio
import time
from fastapi import APIRouter, Depends

from app.services.monitoring_service import get_monitoring_service
from app.auth import User, require_authenticated
from app.core.logging import get_logger
from app.core.exceptions import AppException, get_safe_error_detail

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


async def _get_cached_or_fetch():
    """Retorna datos cacheados o fetch fresh si expiro."""
    now = time.time()

    # Cache valido?
    if _dashboard_cache["data"] and now < _dashboard_cache["expires_at"]:
        logger.info("Monitoring dashboard: returning cached data")
        return _dashboard_cache["data"], True

    # Fetch fresh - wrap blocking GEE call in asyncio.to_thread
    logger.info("Monitoring dashboard: fetching fresh data from GEE")
    monitoring = get_monitoring_service()
    summary = await asyncio.to_thread(monitoring.get_monitoring_summary, days_back=30)

    if "error" not in summary:
        # Guardar en cache
        _dashboard_cache["data"] = summary
        _dashboard_cache["expires_at"] = now + _dashboard_cache["ttl_seconds"]

    return summary, False


@router.get("/dashboard")
async def get_dashboard_data(
    user: User = Depends(require_authenticated),
):
    """
    Obtener todos los datos necesarios para el dashboard de monitoreo.

    Combina multiples fuentes de datos en una sola respuesta:
    - Resumen de estado actual (area productiva vs problematica)
    - Alertas activas
    - Ranking de cuencas por area problematica

    Optimizado con cache de 5 minutos para evitar llamadas repetidas a GEE.
    """
    try:
        summary, from_cache = await _get_cached_or_fetch()

        if "error" in summary:
            raise AppException(
                message=summary["error"],
                code="MONITORING_DATA_ERROR",
                status_code=400,
            )

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

    except AppException:
        raise
    except Exception as e:
        logger.error("Error obteniendo datos del dashboard", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "datos del dashboard"),
            code="DASHBOARD_ERROR",
            status_code=500,
        )
