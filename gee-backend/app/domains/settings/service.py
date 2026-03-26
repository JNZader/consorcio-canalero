"""Business-logic layer for settings domain."""

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.domains.settings.models import SystemSettings
from app.domains.settings.repository import SettingsRepository


# Default settings seeded on first deployment
_SEED_DEFAULTS: list[dict[str, Any]] = [
    # ── general ──
    {
        "clave": "general/nombre_organizacion",
        "valor": "Consorcio Canalero 10 de Mayo",
        "categoria": "general",
        "descripcion": "Nombre oficial de la organizacion",
    },
    {
        "clave": "general/jurisdiccion",
        "valor": "Bell Ville, Cordoba, Argentina",
        "categoria": "general",
        "descripcion": "Jurisdiccion territorial",
    },
    # ── branding ──
    {
        "clave": "branding/logo_url",
        "valor": "/static/logo.png",
        "categoria": "branding",
        "descripcion": "URL del logo principal",
    },
    {
        "clave": "branding/color_primario",
        "valor": "#1976D2",
        "categoria": "branding",
        "descripcion": "Color primario (hex)",
    },
    {
        "clave": "branding/color_secundario",
        "valor": "#424242",
        "categoria": "branding",
        "descripcion": "Color secundario (hex)",
    },
    # ── territorio ──
    {
        "clave": "territorio/aoi_bbox",
        "valor": [-64.1, -33.9, -63.7, -33.5],
        "categoria": "territorio",
        "descripcion": "Bounding box del area de interes [west, south, east, north]",
    },
    {
        "clave": "territorio/srid",
        "valor": 4326,
        "categoria": "territorio",
        "descripcion": "SRID del sistema de referencia espacial",
    },
    {
        "clave": "territorio/dem_source",
        "valor": "COPERNICUS/DEM/GLO30",
        "categoria": "territorio",
        "descripcion": "Fuente del modelo digital de elevacion en GEE",
    },
    # ── analisis ──
    {
        "clave": "analisis/flow_acc_threshold",
        "valor": 1000,
        "categoria": "analisis",
        "descripcion": "Umbral de acumulacion de flujo para red de drenaje",
    },
    {
        "clave": "analisis/twi_riesgo_medio",
        "valor": 8.0,
        "categoria": "analisis",
        "descripcion": "Umbral TWI para riesgo medio de anegamiento",
    },
    {
        "clave": "analisis/twi_riesgo_alto",
        "valor": 12.0,
        "categoria": "analisis",
        "descripcion": "Umbral TWI para riesgo alto de anegamiento",
    },
    # ── contacto ──
    {
        "clave": "contacto/telefono",
        "valor": "+54 353 4000000",
        "categoria": "contacto",
        "descripcion": "Telefono de contacto",
    },
    {
        "clave": "contacto/email",
        "valor": "contacto@consorcio10demayo.gob.ar",
        "categoria": "contacto",
        "descripcion": "Email de contacto",
    },
    # ── mapa ──
    {
        "clave": "mapa/imagen_principal",
        "valor": None,
        "categoria": "mapa",
        "descripcion": "Parametros de la imagen satelital seleccionada para el mapa principal",
    },
    {
        "clave": "mapa/imagen_comparacion",
        "valor": None,
        "categoria": "mapa",
        "descripcion": "Parametros de comparacion de imagenes satelitales",
    },
]


class SettingsService:
    """Orchestrates repository calls with business rules."""

    def __init__(self, repository: SettingsRepository | None = None) -> None:
        self.repo = repository or SettingsRepository()

    def get_setting(self, db: Session, key: str, default: Any = None) -> Any:
        """Get a single setting value by key, with optional default."""
        setting = self.repo.get_by_key(db, key)
        if setting is None:
            return default
        return setting.valor

    def get_setting_full(self, db: Session, key: str) -> Optional[SystemSettings]:
        """Get the full setting object by key."""
        return self.repo.get_by_key(db, key)

    def update_setting(
        self,
        db: Session,
        key: str,
        valor: Any,
        descripcion: Optional[str] = None,
    ) -> Optional[SystemSettings]:
        """Update an existing setting. Returns None if key not found."""
        existing = self.repo.get_by_key(db, key)
        if existing is None:
            return None
        existing.valor = valor
        if descripcion is not None:
            existing.descripcion = descripcion
        db.flush()
        db.commit()
        db.refresh(existing)
        return existing

    def upsert_setting(
        self,
        db: Session,
        key: str,
        valor: Any,
        categoria: str,
        descripcion: Optional[str] = None,
    ) -> SystemSettings:
        """Insert or update a setting by key."""
        setting = self.repo.upsert(
            db,
            clave=key,
            valor=valor,
            categoria=categoria,
            descripcion=descripcion,
        )
        db.commit()
        db.refresh(setting)
        return setting

    def get_all_settings(self, db: Session) -> list[SystemSettings]:
        """Return all settings."""
        return self.repo.get_all(db)

    def get_settings_by_category(
        self, db: Session, categoria: str
    ) -> list[SystemSettings]:
        """Return all settings in a category."""
        return self.repo.get_by_category(db, categoria)

    @classmethod
    def seed_defaults(cls, db: Session) -> int:
        """
        Insert default settings if they don't already exist.

        Returns the number of settings created.
        """
        repo = SettingsRepository()
        created = 0
        for item in _SEED_DEFAULTS:
            existing = repo.get_by_key(db, item["clave"])
            if existing is None:
                repo.upsert(
                    db,
                    clave=item["clave"],
                    valor=item["valor"],
                    categoria=item["categoria"],
                    descripcion=item.get("descripcion"),
                )
                created += 1
        db.commit()
        return created
