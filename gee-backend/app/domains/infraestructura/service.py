"""Business-logic layer for infraestructura domain."""

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.infraestructura.models import Asset, MantenimientoLog
from app.domains.infraestructura.repository import InfraestructuraRepository
from app.domains.infraestructura.schemas import (
    AssetCreate,
    AssetUpdate,
    MantenimientoLogCreate,
)


class InfraestructuraService:
    """Orchestrates repository calls with business rules."""

    def __init__(self, repository: InfraestructuraRepository | None = None) -> None:
        self.repo = repository or InfraestructuraRepository()

    # ── QUERIES ───────────────────────────────

    def get_asset(self, db: Session, asset_id: uuid.UUID) -> Asset:
        asset = self.repo.get_asset(db, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset no encontrado")
        return asset

    def list_assets(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        tipo: Optional[str] = None,
        estado: Optional[str] = None,
    ) -> tuple[list[Asset], int]:
        return self.repo.get_all_assets(
            db,
            page=page,
            limit=limit,
            tipo_filter=tipo,
            estado_filter=estado,
        )

    def get_asset_history(
        self,
        db: Session,
        asset_id: uuid.UUID,
        *,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[MantenimientoLog], int]:
        # Validate asset exists
        self.get_asset(db, asset_id)
        return self.repo.get_asset_history(db, asset_id, page=page, limit=limit)

    def get_stats(self, db: Session) -> dict:
        return self.repo.get_assets_stats(db)

    # ── COMMANDS ──────────────────────────────

    def create_asset(self, db: Session, data: AssetCreate) -> Asset:
        """Create an asset and commit."""
        asset = self.repo.create_asset(db, data)
        db.commit()
        db.refresh(asset)
        return asset

    def update_asset(
        self,
        db: Session,
        asset_id: uuid.UUID,
        data: AssetUpdate,
    ) -> Asset:
        """Update an existing asset."""
        # Validate exists
        self.get_asset(db, asset_id)

        updated = self.repo.update_asset(db, asset_id, data)
        db.commit()
        db.refresh(updated)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    def add_maintenance_log(
        self,
        db: Session,
        asset_id: uuid.UUID,
        data: MantenimientoLogCreate,
        usuario_id: uuid.UUID,
    ) -> MantenimientoLog:
        """Add a maintenance log to an asset and commit."""
        # Validate asset exists
        self.get_asset(db, asset_id)

        log = self.repo.add_maintenance_log(db, asset_id, data, usuario_id)
        db.commit()
        db.refresh(log)
        return log
