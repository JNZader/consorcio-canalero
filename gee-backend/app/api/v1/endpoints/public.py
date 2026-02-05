"""
Public Endpoints.
Endpoints publicos que no requieren autenticacion.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional
import uuid

from app.services.supabase_service import get_supabase_service
from app.core.logging import get_logger
from app.core.file_validation import is_valid_image

logger = get_logger(__name__)

router = APIRouter()

# Constants for file validation
MAX_PHOTO_SIZE_MB = 5
MAX_PHOTO_SIZE_BYTES = MAX_PHOTO_SIZE_MB * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ===========================================
# SCHEMAS
# ===========================================


class ReportCreate(BaseModel):
    """Datos para crear una denuncia publica."""

    tipo: str = Field(
        ...,
        description="Tipo de denuncia: alcantarilla_tapada, desborde, camino_danado, otro",
    )
    descripcion: str = Field(..., min_length=10, max_length=2000)
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    cuenca: Optional[str] = None
    foto_url: Optional[str] = None


class ReportResponse(BaseModel):
    """Respuesta al crear una denuncia."""

    id: str
    message: str
    estado: str


# ===========================================
# ENDPOINTS
# ===========================================


@router.post("/reports", response_model=ReportResponse)
async def create_public_report(report: ReportCreate):
    """
    Crear una denuncia publica.

    No requiere autenticacion. Permite a ciudadanos reportar
    problemas en la red de canales y caminos rurales.

    - **tipo**: Tipo de problema (alcantarilla_tapada, desborde, camino_danado, otro)
    - **descripcion**: Descripcion detallada del problema (min 10 caracteres)
    - **latitud**: Latitud de la ubicacion (-90 a 90)
    - **longitud**: Longitud de la ubicacion (-180 a 180)
    - **cuenca**: Cuenca afectada (opcional)
    - **foto_url**: URL de foto (opcional, usar /public/upload-photo primero)
    """
    # Validate tipo
    valid_tipos = ["alcantarilla_tapada", "desborde", "camino_danado", "otro"]
    if report.tipo not in valid_tipos:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo invalido. Valores permitidos: {', '.join(valid_tipos)}",
        )

    try:
        db = get_supabase_service()

        result = db.create_report(report.model_dump())

        return ReportResponse(
            id=result["id"],
            message="Denuncia creada exitosamente. Gracias por colaborar.",
            estado="pendiente",
        )

    except Exception as e:
        logger.error(
            "Error creating public report",
            error=str(e),
            report_type=report.tipo,
            cuenca=report.cuenca,
        )
        raise HTTPException(status_code=500, detail="Error al crear la denuncia")


@router.post("/upload-photo")
async def upload_report_photo(file: UploadFile = File(...)):
    """
    Subir foto para una denuncia.

    Retorna la URL publica de la foto para usar en la creacion de la denuncia.

    Validaciones:
    - Tamano maximo: 5MB
    - Formatos: JPEG, PNG, WebP
    - Validacion de magic bytes para prevenir spoofing
    """
    # Validate declared content type (first check)
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Tipo de archivo no permitido. Usar: JPEG, PNG o WebP",
        )

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_PHOTO_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo muy grande. Maximo permitido: {MAX_PHOTO_SIZE_MB}MB",
        )

    # Validate magic bytes to prevent spoofing
    is_valid, detected_type = is_valid_image(content, ALLOWED_IMAGE_TYPES)
    if not is_valid:
        logger.warning(
            "Invalid file upload attempt",
            claimed_type=file.content_type,
            detected_type=detected_type,
            size_bytes=len(content),
        )
        raise HTTPException(
            status_code=400,
            detail="Archivo invalido. El contenido no corresponde a una imagen valida.",
        )

    # Generate safe filename based on actual type
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    file_ext = ext_map.get(detected_type, "jpg")
    safe_filename = f"{uuid.uuid4()}.{file_ext}"

    try:
        db = get_supabase_service()
        photo_url = db.upload_report_photo(safe_filename, content)

        return {"photo_url": photo_url, "filename": safe_filename}

    except Exception as e:
        logger.error(
            "Error uploading report photo",
            error=str(e),
            filename=safe_filename,
            content_type=file.content_type,
            size_bytes=len(content),
        )
        raise HTTPException(status_code=500, detail="Error al subir la foto")


@router.get("/health")
async def public_health():
    """Health check publico."""
    return {"status": "ok", "service": "Consorcio Canalero API"}
