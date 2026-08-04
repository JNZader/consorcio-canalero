"""Focused unit tests for the finanzas mutation target — service + pure schemas.

Companion of ``tests/test_mutation_targets.py``, written to close the TODO in
``.cosmic-ray.toml``: the three highest-risk domains were kept OUT of the mutation
gate because their only tests lived in ``tests/new/`` and needed PostGIS via
testcontainers, and the harness runs the whole test-command ONCE PER MUTANT.

The way in is not "run the PostGIS suite faster", it is noticing that
``FinanzasService`` never touches the database itself: every method delegates to
``FinanzasRepository`` and the only logic it owns is the category gate, the 404
mapping and the commit/refresh sequencing. All of that is exercisable with a
``MagicMock`` repository and a ``MagicMock`` session — no engine, no container, no
migrations.

Same rules as the companion file: pure python, fast, and branch-dense — each
conditional is hit on BOTH sides so a flipped operator fails immediately, and the
assertions pin the exact status codes and the exact messages a mutation would move.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import uuid
from unittest.mock import MagicMock

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.domains.finanzas.models import CATEGORIAS_GASTO, CATEGORIAS_INGRESO
from app.domains.finanzas.schemas import (
    GastoCreate,
    GastoUpdate,
    IngresoCreate,
    IngresoUpdate,
    PresupuestoCreate,
)
from app.domains.finanzas.service import FinanzasService


def _service() -> tuple[FinanzasService, MagicMock, MagicMock]:
    """Service wired to a fake repository and a fake session.

    The session is a mock on purpose: ``commit``/``refresh`` are part of the
    contract this layer owns (a mutation that drops either one must fail a test),
    and asserting on the mock is how we pin the sequencing without a database.
    """
    repo = MagicMock()
    return FinanzasService(repository=repo), repo, MagicMock()


def _gasto_create(categoria: str = "obras") -> GastoCreate:
    return GastoCreate(
        descripcion="Compra de caños",
        monto=Decimal("1500.00"),
        categoria=categoria,
        fecha=date(2026, 3, 1),
    )


def _ingreso_create(categoria: str = "cuotas") -> IngresoCreate:
    return IngresoCreate(
        descripcion="Cuota marzo",
        monto=Decimal("900.00"),
        categoria=categoria,
        fecha=date(2026, 3, 1),
    )


# ===========================================================================
# FinanzasService — GASTOS
# ===========================================================================


class TestGetGasto:
    def test_returns_the_row_when_the_repository_finds_it(self) -> None:
        svc, repo, db = _service()
        gasto = object()
        repo.get_gasto.return_value = gasto
        gasto_id = uuid.uuid4()

        assert svc.get_gasto(db, gasto_id) is gasto
        repo.get_gasto.assert_called_once_with(db, gasto_id)

    def test_raises_404_when_the_repository_returns_none(self) -> None:
        svc, repo, db = _service()
        repo.get_gasto.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.get_gasto(db, uuid.uuid4())

        assert exc.value.status_code == 404
        assert exc.value.detail == "Gasto no encontrado"


class TestListGastos:
    def test_defaults_are_page_1_limit_20_and_no_filters(self) -> None:
        """The pagination defaults are part of the contract: a mutated ``limit=20``
        would silently change every un-parameterised listing."""
        svc, repo, db = _service()
        repo.get_gastos.return_value = ([], 0)

        assert svc.list_gastos(db) == ([], 0)
        repo.get_gastos.assert_called_once_with(
            db, page=1, limit=20, categoria_filter=None, year_filter=None
        )

    def test_every_argument_is_forwarded_under_the_repository_kwarg_names(self) -> None:
        svc, repo, db = _service()
        repo.get_gastos.return_value = (["row"], 1)

        assert svc.list_gastos(db, page=3, limit=50, categoria="obras", year=2026) == (["row"], 1)
        repo.get_gastos.assert_called_once_with(
            db, page=3, limit=50, categoria_filter="obras", year_filter=2026
        )


class TestCreateGasto:
    def test_valid_category_creates_commits_and_refreshes(self) -> None:
        svc, repo, db = _service()
        created = object()
        repo.create_gasto.return_value = created
        usuario_id = uuid.uuid4()
        data = _gasto_create()

        assert svc.create_gasto(db, data, usuario_id) is created
        repo.create_gasto.assert_called_once_with(db, data, usuario_id=usuario_id)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(created)

    @pytest.mark.parametrize("categoria", list(CATEGORIAS_GASTO))
    def test_every_declared_category_is_accepted(self, categoria: str) -> None:
        svc, repo, db = _service()
        svc.create_gasto(db, _gasto_create(categoria), uuid.uuid4())
        repo.create_gasto.assert_called_once()

    def test_unknown_category_is_400_and_writes_nothing(self) -> None:
        svc, repo, db = _service()

        with pytest.raises(HTTPException) as exc:
            svc.create_gasto(db, _gasto_create("viaticos"), uuid.uuid4())

        assert exc.value.status_code == 400
        assert exc.value.detail.startswith("Categoria de gasto invalida.")
        # The message must enumerate the valid options — that is what makes the
        # 400 actionable for the operator.
        for categoria in CATEGORIAS_GASTO:
            assert categoria in exc.value.detail
        repo.create_gasto.assert_not_called()
        db.commit.assert_not_called()

    def test_an_ingreso_category_is_not_a_valid_gasto_category(self) -> None:
        """The two namespaces are disjoint by design; ``cuotas`` must not slip
        through a mutated membership test."""
        svc, repo, db = _service()

        with pytest.raises(HTTPException):
            svc.create_gasto(db, _gasto_create("cuotas"), uuid.uuid4())
        repo.create_gasto.assert_not_called()


class TestUpdateGasto:
    def test_valid_category_updates_commits_and_refreshes(self) -> None:
        svc, repo, db = _service()
        updated = object()
        repo.update_gasto.return_value = updated
        gasto_id = uuid.uuid4()
        data = GastoUpdate(categoria="mantenimiento")

        assert svc.update_gasto(db, gasto_id, data) is updated
        repo.update_gasto.assert_called_once_with(db, gasto_id, data)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(updated)

    def test_categoria_none_skips_the_gate_instead_of_rejecting(self) -> None:
        """A partial update that does not touch ``categoria`` must still go
        through — the ``is not None`` guard is the whole difference between a
        working PATCH and a 400 on every other field."""
        svc, repo, db = _service()
        repo.update_gasto.return_value = object()

        svc.update_gasto(db, uuid.uuid4(), GastoUpdate(descripcion="Nuevo detalle"))
        repo.update_gasto.assert_called_once()

    def test_unknown_category_is_400_and_writes_nothing(self) -> None:
        svc, repo, db = _service()

        with pytest.raises(HTTPException) as exc:
            svc.update_gasto(db, uuid.uuid4(), GastoUpdate(categoria="viaticos"))

        assert exc.value.status_code == 400
        assert exc.value.detail.startswith("Categoria de gasto invalida.")
        repo.update_gasto.assert_not_called()
        db.commit.assert_not_called()

    def test_missing_row_is_404_and_does_not_commit(self) -> None:
        svc, repo, db = _service()
        repo.update_gasto.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.update_gasto(db, uuid.uuid4(), GastoUpdate(descripcion="Nuevo detalle"))

        assert exc.value.status_code == 404
        assert exc.value.detail == "Gasto no encontrado"
        db.commit.assert_not_called()


# ===========================================================================
# FinanzasService — INGRESOS
# ===========================================================================


class TestGetIngreso:
    def test_returns_the_row_when_the_repository_finds_it(self) -> None:
        svc, repo, db = _service()
        ingreso = object()
        repo.get_ingreso.return_value = ingreso
        ingreso_id = uuid.uuid4()

        assert svc.get_ingreso(db, ingreso_id) is ingreso
        repo.get_ingreso.assert_called_once_with(db, ingreso_id)

    def test_raises_404_when_the_repository_returns_none(self) -> None:
        svc, repo, db = _service()
        repo.get_ingreso.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.get_ingreso(db, uuid.uuid4())

        assert exc.value.status_code == 404
        assert exc.value.detail == "Ingreso no encontrado"


class TestListIngresos:
    def test_defaults_are_page_1_limit_20_and_no_filters(self) -> None:
        svc, repo, db = _service()
        repo.get_ingresos.return_value = ([], 0)

        assert svc.list_ingresos(db) == ([], 0)
        repo.get_ingresos.assert_called_once_with(
            db, page=1, limit=20, categoria_filter=None, year_filter=None
        )

    def test_every_argument_is_forwarded_under_the_repository_kwarg_names(self) -> None:
        svc, repo, db = _service()
        repo.get_ingresos.return_value = (["row"], 1)

        assert svc.list_ingresos(db, page=2, limit=5, categoria="cuotas", year=2025) == (
            ["row"],
            1,
        )
        repo.get_ingresos.assert_called_once_with(
            db, page=2, limit=5, categoria_filter="cuotas", year_filter=2025
        )


class TestCreateIngreso:
    def test_valid_category_creates_commits_and_refreshes(self) -> None:
        svc, repo, db = _service()
        created = object()
        repo.create_ingreso.return_value = created
        usuario_id = uuid.uuid4()
        data = _ingreso_create()

        assert svc.create_ingreso(db, data, usuario_id) is created
        repo.create_ingreso.assert_called_once_with(db, data, usuario_id=usuario_id)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(created)

    @pytest.mark.parametrize("categoria", list(CATEGORIAS_INGRESO))
    def test_every_declared_category_is_accepted(self, categoria: str) -> None:
        svc, repo, db = _service()
        svc.create_ingreso(db, _ingreso_create(categoria), uuid.uuid4())
        repo.create_ingreso.assert_called_once()

    def test_unknown_category_is_400_and_writes_nothing(self) -> None:
        svc, repo, db = _service()

        with pytest.raises(HTTPException) as exc:
            svc.create_ingreso(db, _ingreso_create("donacion"), uuid.uuid4())

        assert exc.value.status_code == 400
        assert exc.value.detail.startswith("Categoria de ingreso invalida.")
        for categoria in CATEGORIAS_INGRESO:
            assert categoria in exc.value.detail
        repo.create_ingreso.assert_not_called()
        db.commit.assert_not_called()

    def test_a_gasto_category_is_not_a_valid_ingreso_category(self) -> None:
        svc, repo, db = _service()

        with pytest.raises(HTTPException):
            svc.create_ingreso(db, _ingreso_create("obras"), uuid.uuid4())
        repo.create_ingreso.assert_not_called()


class TestUpdateIngreso:
    def test_valid_category_updates_commits_and_refreshes(self) -> None:
        svc, repo, db = _service()
        updated = object()
        repo.update_ingreso.return_value = updated
        ingreso_id = uuid.uuid4()
        data = IngresoUpdate(categoria="subsidio")

        assert svc.update_ingreso(db, ingreso_id, data) is updated
        repo.update_ingreso.assert_called_once_with(db, ingreso_id, data)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(updated)

    def test_categoria_none_skips_the_gate_instead_of_rejecting(self) -> None:
        svc, repo, db = _service()
        repo.update_ingreso.return_value = object()

        svc.update_ingreso(db, uuid.uuid4(), IngresoUpdate(descripcion="Nuevo detalle"))
        repo.update_ingreso.assert_called_once()

    def test_unknown_category_is_400_and_writes_nothing(self) -> None:
        svc, repo, db = _service()

        with pytest.raises(HTTPException) as exc:
            svc.update_ingreso(db, uuid.uuid4(), IngresoUpdate(categoria="donacion"))

        assert exc.value.status_code == 400
        assert exc.value.detail.startswith("Categoria de ingreso invalida.")
        repo.update_ingreso.assert_not_called()
        db.commit.assert_not_called()

    def test_missing_row_is_404_and_does_not_commit(self) -> None:
        svc, repo, db = _service()
        repo.update_ingreso.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.update_ingreso(db, uuid.uuid4(), IngresoUpdate(descripcion="Nuevo detalle"))

        assert exc.value.status_code == 404
        assert exc.value.detail == "Ingreso no encontrado"
        db.commit.assert_not_called()


# ===========================================================================
# FinanzasService — PRESUPUESTO + REPORTS
# ===========================================================================


class TestPresupuestoAndReports:
    def test_list_presupuestos_forwards_the_year_as_year_filter(self) -> None:
        svc, repo, db = _service()
        repo.get_presupuestos.return_value = ["row"]

        assert svc.list_presupuestos(db, 2026) == ["row"]
        repo.get_presupuestos.assert_called_once_with(db, year_filter=2026)

    def test_list_presupuestos_defaults_to_no_year_filter(self) -> None:
        svc, repo, db = _service()
        repo.get_presupuestos.return_value = []

        assert svc.list_presupuestos(db) == []
        repo.get_presupuestos.assert_called_once_with(db, year_filter=None)

    def test_create_presupuesto_commits_and_refreshes(self) -> None:
        svc, repo, db = _service()
        created = object()
        repo.create_presupuesto.return_value = created
        data = PresupuestoCreate(anio=2026, rubro="obras", monto_proyectado=Decimal("100000.00"))

        assert svc.create_presupuesto(db, data) is created
        repo.create_presupuesto.assert_called_once_with(db, data)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(created)

    def test_budget_execution_is_a_straight_passthrough(self) -> None:
        svc, repo, db = _service()
        repo.get_budget_execution.return_value = [{"rubro": "obras"}]

        assert svc.get_budget_execution(db, 2026) == [{"rubro": "obras"}]
        repo.get_budget_execution.assert_called_once_with(db, 2026)

    def test_financial_summary_is_a_straight_passthrough(self) -> None:
        svc, repo, db = _service()
        repo.get_financial_summary.return_value = {"total": 1}

        assert svc.get_financial_summary(db, 2026) == {"total": 1}
        repo.get_financial_summary.assert_called_once_with(db, 2026)

    def test_a_service_built_without_a_repository_makes_its_own(self) -> None:
        """The default-argument branch: the DI seam must not be the only way to
        get a working service."""
        from app.domains.finanzas.repository import FinanzasRepository

        assert isinstance(FinanzasService().repo, FinanzasRepository)


# ===========================================================================
# finanzas schemas — pure validators (no DB, no app boot)
# ===========================================================================


class TestPresupuestoRubroValidator:
    """``rubro`` is constrained to ``CATEGORIAS_GASTO`` so the budget-execution
    report compares projected vs actual in the SAME namespace. Free text made the
    report silently miss matches — so normalisation and rejection both matter."""

    @pytest.mark.parametrize("rubro", list(CATEGORIAS_GASTO))
    def test_every_gasto_category_is_a_valid_rubro(self, rubro: str) -> None:
        assert PresupuestoCreate(anio=2026, rubro=rubro, monto_proyectado=Decimal("1")).rubro == (
            rubro
        )

    def test_case_and_surrounding_whitespace_are_normalised(self) -> None:
        schema = PresupuestoCreate(
            anio=2026, rubro="  OBRAS  ", monto_proyectado=Decimal("1000.00")
        )
        assert schema.rubro == "obras"

    def test_free_text_rubro_is_rejected_naming_the_options(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PresupuestoCreate(anio=2026, rubro="varios", monto_proyectado=Decimal("1"))

        message = str(exc.value)
        assert "Rubro invalido." in message
        for categoria in CATEGORIAS_GASTO:
            assert categoria in message

    @pytest.mark.parametrize("anio", [1999, 2101])
    def test_anio_outside_2000_2100_is_rejected(self, anio: int) -> None:
        with pytest.raises(ValidationError):
            PresupuestoCreate(anio=anio, rubro="obras", monto_proyectado=Decimal("1"))

    @pytest.mark.parametrize("anio", [2000, 2100])
    def test_the_anio_bounds_themselves_are_inclusive(self, anio: int) -> None:
        assert PresupuestoCreate(anio=anio, rubro="obras", monto_proyectado=Decimal("1")).anio == (
            anio
        )

    def test_a_zero_projection_is_valid_but_a_negative_one_is_not(self) -> None:
        assert PresupuestoCreate(
            anio=2026, rubro="obras", monto_proyectado=Decimal("0")
        ).monto_proyectado == Decimal("0")
        with pytest.raises(ValidationError):
            PresupuestoCreate(anio=2026, rubro="obras", monto_proyectado=Decimal("-1"))


class TestMontoAndDescripcionConstraints:
    """``monto`` is ``gt=0`` on gastos AND ingresos: a zero-amount movement is a
    data-entry error, not a record."""

    def test_a_zero_monto_gasto_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _gasto_create_with(monto=Decimal("0"))

    def test_a_negative_monto_gasto_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _gasto_create_with(monto=Decimal("-10.00"))

    def test_more_than_two_decimal_places_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _gasto_create_with(monto=Decimal("10.001"))

    def test_a_too_short_descripcion_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _gasto_create_with(descripcion="ab")

    def test_a_zero_monto_ingreso_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IngresoCreate(
                descripcion="Cuota marzo",
                monto=Decimal("0"),
                categoria="cuotas",
                fecha=date(2026, 3, 1),
            )

    def test_the_update_schemas_keep_the_same_monto_floor(self) -> None:
        with pytest.raises(ValidationError):
            GastoUpdate(monto=Decimal("0"))
        with pytest.raises(ValidationError):
            IngresoUpdate(monto=Decimal("0"))

    def test_an_empty_update_is_valid_every_field_is_optional(self) -> None:
        assert GastoUpdate().categoria is None
        assert IngresoUpdate().categoria is None


def _gasto_create_with(**overrides) -> GastoCreate:
    payload = {
        "descripcion": "Compra de caños",
        "monto": Decimal("1500.00"),
        "categoria": "obras",
        "fecha": date(2026, 3, 1),
    }
    payload.update(overrides)
    return GastoCreate(**payload)
