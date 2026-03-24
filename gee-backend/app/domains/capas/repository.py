"""Repository layer — all database access for the capas domain."""

import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domains.capas.models import Capa
from app.domains.capas.schemas import CapaCreate, CapaUpdate


class CapasRepository:
    """Data-access layer for map layers (capas)."""

    # ── READ ──────────────────────────────────

    def get_all(
        self,
        db: Session,
        *,
        visible_only: bool = False,
    ) -> list[Capa]:
        """Return all layers ordered by 'orden' ascending."""
        stmt = select(Capa).order_by(Capa.orden.asc(), Capa.nombre.asc())
        if visible_only:
            stmt = stmt.where(Capa.visible.is_(True))
        return list(db.execute(stmt).scalars().all())

    def get_by_id(self, db: Session, capa_id: uuid.UUID) -> Optional[Capa]:
        """Return a single layer by ID, or None."""
        stmt = select(Capa).where(Capa.id == capa_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_public(self, db: Session) -> list[Capa]:
        """Return only public layers, ordered by 'orden'."""
        stmt = (
            select(Capa)
            .where(Capa.es_publica.is_(True), Capa.visible.is_(True))
            .order_by(Capa.orden.asc(), Capa.nombre.asc())
        )
        return list(db.execute(stmt).scalars().all())

    # ── WRITE ─────────────────────────────────

    def create(self, db: Session, data: CapaCreate) -> Capa:
        """Insert a new layer."""
        dump = data.model_dump()
        # Serialize estilo sub-model to dict
        if hasattr(dump.get("estilo"), "model_dump"):
            dump["estilo"] = dump["estilo"].model_dump()
        capa = Capa(**dump)
        db.add(capa)
        db.flush()
        return capa

    def update(
        self, db: Session, capa_id: uuid.UUID, data: CapaUpdate
    ) -> Optional[Capa]:
        """Apply partial update to an existing layer."""
        capa = self.get_by_id(db, capa_id)
        if capa is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        # Serialize estilo sub-model to dict
        if "estilo" in update_data and update_data["estilo"] is not None:
            if hasattr(update_data["estilo"], "model_dump"):
                update_data["estilo"] = update_data["estilo"].model_dump()

        for field, value in update_data.items():
            setattr(capa, field, value)

        db.flush()
        return capa

    def delete(self, db: Session, capa_id: uuid.UUID) -> bool:
        """Delete a layer by ID. Returns True if deleted."""
        capa = self.get_by_id(db, capa_id)
        if capa is None:
            return False
        db.delete(capa)
        db.flush()
        return True

    def reorder(self, db: Session, ordered_ids: list[uuid.UUID]) -> int:
        """
        Update 'orden' for each layer based on position in the list.
        Returns the number of layers reordered.
        """
        count = 0
        for idx, capa_id in enumerate(ordered_ids):
            stmt = (
                update(Capa)
                .where(Capa.id == capa_id)
                .values(orden=idx)
            )
            result = db.execute(stmt)
            count += result.rowcount
        db.flush()
        return count
