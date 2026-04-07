"""Repository layer — all database access for the reuniones domain."""

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domains.reuniones.models import (
    AgendaItem,
    AgendaReferencia,
    Reunion,
)
from app.domains.reuniones.schemas import (
    AgendaItemCreate,
    ReunionCreate,
    ReunionUpdate,
)


class ReunionRepository:
    """Data-access layer for reuniones."""

    # ── READ ──────────────────────────────────

    def get_by_id(self, db: Session, reunion_id: uuid.UUID) -> Optional[Reunion]:
        """Return a single reunion with its agenda items, or None."""
        stmt = (
            select(Reunion)
            .options(
                selectinload(Reunion.agenda_items).selectinload(AgendaItem.referencias)
            )
            .where(Reunion.id == reunion_id)
        )
        return db.execute(stmt).scalar_one_or_none()

    def get_all(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado_filter: Optional[str] = None,
        tipo_filter: Optional[str] = None,
    ) -> tuple[list[Reunion], int]:
        """
        Paginated list of reuniones with optional filters.

        Returns (items, total_count).
        """
        base = select(Reunion)

        if estado_filter:
            base = base.where(Reunion.estado == estado_filter)
        if tipo_filter:
            base = base.where(Reunion.tipo == tipo_filter)

        # Total count (separate query for accuracy with LIMIT)
        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        # Paginated items
        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(Reunion.fecha_reunion.desc()).offset(offset).limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    # ── WRITE ─────────────────────────────────

    def create(
        self,
        db: Session,
        data: ReunionCreate,
        usuario_id: uuid.UUID,
    ) -> Reunion:
        """Insert a new reunion."""
        reunion = Reunion(
            titulo=data.titulo,
            fecha_reunion=data.fecha_reunion,
            lugar=data.lugar,
            descripcion=data.descripcion,
            tipo=data.tipo,
            orden_del_dia_items=data.orden_del_dia_items,
            usuario_id=usuario_id,
        )
        db.add(reunion)
        db.flush()
        return reunion

    def update(
        self,
        db: Session,
        reunion_id: uuid.UUID,
        data: ReunionUpdate,
    ) -> Optional[Reunion]:
        """Apply partial update to an existing reunion."""
        reunion = self.get_by_id(db, reunion_id)
        if reunion is None:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(reunion, field, value)

        db.flush()
        return reunion

    def delete(self, db: Session, reunion_id: uuid.UUID) -> bool:
        """Delete a reunion. Returns True if found and deleted."""
        reunion = self.get_by_id(db, reunion_id)
        if reunion is None:
            return False
        db.delete(reunion)
        db.flush()
        return True


class AgendaItemRepository:
    """Data-access layer for agenda items and their referencias."""

    # ── READ ──────────────────────────────────

    def get_by_id(self, db: Session, item_id: uuid.UUID) -> Optional[AgendaItem]:
        """Return a single agenda item with referencias, or None."""
        stmt = (
            select(AgendaItem)
            .options(selectinload(AgendaItem.referencias))
            .where(AgendaItem.id == item_id)
        )
        return db.execute(stmt).scalar_one_or_none()

    def get_by_reunion_id(self, db: Session, reunion_id: uuid.UUID) -> list[AgendaItem]:
        """Return all agenda items for a reunion, ordered by orden."""
        stmt = (
            select(AgendaItem)
            .options(selectinload(AgendaItem.referencias))
            .where(AgendaItem.reunion_id == reunion_id)
            .order_by(AgendaItem.orden)
        )
        return list(db.execute(stmt).scalars().all())

    # ── WRITE ─────────────────────────────────

    def create(
        self,
        db: Session,
        reunion_id: uuid.UUID,
        data: AgendaItemCreate,
    ) -> AgendaItem:
        """Insert an agenda item with optional referencias."""
        item = AgendaItem(
            reunion_id=reunion_id,
            titulo=data.titulo,
            descripcion=data.descripcion,
            orden=data.orden,
        )
        db.add(item)
        db.flush()

        # Bulk insert referencias
        for ref_data in data.referencias:
            ref = AgendaReferencia(
                agenda_item_id=item.id,
                entidad_tipo=ref_data.entidad_tipo,
                entidad_id=ref_data.entidad_id,
                metadata_json=ref_data.metadata,
            )
            db.add(ref)

        db.flush()
        return item

    def delete(self, db: Session, item_id: uuid.UUID) -> bool:
        """Delete an agenda item. Returns True if found and deleted."""
        item = self.get_by_id(db, item_id)
        if item is None:
            return False
        db.delete(item)
        db.flush()
        return True
