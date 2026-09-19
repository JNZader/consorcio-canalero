"""HTTP layer for staff map pins. Operator-and-admin only.

Nothing here is published: these routes are the only way to this data, and the
dependency rejects before the service runs, so a denial has no payload to leak.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.puntos_interes.schemas import (
    PuntoInteresCreate,
    PuntoInteresFeature,
    PuntoInteresFeatureCollection,
)
from app.domains.geo.puntos_interes.service import PuntoInteresService

router = APIRouter(tags=["Points of Interest"])


def _require_operator():
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _get_service() -> PuntoInteresService:
    return PuntoInteresService()


def _user_id(usuario: object) -> Optional[uuid.UUID]:
    raw = getattr(usuario, "id", None)
    return raw if isinstance(raw, uuid.UUID) else None


@router.get("", response_model=PuntoInteresFeatureCollection)
def list_puntos_interes(
    db: Session = Depends(get_db),
    servicio: PuntoInteresService = Depends(_get_service),
    _usuario=Depends(_require_operator()),
) -> PuntoInteresFeatureCollection:
    return servicio.list_all(db)


@router.post("", response_model=PuntoInteresFeature, status_code=status.HTTP_201_CREATED)
def create_punto_interes(
    payload: PuntoInteresCreate,
    db: Session = Depends(get_db),
    servicio: PuntoInteresService = Depends(_get_service),
    usuario=Depends(_require_operator()),
) -> PuntoInteresFeature:
    feature = servicio.create(db, payload, created_by=_user_id(usuario))
    db.commit()
    return feature


@router.delete("/{punto_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_punto_interes(
    punto_id: uuid.UUID,
    db: Session = Depends(get_db),
    servicio: PuntoInteresService = Depends(_get_service),
    _usuario=Depends(_require_operator()),
) -> Response:
    servicio.delete(db, punto_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
