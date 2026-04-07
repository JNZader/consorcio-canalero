"""Pydantic v2 schemas for public-facing endpoints.

These schemas expose limited information — no internal IDs or
personal data are leaked to unauthenticated consumers.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ──────────────────────────────────────────────
# PUBLIC LAYER RESPONSES
# ──────────────────────────────────────────────


class PublicLayerListResponse(BaseModel):
    """Lightweight public layer for list endpoint (no geojson_data)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    estilo: dict[str, Any]
    orden: int


class PublicLayerDetailResponse(BaseModel):
    """Full public layer detail with GeoJSON data."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    estilo: dict[str, Any]
    geojson_data: Optional[dict[str, Any]] = None
    orden: int


# ──────────────────────────────────────────────
# PUBLIC DENUNCIA STATUS
# ──────────────────────────────────────────────


class PublicDenunciaStatusResponse(BaseModel):
    """Limited denuncia status for anonymous status checks.

    No personal info (contacto_*, user_id) is exposed.
    """

    model_config = ConfigDict(from_attributes=True)

    estado: str
    created_at: datetime


# ──────────────────────────────────────────────
# PUBLIC STATS
# ──────────────────────────────────────────────


class PublicStatsResponse(BaseModel):
    """Basic public statistics — safe to expose without auth."""

    total_denuncias: int = 0
    total_sugerencias: int = 0
    total_capas_publicas: int = 0


# ──────────────────────────────────────────────
# ADMIN PUBLISH WORKFLOW
# ──────────────────────────────────────────────


class PublishLayerResponse(BaseModel):
    """Response after publishing/unpublishing a layer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    es_publica: bool
    publicacion_fecha: Optional[datetime] = None


class AdminLayerPublishStatus(BaseModel):
    """Layer with its publish status for admin listing."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    visible: bool
    es_publica: bool
    publicacion_fecha: Optional[datetime] = None
    created_at: datetime


# ──────────────────────────────────────────────
# MARTIN TILE CATALOG
# ──────────────────────────────────────────────


class MartinLayerCatalogItem(BaseModel):
    """A single Martin-published vector tile layer, URL-rewritten for public consumption."""

    id: str
    tile_url: str  # public-facing template: {base}/{id}/{z}/{x}/{y}
    description: str
    geometry_type: (
        str  # normalized to lowercase: "polygon", "point", "linestring", etc.
    )
    source_layer: str  # same as id for Martin auto-published PostGIS views


class MartinCatalogResponse(BaseModel):
    """Catalog of all Martin-published vector tile layers."""

    layers: list[MartinLayerCatalogItem]
    count: int
