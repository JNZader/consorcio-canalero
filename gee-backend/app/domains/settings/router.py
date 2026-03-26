"""FastAPI router for the settings domain."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.settings.schemas import (
    BrandingResponse,
    ImagenComparacionParams,
    ImagenMapaParams,
    ImagenMapaResponse,
    SettingResponse,
    SettingsByCategoryResponse,
    SettingUpdate,
)
from app.domains.settings.service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])
public_settings_router = APIRouter(prefix="/public/settings", tags=["public"])


def get_service() -> SettingsService:
    """Dependency that provides the service instance."""
    return SettingsService()


# Lazy import to avoid circular deps at module level.
def _require_operator():
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _require_admin():
    from app.auth import require_admin

    return require_admin


# ──────────────────────────────────────────────
# AUTHENTICATED ENDPOINTS (operator+)
# ──────────────────────────────────────────────


@router.get("", response_model=list[SettingResponse])
def get_all_settings(
    db: Session = Depends(get_db),
    service: SettingsService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """List all system settings (require operator)."""
    return service.get_all_settings(db)


# NOTE: /key/* routes MUST be registered before /{categoria} to avoid
# FastAPI matching "key" as a categoria path parameter.


@router.get("/key/{clave:path}", response_model=SettingResponse)
def get_setting_by_key(
    clave: str,
    db: Session = Depends(get_db),
    service: SettingsService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Get a single setting by key (require operator)."""
    setting = service.get_setting_full(db, clave)
    if setting is None:
        raise HTTPException(status_code=404, detail=f"Setting '{clave}' no encontrado")
    return setting


@router.put("/key/{clave:path}", response_model=SettingResponse)
def update_setting(
    clave: str,
    payload: SettingUpdate,
    db: Session = Depends(get_db),
    service: SettingsService = Depends(get_service),
    _user=Depends(_require_admin()),
):
    """Update a setting value (require admin)."""
    updated = service.update_setting(
        db, clave, payload.valor, payload.descripcion
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Setting '{clave}' no encontrado")
    return updated


@router.get("/{categoria}", response_model=SettingsByCategoryResponse)
def get_settings_by_category(
    categoria: str,
    db: Session = Depends(get_db),
    service: SettingsService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Get settings by category (require operator)."""
    items = service.get_settings_by_category(db, categoria)
    return SettingsByCategoryResponse(categoria=categoria, settings=items)


# ──────────────────────────────────────────────
# PUBLIC BRANDING ENDPOINT (no auth)
# ──────────────────────────────────────────────


@public_settings_router.get("/branding", response_model=BrandingResponse)
def get_public_branding(
    db: Session = Depends(get_db),
    service: SettingsService = Depends(get_service),
):
    """Public branding settings for frontend theming (no auth required)."""
    return BrandingResponse(
        nombre_organizacion=service.get_setting(
            db, "general/nombre_organizacion"
        ),
        logo_url=service.get_setting(db, "branding/logo_url"),
        color_primario=service.get_setting(db, "branding/color_primario"),
        color_secundario=service.get_setting(db, "branding/color_secundario"),
    )


# ──────────────────────────────────────────────
# MAP IMAGE SELECTION (public read, operator+ write)
# ──────────────────────────────────────────────


@public_settings_router.get("/mapa/imagen", response_model=ImagenMapaResponse)
def get_public_mapa_imagen(
    db: Session = Depends(get_db),
    service: SettingsService = Depends(get_service),
):
    """Get saved map image parameters (public, no auth)."""
    principal_raw = service.get_setting(db, "mapa/imagen_principal")
    comparacion_raw = service.get_setting(db, "mapa/imagen_comparacion")

    principal = ImagenMapaParams(**principal_raw) if principal_raw else None
    comparacion = (
        ImagenComparacionParams(**comparacion_raw) if comparacion_raw else None
    )

    return ImagenMapaResponse(
        imagen_principal=principal,
        imagen_comparacion=comparacion,
    )


@router.put("/mapa/imagen-principal", response_model=ImagenMapaResponse)
def save_mapa_imagen_principal(
    payload: ImagenMapaParams,
    db: Session = Depends(get_db),
    service: SettingsService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Save the selected main image parameters (operator+)."""
    service.upsert_setting(
        db,
        key="mapa/imagen_principal",
        valor=payload.model_dump(),
        categoria="mapa",
        descripcion="Parametros de la imagen satelital seleccionada para el mapa principal",
    )

    # Return full response
    comparacion_raw = service.get_setting(db, "mapa/imagen_comparacion")
    comparacion = (
        ImagenComparacionParams(**comparacion_raw) if comparacion_raw else None
    )
    return ImagenMapaResponse(
        imagen_principal=payload,
        imagen_comparacion=comparacion,
    )


@router.put("/mapa/imagen-comparacion", response_model=ImagenMapaResponse)
def save_mapa_imagen_comparacion(
    payload: ImagenComparacionParams,
    db: Session = Depends(get_db),
    service: SettingsService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Save the comparison image parameters (operator+)."""
    service.upsert_setting(
        db,
        key="mapa/imagen_comparacion",
        valor=payload.model_dump(),
        categoria="mapa",
        descripcion="Parametros de comparacion de imagenes satelitales",
    )

    # Return full response
    principal_raw = service.get_setting(db, "mapa/imagen_principal")
    principal = ImagenMapaParams(**principal_raw) if principal_raw else None
    return ImagenMapaResponse(
        imagen_principal=principal,
        imagen_comparacion=payload,
    )
