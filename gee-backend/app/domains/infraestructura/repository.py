"""Repository layer — all database access for the infraestructura domain."""

import uuid
from typing import Optional

from geoalchemy2.functions import ST_MakePoint, ST_SetSRID
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domains.infraestructura.models import Asset, MantenimientoLog
from app.domains.infraestructura.schemas import (
    AssetCreate,
    AssetUpdate,
    MantenimientoLogCreate,
)


class InfraestructuraRepository:
    """Data-access layer for assets and their maintenance logs."""

    # ── READ ──────────────────────────────────

    def get_asset(self, db: Session, asset_id: uuid.UUID) -> Optional[Asset]:
        """Return a single asset with its maintenance logs, or None."""
        stmt = (
            select(Asset)
            .options(selectinload(Asset.mantenimientos))
            .where(Asset.id == asset_id)
        )
        return db.execute(stmt).scalar_one_or_none()

    def get_all_assets(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        tipo_filter: Optional[str] = None,
        estado_filter: Optional[str] = None,
    ) -> tuple[list[Asset], int]:
        """
        Paginated list of assets with optional filters.

        Returns (items, total_count).
        """
        base = select(Asset)

        if tipo_filter:
            base = base.where(Asset.tipo == tipo_filter)
        if estado_filter:
            base = base.where(Asset.estado_actual == estado_filter)

        # Total count (separate query for accuracy with LIMIT)
        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        # Paginated items
        offset = (page - 1) * limit
        items_stmt = base.order_by(Asset.created_at.desc()).offset(offset).limit(limit)
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    # ── WRITE ─────────────────────────────────

    def create_asset(self, db: Session, data: AssetCreate) -> Asset:
        """Insert a new asset with PostGIS point geometry."""
        asset = Asset(
            nombre=data.nombre,
            tipo=data.tipo,
            descripcion=data.descripcion,
            estado_actual=data.estado_actual,
            latitud=data.latitud,
            longitud=data.longitud,
            geom=ST_SetSRID(ST_MakePoint(data.longitud, data.latitud), 4326),
            longitud_km=data.longitud_km,
            material=data.material,
            anio_construccion=data.anio_construccion,
            responsable=data.responsable,
        )
        db.add(asset)
        db.flush()
        return asset

    def update_asset(
        self,
        db: Session,
        asset_id: uuid.UUID,
        data: AssetUpdate,
    ) -> Optional[Asset]:
        """Apply partial update to an existing asset."""
        asset = self.get_asset(db, asset_id)
        if asset is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(asset, field, value)

        db.flush()
        return asset

    # ── MAINTENANCE HISTORY ───────────────────

    def get_asset_history(
        self,
        db: Session,
        asset_id: uuid.UUID,
        *,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[MantenimientoLog], int]:
        """
        Paginated maintenance history for a specific asset.

        Returns (items, total_count).
        """
        base = select(MantenimientoLog).where(MantenimientoLog.asset_id == asset_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        offset = (page - 1) * limit
        items_stmt = (
            base.order_by(MantenimientoLog.fecha_trabajo.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    def add_maintenance_log(
        self,
        db: Session,
        asset_id: uuid.UUID,
        data: MantenimientoLogCreate,
        usuario_id: uuid.UUID,
    ) -> MantenimientoLog:
        """Record a new maintenance activity for an asset."""
        log = MantenimientoLog(
            asset_id=asset_id,
            tipo_trabajo=data.tipo_trabajo,
            descripcion=data.descripcion,
            costo=data.costo,
            fecha_trabajo=data.fecha_trabajo,
            realizado_por=data.realizado_por,
            usuario_id=usuario_id,
        )
        db.add(log)
        db.flush()
        return log

    # ── STATS ─────────────────────────────────

    def get_assets_stats(self, db: Session) -> dict:
        """Aggregate counts by tipo and estado."""
        # By tipo
        tipo_rows = db.execute(
            select(Asset.tipo, func.count()).group_by(Asset.tipo)
        ).all()
        por_tipo = {row[0]: row[1] for row in tipo_rows}

        # By estado
        estado_rows = db.execute(
            select(Asset.estado_actual, func.count()).group_by(Asset.estado_actual)
        ).all()
        por_estado = {row[0]: row[1] for row in estado_rows}

        total = sum(por_tipo.values())

        return {
            "total": total,
            "por_tipo": por_tipo,
            "por_estado": por_estado,
        }
