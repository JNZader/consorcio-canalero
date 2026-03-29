"""Business-logic layer for finanzas domain."""

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.finanzas.models import (
    CATEGORIAS_GASTO,
    CATEGORIAS_INGRESO,
    Gasto,
    Ingreso,
    Presupuesto,
)
from app.domains.finanzas.repository import FinanzasRepository
from app.domains.finanzas.schemas import (
    GastoCreate,
    GastoUpdate,
    IngresoCreate,
    IngresoUpdate,
    PresupuestoCreate,
)


class FinanzasService:
    """Orchestrates repository calls with business rules."""

    def __init__(self, repository: FinanzasRepository | None = None) -> None:
        self.repo = repository or FinanzasRepository()

    # ── GASTOS ─────────────────────────────────

    def get_gasto(self, db: Session, gasto_id: uuid.UUID) -> Gasto:
        gasto = self.repo.get_gasto(db, gasto_id)
        if gasto is None:
            raise HTTPException(status_code=404, detail="Gasto no encontrado")
        return gasto

    def list_gastos(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        categoria: Optional[str] = None,
        year: Optional[int] = None,
    ) -> tuple[list[Gasto], int]:
        return self.repo.get_gastos(
            db,
            page=page,
            limit=limit,
            categoria_filter=categoria,
            year_filter=year,
        )

    def create_gasto(
        self,
        db: Session,
        data: GastoCreate,
        usuario_id: uuid.UUID,
    ) -> Gasto:
        if data.categoria not in CATEGORIAS_GASTO:
            raise HTTPException(
                status_code=400,
                detail=f"Categoria de gasto invalida. Opciones: {', '.join(CATEGORIAS_GASTO)}",
            )
        gasto = self.repo.create_gasto(db, data, usuario_id=usuario_id)
        db.commit()
        db.refresh(gasto)
        return gasto

    def update_gasto(
        self,
        db: Session,
        gasto_id: uuid.UUID,
        data: GastoUpdate,
    ) -> Gasto:
        if data.categoria is not None and data.categoria not in CATEGORIAS_GASTO:
            raise HTTPException(
                status_code=400,
                detail=f"Categoria de gasto invalida. Opciones: {', '.join(CATEGORIAS_GASTO)}",
            )
        updated = self.repo.update_gasto(db, gasto_id, data)
        if updated is None:
            raise HTTPException(status_code=404, detail="Gasto no encontrado")
        db.commit()
        db.refresh(updated)
        return updated

    # ── INGRESOS ───────────────────────────────

    def get_ingreso(self, db: Session, ingreso_id: uuid.UUID) -> Ingreso:
        ingreso = self.repo.get_ingreso(db, ingreso_id)
        if ingreso is None:
            raise HTTPException(status_code=404, detail="Ingreso no encontrado")
        return ingreso

    def list_ingresos(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        categoria: Optional[str] = None,
        year: Optional[int] = None,
    ) -> tuple[list[Ingreso], int]:
        return self.repo.get_ingresos(
            db,
            page=page,
            limit=limit,
            categoria_filter=categoria,
            year_filter=year,
        )

    def create_ingreso(
        self,
        db: Session,
        data: IngresoCreate,
        usuario_id: uuid.UUID,
    ) -> Ingreso:
        if data.categoria not in CATEGORIAS_INGRESO:
            raise HTTPException(
                status_code=400,
                detail=f"Categoria de ingreso invalida. Opciones: {', '.join(CATEGORIAS_INGRESO)}",
            )
        ingreso = self.repo.create_ingreso(db, data, usuario_id=usuario_id)
        db.commit()
        db.refresh(ingreso)
        return ingreso

    def update_ingreso(
        self,
        db: Session,
        ingreso_id: uuid.UUID,
        data: IngresoUpdate,
    ) -> Ingreso:
        if data.categoria is not None and data.categoria not in CATEGORIAS_INGRESO:
            raise HTTPException(
                status_code=400,
                detail=f"Categoria de ingreso invalida. Opciones: {', '.join(CATEGORIAS_INGRESO)}",
            )
        updated = self.repo.update_ingreso(db, ingreso_id, data)
        if updated is None:
            raise HTTPException(status_code=404, detail="Ingreso no encontrado")
        db.commit()
        db.refresh(updated)
        return updated

    # ── PRESUPUESTO ────────────────────────────

    def list_presupuestos(
        self,
        db: Session,
        year: Optional[int] = None,
    ) -> list[Presupuesto]:
        return self.repo.get_presupuestos(db, year_filter=year)

    def create_presupuesto(
        self,
        db: Session,
        data: PresupuestoCreate,
    ) -> Presupuesto:
        presupuesto = self.repo.create_presupuesto(db, data)
        db.commit()
        db.refresh(presupuesto)
        return presupuesto

    # ── REPORTS ─────────────────────────────────

    def get_budget_execution(self, db: Session, year: int) -> list[dict]:
        return self.repo.get_budget_execution(db, year)

    def get_financial_summary(self, db: Session, year: int) -> dict:
        return self.repo.get_financial_summary(db, year)
