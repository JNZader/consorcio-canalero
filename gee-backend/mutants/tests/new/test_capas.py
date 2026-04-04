"""Tests for the capas (map layers) domain — models, repository, service."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.domains.capas.models import Capa, FuenteCapa, TipoCapa
from app.domains.capas.repository import CapasRepository
from app.domains.capas.schemas import CapaCreate, CapaReorder, CapaUpdate, EstiloCapa
from app.domains.capas.service import CapasService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def repo() -> CapasRepository:
    return CapasRepository()


@pytest.fixture
def service(repo: CapasRepository) -> CapasService:
    return CapasService(repository=repo)


@pytest.fixture
def sample_create_data() -> CapaCreate:
    return CapaCreate(
        nombre="Zona de riego",
        descripcion="Delimitacion de la zona de riego principal",
        tipo="polygon",
        fuente="local",
        estilo=EstiloCapa(
            color="#ff0000",
            weight=3,
            fillColor="#ff0000",
            fillOpacity=0.3,
        ),
        visible=True,
        orden=1,
        es_publica=True,
    )


@pytest.fixture
def sample_tile_data() -> CapaCreate:
    return CapaCreate(
        nombre="Sentinel-2 RGB",
        tipo="tile",
        fuente="gee",
        url="https://earthengine.googleapis.com/v1/tiles/{z}/{x}/{y}",
        visible=True,
        orden=0,
        es_publica=False,
    )


# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class TestCapaModel:
    """Basic ORM smoke tests."""

    def test_create_capa(self, db: Session):
        capa = Capa(
            nombre="Test Layer",
            tipo=TipoCapa.POLYGON,
            fuente=FuenteCapa.LOCAL,
            estilo={"color": "#333", "weight": 2},
        )
        db.add(capa)
        db.flush()

        assert capa.id is not None
        assert capa.nombre == "Test Layer"
        assert capa.tipo == TipoCapa.POLYGON
        assert capa.fuente == FuenteCapa.LOCAL
        assert capa.created_at is not None

    def test_default_values(self, db: Session):
        capa = Capa(
            nombre="Defaults",
            tipo=TipoCapa.POINT,
            fuente=FuenteCapa.UPLOAD,
            estilo={},
        )
        db.add(capa)
        db.flush()

        assert capa.visible is True
        assert capa.orden == 0
        assert capa.es_publica is False

    def test_optional_fields(self, db: Session):
        capa = Capa(
            nombre="Optional",
            tipo=TipoCapa.LINE,
            fuente=FuenteCapa.GEE,
            estilo={},
            url="https://example.com/tiles",
            descripcion="Una capa con URL externa",
            geojson_data={"type": "FeatureCollection", "features": []},
        )
        db.add(capa)
        db.flush()

        assert capa.url == "https://example.com/tiles"
        assert capa.descripcion is not None
        assert capa.geojson_data is not None

    def test_repr(self, db: Session):
        capa = Capa(
            nombre="Repr Test",
            tipo=TipoCapa.RASTER,
            fuente=FuenteCapa.LOCAL,
            estilo={},
        )
        db.add(capa)
        db.flush()

        r = repr(capa)
        assert "Repr Test" in r
        assert "Capa" in r


# ──────────────────────────────────────────────
# REPOSITORY TESTS
# ──────────────────────────────────────────────


class TestCapasRepository:
    """Repository tests against real DB (rolled-back transactions)."""

    def test_create_and_get_by_id(
        self, db: Session, repo: CapasRepository, sample_create_data: CapaCreate
    ):
        created = repo.create(db, sample_create_data)
        db.flush()

        fetched = repo.get_by_id(db, created.id)
        assert fetched is not None
        assert fetched.nombre == "Zona de riego"
        assert fetched.tipo == TipoCapa.POLYGON
        assert fetched.fuente == FuenteCapa.LOCAL

    def test_get_by_id_returns_none(self, db: Session, repo: CapasRepository):
        result = repo.get_by_id(db, uuid.uuid4())
        assert result is None

    def test_get_all_ordered(
        self, db: Session, repo: CapasRepository
    ):
        # Create layers with different orden values
        for i, name in enumerate(["Third", "First", "Second"]):
            data = CapaCreate(
                nombre=name,
                tipo="point",
                fuente="local",
                orden=[2, 0, 1][i],
            )
            repo.create(db, data)
        db.flush()

        all_capas = repo.get_all(db)
        assert len(all_capas) >= 3
        # Verify ordering by 'orden' asc
        orders = [c.orden for c in all_capas]
        assert orders == sorted(orders)

    def test_get_all_visible_only(
        self, db: Session, repo: CapasRepository
    ):
        visible = CapaCreate(nombre="Visible", tipo="point", fuente="local", visible=True)
        hidden = CapaCreate(nombre="Hidden", tipo="point", fuente="local", visible=False)
        repo.create(db, visible)
        repo.create(db, hidden)
        db.flush()

        all_capas = repo.get_all(db, visible_only=True)
        names = [c.nombre for c in all_capas]
        assert "Visible" in names
        assert "Hidden" not in names

    def test_get_public(self, db: Session, repo: CapasRepository):
        public = CapaCreate(
            nombre="Public", tipo="polygon", fuente="local",
            es_publica=True, visible=True,
        )
        private = CapaCreate(
            nombre="Private", tipo="polygon", fuente="local",
            es_publica=False, visible=True,
        )
        repo.create(db, public)
        repo.create(db, private)
        db.flush()

        public_capas = repo.get_public(db)
        names = [c.nombre for c in public_capas]
        assert "Public" in names
        assert "Private" not in names

    def test_update(
        self, db: Session, repo: CapasRepository, sample_create_data: CapaCreate
    ):
        created = repo.create(db, sample_create_data)
        db.flush()

        update_data = CapaUpdate(nombre="Zona actualizada", visible=False)
        updated = repo.update(db, created.id, update_data)

        assert updated is not None
        assert updated.nombre == "Zona actualizada"
        assert updated.visible is False
        # Unchanged fields stay the same
        assert updated.tipo == TipoCapa.POLYGON

    def test_update_nonexistent_returns_none(
        self, db: Session, repo: CapasRepository
    ):
        result = repo.update(db, uuid.uuid4(), CapaUpdate(nombre="Nope"))
        assert result is None

    def test_delete(
        self, db: Session, repo: CapasRepository, sample_create_data: CapaCreate
    ):
        created = repo.create(db, sample_create_data)
        db.flush()

        deleted = repo.delete(db, created.id)
        assert deleted is True

        fetched = repo.get_by_id(db, created.id)
        assert fetched is None

    def test_delete_nonexistent_returns_false(
        self, db: Session, repo: CapasRepository
    ):
        result = repo.delete(db, uuid.uuid4())
        assert result is False

    def test_reorder(self, db: Session, repo: CapasRepository):
        capas = []
        for name in ["A", "B", "C"]:
            data = CapaCreate(nombre=name, tipo="point", fuente="local")
            capas.append(repo.create(db, data))
        db.flush()

        # Reverse order
        ordered_ids = [capas[2].id, capas[1].id, capas[0].id]
        count = repo.reorder(db, ordered_ids)
        assert count == 3

        # Verify new ordering
        refreshed = repo.get_all(db)
        id_order = [c.id for c in refreshed]
        assert id_order[0] == capas[2].id
        assert id_order[1] == capas[1].id
        assert id_order[2] == capas[0].id


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────


class TestCapasService:
    """Service-layer tests."""

    def test_create_commits_and_returns(
        self, db: Session, service: CapasService, sample_create_data: CapaCreate
    ):
        capa = service.create(db, sample_create_data)
        assert capa.id is not None
        assert capa.nombre == "Zona de riego"

    def test_get_by_id_raises_on_missing(
        self, db: Session, service: CapasService
    ):
        with pytest.raises(Exception) as exc_info:
            service.get_by_id(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_list_capas(
        self, db: Session, service: CapasService, sample_create_data: CapaCreate
    ):
        service.create(db, sample_create_data)
        capas = service.list_capas(db)
        assert len(capas) >= 1

    def test_list_public(
        self, db: Session, service: CapasService
    ):
        public = CapaCreate(
            nombre="Public layer", tipo="polygon", fuente="local",
            es_publica=True, visible=True,
        )
        private = CapaCreate(
            nombre="Private layer", tipo="polygon", fuente="local",
            es_publica=False,
        )
        service.create(db, public)
        service.create(db, private)

        public_capas = service.list_public(db)
        names = [c.nombre for c in public_capas]
        assert "Public layer" in names
        assert "Private layer" not in names

    def test_update(
        self, db: Session, service: CapasService, sample_create_data: CapaCreate
    ):
        capa = service.create(db, sample_create_data)
        updated = service.update(db, capa.id, CapaUpdate(nombre="Updated name"))
        assert updated.nombre == "Updated name"

    def test_update_nonexistent_raises_404(
        self, db: Session, service: CapasService
    ):
        with pytest.raises(Exception) as exc_info:
            service.update(db, uuid.uuid4(), CapaUpdate(nombre="Nope"))
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_delete(
        self, db: Session, service: CapasService, sample_create_data: CapaCreate
    ):
        capa = service.create(db, sample_create_data)
        service.delete(db, capa.id)

        with pytest.raises(Exception) as exc_info:
            service.get_by_id(db, capa.id)
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_delete_nonexistent_raises_404(
        self, db: Session, service: CapasService
    ):
        with pytest.raises(Exception) as exc_info:
            service.delete(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_reorder(
        self, db: Session, service: CapasService
    ):
        capas = []
        for name in ["X", "Y", "Z"]:
            data = CapaCreate(nombre=name, tipo="point", fuente="local")
            capas.append(service.create(db, data))

        ordered_ids = [capas[2].id, capas[0].id, capas[1].id]
        count = service.reorder(db, ordered_ids)
        assert count == 3

    def test_reorder_empty_raises_400(
        self, db: Session, service: CapasService
    ):
        with pytest.raises(Exception) as exc_info:
            service.reorder(db, [])
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]


# ──────────────────────────────────────────────
# SCHEMA VALIDATION TESTS
# ──────────────────────────────────────────────


class TestCapaSchemas:
    """Schema validation tests."""

    def test_create_minimal(self):
        data = CapaCreate(nombre="Min", tipo="point", fuente="local")
        assert data.visible is True
        assert data.orden == 0
        assert data.es_publica is False
        assert data.estilo.color == "#3388ff"

    def test_create_with_all_fields(self):
        data = CapaCreate(
            nombre="Full",
            descripcion="Full description",
            tipo="polygon",
            fuente="upload",
            url="https://example.com",
            geojson_data={"type": "FeatureCollection", "features": []},
            estilo=EstiloCapa(color="#000", weight=5, fillColor="#111", fillOpacity=0.5),
            visible=False,
            orden=10,
            es_publica=True,
        )
        assert data.nombre == "Full"
        assert data.estilo.weight == 5

    def test_update_partial(self):
        data = CapaUpdate(nombre="Only name")
        dumped = data.model_dump(exclude_unset=True)
        assert "nombre" in dumped
        assert "tipo" not in dumped

    def test_reorder_schema(self):
        ids = [uuid.uuid4(), uuid.uuid4()]
        reorder = CapaReorder(ordered_ids=ids)
        assert len(reorder.ordered_ids) == 2

    def test_estilo_defaults(self):
        estilo = EstiloCapa()
        assert estilo.color == "#3388ff"
        assert estilo.weight == 2
        assert estilo.fillOpacity == 0.2
