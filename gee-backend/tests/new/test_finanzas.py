"""Tests for the finanzas domain (models, repository, service)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
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
from app.domains.finanzas.service import FinanzasService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def repo() -> FinanzasRepository:
    return FinanzasRepository()


@pytest.fixture
def service(repo: FinanzasRepository) -> FinanzasService:
    return FinanzasService(repository=repo)


@pytest.fixture
def user_with_id(db: Session) -> uuid.UUID:
    """Create a real User row and return its id."""
    from app.auth.models import User, UserRole

    user = User(
        email=f"operator-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="fakehash",
        nombre="Operator",
        apellido="Test",
        role=UserRole.OPERADOR,
    )
    db.add(user)
    db.flush()
    return user.id


@pytest.fixture
def sample_gasto_data() -> GastoCreate:
    return GastoCreate(
        descripcion="Reparacion canal zona sur",
        monto=Decimal("15000.50"),
        categoria="mantenimiento",
        fecha=date(2026, 3, 15),
        proveedor="Construcciones SRL",
    )


@pytest.fixture
def sample_ingreso_data() -> IngresoCreate:
    return IngresoCreate(
        descripcion="Cobro cuota marzo 2026",
        monto=Decimal("5000.00"),
        categoria="cuotas",
        fecha=date(2026, 3, 1),
    )


@pytest.fixture
def sample_presupuesto_data() -> PresupuestoCreate:
    return PresupuestoCreate(
        anio=2026,
        rubro="mantenimiento",
        monto_proyectado=Decimal("200000.00"),
    )


# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class TestGastoModel:
    """Basic ORM smoke tests for Gasto."""

    def test_create_gasto(self, db: Session, user_with_id: uuid.UUID):
        gasto = Gasto(
            descripcion="Test expense",
            monto=Decimal("1000.00"),
            categoria="obras",
            fecha=date(2026, 1, 15),
            usuario_id=user_with_id,
        )
        db.add(gasto)
        db.flush()

        assert gasto.id is not None
        assert gasto.categoria == "obras"
        assert gasto.created_at is not None

    def test_gasto_optional_fields(self, db: Session, user_with_id: uuid.UUID):
        gasto = Gasto(
            descripcion="Minimal gasto",
            monto=Decimal("500.00"),
            categoria="otros",
            fecha=date(2026, 2, 1),
            usuario_id=user_with_id,
        )
        db.add(gasto)
        db.flush()

        assert gasto.comprobante_url is None
        assert gasto.proveedor is None


class TestIngresoModel:
    """Basic ORM smoke tests for Ingreso."""

    def test_create_ingreso(self, db: Session, user_with_id: uuid.UUID):
        ingreso = Ingreso(
            descripcion="Test income",
            monto=Decimal("3000.00"),
            categoria="cuotas",
            fecha=date(2026, 1, 1),
            usuario_id=user_with_id,
        )
        db.add(ingreso)
        db.flush()

        assert ingreso.id is not None
        assert ingreso.categoria == "cuotas"
        assert ingreso.created_at is not None

    def test_ingreso_with_consorcista(self, db: Session, user_with_id: uuid.UUID):
        consorcista_uuid = uuid.uuid4()
        ingreso = Ingreso(
            descripcion="Cuota from consorcista",
            monto=Decimal("2500.00"),
            categoria="cuotas",
            fecha=date(2026, 3, 1),
            consorcista_id=consorcista_uuid,
            usuario_id=user_with_id,
        )
        db.add(ingreso)
        db.flush()

        assert ingreso.consorcista_id == consorcista_uuid


class TestPresupuestoModel:
    """Basic ORM smoke tests for Presupuesto."""

    def test_create_presupuesto(self, db: Session):
        presupuesto = Presupuesto(
            anio=2026,
            rubro="obras",
            monto_proyectado=Decimal("500000.00"),
        )
        db.add(presupuesto)
        db.flush()

        assert presupuesto.id is not None
        assert presupuesto.anio == 2026
        assert presupuesto.created_at is not None


# ──────────────────────────────────────────────
# REPOSITORY TESTS
# ──────────────────────────────────────────────


class TestFinanzasRepositoryGastos:
    """Repository tests for gastos."""

    def test_create_and_get_gasto(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_gasto_data: GastoCreate,
        user_with_id: uuid.UUID,
    ):
        created = repo.create_gasto(db, sample_gasto_data, usuario_id=user_with_id)
        db.flush()

        fetched = repo.get_gasto(db, created.id)
        assert fetched is not None
        assert fetched.descripcion == "Reparacion canal zona sur"
        assert fetched.categoria == "mantenimiento"

    def test_get_gasto_returns_none(self, db: Session, repo: FinanzasRepository):
        result = repo.get_gasto(db, uuid.uuid4())
        assert result is None

    def test_get_gastos_pagination(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_gasto_data: GastoCreate,
        user_with_id: uuid.UUID,
    ):
        for _ in range(5):
            repo.create_gasto(db, sample_gasto_data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_gastos(db, page=1, limit=3)
        assert total == 5
        assert len(items) == 3

        items2, total2 = repo.get_gastos(db, page=2, limit=3)
        assert total2 == 5
        assert len(items2) == 2

    def test_get_gastos_filter_by_categoria(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_gasto_data: GastoCreate,
        user_with_id: uuid.UUID,
    ):
        repo.create_gasto(db, sample_gasto_data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_gastos(db, categoria_filter="mantenimiento")
        assert total >= 1

        items_none, total_none = repo.get_gastos(db, categoria_filter="personal")
        assert total_none == 0

    def test_get_gastos_filter_by_year(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_gasto_data: GastoCreate,
        user_with_id: uuid.UUID,
    ):
        repo.create_gasto(db, sample_gasto_data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_gastos(db, year_filter=2026)
        assert total >= 1

        items_none, total_none = repo.get_gastos(db, year_filter=2020)
        assert total_none == 0

    def test_update_gasto(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_gasto_data: GastoCreate,
        user_with_id: uuid.UUID,
    ):
        created = repo.create_gasto(db, sample_gasto_data, usuario_id=user_with_id)
        db.flush()

        update_data = GastoUpdate(monto=Decimal("20000.00"))
        updated = repo.update_gasto(db, created.id, update_data)

        assert updated is not None
        assert updated.monto == Decimal("20000.00")

    def test_update_nonexistent_returns_none(
        self, db: Session, repo: FinanzasRepository
    ):
        update_data = GastoUpdate(monto=Decimal("100.00"))
        result = repo.update_gasto(db, uuid.uuid4(), update_data)
        assert result is None


class TestFinanzasRepositoryIngresos:
    """Repository tests for ingresos."""

    def test_create_and_get_ingreso(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_ingreso_data: IngresoCreate,
        user_with_id: uuid.UUID,
    ):
        created = repo.create_ingreso(db, sample_ingreso_data, usuario_id=user_with_id)
        db.flush()

        fetched = repo.get_ingreso(db, created.id)
        assert fetched is not None
        assert fetched.descripcion == "Cobro cuota marzo 2026"

    def test_get_ingreso_returns_none(self, db: Session, repo: FinanzasRepository):
        result = repo.get_ingreso(db, uuid.uuid4())
        assert result is None

    def test_get_ingresos_pagination(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_ingreso_data: IngresoCreate,
        user_with_id: uuid.UUID,
    ):
        for _ in range(5):
            repo.create_ingreso(db, sample_ingreso_data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_ingresos(db, page=1, limit=3)
        assert total == 5
        assert len(items) == 3

    def test_get_ingresos_filter_by_categoria(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_ingreso_data: IngresoCreate,
        user_with_id: uuid.UUID,
    ):
        repo.create_ingreso(db, sample_ingreso_data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_ingresos(db, categoria_filter="cuotas")
        assert total >= 1

        items_none, total_none = repo.get_ingresos(db, categoria_filter="subsidio")
        assert total_none == 0

    def test_update_ingreso(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_ingreso_data: IngresoCreate,
        user_with_id: uuid.UUID,
    ):
        created = repo.create_ingreso(db, sample_ingreso_data, usuario_id=user_with_id)
        db.flush()

        update_data = IngresoUpdate(monto=Decimal("6000.00"))
        updated = repo.update_ingreso(db, created.id, update_data)

        assert updated is not None
        assert updated.monto == Decimal("6000.00")


class TestFinanzasRepositoryPresupuesto:
    """Repository tests for presupuesto."""

    def test_create_and_list_presupuesto(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_presupuesto_data: PresupuestoCreate,
    ):
        repo.create_presupuesto(db, sample_presupuesto_data)
        db.flush()

        items = repo.get_presupuestos(db, year_filter=2026)
        assert len(items) >= 1
        assert items[0].rubro == "mantenimiento"

    def test_get_presupuestos_no_filter(
        self,
        db: Session,
        repo: FinanzasRepository,
        sample_presupuesto_data: PresupuestoCreate,
    ):
        repo.create_presupuesto(db, sample_presupuesto_data)
        db.flush()

        items = repo.get_presupuestos(db)
        assert len(items) >= 1


class TestFinanzasRepositoryReports:
    """Repository tests for budget execution and financial summary."""

    def test_budget_execution(
        self,
        db: Session,
        repo: FinanzasRepository,
        user_with_id: uuid.UUID,
    ):
        # Create presupuesto
        repo.create_presupuesto(
            db,
            PresupuestoCreate(
                anio=2026, rubro="mantenimiento", monto_proyectado=Decimal("100000.00")
            ),
        )
        # Create a gasto in the same category
        repo.create_gasto(
            db,
            GastoCreate(
                descripcion="Gasto de mantenimiento",
                monto=Decimal("30000.00"),
                categoria="mantenimiento",
                fecha=date(2026, 6, 15),
            ),
            usuario_id=user_with_id,
        )
        db.flush()

        execution = repo.get_budget_execution(db, 2026)
        assert len(execution) >= 1

        mant = next(e for e in execution if e["rubro"] == "mantenimiento")
        assert mant["proyectado"] == Decimal("100000.00")
        assert mant["real"] == Decimal("30000.00")

    def test_budget_execution_empty_year(
        self, db: Session, repo: FinanzasRepository
    ):
        execution = repo.get_budget_execution(db, 1999)
        assert execution == []

    def test_financial_summary(
        self,
        db: Session,
        repo: FinanzasRepository,
        user_with_id: uuid.UUID,
    ):
        repo.create_ingreso(
            db,
            IngresoCreate(
                descripcion="Ingreso test",
                monto=Decimal("50000.00"),
                categoria="cuotas",
                fecha=date(2026, 4, 1),
            ),
            usuario_id=user_with_id,
        )
        repo.create_gasto(
            db,
            GastoCreate(
                descripcion="Gasto test",
                monto=Decimal("20000.00"),
                categoria="obras",
                fecha=date(2026, 4, 15),
            ),
            usuario_id=user_with_id,
        )
        db.flush()

        summary = repo.get_financial_summary(db, 2026)
        assert summary["anio"] == 2026
        assert summary["total_ingresos"] >= Decimal("50000.00")
        assert summary["total_gastos"] >= Decimal("20000.00")
        assert summary["balance"] == summary["total_ingresos"] - summary["total_gastos"]

    def test_financial_summary_empty_year(
        self, db: Session, repo: FinanzasRepository
    ):
        summary = repo.get_financial_summary(db, 1999)
        assert summary["total_ingresos"] == Decimal("0")
        assert summary["total_gastos"] == Decimal("0")
        assert summary["balance"] == Decimal("0")


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────


class TestFinanzasService:
    """Service-layer tests."""

    def test_create_gasto_commits(
        self,
        db: Session,
        service: FinanzasService,
        sample_gasto_data: GastoCreate,
        user_with_id: uuid.UUID,
    ):
        gasto = service.create_gasto(db, sample_gasto_data, usuario_id=user_with_id)
        assert gasto.id is not None
        assert gasto.categoria == "mantenimiento"

    def test_create_gasto_invalid_categoria(
        self,
        db: Session,
        service: FinanzasService,
        user_with_id: uuid.UUID,
    ):
        bad_data = GastoCreate(
            descripcion="Bad category",
            monto=Decimal("1000.00"),
            categoria="nonexistent",
            fecha=date(2026, 1, 1),
        )
        with pytest.raises(Exception) as exc_info:
            service.create_gasto(db, bad_data, usuario_id=user_with_id)
        assert exc_info.value.status_code == 400
        assert "invalida" in str(exc_info.value.detail).lower()

    def test_get_gasto_raises_on_missing(
        self, db: Session, service: FinanzasService
    ):
        with pytest.raises(Exception) as exc_info:
            service.get_gasto(db, uuid.uuid4())
        assert exc_info.value.status_code == 404

    def test_create_ingreso_commits(
        self,
        db: Session,
        service: FinanzasService,
        sample_ingreso_data: IngresoCreate,
        user_with_id: uuid.UUID,
    ):
        ingreso = service.create_ingreso(
            db, sample_ingreso_data, usuario_id=user_with_id
        )
        assert ingreso.id is not None
        assert ingreso.categoria == "cuotas"

    def test_create_ingreso_invalid_categoria(
        self,
        db: Session,
        service: FinanzasService,
        user_with_id: uuid.UUID,
    ):
        bad_data = IngresoCreate(
            descripcion="Bad income",
            monto=Decimal("1000.00"),
            categoria="nonexistent",
            fecha=date(2026, 1, 1),
        )
        with pytest.raises(Exception) as exc_info:
            service.create_ingreso(db, bad_data, usuario_id=user_with_id)
        assert exc_info.value.status_code == 400
        assert "invalida" in str(exc_info.value.detail).lower()

    def test_get_ingreso_raises_on_missing(
        self, db: Session, service: FinanzasService
    ):
        with pytest.raises(Exception) as exc_info:
            service.get_ingreso(db, uuid.uuid4())
        assert exc_info.value.status_code == 404

    def test_create_presupuesto(
        self,
        db: Session,
        service: FinanzasService,
        sample_presupuesto_data: PresupuestoCreate,
    ):
        presupuesto = service.create_presupuesto(db, sample_presupuesto_data)
        assert presupuesto.id is not None
        assert presupuesto.anio == 2026

    def test_budget_execution(
        self,
        db: Session,
        service: FinanzasService,
        user_with_id: uuid.UUID,
    ):
        result = service.get_budget_execution(db, 2026)
        assert isinstance(result, list)

    def test_financial_summary(
        self,
        db: Session,
        service: FinanzasService,
    ):
        result = service.get_financial_summary(db, 2026)
        assert "anio" in result
        assert "balance" in result


# ──────────────────────────────────────────────
# CATEGORY VALIDATION TESTS
# ──────────────────────────────────────────────


class TestCategoryValidation:
    """Validate category constants and service enforcement."""

    def test_gasto_categories_defined(self):
        assert "obras" in CATEGORIAS_GASTO
        assert "mantenimiento" in CATEGORIAS_GASTO
        assert "personal" in CATEGORIAS_GASTO
        assert "administrativo" in CATEGORIAS_GASTO
        assert "otros" in CATEGORIAS_GASTO
        assert len(CATEGORIAS_GASTO) == 5

    def test_ingreso_categories_defined(self):
        assert "cuotas" in CATEGORIAS_INGRESO
        assert "subsidio" in CATEGORIAS_INGRESO
        assert "otros" in CATEGORIAS_INGRESO
        assert len(CATEGORIAS_INGRESO) == 3

    def test_update_gasto_invalid_categoria_rejected(
        self,
        db: Session,
        service: FinanzasService,
        sample_gasto_data: GastoCreate,
        user_with_id: uuid.UUID,
    ):
        gasto = service.create_gasto(db, sample_gasto_data, usuario_id=user_with_id)

        with pytest.raises(Exception) as exc_info:
            service.update_gasto(
                db, gasto.id, GastoUpdate(categoria="invalid_cat")
            )
        assert exc_info.value.status_code == 400

    def test_update_ingreso_invalid_categoria_rejected(
        self,
        db: Session,
        service: FinanzasService,
        sample_ingreso_data: IngresoCreate,
        user_with_id: uuid.UUID,
    ):
        ingreso = service.create_ingreso(
            db, sample_ingreso_data, usuario_id=user_with_id
        )

        with pytest.raises(Exception) as exc_info:
            service.update_ingreso(
                db, ingreso.id, IngresoUpdate(categoria="invalid_cat")
            )
        assert exc_info.value.status_code == 400
