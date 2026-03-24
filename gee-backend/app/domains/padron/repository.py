"""Repository layer — all database access for the padron domain."""

import uuid
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.padron.models import Consorcista
from app.domains.padron.schemas import ConsorcistaCreate, ConsorcistaUpdate


class PadronRepository:
    """Data-access layer for consorcistas."""

    # ── READ ──────────────────────────────────

    def get_by_id(self, db: Session, consorcista_id: uuid.UUID) -> Optional[Consorcista]:
        """Return a single consorcista, or None."""
        stmt = select(Consorcista).where(Consorcista.id == consorcista_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_by_cuit(self, db: Session, cuit: str) -> Optional[Consorcista]:
        """Return a consorcista by CUIT, or None."""
        stmt = select(Consorcista).where(Consorcista.cuit == cuit)
        return db.execute(stmt).scalar_one_or_none()

    def get_all(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado_filter: Optional[str] = None,
        categoria_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[Consorcista], int]:
        """
        Paginated list of consorcistas with optional filters.

        Returns (items, total_count).
        """
        base = select(Consorcista)

        if estado_filter:
            base = base.where(Consorcista.estado == estado_filter)
        if categoria_filter:
            base = base.where(Consorcista.categoria == categoria_filter)
        if search:
            pattern = f"%{search}%"
            base = base.where(
                or_(
                    Consorcista.nombre.ilike(pattern),
                    Consorcista.apellido.ilike(pattern),
                    Consorcista.cuit.ilike(pattern),
                )
            )

        # Total count (separate query for accuracy with LIMIT)
        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        # Paginated items
        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(Consorcista.apellido.asc(), Consorcista.nombre.asc())
            .offset(offset)
            .limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    # ── WRITE ─────────────────────────────────

    def create(self, db: Session, data: ConsorcistaCreate) -> Consorcista:
        """Insert a new consorcista."""
        consorcista = Consorcista(
            nombre=data.nombre,
            apellido=data.apellido,
            cuit=data.cuit,
            dni=data.dni,
            domicilio=data.domicilio,
            localidad=data.localidad,
            telefono=data.telefono,
            email=data.email,
            parcela=data.parcela,
            hectareas=data.hectareas,
            categoria=data.categoria,
            estado=data.estado,
            fecha_ingreso=data.fecha_ingreso,
            notas=data.notas,
        )
        db.add(consorcista)
        db.flush()
        return consorcista

    def update(
        self,
        db: Session,
        consorcista_id: uuid.UUID,
        data: ConsorcistaUpdate,
    ) -> Optional[Consorcista]:
        """Apply partial update to an existing consorcista."""
        consorcista = self.get_by_id(db, consorcista_id)
        if consorcista is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(consorcista, field, value)

        db.flush()
        return consorcista

    def bulk_create(
        self,
        db: Session,
        items: list[ConsorcistaCreate],
    ) -> list[Consorcista]:
        """Bulk insert consorcistas. Returns list of created instances."""
        created = []
        for data in items:
            consorcista = Consorcista(
                nombre=data.nombre,
                apellido=data.apellido,
                cuit=data.cuit,
                dni=data.dni,
                domicilio=data.domicilio,
                localidad=data.localidad,
                telefono=data.telefono,
                email=data.email,
                parcela=data.parcela,
                hectareas=data.hectareas,
                categoria=data.categoria,
                estado=data.estado,
                fecha_ingreso=data.fecha_ingreso,
                notas=data.notas,
            )
            db.add(consorcista)
            created.append(consorcista)
        db.flush()
        return created

    # ── STATS ─────────────────────────────────

    def get_stats(self, db: Session) -> dict:
        """Aggregate counts by estado, by categoria, and total hectareas."""
        # By estado
        estado_rows = db.execute(
            select(Consorcista.estado, func.count())
            .group_by(Consorcista.estado)
        ).all()
        por_estado = {row[0]: row[1] for row in estado_rows}

        # By categoria
        categoria_rows = db.execute(
            select(Consorcista.categoria, func.count())
            .where(Consorcista.categoria.isnot(None))
            .group_by(Consorcista.categoria)
        ).all()
        por_categoria = {row[0]: row[1] for row in categoria_rows}

        total = sum(por_estado.values())

        # Total hectareas
        total_hectareas: float = (
            db.execute(
                select(func.coalesce(func.sum(Consorcista.hectareas), 0.0))
            ).scalar_one()
        )

        return {
            "total": total,
            "por_estado": por_estado,
            "por_categoria": por_categoria,
            "total_hectareas": float(total_hectareas),
        }
