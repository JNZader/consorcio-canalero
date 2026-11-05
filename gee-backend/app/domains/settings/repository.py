"""Repository layer — all database access for the settings domain."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.settings.models import SystemSettings


class SettingsRepository:
    """Data-access layer for system settings."""

    def get_all(self, db: Session) -> list[SystemSettings]:
        """Return all settings ordered by category then key."""
        stmt = select(SystemSettings).order_by(
            SystemSettings.categoria.asc(), SystemSettings.clave.asc()
        )
        return list(db.execute(stmt).scalars().all())

    def get_by_key(
        self,
        db: Session,
        clave: str,
        *,
        for_update: bool = False,
    ) -> Optional[SystemSettings]:
        """Return a single setting by its unique key, or None.

        ``for_update`` takes a row lock so two admin writes of the same key
        cannot interleave the read and the replacement of the JSON blob.
        """
        stmt = select(SystemSettings).where(SystemSettings.clave == clave)
        if for_update:
            stmt = stmt.with_for_update()
        return db.execute(stmt).scalar_one_or_none()

    def get_by_category(self, db: Session, categoria: str) -> list[SystemSettings]:
        """Return all settings in a given category."""
        stmt = (
            select(SystemSettings)
            .where(SystemSettings.categoria == categoria)
            .order_by(SystemSettings.clave.asc())
        )
        return list(db.execute(stmt).scalars().all())

    def upsert(
        self,
        db: Session,
        *,
        clave: str,
        valor: Any,
        categoria: str,
        descripcion: Optional[str] = None,
    ) -> SystemSettings:
        """Insert or update a setting by key."""
        existing = self.get_by_key(db, clave, for_update=True)
        if existing is not None:
            existing.valor = valor
            if descripcion is not None:
                existing.descripcion = descripcion
            db.flush()
            return existing

        setting = SystemSettings(
            clave=clave,
            valor=valor,
            categoria=categoria,
            descripcion=descripcion,
        )
        db.add(setting)
        db.flush()
        return setting
