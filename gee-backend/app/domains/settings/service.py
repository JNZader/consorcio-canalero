"""Business-logic layer for settings domain."""

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.domains.settings.models import CategoriaSettings, SystemSettings
from app.domains.settings.repository import SettingsRepository
from app.domains.settings.schemas import ImagenComparacionParams, ImagenMapaParams
from app.shared.audit_log import write_audit_entry_sync
from app.shared.enum_params import require_choice

# Keys whose stored JSON is unpacked into a typed public response. Garbage
# here used to 500 the public branding and map-image reads permanently.
_TEXT_SETTING_KEYS = frozenset(
    {
        "general/nombre_organizacion",
        "branding/logo_url",
        "branding/color_primario",
        "branding/color_secundario",
    }
)


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
    # ── analisis / cruces camino x flujo (flujo-caminos Fase A) ──
    #
    # These five are SEEDS, not calibrated values, and they live here rather
    # than as task-dispatch parameters so they are changeable without a code
    # change AND so every run records the same tuning. A dispatch parameter's
    # default is still code, and two callers passing different literals would
    # make "the parameters that produced this rank list" depend on who launched
    # it. Each run copies these into ``geo_jobs.resultado`` and the read
    # response echoes them, so a rank list can never be read without them.
    {
        "clave": "analisis/cruce_acc_threshold_cells",
        "valor": 1000,
        "categoria": "analisis",
        # Borrowed from extract_drainage_network(flow_acc, 1000, ...), which
        # thresholds the BURNED accumulation. This one thresholds the NATURAL
        # accumulation, so the same number selects a different -- generally
        # sparser -- set of channels. Familiarity, NOT parity with the map's
        # drainage layer. Calibration against known culverts is pending.
        "descripcion": (
            "Celdas de acumulacion minimas para que un maximo local cuente como "
            "cauce. Semilla sin calibrar; NO equivale al umbral de la capa de drenaje"
        ),
    },
    {
        "clave": "analisis/cruce_min_separation_m",
        "valor": 90.0,
        "categoria": "analisis",
        "descripcion": (
            "Distancia minima sobre el camino entre dos cruces aceptados (3 celdas "
            "GLO-30); por debajo, una sola loma de acumulacion registra varios"
        ),
    },
    {
        "clave": "analisis/cruce_parallel_min_angle_deg",
        "valor": 22.5,
        "categoria": "analisis",
        "descripcion": (
            "Borde INFERIOR del predicado de cruce: por debajo se excluye como flujo "
            "paralelo. Es medio paso D8, no un numero redondo"
        ),
    },
    {
        "clave": "analisis/cruce_parallel_high_angle_deg",
        "valor": 45.0,
        "categoria": "analisis",
        "descripcion": (
            "Borde SUPERIOR del predicado de cruce: desde aqui la orientacion es de "
            "confianza alta; entre ambos bordes se guarda con confianza baja"
        ),
    },
    {
        "clave": "analisis/cruce_bearing_window_m",
        "valor": 60.0,
        "categoria": "analisis",
        "descripcion": (
            "Semiventana para calcular el rumbo local del camino, para que los "
            "escalones de rasterizacion no dominen la prueba de angulo"
        ),
    },
    # ── analisis / clasificador de tramos (flujo-caminos Fase B) ──
    #
    # The SAME home as the five above, decided at task 3.1: seven parameters of
    # one change living in two different mechanisms would be a defect. Both are
    # read once per run and copied into the run's result, so a candidate row can
    # never be read without the tuning that produced it.
    {
        "clave": "analisis/tramo_clasif_umbral_m",
        "valor": 1.0,
        "categoria": "analisis",
        "descripcion": (
            "Diferencia de elevacion minima (m) entre la mediana del camino y la de "
            "sus flancos para clasificarlo como terraplen o canal. Semilla sin calibrar: "
            "el error vertical del DEM de 30 m es del mismo orden que este umbral"
        ),
    },
    {
        "clave": "analisis/tramo_clasif_flanco_offset_m",
        "valor": 60.0,
        "categoria": "analisis",
        "descripcion": (
            "Distancia perpendicular (m) a cada lado del camino donde se muestrea el "
            "terreno de referencia; 60 m son dos celdas GLO-30"
        ),
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


_BRANDING_CACHE: dict[str, Any] | None = None
_BRANDING_CACHE_TIME: float = 0.0
_BRANDING_CACHE_TTL: float = 600.0  # 10 minutes
# Bumped on every drop, under the same lock that publishes a fill. A reader
# that already left to query settings must not write that snapshot back.
_BRANDING_CACHE_GENERATION: int = 0
_BRANDING_CACHE_LOCK = threading.Lock()


def _invalidate_branding_cache() -> None:
    """Drop the cached branding dict. The next read reloads it."""
    global _BRANDING_CACHE, _BRANDING_CACHE_GENERATION
    with _BRANDING_CACHE_LOCK:
        _BRANDING_CACHE = None
        _BRANDING_CACHE_GENERATION += 1


def _as_optional_str(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return None


def _require_setting_model(valor: Any, model: type[BaseModel], key: str) -> None:
    if valor is None:
        return
    try:
        model.model_validate(valor)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Setting '{key}' no tiene la forma esperada",
        ) from exc


def _reject_bad_setting_valor(key: str, valor: Any) -> None:
    """Refuse shapes that the typed public readers cannot render."""
    if key in _TEXT_SETTING_KEYS:
        if valor is not None and not isinstance(valor, str):
            raise HTTPException(status_code=422, detail=f"Setting '{key}' debe ser texto")
        return
    if key == "mapa/imagen_principal":
        _require_setting_model(valor, ImagenMapaParams, key)
    elif key == "mapa/imagen_comparacion":
        _require_setting_model(valor, ImagenComparacionParams, key)


def _same_instant(left: datetime, right: datetime) -> bool:
    return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)


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
        *,
        actor_id: uuid.UUID | None = None,
        expected_updated_at: datetime | None = None,
    ) -> Optional[SystemSettings]:
        """Update an existing setting. Returns None if key not found.

        The row is locked with ``FOR UPDATE``. When the caller echoes
        ``expected_updated_at`` from a previous read and it no longer matches,
        the write is rejected with 409 instead of silently replacing the blob.
        """
        _reject_bad_setting_valor(key, valor)
        existing = self.repo.get_by_key(db, key, for_update=True)
        if existing is None:
            return None
        if expected_updated_at is not None and not _same_instant(
            existing.updated_at, expected_updated_at
        ):
            raise HTTPException(
                status_code=409,
                detail="El setting fue modificado por otro operador",
            )
        existing.valor = valor
        if descripcion is not None:
            existing.descripcion = descripcion
        write_audit_entry_sync(
            db,
            user_id=actor_id,
            action="settings.update",
            resource=f"clave={key}",
        )
        db.flush()
        db.commit()
        db.refresh(existing)
        if key.startswith("branding/") or key.startswith("general/"):
            _invalidate_branding_cache()
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
        _reject_bad_setting_valor(key, valor)
        setting = self.repo.upsert(
            db,
            clave=key,
            valor=valor,
            categoria=categoria,
            descripcion=descripcion,
        )
        db.commit()
        db.refresh(setting)
        if key.startswith("branding/") or key.startswith("general/"):
            _invalidate_branding_cache()
        return setting

    def get_branding(self, db: Session) -> dict[str, Any]:
        """Return a copy of the public branding dict, cached in memory with a TTL."""
        global _BRANDING_CACHE, _BRANDING_CACHE_TIME
        now = time.time()
        with _BRANDING_CACHE_LOCK:
            cached = _BRANDING_CACHE
            generation = _BRANDING_CACHE_GENERATION
            if cached is not None and (now - _BRANDING_CACHE_TIME) < _BRANDING_CACHE_TTL:
                return dict(cached)

        data = {
            "nombre_organizacion": _as_optional_str(
                self.get_setting(db, "general/nombre_organizacion")
            ),
            "logo_url": _as_optional_str(self.get_setting(db, "branding/logo_url")),
            "color_primario": _as_optional_str(self.get_setting(db, "branding/color_primario")),
            "color_secundario": _as_optional_str(self.get_setting(db, "branding/color_secundario")),
        }
        with _BRANDING_CACHE_LOCK:
            if _BRANDING_CACHE_GENERATION == generation:
                _BRANDING_CACHE = dict(data)
                _BRANDING_CACHE_TIME = now
        return dict(data)

    def get_all_settings(self, db: Session) -> list[SystemSettings]:
        """Return all settings."""
        return self.repo.get_all(db)

    def get_settings_by_category(self, db: Session, categoria: str) -> list[SystemSettings]:
        """Return all settings in a category."""
        parsed = require_choice(categoria, CategoriaSettings, "categoria")
        if parsed is None:
            raise HTTPException(status_code=422, detail="categoria invalida")
        return self.repo.get_by_category(db, parsed)

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
