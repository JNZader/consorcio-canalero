"""Repository layer — all database access for the tramites domain."""

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domains.tramites.models import (
    Tramite,
    TramiteSeguimiento,
    EstadoTramite,
)
from app.domains.tramites.schemas import TramiteCreate, TramiteUpdate


class TramiteRepository:
    """Data-access layer for tramites and their seguimiento log."""

    # ── READ ──────────────────────────────────

    def get_by_id(self, db: Session, tramite_id: uuid.UUID) -> Optional[Tramite]:
        """Return a single tramite with its seguimiento, or None."""
        stmt = (
            select(Tramite)
            .options(selectinload(Tramite.seguimiento))
            .where(Tramite.id == tramite_id)
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
        prioridad_filter: Optional[str] = None,
    ) -> tuple[list[Tramite], int]:
        """
        Paginated list of tramites with optional filters.

        Returns (items, total_count).
        """
        base = select(Tramite)

        if estado_filter:
            base = base.where(Tramite.estado == estado_filter)
        if tipo_filter:
            base = base.where(Tramite.tipo == tipo_filter)
        if prioridad_filter:
            base = base.where(Tramite.prioridad == prioridad_filter)

        # Total count (separate query for accuracy with LIMIT)
        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        # Paginated items
        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(Tramite.created_at.desc()).offset(offset).limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    # ── WRITE ─────────────────────────────────

    def create(
        self,
        db: Session,
        data: TramiteCreate,
        usuario_id: uuid.UUID,
    ) -> Tramite:
        """Insert a new tramite."""
        tramite = Tramite(
            tipo=data.tipo,
            titulo=data.titulo,
            descripcion=data.descripcion,
            solicitante=data.solicitante,
            estado=EstadoTramite.INGRESADO,
            prioridad=data.prioridad,
            fecha_ingreso=data.fecha_ingreso,
            usuario_id=usuario_id,
        )
        db.add(tramite)
        db.flush()
        return tramite

    def update(
        self,
        db: Session,
        tramite_id: uuid.UUID,
        data: TramiteUpdate,
    ) -> Optional[Tramite]:
        """Apply partial update to an existing tramite."""
        tramite = self.get_by_id(db, tramite_id)
        if tramite is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        # Remove comentario — it belongs to seguimiento, not to the tramite row
        update_data.pop("comentario", None)

        for field, value in update_data.items():
            setattr(tramite, field, value)

        db.flush()
        return tramite

    # ── SEGUIMIENTO ────────────────────────────

    def add_seguimiento(
        self,
        db: Session,
        *,
        tramite_id: uuid.UUID,
        estado_anterior: str,
        estado_nuevo: str,
        comentario: str,
        usuario_id: uuid.UUID,
    ) -> TramiteSeguimiento:
        """Record a state transition or follow-up in the audit log."""
        entry = TramiteSeguimiento(
            tramite_id=tramite_id,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            comentario=comentario,
            usuario_id=usuario_id,
        )
        db.add(entry)
        db.flush()
        return entry

    # ── STATS ─────────────────────────────────

    def get_stats(self, db: Session) -> dict:
        """Aggregate counts by estado, tipo, and prioridad."""
        # By estado
        estado_rows = db.execute(
            select(Tramite.estado, func.count()).group_by(Tramite.estado)
        ).all()
        por_estado = {row[0]: row[1] for row in estado_rows}

        # By tipo
        tipo_rows = db.execute(
            select(Tramite.tipo, func.count()).group_by(Tramite.tipo)
        ).all()
        por_tipo = {row[0]: row[1] for row in tipo_rows}

        # By prioridad
        prioridad_rows = db.execute(
            select(Tramite.prioridad, func.count()).group_by(Tramite.prioridad)
        ).all()
        por_prioridad = {row[0]: row[1] for row in prioridad_rows}

        total = sum(por_estado.values())

        return {
            "total": total,
            "por_estado": por_estado,
            "por_tipo": por_tipo,
            "por_prioridad": por_prioridad,
        }
