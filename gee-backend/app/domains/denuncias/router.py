"""FastAPI router for the denuncias domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.denuncias.models import Denuncia
from app.domains.denuncias.schemas import (
    DenunciaCreate,
    DenunciaCreateResponse,
    DenunciaListResponse,
    DenunciaResponse,
    DenunciaStatsResponse,
    DenunciaUpdate,
)
from app.shared.quota import SubmissionStatusResponse
from app.domains.denuncias.service import DenunciaService
from app.shared.pagination import PaginatedResponse
from app.shared.storage import (
    ALLOWED_PHOTO_MIME_TYPES,
    MAX_PHOTO_BYTES,
    PhotoStorage,
    get_photo_storage,
    make_denuncia_photo_key,
    photo_key_from_url,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/denuncias", tags=["denuncias"])


class DenunciaPhotoResponse(BaseModel):
    """Response from POST /denuncias/{id}/photo."""

    photo_url: str


def get_service() -> DenunciaService:
    """Dependency that provides the service instance."""
    return DenunciaService()


def _scoped_photo_key(photo_url: str | None, denuncia_id: uuid.UUID) -> str | None:
    """Return a deletion key only when the pointer belongs to this denuncia."""
    if not photo_url:
        return None

    key = photo_key_from_url(photo_url)
    if key is None:
        return None

    base = make_denuncia_photo_key(denuncia_id)
    if key == base:
        return key

    prefix = f"{base}-"
    if not key.startswith(prefix):
        return None

    version = key.removeprefix(prefix)
    if len(version) != 32 or any(
        character not in "0123456789abcdef" for character in version.lower()
    ):
        return None
    return key


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
    coords y cuenca). Cualquier `contacto_*`
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
    # Legacy denuncias (pre-auth) may have ``user_id=None``. ``UUID(str(None))``
    # would raise ValueError → 500; explicit guard makes it a clean 403.
    if denuncia.user_id is None or denuncia.user_id != uuid.UUID(str(user.id)):
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

    previous_photo_url = denuncia.foto_url
    storage_key = make_denuncia_photo_key(denuncia_id, uuid.uuid4().hex)
    try:
        photo_url = await storage.save(file, storage_key)
    except OSError as exc:
        raise HTTPException(status_code=503, detail="No se pudo guardar la foto") from exc

    denuncia.foto_url = photo_url
    try:
        db.commit()
    except Exception as exc:
        # A disconnect can be reported after PostgreSQL made COMMIT durable.
        # Never delete the new file here: an orphan is recoverable, while a
        # durable DB pointer to a deleted file is permanent data loss.
        db.rollback()
        denuncia.foto_url = previous_photo_url
        raise HTTPException(status_code=503, detail="No se pudo confirmar la foto") from exc

    try:
        db.refresh(denuncia)
    except Exception as exc:
        # COMMIT succeeded. Preserve both files and the committed pointer;
        # refresh failure only makes the response acknowledgement ambiguous.
        raise HTTPException(
            status_code=503, detail="La foto fue guardada; reintente la consulta"
        ) from exc

    previous_key = _scoped_photo_key(previous_photo_url, denuncia_id)
    if previous_key:
        try:
            await storage.delete(previous_key)
        except Exception as exc:
            # The new pointer is already durable. Returning an error now
            # would make a successful replacement look failed and invite a
            # duplicate retry. Record the orphan for the scheduled
            # reconciler instead; never revert the committed pointer.
            logger.exception(
                "denuncia.previous_photo_cleanup_failed",
                denuncia_id=str(denuncia_id),
                previous_key=previous_key,
                error=str(exc),
            )

    return DenunciaPhotoResponse(photo_url=photo_url)


@router.delete("/{denuncia_id}/mine", status_code=204)
async def delete_my_denuncia(
    denuncia_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: PhotoStorage = Depends(get_photo_storage),
    user=Depends(_require_user()),
):
    """ARCO right to cancellation (Ley 25.326 art. 16).

    Soft-deletes the denuncia (stamps ``deleted_at``) and hard-deletes
    the associated photo from storage. The row remains for the 1-year
    audit window before the cleanup cron purges it.

    Only the owner can delete their own denuncia; operators can NOT
    delete a citizen's denuncia from here (that would defeat the
    auditability of their administrative response). Operators who
    need to remove a denuncia for moderation reasons use a separate
    admin endpoint with full justification logging (out of scope of
    this commit).
    """
    from datetime import datetime, timezone
    from sqlalchemy import select as sa_select

    stmt = sa_select(Denuncia).where(Denuncia.id == denuncia_id)
    denuncia = db.execute(stmt).scalar_one_or_none()
    if denuncia is None or denuncia.deleted_at is not None:
        # 404 either way — don't leak that a deleted row exists
        raise HTTPException(status_code=404, detail="Denuncia no encontrada")
    if denuncia.user_id is None or denuncia.user_id != uuid.UUID(str(user.id)):
        # Same 404 vs 403 reasoning as the photo GET endpoint
        raise HTTPException(status_code=404, detail="Denuncia no encontrada")

    previous_photo_url = denuncia.foto_url
    previous_deleted_at = denuncia.deleted_at
    photo_key = _scoped_photo_key(previous_photo_url, denuncia_id)

    # Make the tombstone and pointer removal durable before unlinking bytes.
    # This guarantees a failed commit never leaves a live DB pointer to a
    # missing photo. Cleanup failures are retried by the orphan reconciler.
    denuncia.foto_url = None
    denuncia.deleted_at = datetime.now(tz=timezone.utc)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        denuncia.foto_url = previous_photo_url
        denuncia.deleted_at = previous_deleted_at
        raise HTTPException(
            status_code=503,
            detail="No se pudo confirmar la cancelación; reintente más tarde",
        ) from exc

    if photo_key:
        try:
            await storage.delete(photo_key)
        except Exception as exc:
            logger.exception(
                "denuncia.cancelled_photo_cleanup_failed",
                denuncia_id=str(denuncia_id),
                photo_key=photo_key,
                error=str(exc),
            )
    return None


@router.get("/mine", response_model=PaginatedResponse[DenunciaResponse])
def list_my_denuncias(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    user=Depends(_require_user()),
) -> PaginatedResponse[DenunciaResponse]:
    """
    Lista paginada de denuncias del ciudadano logueado, con todo el
    detalle (incluida la `respuesta` que el operador escribió). Se usa
    en la sección "Mis denuncias" del `/perfil`.
    """
    items, total = service.list_by_user(db, user_id=uuid.UUID(str(user.id)), page=page, limit=limit)
    return PaginatedResponse[DenunciaResponse].create(
        items=[DenunciaResponse.model_validate(d) for d in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/rate-limit", response_model=SubmissionStatusResponse)
def get_denuncia_rate_limit(
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    user=Depends(_require_user()),
) -> SubmissionStatusResponse:
    """
    Cupo restante del ciudadano para crear denuncias (5 cada 24 h
    rolling, source-of-truth = base de datos). El form lo usa para
    mostrar el badge "Te quedan N" antes de que el usuario llene el
    formulario.
    """
    return SubmissionStatusResponse.model_validate(
        service.get_rate_limit_status(db, uuid.UUID(str(user.id)))
    )


# ──────────────────────────────────────────────
# PROTECTED (operator+)
# ──────────────────────────────────────────────


@router.get("/stats", response_model=DenunciaStatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    _user=Depends(_require_operator()),
) -> DenunciaStatsResponse:
    """Estadisticas agregadas de denuncias (requiere operador)."""
    return DenunciaStatsResponse.model_validate(service.get_stats(db))


@router.get("", response_model=PaginatedResponse[DenunciaListResponse])
def list_denuncias(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    cuenca: Optional[str] = None,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    _user=Depends(_require_operator()),
) -> PaginatedResponse[DenunciaListResponse]:
    """Listar denuncias con paginacion y filtros (requiere operador)."""
    items, total = service.list_denuncias(db, page=page, limit=limit, estado=estado, cuenca=cuenca)
    return PaginatedResponse[DenunciaListResponse].create(
        items=[DenunciaListResponse.model_validate(d) for d in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{denuncia_id}", response_model=DenunciaResponse)
def get_denuncia(
    denuncia_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Obtener detalle de una denuncia con historial (requiere operador)."""
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
