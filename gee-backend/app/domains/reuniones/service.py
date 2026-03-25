"""Business-logic layer for reuniones domain."""

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.reuniones.models import (
    AgendaItem,
    Reunion,
    VALID_TRANSITIONS,
)
from app.domains.reuniones.repository import (
    AgendaItemRepository,
    ReunionRepository,
)
from app.domains.reuniones.schemas import (
    AgendaItemCreate,
    ReunionCreate,
    ReunionUpdate,
)


class ReunionService:
    """Orchestrates repository calls with business rules."""

    def __init__(
        self,
        repository: ReunionRepository | None = None,
        agenda_repository: AgendaItemRepository | None = None,
    ) -> None:
        self.repo = repository or ReunionRepository()
        self.agenda_repo = agenda_repository or AgendaItemRepository()

    # ── QUERIES ───────────────────────────────

    def get_by_id(self, db: Session, reunion_id: uuid.UUID) -> Reunion:
        reunion = self.repo.get_by_id(db, reunion_id)
        if reunion is None:
            raise HTTPException(status_code=404, detail="Reunion no encontrada")
        return reunion

    def list_reuniones(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado: Optional[str] = None,
        tipo: Optional[str] = None,
    ) -> tuple[list[Reunion], int]:
        return self.repo.get_all(
            db,
            page=page,
            limit=limit,
            estado_filter=estado,
            tipo_filter=tipo,
        )

    # ── COMMANDS ──────────────────────────────

    def create(
        self,
        db: Session,
        data: ReunionCreate,
        usuario_id: uuid.UUID,
    ) -> Reunion:
        """Create a reunion and commit."""
        reunion = self.repo.create(db, data, usuario_id=usuario_id)
        db.commit()
        db.refresh(reunion)
        return reunion

    def update(
        self,
        db: Session,
        reunion_id: uuid.UUID,
        data: ReunionUpdate,
    ) -> Reunion:
        """
        Update a reunion, validating state transitions.
        """
        reunion = self.get_by_id(db, reunion_id)

        # State transition validation
        if data.estado is not None and data.estado != reunion.estado:
            allowed = VALID_TRANSITIONS.get(reunion.estado, set())
            if data.estado not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Transicion de estado invalida: "
                        f"{reunion.estado} -> {data.estado}"
                    ),
                )

        updated = self.repo.update(db, reunion_id, data)
        db.commit()
        db.refresh(updated)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    def delete(
        self,
        db: Session,
        reunion_id: uuid.UUID,
    ) -> None:
        """Delete a reunion (cascade deletes agenda items + referencias)."""
        deleted = self.repo.delete(db, reunion_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Reunion no encontrada")
        db.commit()

    # ── AGENDA ITEMS ──────────────────────────

    def get_agenda_items(
        self, db: Session, reunion_id: uuid.UUID
    ) -> list[AgendaItem]:
        """List agenda items for a reunion (validates reunion exists)."""
        self.get_by_id(db, reunion_id)  # 404 if not found
        return self.agenda_repo.get_by_reunion_id(db, reunion_id)

    def add_agenda_item(
        self,
        db: Session,
        reunion_id: uuid.UUID,
        data: AgendaItemCreate,
    ) -> AgendaItem:
        """Add an agenda item with optional referencias."""
        self.get_by_id(db, reunion_id)  # 404 if not found
        item = self.agenda_repo.create(db, reunion_id, data)
        db.commit()
        db.refresh(item)
        return item

    def delete_agenda_item(
        self,
        db: Session,
        reunion_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> None:
        """Delete an agenda item (validates it belongs to the reunion)."""
        self.get_by_id(db, reunion_id)  # 404 if reunion not found
        item = self.agenda_repo.get_by_id(db, item_id)
        if item is None or item.reunion_id != reunion_id:
            raise HTTPException(
                status_code=404, detail="Agenda item no encontrado"
            )
        self.agenda_repo.delete(db, item_id)
        db.commit()
