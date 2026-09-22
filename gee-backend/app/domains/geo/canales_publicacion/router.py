"""HTTP: staff catalog + public FeatureCollections."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.canales_publicacion.schemas import (
    CanalPublicacionList,
    CanalPublicacionPatch,
    CanalPublicacionRow,
)
from app.domains.geo.canales_publicacion.service import CanalPublicacionService

router = APIRouter(tags=["Canal publication"])


def _require_operator():
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _service() -> CanalPublicacionService:
    return CanalPublicacionService()


@router.get("/publico")
def get_canales_publico(
    db: Session = Depends(get_db),
    servicio: CanalPublicacionService = Depends(_service),
) -> dict[str, Any]:
    """Citizen map. No auth. Only ``publicado`` rows, public names."""
    return servicio.public_collections(db)


@router.get("/publicacion", response_model=CanalPublicacionList)
def list_publicacion(
    db: Session = Depends(get_db),
    servicio: CanalPublicacionService = Depends(_service),
    _usuario=Depends(_require_operator()),
) -> CanalPublicacionList:
    return servicio.list_staff(db)


@router.get("/aprhi-referencia")
def get_aprhi_referencia(
    db: Session = Depends(get_db),
    servicio: CanalPublicacionService = Depends(_service),
    _usuario=Depends(_require_operator()),
) -> dict[str, Any]:
    """Staff overlay: APRHI ``canales_existentes`` inside the consorcio hull. Not public."""
    return servicio.aprhi_referencia(db)


@router.patch("/publicacion/aprhi/{canal_id}", response_model=CanalPublicacionRow)
def patch_publicacion_aprhi(
    canal_id: str,
    payload: CanalPublicacionPatch,
    db: Session = Depends(get_db),
    servicio: CanalPublicacionService = Depends(_service),
    _usuario=Depends(_require_operator()),
) -> CanalPublicacionRow:
    row = servicio.patch_aprhi(db, canal_id, payload)
    db.commit()
    return row


@router.patch("/publicacion/{canal_id}", response_model=CanalPublicacionRow)
def patch_publicacion(
    canal_id: str,
    payload: CanalPublicacionPatch,
    db: Session = Depends(get_db),
    servicio: CanalPublicacionService = Depends(_service),
    _usuario=Depends(_require_operator()),
) -> CanalPublicacionRow:
    row = servicio.patch(db, canal_id, payload)
    db.commit()
    return row
