"""Repository layer — all database access for the denuncias domain."""

import uuid
from typing import Optional

from geoalchemy2.functions import ST_MakePoint, ST_SetSRID
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domains.denuncias.models import (
    Denuncia,
    DenunciaHistorial,
    EstadoDenuncia,
)
from app.domains.denuncias.schemas import DenunciaCreate, DenunciaUpdate


class DenunciaRepository:
    """Data-access layer for denuncias and their audit log."""

    # ── READ ──────────────────────────────────

    def get_by_id(self, db: Session, denuncia_id: uuid.UUID) -> Optional[Denuncia]:
        """Return a single denuncia with its historial, or None."""
        stmt = (
            select(Denuncia)
            .options(selectinload(Denuncia.historial))
            .where(Denuncia.id == denuncia_id)
        )
        return db.execute(stmt).scalar_one_or_none()

    def get_all(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado_filter: Optional[str] = None,
        cuenca_filter: Optional[str] = None,
    ) -> tuple[list[Denuncia], int]:
        """
        Paginated list of denuncias with optional filters.

        Returns (items, total_count).
        """
        base = select(Denuncia)

        if estado_filter:
            base = base.where(Denuncia.estado == estado_filter)
        if cuenca_filter:
            base = base.where(Denuncia.cuenca == cuenca_filter)

        # Total count (separate query for accuracy with LIMIT)
        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        # Paginated items
        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(Denuncia.created_at.desc()).offset(offset).limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    # ── WRITE ─────────────────────────────────

    def create(
        self,
        db: Session,
        data: DenunciaCreate,
        user_id: Optional[uuid.UUID] = None,
    ) -> Denuncia:
        """Insert a new denuncia with PostGIS point geometry."""
        denuncia = Denuncia(
            tipo=data.tipo,
            descripcion=data.descripcion,
            latitud=data.latitud,
            longitud=data.longitud,
            geom=ST_SetSRID(ST_MakePoint(data.longitud, data.latitud), 4326),
            cuenca=data.cuenca,
            estado=EstadoDenuncia.PENDIENTE,
            contacto_telefono=data.contacto_telefono,
            contacto_email=data.contacto_email,
            foto_url=data.foto_url,
            user_id=user_id,
        )
        db.add(denuncia)
        db.flush()
        return denuncia

    def update(
        self,
        db: Session,
        denuncia_id: uuid.UUID,
        data: DenunciaUpdate,
    ) -> Optional[Denuncia]:
        """Apply partial update to an existing denuncia."""
        denuncia = self.get_by_id(db, denuncia_id)
        if denuncia is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        # Remove comentario — it belongs to historial, not to the denuncia row
        update_data.pop("comentario", None)

        for field, value in update_data.items():
            setattr(denuncia, field, value)

        db.flush()
        return denuncia

    # ── HISTORIAL ─────────────────────────────

    def add_historial(
        self,
        db: Session,
        *,
        denuncia_id: uuid.UUID,
        estado_anterior: str,
        estado_nuevo: str,
        comentario: Optional[str],
        usuario_id: uuid.UUID,
    ) -> DenunciaHistorial:
        """Record a state transition in the audit log."""
        entry = DenunciaHistorial(
            denuncia_id=denuncia_id,
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
        """Aggregate counts by estado, tipo, and cuenca."""
        # By estado
        estado_rows = db.execute(
            select(Denuncia.estado, func.count()).group_by(Denuncia.estado)
        ).all()
        por_estado = {row[0]: row[1] for row in estado_rows}

        # By tipo
        tipo_rows = db.execute(
            select(Denuncia.tipo, func.count()).group_by(Denuncia.tipo)
        ).all()
        por_tipo = {row[0]: row[1] for row in tipo_rows}

        # By cuenca
        cuenca_rows = db.execute(
            select(Denuncia.cuenca, func.count())
            .where(Denuncia.cuenca.isnot(None))
            .group_by(Denuncia.cuenca)
        ).all()
        por_cuenca = {row[0]: row[1] for row in cuenca_rows}

        total = sum(por_estado.values())

        return {
            "total": total,
            "por_estado": por_estado,
            "por_tipo": por_tipo,
            "por_cuenca": por_cuenca,
        }
