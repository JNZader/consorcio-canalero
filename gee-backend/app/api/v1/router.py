"""
Main API router - combines all endpoint routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    layers,
    reports,
    stats,
    public,
    sugerencias,
    monitoring,
    gee_layers,
    image_explorer,
    config,
    jobs,
    infrastructure,
    management,
    padron,
    finance,
)

api_router = APIRouter()

# Public endpoints (no authentication required)
api_router.include_router(
    public.router,
    prefix="/public",
    tags=["Public"],
)

api_router.include_router(
    config.router,
    prefix="/config",
    tags=["Configuracion"],
)

# Protected endpoints
api_router.include_router(
    jobs.router,
    prefix="/jobs",
    tags=["Background Jobs"],
)

api_router.include_router(
    infrastructure.router,
    prefix="/infrastructure",
    tags=["Infraestructura"],
)

api_router.include_router(
    management.router,
    prefix="/management",
    tags=["Gestion y Seguimiento"],
)

api_router.include_router(
    padron.router,
    prefix="/padron",
    tags=["Padron y Cuotas"],
)

api_router.include_router(
    finance.router,
    prefix="/finance",
    tags=["Finanzas y Presupuesto"],
)
api_router.include_router(
    layers.router,
    prefix="/layers",
    tags=["Layers"],
)

api_router.include_router(
    reports.router,
    prefix="/reports",
    tags=["Reports"],
)

api_router.include_router(
    stats.router,
    prefix="/stats",
    tags=["Statistics"],
)

api_router.include_router(
    sugerencias.router,
    prefix="/sugerencias",
    tags=["Sugerencias"],
)

api_router.include_router(
    monitoring.router,
    prefix="/monitoring",
    tags=["Monitoreo Satelital"],
)

api_router.include_router(
    gee_layers.router,
    prefix="/gee/layers",
    tags=["GEE Layers"],
)

api_router.include_router(
    image_explorer.router,
    tags=["Image Explorer"],
)
