"""Business-logic layer for the capas (map layers) domain."""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.capas.models import Capa
from app.domains.capas.repository import CapasRepository
from app.domains.capas.schemas import CapaCreate, CapaUpdate


class CapasService:
    """Orchestrates repository calls with business rules."""

    def __init__(self, repository: CapasRepository | None = None) -> None:
        self.repo = repository or CapasRepository()

    # ── QUERIES ───────────────────────────────

    def get_by_id(self, db: Session, capa_id: uuid.UUID) -> Capa:
        capa = self.repo.get_by_id(db, capa_id)
        if capa is None:
            raise HTTPException(status_code=404, detail="Capa no encontrada")
        return capa

    def list_capas(
        self,
        db: Session,
        *,
        visible_only: bool = False,
    ) -> list[Capa]:
        return self.repo.get_all(db, visible_only=visible_only)

    def list_public(self, db: Session) -> list[Capa]:
        return self.repo.get_public(db)

    # ── COMMANDS ──────────────────────────────

    def create(self, db: Session, data: CapaCreate) -> Capa:
        """Create a layer and commit."""
        capa = self.repo.create(db, data)
        db.commit()
        db.refresh(capa)
        return capa

    def update(self, db: Session, capa_id: uuid.UUID, data: CapaUpdate) -> Capa:
        """Update a layer and commit."""
        # Verify it exists first (raises 404 if not)
        self.get_by_id(db, capa_id)

        updated = self.repo.update(db, capa_id, data)
        db.commit()
        db.refresh(updated)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    def delete(self, db: Session, capa_id: uuid.UUID) -> None:
        """Delete a layer and commit."""
        # Verify it exists first (raises 404 if not)
        self.get_by_id(db, capa_id)

        self.repo.delete(db, capa_id)
        db.commit()

    def reorder(self, db: Session, ordered_ids: list[uuid.UUID]) -> int:
        """Reorder layers and commit. Returns count of reordered layers."""
        if not ordered_ids:
            raise HTTPException(status_code=400, detail="Lista de IDs vacia")
        count = self.repo.reorder(db, ordered_ids)
        db.commit()
        return count
