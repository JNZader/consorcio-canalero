"""
V2 API Router — aggregates all new domain routers under /api/v2.

This is the single entry point for the rewritten backend.
Each domain owns its own prefix and tags.
"""

from fastapi import APIRouter

from app.api.v2.public import admin_publish_router, public_router
from app.auth.router import router as auth_router
from app.domains.denuncias.router import router as denuncias_router
from app.domains.infraestructura.router import router as infraestructura_router
from app.domains.padron.router import router as padron_router
from app.domains.finanzas.router import router as finanzas_router
from app.domains.tramites.router import router as tramites_router
from app.domains.capas.router import router as capas_router
from app.domains.geo.router import router as geo_router
from app.domains.monitoring.router import router as monitoring_router
from app.domains.settings.router import router as settings_router
from app.domains.settings.router import public_settings_router

api_router = APIRouter(prefix="/api/v2")

# Auth (login, register, user management)
api_router.include_router(auth_router)

# Domain routers — each already carries its own prefix (/denuncias, etc.)
api_router.include_router(denuncias_router)
api_router.include_router(infraestructura_router)
api_router.include_router(padron_router)
api_router.include_router(finanzas_router)
api_router.include_router(tramites_router)
api_router.include_router(capas_router)

# Geo processing + GEE endpoints
api_router.include_router(geo_router, prefix="/geo")

# Monitoring has no prefix on its router — paths are /sugerencias and /monitoring/*
api_router.include_router(monitoring_router)

# System settings
api_router.include_router(settings_router)

# Public-facing endpoints (no auth) and admin publication workflow
api_router.include_router(public_router)
api_router.include_router(public_settings_router)
api_router.include_router(admin_publish_router)
