"""FastAPI router for the finanzas domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.finanzas.schemas import (
    BudgetExecutionResponse,
    FinancialSummaryResponse,
    GastoCreate,
    GastoListResponse,
    GastoResponse,
    GastoUpdate,
    IngresoCreate,
    IngresoListResponse,
    IngresoResponse,
    IngresoUpdate,
    PresupuestoCreate,
    PresupuestoResponse,
)
from app.domains.finanzas.service import FinanzasService

router = APIRouter(prefix="/finanzas", tags=["finanzas"])


def get_service() -> FinanzasService:
    """Dependency that provides the service instance."""
    return FinanzasService()


# Lazy import to avoid circular deps at module level.
def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


# ──────────────────────────────────────────────
# GASTOS
# ──────────────────────────────────────────────


@router.get("/gastos", response_model=dict)
def list_gastos(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    categoria: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
):
    """Listar gastos con paginacion y filtros."""
    items, total = service.list_gastos(
        db, page=page, limit=limit, categoria=categoria, year=year
    )
    return {
        "items": [GastoListResponse.model_validate(g) for g in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/gastos/{gasto_id}", response_model=GastoResponse)
def get_gasto(
    gasto_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
):
    """Obtener detalle de un gasto."""
    return service.get_gasto(db, gasto_id)


@router.post("/gastos", response_model=GastoResponse, status_code=201)
def create_gasto(
    payload: GastoCreate,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
    user=Depends(_require_operator()),
):
    """Crear un nuevo gasto (requiere operador)."""
    return service.create_gasto(db, payload, usuario_id=uuid.UUID(str(user.id)))


@router.patch("/gastos/{gasto_id}", response_model=GastoResponse)
def update_gasto(
    gasto_id: uuid.UUID,
    payload: GastoUpdate,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Actualizar un gasto existente (requiere operador)."""
    return service.update_gasto(db, gasto_id, payload)


# ──────────────────────────────────────────────
# INGRESOS
# ──────────────────────────────────────────────


@router.get("/ingresos", response_model=dict)
def list_ingresos(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    categoria: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
):
    """Listar ingresos con paginacion y filtros."""
    items, total = service.list_ingresos(
        db, page=page, limit=limit, categoria=categoria, year=year
    )
    return {
        "items": [IngresoListResponse.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/ingresos/{ingreso_id}", response_model=IngresoResponse)
def get_ingreso(
    ingreso_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
):
    """Obtener detalle de un ingreso."""
    return service.get_ingreso(db, ingreso_id)


@router.post("/ingresos", response_model=IngresoResponse, status_code=201)
def create_ingreso(
    payload: IngresoCreate,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
    user=Depends(_require_operator()),
):
    """Crear un nuevo ingreso (requiere operador)."""
    return service.create_ingreso(db, payload, usuario_id=uuid.UUID(str(user.id)))


@router.patch("/ingresos/{ingreso_id}", response_model=IngresoResponse)
def update_ingreso(
    ingreso_id: uuid.UUID,
    payload: IngresoUpdate,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Actualizar un ingreso existente (requiere operador)."""
    return service.update_ingreso(db, ingreso_id, payload)


# ──────────────────────────────────────────────
# PRESUPUESTO
# ──────────────────────────────────────────────


@router.get("/presupuesto", response_model=list[PresupuestoResponse])
def list_presupuestos(
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
):
    """Listar presupuestos (opcionalmente filtrar por anio)."""
    return service.list_presupuestos(db, year=year)


@router.post("/presupuesto", response_model=PresupuestoResponse, status_code=201)
def create_presupuesto(
    payload: PresupuestoCreate,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Crear una linea de presupuesto (requiere operador)."""
    return service.create_presupuesto(db, payload)


# ──────────────────────────────────────────────
# REPORTS
# ──────────────────────────────────────────────


@router.get(
    "/ejecucion/{year}",
    response_model=list[BudgetExecutionResponse],
)
def get_budget_execution(
    year: int,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
):
    """Ejecucion presupuestaria: proyectado vs real por rubro."""
    return service.get_budget_execution(db, year)


@router.get("/resumen/{year}", response_model=FinancialSummaryResponse)
def get_financial_summary(
    year: int,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
):
    """Resumen financiero anual: total ingresos, gastos y balance."""
    return service.get_financial_summary(db, year)


# ──────────────────────────────────────────────
# PDF EXPORT
# ──────────────────────────────────────────────


@router.get("/resumen/{year}/export-pdf")
def export_financial_summary_pdf(
    year: int,
    db: Session = Depends(get_db),
    service: FinanzasService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Exportar resumen financiero anual como PDF (requiere operador)."""
    from app.shared.pdf import build_finanzas_pdf, get_branding

    summary = service.get_financial_summary(db, year)
    execution = service.get_budget_execution(db, year)
    branding = get_branding(db)

    # summary may be a Pydantic model or dict
    if hasattr(summary, "model_dump"):
        summary_dict = summary.model_dump()
    elif hasattr(summary, "__dict__"):
        summary_dict = {
            "total_ingresos": getattr(summary, "total_ingresos", 0),
            "total_gastos": getattr(summary, "total_gastos", 0),
            "balance": getattr(summary, "balance", 0),
        }
    else:
        summary_dict = summary

    # execution items may be Pydantic models or dicts
    execution_list = []
    for item in execution:
        if hasattr(item, "model_dump"):
            execution_list.append(item.model_dump())
        elif isinstance(item, dict):
            execution_list.append(item)
        else:
            execution_list.append(
                {
                    "rubro": getattr(item, "rubro", ""),
                    "proyectado": getattr(item, "proyectado", 0),
                    "real": getattr(item, "real", 0),
                }
            )

    pdf_buffer = build_finanzas_pdf(summary_dict, execution_list, year, branding)

    filename = f"finanzas-resumen-{year}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
