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
