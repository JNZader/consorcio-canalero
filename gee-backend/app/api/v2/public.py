"""
Public API router — unauthenticated endpoints for the public viewer,
external reporting, and the admin publication workflow.

No auth is required for /public/* endpoints.
Admin endpoints under /admin/publish/* require admin role.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v2.public_schemas import (
    AdminLayerPublishStatus,
    PublicDenunciaStatusResponse,
    PublicLayerDetailResponse,
    PublicLayerListResponse,
    PublicStatsResponse,
    PublishLayerResponse,
)
from app.db.session import get_db
from app.domains.capas.models import Capa
from app.domains.capas.repository import CapasRepository
from app.domains.denuncias.models import Denuncia
from app.domains.denuncias.schemas import DenunciaCreate, DenunciaCreateResponse
from app.domains.denuncias.service import DenunciaService
from app.domains.monitoring.models import Sugerencia
from app.domains.monitoring.schemas import SugerenciaCreate, SugerenciaResponse
from app.domains.monitoring.service import MonitoringService

# ──────────────────────────────────────────────
# ROUTERS
# ──────────────────────────────────────────────

public_router = APIRouter(prefix="/public", tags=["public"])
admin_publish_router = APIRouter(prefix="/admin/publish", tags=["admin-publish"])


# ──────────────────────────────────────────────
# DEPENDENCIES
# ──────────────────────────────────────────────


def _get_capas_repo() -> CapasRepository:
    return CapasRepository()


def _get_denuncia_service() -> DenunciaService:
    return DenunciaService()


def _get_monitoring_service() -> MonitoringService:
    return MonitoringService()


def _require_admin():
    """Lazy import to avoid circular deps at module level."""
    from app.auth import require_admin

    return require_admin


# ══════════════════════════════════════════════
# PUBLIC VIEWER ENDPOINTS (no auth)
# ══════════════════════════════════════════════


@public_router.get("/layers", response_model=list[PublicLayerListResponse])
def list_public_layers(
    db: Session = Depends(get_db),
    repo: CapasRepository = Depends(_get_capas_repo),
):
    """List all public layers (es_publica=True, visible=True)."""
    return repo.get_public(db)


@public_router.get("/layers/{layer_id}", response_model=PublicLayerDetailResponse)
def get_public_layer(
    layer_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: CapasRepository = Depends(_get_capas_repo),
):
    """Get detail of a single public layer including GeoJSON data."""
    capa = repo.get_by_id(db, layer_id)
    if capa is None or not capa.es_publica or not capa.visible:
        raise HTTPException(status_code=404, detail="Capa publica no encontrada")
    return capa


@public_router.get("/images", response_model=list[PublicLayerListResponse])
def list_public_images(
    db: Session = Depends(get_db),
):
    """
    List published image/raster layers.

    Filters public layers to those of type 'raster' or 'tile' —
    satellite imagery and generated maps.
    """
    stmt = (
        select(Capa)
        .where(
            Capa.es_publica.is_(True),
            Capa.visible.is_(True),
            Capa.tipo.in_(["raster", "tile"]),
        )
        .order_by(Capa.orden.asc(), Capa.nombre.asc())
    )
    return list(db.execute(stmt).scalars().all())


@public_router.get("/stats", response_model=PublicStatsResponse)
def get_public_stats(
    db: Session = Depends(get_db),
):
    """Basic public statistics — safe to show without authentication."""
    total_denuncias: int = db.execute(
        select(func.count()).select_from(Denuncia)
    ).scalar_one()

    total_sugerencias: int = db.execute(
        select(func.count()).select_from(Sugerencia)
    ).scalar_one()

    total_capas_publicas: int = db.execute(
        select(func.count())
        .select_from(Capa)
        .where(Capa.es_publica.is_(True), Capa.visible.is_(True))
    ).scalar_one()

    return PublicStatsResponse(
        total_denuncias=total_denuncias,
        total_sugerencias=total_sugerencias,
        total_capas_publicas=total_capas_publicas,
    )


# ══════════════════════════════════════════════
# EXTERNAL REPORTING ENDPOINTS (no auth)
# ══════════════════════════════════════════════


@public_router.post("/denuncias", response_model=DenunciaCreateResponse, status_code=201)
def create_anonymous_denuncia(
    payload: DenunciaCreate,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(_get_denuncia_service),
):
    """
    Create an anonymous denuncia (citizen report).

    Re-exposes the denuncias domain creation under /public
    for a cleaner public-facing API surface.
    """
    denuncia = service.create(db, payload)
    return DenunciaCreateResponse(
        id=denuncia.id,
        message="Denuncia creada exitosamente. Gracias por colaborar.",
        estado=denuncia.estado,
    )


@public_router.post(
    "/sugerencias", response_model=SugerenciaResponse, status_code=201
)
def create_anonymous_sugerencia(
    payload: SugerenciaCreate,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(_get_monitoring_service),
):
    """
    Create an anonymous suggestion.

    Re-exposes the monitoring domain creation under /public
    for a cleaner public-facing API surface.
    """
    return service.create_sugerencia(db, payload)


@public_router.get("/sugerencias/canales-existentes", response_model=dict)
def list_incorporated_suggestion_channels(
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(_get_monitoring_service),
):
    """Return incorporated suggestion lines as a public FeatureCollection."""
    return service.get_incorporated_channel_feature_collection(db)


@public_router.get(
    "/denuncias/{denuncia_id}/status",
    response_model=PublicDenunciaStatusResponse,
)
def check_denuncia_status(
    denuncia_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(_get_denuncia_service),
):
    """
    Check the status of a submitted denuncia by ID.

    Returns only estado and created_at — no personal information.
    """
    denuncia = service.get_by_id(db, denuncia_id)
    return PublicDenunciaStatusResponse(
        estado=denuncia.estado,
        created_at=denuncia.created_at,
    )


# ══════════════════════════════════════════════
# ADMIN PUBLICATION WORKFLOW (require admin)
# ══════════════════════════════════════════════


@admin_publish_router.get("/layers", response_model=list[AdminLayerPublishStatus])
def list_layers_with_publish_status(
    db: Session = Depends(get_db),
    repo: CapasRepository = Depends(_get_capas_repo),
    _user=Depends(_require_admin()),
):
    """List all layers with their publish status (admin only)."""
    return repo.get_all(db)


@admin_publish_router.post(
    "/layers/{layer_id}", response_model=PublishLayerResponse
)
def publish_layer(
    layer_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: CapasRepository = Depends(_get_capas_repo),
    _user=Depends(_require_admin()),
):
    """Mark a layer as public (admin only)."""
    capa = repo.get_by_id(db, layer_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="Capa no encontrada")

    if capa.es_publica:
        raise HTTPException(
            status_code=409, detail="La capa ya esta publicada"
        )

    capa.es_publica = True
    capa.publicacion_fecha = datetime.now(timezone.utc)
    db.flush()
    db.commit()
    db.refresh(capa)
    return capa


@admin_publish_router.delete(
    "/layers/{layer_id}", response_model=PublishLayerResponse
)
def unpublish_layer(
    layer_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: CapasRepository = Depends(_get_capas_repo),
    _user=Depends(_require_admin()),
):
    """Remove a layer from public access (admin only)."""
    capa = repo.get_by_id(db, layer_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="Capa no encontrada")

    if not capa.es_publica:
        raise HTTPException(
            status_code=409, detail="La capa no esta publicada"
        )

    capa.es_publica = False
    capa.publicacion_fecha = None
    db.flush()
    db.commit()
    db.refresh(capa)
    return capa
