"""
Finance Endpoints.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from typing import Optional

from app.core.file_validation import get_image_type_from_magic

from app.services.finance_service import get_finance_service
from app.services.pdf_service import get_pdf_service
from app.auth import User, require_admin_or_operator, require_authenticated
from app.api.v1.schemas import GastoCreate, GastoUpdate, IngresoCreate, IngresoUpdate

router = APIRouter()

MAX_COMPROBANTE_SIZE_MB = 10
MAX_COMPROBANTE_SIZE_BYTES = MAX_COMPROBANTE_SIZE_MB * 1024 * 1024
ALLOWED_COMPROBANTE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}
EXTENSION_MAP = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}


@router.get("/gastos")
async def list_gastos(
    categoria: Optional[str] = Query(None),
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_gastos(categoria)


@router.post("/gastos")
async def add_gasto(
    data: GastoCreate,
    user: User = Depends(require_admin_or_operator),
):
    service = get_finance_service()
    return service.create_gasto(data.model_dump(exclude_unset=True))


@router.patch("/gastos/{gasto_id}")
async def update_gasto(
    gasto_id: str,
    data: GastoUpdate,
    user: User = Depends(require_admin_or_operator),
):
    service = get_finance_service()
    return service.update_gasto(gasto_id, data.model_dump(exclude_unset=True))


@router.get("/categorias")
async def list_categorias(
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_categorias()


@router.get("/ingresos")
async def list_ingresos(
    fuente: Optional[str] = Query(None),
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_ingresos(fuente)


@router.post("/ingresos")
async def add_ingreso(
    data: IngresoCreate,
    user: User = Depends(require_admin_or_operator),
):
    service = get_finance_service()
    return service.create_ingreso(data.model_dump(exclude_unset=True))


@router.patch("/ingresos/{ingreso_id}")
async def update_ingreso(
    ingreso_id: str,
    data: IngresoUpdate,
    user: User = Depends(require_admin_or_operator),
):
    service = get_finance_service()
    return service.update_ingreso(ingreso_id, data.model_dump(exclude_unset=True))


@router.get("/fuentes")
async def list_fuentes(
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_fuentes_ingreso()


@router.get("/presupuestos")
async def list_presupuestos(
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_presupuestos()


@router.get("/presupuestos/ejecucion/{anio}")
async def get_budget_execution_by_category(
    anio: int,
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_budget_execution_by_category(anio)


@router.get("/balance-summary/{anio}")
async def get_summary(
    anio: int,
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_balance_summary(anio)


@router.get("/export-presupuesto/{anio}")
async def export_presupuesto_pdf(
    anio: int,
    user: User = Depends(require_authenticated),
):
    """Generates a PDF for the general assembly."""
    finance = get_finance_service()
    get_pdf_service()

    summary = finance.get_balance_summary(anio)
    gastos = finance.get_gastos()  # Filter by year in real case

    # Mock structure for PDF generation
    report_data = {"anio": anio, "summary": summary, "gastos_detalle": gastos}

    # We'll need to implement create_presupuesto_pdf in pdf_service later
    # For now, using a placeholder logic
    return {
        "message": "PDF Generation logic pending in pdf_service",
        "data": report_data,
    }


@router.post("/comprobantes/upload")
async def upload_comprobante(
    tipo: str = Form(default="gasto"),
    file: UploadFile = File(...),
    user: User = Depends(require_admin_or_operator),
):
    normalized_type = tipo.strip().lower()
    if normalized_type not in {"gasto", "ingreso"}:
        raise HTTPException(status_code=400, detail="tipo debe ser 'gasto' o 'ingreso'")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")
    if len(content) > MAX_COMPROBANTE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo muy grande. Maximo permitido: {MAX_COMPROBANTE_SIZE_MB}MB",
        )

    detected_type = get_image_type_from_magic(content)
    if not detected_type and content[:4] == b"%PDF":
        detected_type = "application/pdf"

    if not detected_type or detected_type not in ALLOWED_COMPROBANTE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Tipo de archivo no permitido. Use imagen JPG/PNG/WebP o PDF",
        )

    declared = (file.content_type or "").lower().replace("image/jpg", "image/jpeg")
    if declared and declared != detected_type:
        raise HTTPException(
            status_code=400,
            detail="El tipo de archivo declarado no coincide con el contenido",
        )

    extension = EXTENSION_MAP[detected_type]
    service = get_finance_service()
    result = service.upload_finance_comprobante(
        content=content,
        content_type=detected_type,
        record_type=normalized_type,
        extension=extension,
    )

    return result
