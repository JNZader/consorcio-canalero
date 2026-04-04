"""Tests for the padron domain (models, repository, service, schemas)."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domains.padron.models import Consorcista, EstadoConsorcista
from app.domains.padron.repository import PadronRepository
from app.domains.padron.schemas import (
    ConsorcistaCreate,
    ConsorcistaUpdate,
    _normalize_cuit,
)
from app.domains.padron.service import PadronService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def repo() -> PadronRepository:
    return PadronRepository()


@pytest.fixture
def service(repo: PadronRepository) -> PadronService:
    return PadronService(repository=repo)


@pytest.fixture
def sample_create_data() -> ConsorcistaCreate:
    return ConsorcistaCreate(
        nombre="Juan",
        apellido="Perez",
        cuit="20-12345678-9",
        dni="12345678",
        domicilio="Calle Falsa 123",
        localidad="Bell Ville",
        telefono="3537123456",
        email="juan@example.com",
        parcela="A-100",
        hectareas=150.5,
        categoria="propietario",
        estado="activo",
    )


def _unique_cuit() -> str:
    """Generate a unique 11-digit CUIT for test isolation."""
    digits = str(uuid.uuid4().int)[:11].zfill(11)
    return f"{digits[:2]}-{digits[2:10]}-{digits[10:]}"


def _create_data_with_unique_cuit(**overrides) -> ConsorcistaCreate:
    """Create sample data with a guaranteed unique CUIT."""
    defaults = {
        "nombre": "Test",
        "apellido": "User",
        "cuit": _unique_cuit(),
        "estado": "activo",
    }
    defaults.update(overrides)
    return ConsorcistaCreate(**defaults)


# ──────────────────────────────────────────────
# CUIT VALIDATION TESTS
# ──────────────────────────────────────────────


class TestCuitValidation:
    """Test CUIT format validation in schemas."""

    def test_valid_cuit_formatted(self):
        data = ConsorcistaCreate(
            nombre="Ana", apellido="Garcia", cuit="20-12345678-9"
        )
        assert data.cuit == "20-12345678-9"

    def test_valid_cuit_digits_only(self):
        data = ConsorcistaCreate(
            nombre="Ana", apellido="Garcia", cuit="20123456789"
        )
        assert data.cuit == "20-12345678-9"

    def test_valid_cuit_with_spaces(self):
        data = ConsorcistaCreate(
            nombre="Ana", apellido="Garcia", cuit="  20-12345678-9  "
        )
        assert data.cuit == "20-12345678-9"

    def test_valid_cuit_with_dots(self):
        """Dots and dashes mixed — should normalize to formatted."""
        data = ConsorcistaCreate(
            nombre="Ana", apellido="Garcia", cuit="20.12345678.9"
        )
        assert data.cuit == "20-12345678-9"

    def test_invalid_cuit_too_short(self):
        with pytest.raises(ValidationError) as exc_info:
            ConsorcistaCreate(
                nombre="Ana", apellido="Garcia", cuit="1234567"
            )
        assert "11 digitos" in str(exc_info.value)

    def test_invalid_cuit_too_long(self):
        with pytest.raises(ValidationError) as exc_info:
            ConsorcistaCreate(
                nombre="Ana", apellido="Garcia", cuit="123456789012"
            )
        assert "11 digitos" in str(exc_info.value)

    def test_invalid_cuit_letters(self):
        with pytest.raises(ValidationError) as exc_info:
            ConsorcistaCreate(
                nombre="Ana", apellido="Garcia", cuit="AB-CDEFGHIJ-K"
            )
        assert "11 digitos" in str(exc_info.value)

    def test_update_cuit_validation(self):
        data = ConsorcistaUpdate(cuit="20123456789")
        assert data.cuit == "20-12345678-9"

    def test_update_cuit_none_is_valid(self):
        data = ConsorcistaUpdate(cuit=None)
        assert data.cuit is None

    def test_normalize_cuit_function(self):
        assert _normalize_cuit("20-12345678-9") == "20-12345678-9"
        assert _normalize_cuit("20123456789") == "20-12345678-9"


# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class TestConsorcistaModel:
    """Basic ORM smoke tests."""

    def test_create_consorcista(self, db: Session):
        consorcista = Consorcista(
            nombre="Maria",
            apellido="Lopez",
            cuit="27-98765432-1",
            estado=EstadoConsorcista.ACTIVO,
        )
        db.add(consorcista)
        db.flush()

        assert consorcista.id is not None
        assert consorcista.estado == EstadoConsorcista.ACTIVO
        assert consorcista.created_at is not None

    def test_default_estado_is_activo(self, db: Session):
        consorcista = Consorcista(
            nombre="Carlos",
            apellido="Gomez",
            cuit="23-11223344-5",
        )
        db.add(consorcista)
        db.flush()
        assert consorcista.estado == EstadoConsorcista.ACTIVO

    def test_optional_fields_nullable(self, db: Session):
        consorcista = Consorcista(
            nombre="Pedro",
            apellido="Martinez",
            cuit="20-55667788-0",
            estado=EstadoConsorcista.ACTIVO,
        )
        db.add(consorcista)
        db.flush()

        assert consorcista.dni is None
        assert consorcista.domicilio is None
        assert consorcista.hectareas is None
        assert consorcista.email is None

    def test_cuit_unique_constraint(self, db: Session):
        c1 = Consorcista(
            nombre="A", apellido="B", cuit="20-99887766-5",
            estado=EstadoConsorcista.ACTIVO,
        )
        c2 = Consorcista(
            nombre="C", apellido="D", cuit="20-99887766-5",
            estado=EstadoConsorcista.ACTIVO,
        )
        db.add(c1)
        db.flush()
        db.add(c2)
        with pytest.raises(Exception):
            db.flush()


# ──────────────────────────────────────────────
# REPOSITORY TESTS
# ──────────────────────────────────────────────


class TestPadronRepository:
    """Repository tests against real DB (rolled-back transactions)."""

    def test_create_and_get_by_id(self, db: Session, repo: PadronRepository):
        data = _create_data_with_unique_cuit(nombre="Juan", apellido="Perez")
        created = repo.create(db, data)
        db.flush()

        fetched = repo.get_by_id(db, created.id)
        assert fetched is not None
        assert fetched.nombre == "Juan"
        assert fetched.apellido == "Perez"

    def test_get_by_id_returns_none(self, db: Session, repo: PadronRepository):
        result = repo.get_by_id(db, uuid.uuid4())
        assert result is None

    def test_get_by_cuit(self, db: Session, repo: PadronRepository):
        data = _create_data_with_unique_cuit()
        created = repo.create(db, data)
        db.flush()

        found = repo.get_by_cuit(db, created.cuit)
        assert found is not None
        assert found.id == created.id

    def test_get_by_cuit_returns_none(self, db: Session, repo: PadronRepository):
        result = repo.get_by_cuit(db, "99-00000000-0")
        assert result is None

    def test_get_all_pagination(self, db: Session, repo: PadronRepository):
        for _ in range(5):
            repo.create(db, _create_data_with_unique_cuit())
        db.flush()

        items, total = repo.get_all(db, page=1, limit=3)
        assert total == 5
        assert len(items) == 3

        items2, total2 = repo.get_all(db, page=2, limit=3)
        assert total2 == 5
        assert len(items2) == 2

    def test_get_all_filter_by_estado(self, db: Session, repo: PadronRepository):
        repo.create(db, _create_data_with_unique_cuit(estado="activo"))
        repo.create(db, _create_data_with_unique_cuit(estado="inactivo"))
        db.flush()

        items, total = repo.get_all(db, estado_filter="activo")
        assert total >= 1
        for item in items:
            assert item.estado == EstadoConsorcista.ACTIVO

    def test_get_all_filter_by_categoria(self, db: Session, repo: PadronRepository):
        repo.create(db, _create_data_with_unique_cuit(categoria="propietario"))
        repo.create(db, _create_data_with_unique_cuit(categoria="arrendatario"))
        db.flush()

        items, total = repo.get_all(db, categoria_filter="propietario")
        assert total >= 1
        for item in items:
            assert item.categoria == "propietario"

    def test_get_all_search(self, db: Session, repo: PadronRepository):
        repo.create(db, _create_data_with_unique_cuit(
            nombre="Alfredo", apellido="Gonzalez"
        ))
        repo.create(db, _create_data_with_unique_cuit(
            nombre="Maria", apellido="Lopez"
        ))
        db.flush()

        items, total = repo.get_all(db, search="Alfredo")
        assert total >= 1
        assert any(c.nombre == "Alfredo" for c in items)

    def test_update(self, db: Session, repo: PadronRepository):
        data = _create_data_with_unique_cuit(nombre="Old")
        created = repo.create(db, data)
        db.flush()

        update_data = ConsorcistaUpdate(nombre="New")
        updated = repo.update(db, created.id, update_data)

        assert updated is not None
        assert updated.nombre == "New"

    def test_update_nonexistent_returns_none(self, db: Session, repo: PadronRepository):
        update_data = ConsorcistaUpdate(nombre="Whatever")
        result = repo.update(db, uuid.uuid4(), update_data)
        assert result is None

    def test_bulk_create(self, db: Session, repo: PadronRepository):
        items = [_create_data_with_unique_cuit() for _ in range(3)]
        created = repo.bulk_create(db, items)
        db.flush()

        assert len(created) == 3
        for c in created:
            assert c.id is not None

    def test_get_stats(self, db: Session, repo: PadronRepository):
        repo.create(db, _create_data_with_unique_cuit(
            hectareas=100.0, categoria="propietario"
        ))
        repo.create(db, _create_data_with_unique_cuit(
            hectareas=50.0, categoria="arrendatario"
        ))
        db.flush()

        stats = repo.get_stats(db)

        assert stats["total"] >= 2
        assert EstadoConsorcista.ACTIVO in stats["por_estado"]
        assert stats["total_hectareas"] >= 150.0
        assert "propietario" in stats["por_categoria"]


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────


class TestPadronService:
    """Service-layer tests."""

    def test_create_commits_and_returns(
        self, db: Session, service: PadronService
    ):
        data = _create_data_with_unique_cuit(nombre="Luis")
        consorcista = service.create(db, data)
        assert consorcista.id is not None
        assert consorcista.nombre == "Luis"

    def test_create_duplicate_cuit_raises_409(
        self, db: Session, service: PadronService
    ):
        cuit = _unique_cuit()
        service.create(db, _create_data_with_unique_cuit(cuit=cuit))

        with pytest.raises(Exception) as exc_info:
            service.create(db, _create_data_with_unique_cuit(cuit=cuit))
        assert exc_info.value.status_code == 409  # type: ignore[union-attr]
        assert "CUIT" in str(exc_info.value.detail)

    def test_get_by_id_raises_on_missing(
        self, db: Session, service: PadronService
    ):
        with pytest.raises(Exception) as exc_info:
            service.get_by_id(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_list_consorcistas(
        self, db: Session, service: PadronService
    ):
        service.create(db, _create_data_with_unique_cuit())
        items, total = service.list_consorcistas(db, page=1, limit=10)
        assert total >= 1
        assert len(items) >= 1

    def test_list_with_search(
        self, db: Session, service: PadronService
    ):
        service.create(db, _create_data_with_unique_cuit(
            nombre="Buscable", apellido="Unico"
        ))
        items, total = service.list_consorcistas(db, search="Buscable")
        assert total >= 1

    def test_update_consorcista(
        self, db: Session, service: PadronService
    ):
        created = service.create(db, _create_data_with_unique_cuit(nombre="Before"))
        updated = service.update(
            db, created.id, ConsorcistaUpdate(nombre="After")
        )
        assert updated.nombre == "After"

    def test_update_cuit_duplicate_raises_409(
        self, db: Session, service: PadronService
    ):
        cuit1 = _unique_cuit()
        cuit2 = _unique_cuit()
        service.create(db, _create_data_with_unique_cuit(cuit=cuit1))
        c2 = service.create(db, _create_data_with_unique_cuit(cuit=cuit2))

        with pytest.raises(Exception) as exc_info:
            service.update(db, c2.id, ConsorcistaUpdate(cuit=cuit1))
        assert exc_info.value.status_code == 409  # type: ignore[union-attr]

    def test_get_stats(
        self, db: Session, service: PadronService
    ):
        service.create(db, _create_data_with_unique_cuit())
        stats = service.get_stats(db)
        assert "total" in stats
        assert "por_estado" in stats
        assert "total_hectareas" in stats


# ──────────────────────────────────────────────
# IMPORT TESTS
# ──────────────────────────────────────────────


class TestCsvImport:
    """Test CSV import logic in the service."""

    def test_import_valid_csv(self, db: Session, service: PadronService):
        csv_content = (
            "nombre,apellido,cuit,localidad\n"
            "Ana,Garcia,20-11223344-5,Bell Ville\n"
            "Pedro,Lopez,27-99887766-1,Cordoba\n"
        ).encode("utf-8")

        result = service.import_csv(db, csv_content, "test.csv")

        assert result["processed"] == 2
        assert result["created"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_import_skips_missing_nombre(self, db: Session, service: PadronService):
        csv_content = (
            "nombre,apellido,cuit\n"
            ",Garcia,20-11223344-5\n"
        ).encode("utf-8")

        result = service.import_csv(db, csv_content, "test.csv")

        assert result["skipped"] == 1
        assert "obligatorios" in result["errors"][0]["error"]

    def test_import_skips_missing_cuit(self, db: Session, service: PadronService):
        csv_content = (
            "nombre,apellido,cuit\n"
            "Ana,Garcia,\n"
        ).encode("utf-8")

        result = service.import_csv(db, csv_content, "test.csv")

        assert result["skipped"] == 1
        assert "CUIT" in result["errors"][0]["error"]

    def test_import_skips_duplicate_cuit_in_file(
        self, db: Session, service: PadronService
    ):
        csv_content = (
            "nombre,apellido,cuit\n"
            "Ana,Garcia,20-33445566-7\n"
            "Pedro,Lopez,20-33445566-7\n"
        ).encode("utf-8")

        result = service.import_csv(db, csv_content, "test.csv")

        assert result["created"] == 1
        assert result["skipped"] == 1
        assert "duplicado" in result["errors"][0]["error"]

    def test_import_skips_duplicate_cuit_in_db(
        self, db: Session, service: PadronService
    ):
        cuit = _unique_cuit()
        service.create(db, _create_data_with_unique_cuit(cuit=cuit))

        csv_content = (
            f"nombre,apellido,cuit\n"
            f"Ana,Garcia,{cuit}\n"
        ).encode("utf-8")

        result = service.import_csv(db, csv_content, "test.csv")

        assert result["skipped"] == 1
        assert "ya existe" in result["errors"][0]["error"]

    def test_import_unsupported_format(self, db: Session, service: PadronService):
        with pytest.raises(ValueError, match="Formato no soportado"):
            service.import_csv(db, b"data", "test.txt")

    def test_import_normalizes_cuit(self, db: Session, service: PadronService):
        csv_content = (
            "nombre,apellido,cuit\n"
            "Ana,Garcia,20443355667\n"
        ).encode("utf-8")

        result = service.import_csv(db, csv_content, "test.csv")
        assert result["created"] == 1

        # Verify the CUIT was normalized
        found = service.repo.get_by_cuit(db, "20-44335566-7")
        assert found is not None

    def test_import_column_aliases(self, db: Session, service: PadronService):
        """Headers like 'nombres', 'cuil', 'direccion' should be recognized."""
        csv_content = (
            "nombres,apellidos,cuil,direccion\n"
            "Ana,Garcia,20-55667788-9,Calle 1\n"
        ).encode("utf-8")

        result = service.import_csv(db, csv_content, "test.csv")
        assert result["created"] == 1
