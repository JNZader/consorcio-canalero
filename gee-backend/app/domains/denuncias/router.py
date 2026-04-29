"""FastAPI router for the denuncias domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.denuncias.models import Denuncia
from app.domains.denuncias.schemas import (
    DenunciaCreate,
    DenunciaCreateResponse,
    DenunciaListResponse,
    DenunciaResponse,
    DenunciaUpdate,
)
from app.domains.denuncias.service import DenunciaService
from app.shared.storage import (
    ALLOWED_PHOTO_MIME_TYPES,
    MAX_PHOTO_BYTES,
    PhotoStorage,
    get_photo_storage,
    make_denuncia_photo_key,
)

router = APIRouter(prefix="/denuncias", tags=["denuncias"])


class DenunciaPhotoResponse(BaseModel):
    """Response from POST /denuncias/{id}/photo."""

    photo_url: str


def get_service() -> DenunciaService:
    """Dependency that provides the service instance."""
    return DenunciaService()


# ──────────────────────────────────────────────
# AUTH DEPENDENCIES
# ──────────────────────────────────────────────
#
# Lazy imports to dodge a module-load circular dep — the auth module
# imports from config, and config sometimes isn't fully resolved when
# this file is first imported (notably in pytest). Calling them as
# `Depends(_require_x())` defers the resolution until request time.


def _require_operator():
    """Operator+ dependency. Resolved at request time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _require_user():
    """Any authenticated user (citizen / operador / admin)."""
    from app.auth import require_authenticated

    return require_authenticated


# ──────────────────────────────────────────────
# AUTHENTICATED CITIZEN ENDPOINTS
# ──────────────────────────────────────────────


@router.post("", response_model=DenunciaCreateResponse, status_code=201)
def create_denuncia(
    payload: DenunciaCreate,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    user=Depends(_require_user()),
):
    """
    Crear una denuncia (requiere ciudadano autenticado).

    Anti-spam: el endpoint deja de aceptar denuncias anónimas. El
    `user_id` y el `contacto_email` se autollenan desde el JWT del
    usuario logueado — el payload `DenunciaCreate` contiene SÓLO los
    campos que el ciudadano controla en el form (tipo, descripción,
    coords, cuenca, foto_url opcional). Cualquier `contacto_*`
    enviado por el cliente se ignora deliberadamente; el server confía
    en el token, no en el body.
    """
    payload_data = payload.model_copy(
        update={
            "contacto_email": user.email,
        }
    )
    denuncia = service.create(db, payload_data, user_id=uuid.UUID(str(user.id)))
    return DenunciaCreateResponse(
        id=denuncia.id,
        message="Denuncia creada exitosamente. Gracias por colaborar.",
        estado=denuncia.estado,
    )


@router.post(
    "/{denuncia_id}/photo",
    response_model=DenunciaPhotoResponse,
    status_code=201,
)
async def upload_denuncia_photo(
    denuncia_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: PhotoStorage = Depends(get_photo_storage),
    user=Depends(_require_user()),
):
    """
    Attach (or replace) the photo of a denuncia owned by the current user.

    Requires the denuncia to belong to the caller (`user_id` match) — an
    operator cannot upload a photo on behalf of a citizen, and a citizen
    cannot upload to someone else's denuncia. The previous version of
    this endpoint lived under `/public/denuncias/{id}/photo` with no
    auth, treating the UUID as the capability; that worked while
    denuncias were anonymous, but the anti-spam rule (must be logged in
    to create) made the auth-less form pointless.

    Validation:
    - Content-Type must be image/jpeg | image/png | image/webp.
    - Body size enforced incrementally inside `storage.save()` (10 MB cap).
    - Denuncia must exist (404) AND belong to the user (403 otherwise —
      we do NOT collapse to 404 here because the citizen has just been
      told the denuncia exists in the listing).

    On success the denuncia's `foto_url` is updated and the URL is
    returned.
    """
    denuncia = db.get(Denuncia, denuncia_id)
    if denuncia is None:
        raise HTTPException(status_code=404, detail="Denuncia no encontrada")
    if denuncia.user_id != uuid.UUID(str(user.id)):
        raise HTTPException(
            status_code=403,
            detail="No podés modificar una denuncia que no es tuya.",
        )

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_PHOTO_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tipo de archivo no permitido: {content_type or 'desconocido'}. "
                f"Use JPG, PNG o WebP. Tamaño máximo: {MAX_PHOTO_BYTES // (1024 * 1024)} MB."
            ),
        )

    storage_key = make_denuncia_photo_key(denuncia_id)
    await storage.delete(storage_key)
    photo_url = await storage.save(file, storage_key)

    denuncia.foto_url = photo_url
    db.commit()
    db.refresh(denuncia)

    return DenunciaPhotoResponse(photo_url=photo_url)


@router.get("/mine", response_model=dict)
def list_my_denuncias(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    user=Depends(_require_user()),
):
    """
    Lista paginada de denuncias del ciudadano logueado, con todo el
    detalle (incluida la `respuesta` que el operador escribió). Se usa
    en la sección "Mis denuncias" del `/perfil`.
    """
    items, total = service.list_by_user(
        db, user_id=uuid.UUID(str(user.id)), page=page, limit=limit
    )
    return {
        "items": [DenunciaResponse.model_validate(d) for d in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/rate-limit", response_model=dict)
def get_denuncia_rate_limit(
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    user=Depends(_require_user()),
):
    """
    Cupo restante del ciudadano para crear denuncias (5 cada 24 h
    rolling, source-of-truth = base de datos). Devuelve
    `{remaining, limit, reset_seconds}`. El form lo usa para mostrar el
    badge "Te quedan N" antes de que el usuario llene el formulario.
    """
    return service.get_rate_limit_status(db, uuid.UUID(str(user.id)))


# ──────────────────────────────────────────────
# PROTECTED (operator+)
# ──────────────────────────────────────────────


@router.get("/stats", response_model=dict)
def get_stats(
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Estadisticas agregadas de denuncias (requiere operador)."""
    return service.get_stats(db)


@router.get("", response_model=dict)
def list_denuncias(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    cuenca: Optional[str] = None,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
):
    """Listar denuncias con paginacion y filtros."""
    items, total = service.list_denuncias(
        db, page=page, limit=limit, estado=estado, cuenca=cuenca
    )
    return {
        "items": [DenunciaListResponse.model_validate(d) for d in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{denuncia_id}", response_model=DenunciaResponse)
def get_denuncia(
    denuncia_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
):
    """Obtener detalle de una denuncia con historial."""
    return service.get_by_id(db, denuncia_id)


@router.patch("/{denuncia_id}", response_model=DenunciaResponse)
def update_denuncia(
    denuncia_id: uuid.UUID,
    payload: DenunciaUpdate,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    user=Depends(_require_operator()),
):
    """Actualizar estado/respuesta de una denuncia (requiere operador)."""
    return service.update(db, denuncia_id, payload, operator_id=uuid.UUID(str(user.id)))
