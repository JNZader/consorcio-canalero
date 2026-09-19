"""Application service for staff map pins."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.geo.puntos_interes.repository import PuntoInteresRepository
from app.domains.geo.puntos_interes.schemas import (
    PuntoInteresCreate,
    PuntoInteresFeature,
    PuntoInteresFeatureCollection,
)


class PuntoInteresService:
    def __init__(self, repo: PuntoInteresRepository | None = None) -> None:
        self._repo = repo or PuntoInteresRepository()

    def list_all(self, db: Session) -> PuntoInteresFeatureCollection:
        return self._repo.list_all(db)

    def create(
        self,
        db: Session,
        payload: PuntoInteresCreate,
        created_by: Optional[uuid.UUID],
    ) -> PuntoInteresFeature:
        return self._repo.create(db, payload, created_by)

    def delete(self, db: Session, punto_id: uuid.UUID) -> None:
        deleted = self._repo.delete(db, punto_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Punto de interés no encontrado",
            )
