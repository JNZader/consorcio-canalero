"""Repository layer — all database access for the finanzas domain."""

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.domains.finanzas.models import Gasto, Ingreso, Presupuesto
from app.domains.finanzas.schemas import (
    GastoCreate,
    GastoUpdate,
    IngresoCreate,
    IngresoUpdate,
    PresupuestoCreate,
    PresupuestoUpdate,
)


class FinanzasRepository:
    """Data-access layer for gastos, ingresos and presupuestos."""

    # ── GASTOS ─────────────────────────────────

    def get_gasto(self, db: Session, gasto_id: uuid.UUID) -> Optional[Gasto]:
        stmt = select(Gasto).where(Gasto.id == gasto_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_gastos(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        categoria_filter: Optional[str] = None,
        year_filter: Optional[int] = None,
    ) -> tuple[list[Gasto], int]:
        """Paginated list of gastos with optional filters."""
        base = select(Gasto)

        if categoria_filter:
            base = base.where(Gasto.categoria == categoria_filter)
        if year_filter:
            base = base.where(extract("year", Gasto.fecha) == year_filter)

        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        offset = (page - 1) * limit
        items_stmt = base.order_by(Gasto.fecha.desc()).offset(offset).limit(limit)
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    def create_gasto(
        self,
        db: Session,
        data: GastoCreate,
        usuario_id: uuid.UUID,
    ) -> Gasto:
        gasto = Gasto(
            descripcion=data.descripcion,
            monto=data.monto,
            categoria=data.categoria,
            fecha=data.fecha,
            comprobante_url=data.comprobante_url,
            proveedor=data.proveedor,
            usuario_id=usuario_id,
        )
        db.add(gasto)
        db.flush()
        return gasto

    def update_gasto(
        self,
        db: Session,
        gasto_id: uuid.UUID,
        data: GastoUpdate,
    ) -> Optional[Gasto]:
        gasto = self.get_gasto(db, gasto_id)
        if gasto is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(gasto, field, value)

        db.flush()
        return gasto

    # ── INGRESOS ───────────────────────────────

    def get_ingreso(self, db: Session, ingreso_id: uuid.UUID) -> Optional[Ingreso]:
        stmt = select(Ingreso).where(Ingreso.id == ingreso_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_ingresos(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        categoria_filter: Optional[str] = None,
        year_filter: Optional[int] = None,
    ) -> tuple[list[Ingreso], int]:
        """Paginated list of ingresos with optional filters."""
        base = select(Ingreso)

        if categoria_filter:
            base = base.where(Ingreso.categoria == categoria_filter)
        if year_filter:
            base = base.where(extract("year", Ingreso.fecha) == year_filter)

        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = db.execute(count_stmt).scalar_one()

        offset = (page - 1) * limit
        items_stmt = base.order_by(Ingreso.fecha.desc()).offset(offset).limit(limit)
        items = list(db.execute(items_stmt).scalars().all())

        return items, total

    def create_ingreso(
        self,
        db: Session,
        data: IngresoCreate,
        usuario_id: uuid.UUID,
    ) -> Ingreso:
        ingreso = Ingreso(
            descripcion=data.descripcion,
            monto=data.monto,
            categoria=data.categoria,
            fecha=data.fecha,
            consorcista_id=data.consorcista_id,
            comprobante_url=data.comprobante_url,
            usuario_id=usuario_id,
        )
        db.add(ingreso)
        db.flush()
        return ingreso

    def update_ingreso(
        self,
        db: Session,
        ingreso_id: uuid.UUID,
        data: IngresoUpdate,
    ) -> Optional[Ingreso]:
        ingreso = self.get_ingreso(db, ingreso_id)
        if ingreso is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(ingreso, field, value)

        db.flush()
        return ingreso

    # ── PRESUPUESTO ────────────────────────────

    def get_presupuestos(
        self,
        db: Session,
        *,
        year_filter: Optional[int] = None,
    ) -> list[Presupuesto]:
        base = select(Presupuesto)
        if year_filter:
            base = base.where(Presupuesto.anio == year_filter)
        stmt = base.order_by(Presupuesto.anio.desc(), Presupuesto.rubro)
        return list(db.execute(stmt).scalars().all())

    def create_presupuesto(
        self,
        db: Session,
        data: PresupuestoCreate,
    ) -> Presupuesto:
        presupuesto = Presupuesto(
            anio=data.anio,
            rubro=data.rubro,
            monto_proyectado=data.monto_proyectado,
        )
        db.add(presupuesto)
        db.flush()
        return presupuesto

    def update_presupuesto(
        self,
        db: Session,
        presupuesto_id: uuid.UUID,
        data: PresupuestoUpdate,
    ) -> Optional[Presupuesto]:
        stmt = select(Presupuesto).where(Presupuesto.id == presupuesto_id)
        presupuesto = db.execute(stmt).scalar_one_or_none()
        if presupuesto is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(presupuesto, field, value)

        db.flush()
        return presupuesto

    # ── REPORTS ─────────────────────────────────

    def get_budget_execution(
        self,
        db: Session,
        year: int,
    ) -> list[dict]:
        """
        Compare presupuesto projections vs actual gastos by rubro.

        Returns list of {rubro, proyectado, real}.
        """
        # Projected amounts by rubro
        proj_stmt = (
            select(
                Presupuesto.rubro,
                func.sum(Presupuesto.monto_proyectado).label("proyectado"),
            )
            .where(Presupuesto.anio == year)
            .group_by(Presupuesto.rubro)
        )
        projected = {
            row.rubro: Decimal(str(row.proyectado))
            for row in db.execute(proj_stmt).all()
        }

        # Actual expenses by categoria (maps to rubro)
        actual_stmt = (
            select(
                Gasto.categoria,
                func.sum(Gasto.monto).label("real"),
            )
            .where(extract("year", Gasto.fecha) == year)
            .group_by(Gasto.categoria)
        )
        actual = {
            row.categoria: Decimal(str(row.real))
            for row in db.execute(actual_stmt).all()
        }

        rubros = sorted(set(projected) | set(actual))
        return [
            {
                "rubro": rubro,
                "proyectado": projected.get(rubro, Decimal("0")),
                "real": actual.get(rubro, Decimal("0")),
            }
            for rubro in rubros
        ]

    def get_financial_summary(
        self,
        db: Session,
        year: int,
    ) -> dict:
        """
        Total ingresos, total gastos, and balance for a given year.
        """
        ingresos_stmt = select(func.coalesce(func.sum(Ingreso.monto), 0)).where(
            extract("year", Ingreso.fecha) == year
        )
        total_ingresos = Decimal(str(db.execute(ingresos_stmt).scalar_one()))

        gastos_stmt = select(func.coalesce(func.sum(Gasto.monto), 0)).where(
            extract("year", Gasto.fecha) == year
        )
        total_gastos = Decimal(str(db.execute(gastos_stmt).scalar_one()))

        return {
            "anio": year,
            "total_ingresos": total_ingresos,
            "total_gastos": total_gastos,
            "balance": total_ingresos - total_gastos,
        }
