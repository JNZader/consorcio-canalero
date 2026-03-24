"""Tests for the infraestructura domain (models, repository, service)."""

import uuid
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.domains.infraestructura.models import (
    Asset,
    EstadoAsset,
    MantenimientoLog,
)
from app.domains.infraestructura.repository import InfraestructuraRepository
from app.domains.infraestructura.schemas import (
    AssetCreate,
    AssetUpdate,
    MantenimientoLogCreate,
)
from app.domains.infraestructura.service import InfraestructuraService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def repo() -> InfraestructuraRepository:
    return InfraestructuraRepository()


@pytest.fixture
def service(repo: InfraestructuraRepository) -> InfraestructuraService:
    return InfraestructuraService(repository=repo)


@pytest.fixture
def sample_asset_data() -> AssetCreate:
    return AssetCreate(
        nombre="Canal Principal Norte",
        tipo="canal",
        descripcion="Canal principal de la zona norte, conecta cuenca Candil con ML.",
        estado_actual="bueno",
        latitud=-33.7,
        longitud=-63.9,
        longitud_km=12.5,
        material="hormigon",
        anio_construccion=1995,
        responsable="Juan Perez",
    )


@pytest.fixture
def sample_maintenance_data() -> MantenimientoLogCreate:
    return MantenimientoLogCreate(
        tipo_trabajo="Limpieza de malezas",
        descripcion="Limpieza general de malezas y sedimentos en tramo km 3-5.",
        costo=15000.50,
        fecha_trabajo=date(2026, 3, 15),
        realizado_por="Equipo Mantenimiento Norte",
    )


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


# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class TestAssetModel:
    """Basic ORM smoke tests for Asset."""

    def test_create_asset(self, db: Session):
        asset = Asset(
            nombre="Puente Viejo",
            tipo="puente",
            descripcion="Puente sobre canal principal en km 7.",
            estado_actual=EstadoAsset.BUENO,
            latitud=-33.7,
            longitud=-63.9,
        )
        db.add(asset)
        db.flush()

        assert asset.id is not None
        assert asset.estado_actual == EstadoAsset.BUENO
        assert asset.created_at is not None

    def test_default_estado_is_bueno(self, db: Session):
        asset = Asset(
            nombre="Alcantarilla km 12",
            tipo="alcantarilla",
            descripcion="Alcantarilla de hormigon bajo camino rural.",
            latitud=-33.5,
            longitud=-63.8,
        )
        db.add(asset)
        db.flush()
        assert asset.estado_actual == EstadoAsset.BUENO

    def test_mantenimiento_relationship(
        self, db: Session, user_with_id: uuid.UUID
    ):
        asset = Asset(
            nombre="Canal Secundario",
            tipo="canal",
            descripcion="Canal secundario zona sur de la cuenca.",
            estado_actual=EstadoAsset.REGULAR,
            latitud=-33.7,
            longitud=-63.9,
        )
        db.add(asset)
        db.flush()

        log = MantenimientoLog(
            asset_id=asset.id,
            tipo_trabajo="Reparacion",
            descripcion="Reparacion de tramo danado por crecida.",
            costo=25000.0,
            fecha_trabajo=date(2026, 3, 10),
            realizado_por="Cuadrilla Sur",
            usuario_id=user_with_id,
        )
        db.add(log)
        db.flush()

        db.refresh(asset)
        assert len(asset.mantenimientos) == 1
        assert asset.mantenimientos[0].tipo_trabajo == "Reparacion"

    def test_optional_fields_nullable(self, db: Session):
        asset = Asset(
            nombre="Compuerta Este",
            tipo="compuerta",
            descripcion="Compuerta reguladora de caudal zona este.",
            estado_actual=EstadoAsset.MALO,
            latitud=-33.6,
            longitud=-63.7,
        )
        db.add(asset)
        db.flush()

        assert asset.longitud_km is None
        assert asset.material is None
        assert asset.anio_construccion is None
        assert asset.responsable is None


# ──────────────────────────────────────────────
# REPOSITORY TESTS
# ──────────────────────────────────────────────


class TestInfraestructuraRepository:
    """Repository tests against real DB (rolled-back transactions)."""

    def test_create_and_get_asset(
        self, db: Session, repo: InfraestructuraRepository, sample_asset_data: AssetCreate
    ):
        created = repo.create_asset(db, sample_asset_data)
        db.flush()

        fetched = repo.get_asset(db, created.id)
        assert fetched is not None
        assert fetched.nombre == "Canal Principal Norte"
        assert fetched.tipo == "canal"
        assert fetched.latitud == pytest.approx(-33.7)
        assert fetched.longitud == pytest.approx(-63.9)
        assert fetched.longitud_km == pytest.approx(12.5)

    def test_get_asset_returns_none(self, db: Session, repo: InfraestructuraRepository):
        result = repo.get_asset(db, uuid.uuid4())
        assert result is None

    def test_get_all_assets_pagination(
        self, db: Session, repo: InfraestructuraRepository, sample_asset_data: AssetCreate
    ):
        for _ in range(5):
            repo.create_asset(db, sample_asset_data)
        db.flush()

        items, total = repo.get_all_assets(db, page=1, limit=3)
        assert total == 5
        assert len(items) == 3

        items2, total2 = repo.get_all_assets(db, page=2, limit=3)
        assert total2 == 5
        assert len(items2) == 2

    def test_get_all_assets_filter_by_tipo(
        self, db: Session, repo: InfraestructuraRepository, sample_asset_data: AssetCreate
    ):
        repo.create_asset(db, sample_asset_data)
        db.flush()

        items, total = repo.get_all_assets(db, tipo_filter="canal")
        assert total >= 1

        items_none, total_none = repo.get_all_assets(db, tipo_filter="puente")
        assert total_none == 0

    def test_get_all_assets_filter_by_estado(
        self, db: Session, repo: InfraestructuraRepository, sample_asset_data: AssetCreate
    ):
        repo.create_asset(db, sample_asset_data)
        db.flush()

        items, total = repo.get_all_assets(db, estado_filter="bueno")
        assert total >= 1

        items_none, total_none = repo.get_all_assets(db, estado_filter="critico")
        assert total_none == 0

    def test_update_asset(
        self, db: Session, repo: InfraestructuraRepository, sample_asset_data: AssetCreate
    ):
        created = repo.create_asset(db, sample_asset_data)
        db.flush()

        update_data = AssetUpdate(
            estado_actual="regular",
            responsable="Maria Lopez",
        )
        updated = repo.update_asset(db, created.id, update_data)

        assert updated is not None
        assert updated.estado_actual == "regular"
        assert updated.responsable == "Maria Lopez"
        # Unchanged fields remain
        assert updated.nombre == "Canal Principal Norte"

    def test_update_nonexistent_returns_none(
        self, db: Session, repo: InfraestructuraRepository
    ):
        update_data = AssetUpdate(estado_actual="malo")
        result = repo.update_asset(db, uuid.uuid4(), update_data)
        assert result is None

    def test_add_maintenance_log(
        self,
        db: Session,
        repo: InfraestructuraRepository,
        sample_asset_data: AssetCreate,
        sample_maintenance_data: MantenimientoLogCreate,
        user_with_id: uuid.UUID,
    ):
        asset = repo.create_asset(db, sample_asset_data)
        db.flush()

        log = repo.add_maintenance_log(
            db, asset.id, sample_maintenance_data, user_with_id
        )
        db.flush()

        assert log.id is not None
        assert log.asset_id == asset.id
        assert log.tipo_trabajo == "Limpieza de malezas"
        assert log.costo == pytest.approx(15000.50)

    def test_get_asset_history_pagination(
        self,
        db: Session,
        repo: InfraestructuraRepository,
        sample_asset_data: AssetCreate,
        sample_maintenance_data: MantenimientoLogCreate,
        user_with_id: uuid.UUID,
    ):
        asset = repo.create_asset(db, sample_asset_data)
        db.flush()

        for _ in range(5):
            repo.add_maintenance_log(
                db, asset.id, sample_maintenance_data, user_with_id
            )
        db.flush()

        items, total = repo.get_asset_history(db, asset.id, page=1, limit=3)
        assert total == 5
        assert len(items) == 3

        items2, total2 = repo.get_asset_history(db, asset.id, page=2, limit=3)
        assert total2 == 5
        assert len(items2) == 2

    def test_get_assets_stats(
        self, db: Session, repo: InfraestructuraRepository, sample_asset_data: AssetCreate
    ):
        repo.create_asset(db, sample_asset_data)
        repo.create_asset(db, sample_asset_data)
        db.flush()

        stats = repo.get_assets_stats(db)

        assert stats["total"] >= 2
        assert "canal" in stats["por_tipo"]
        assert "bueno" in stats["por_estado"] or EstadoAsset.BUENO in stats["por_estado"]


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────


class TestInfraestructuraService:
    """Service-layer tests."""

    def test_create_asset_commits_and_returns(
        self,
        db: Session,
        service: InfraestructuraService,
        sample_asset_data: AssetCreate,
    ):
        asset = service.create_asset(db, sample_asset_data)
        assert asset.id is not None
        assert asset.nombre == "Canal Principal Norte"
        assert asset.estado_actual == "bueno"

    def test_get_asset_raises_on_missing(
        self, db: Session, service: InfraestructuraService
    ):
        with pytest.raises(Exception) as exc_info:
            service.get_asset(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_list_assets(
        self,
        db: Session,
        service: InfraestructuraService,
        sample_asset_data: AssetCreate,
    ):
        service.create_asset(db, sample_asset_data)
        items, total = service.list_assets(db, page=1, limit=10)
        assert total >= 1
        assert len(items) >= 1

    def test_update_asset(
        self,
        db: Session,
        service: InfraestructuraService,
        sample_asset_data: AssetCreate,
    ):
        asset = service.create_asset(db, sample_asset_data)
        updated = service.update_asset(
            db, asset.id, AssetUpdate(estado_actual="malo")
        )
        assert updated.estado_actual == "malo"

    def test_add_maintenance_log(
        self,
        db: Session,
        service: InfraestructuraService,
        sample_asset_data: AssetCreate,
        sample_maintenance_data: MantenimientoLogCreate,
        user_with_id: uuid.UUID,
    ):
        asset = service.create_asset(db, sample_asset_data)
        log = service.add_maintenance_log(
            db, asset.id, sample_maintenance_data, user_with_id
        )
        assert log.id is not None
        assert log.asset_id == asset.id

    def test_get_asset_history_validates_asset(
        self, db: Session, service: InfraestructuraService
    ):
        """History endpoint should 404 if asset doesn't exist."""
        with pytest.raises(Exception) as exc_info:
            service.get_asset_history(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_get_stats(
        self,
        db: Session,
        service: InfraestructuraService,
        sample_asset_data: AssetCreate,
    ):
        service.create_asset(db, sample_asset_data)
        stats = service.get_stats(db)
        assert "total" in stats
        assert "por_tipo" in stats
        assert "por_estado" in stats
