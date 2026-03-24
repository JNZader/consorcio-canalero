"""Tests for the denuncias domain (models, repository, service)."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.domains.denuncias.models import (
    Denuncia,
    DenunciaHistorial,
    EstadoDenuncia,
    VALID_TRANSITIONS,
)
from app.domains.denuncias.repository import DenunciaRepository
from app.domains.denuncias.schemas import DenunciaCreate, DenunciaUpdate
from app.domains.denuncias.service import DenunciaService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def repo() -> DenunciaRepository:
    return DenunciaRepository()


@pytest.fixture
def service(repo: DenunciaRepository) -> DenunciaService:
    return DenunciaService(repository=repo)


@pytest.fixture
def sample_create_data() -> DenunciaCreate:
    return DenunciaCreate(
        tipo="desborde",
        descripcion="Canal desbordado en la zona norte, afectando caminos rurales.",
        latitud=-33.7,
        longitud=-63.9,
        cuenca="cuenca_1",
        contacto_telefono="3537123456",
        contacto_email="vecino@example.com",
    )


@pytest.fixture
def operator_id() -> uuid.UUID:
    return uuid.uuid4()


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


class TestDenunciaModel:
    """Basic ORM smoke tests."""

    def test_create_denuncia(self, db: Session):
        denuncia = Denuncia(
            tipo="desborde",
            descripcion="Test description with enough chars.",
            latitud=-33.7,
            longitud=-63.9,
            estado=EstadoDenuncia.PENDIENTE,
        )
        db.add(denuncia)
        db.flush()

        assert denuncia.id is not None
        assert denuncia.estado == EstadoDenuncia.PENDIENTE
        assert denuncia.created_at is not None

    def test_historial_relationship(self, db: Session, user_with_id: uuid.UUID):
        denuncia = Denuncia(
            tipo="desborde",
            descripcion="Test description with enough chars.",
            latitud=-33.7,
            longitud=-63.9,
            estado=EstadoDenuncia.PENDIENTE,
        )
        db.add(denuncia)
        db.flush()

        historial = DenunciaHistorial(
            denuncia_id=denuncia.id,
            estado_anterior=EstadoDenuncia.PENDIENTE,
            estado_nuevo=EstadoDenuncia.EN_REVISION,
            comentario="Asignado a operador",
            usuario_id=user_with_id,
        )
        db.add(historial)
        db.flush()

        # Refresh to load relationship
        db.refresh(denuncia)
        assert len(denuncia.historial) == 1
        assert denuncia.historial[0].estado_nuevo == EstadoDenuncia.EN_REVISION

    def test_default_estado_is_pendiente(self, db: Session):
        denuncia = Denuncia(
            tipo="camino_danado",
            descripcion="Camino danado cerca del puente principal.",
            latitud=-33.5,
            longitud=-63.8,
        )
        db.add(denuncia)
        db.flush()
        assert denuncia.estado == EstadoDenuncia.PENDIENTE


# ──────────────────────────────────────────────
# REPOSITORY TESTS
# ──────────────────────────────────────────────


class TestDenunciaRepository:
    """Repository tests against real DB (rolled-back transactions)."""

    def test_create_and_get_by_id(
        self, db: Session, repo: DenunciaRepository, sample_create_data: DenunciaCreate
    ):
        created = repo.create(db, sample_create_data)
        db.flush()

        fetched = repo.get_by_id(db, created.id)
        assert fetched is not None
        assert fetched.tipo == "desborde"
        assert fetched.latitud == pytest.approx(-33.7)
        assert fetched.longitud == pytest.approx(-63.9)

    def test_get_by_id_returns_none(self, db: Session, repo: DenunciaRepository):
        result = repo.get_by_id(db, uuid.uuid4())
        assert result is None

    def test_get_all_pagination(
        self, db: Session, repo: DenunciaRepository, sample_create_data: DenunciaCreate
    ):
        # Create 5 denuncias
        for _ in range(5):
            repo.create(db, sample_create_data)
        db.flush()

        items, total = repo.get_all(db, page=1, limit=3)
        assert total == 5
        assert len(items) == 3

        items2, total2 = repo.get_all(db, page=2, limit=3)
        assert total2 == 5
        assert len(items2) == 2

    def test_get_all_filter_by_estado(
        self, db: Session, repo: DenunciaRepository, sample_create_data: DenunciaCreate
    ):
        repo.create(db, sample_create_data)
        db.flush()

        items, total = repo.get_all(
            db, estado_filter=EstadoDenuncia.PENDIENTE
        )
        assert total >= 1

        items_none, total_none = repo.get_all(
            db, estado_filter=EstadoDenuncia.RESUELTO
        )
        assert total_none == 0

    def test_get_all_filter_by_cuenca(
        self, db: Session, repo: DenunciaRepository, sample_create_data: DenunciaCreate
    ):
        repo.create(db, sample_create_data)
        db.flush()

        items, total = repo.get_all(db, cuenca_filter="cuenca_1")
        assert total >= 1

        items_none, total_none = repo.get_all(db, cuenca_filter="nonexistent")
        assert total_none == 0

    def test_update(
        self, db: Session, repo: DenunciaRepository, sample_create_data: DenunciaCreate
    ):
        created = repo.create(db, sample_create_data)
        db.flush()

        update_data = DenunciaUpdate(
            estado=EstadoDenuncia.EN_REVISION,
            respuesta="Estamos revisando",
        )
        updated = repo.update(db, created.id, update_data)

        assert updated is not None
        assert updated.estado == EstadoDenuncia.EN_REVISION
        assert updated.respuesta == "Estamos revisando"

    def test_update_nonexistent_returns_none(
        self, db: Session, repo: DenunciaRepository
    ):
        update_data = DenunciaUpdate(estado=EstadoDenuncia.EN_REVISION)
        result = repo.update(db, uuid.uuid4(), update_data)
        assert result is None

    def test_add_historial(
        self,
        db: Session,
        repo: DenunciaRepository,
        sample_create_data: DenunciaCreate,
        user_with_id: uuid.UUID,
    ):
        created = repo.create(db, sample_create_data)
        db.flush()

        entry = repo.add_historial(
            db,
            denuncia_id=created.id,
            estado_anterior=EstadoDenuncia.PENDIENTE,
            estado_nuevo=EstadoDenuncia.EN_REVISION,
            comentario="Revisando el caso",
            usuario_id=user_with_id,
        )
        db.flush()

        assert entry.id is not None
        assert entry.estado_anterior == EstadoDenuncia.PENDIENTE
        assert entry.estado_nuevo == EstadoDenuncia.EN_REVISION

    def test_get_stats(
        self, db: Session, repo: DenunciaRepository, sample_create_data: DenunciaCreate
    ):
        # Create a couple of denuncias
        repo.create(db, sample_create_data)
        repo.create(db, sample_create_data)
        db.flush()

        stats = repo.get_stats(db)

        assert stats["total"] >= 2
        assert EstadoDenuncia.PENDIENTE in stats["por_estado"]
        assert "desborde" in stats["por_tipo"]
        assert "cuenca_1" in stats["por_cuenca"]


# ──────────────────────────────────────────────
# STATE TRANSITION TESTS
# ──────────────────────────────────────────────


class TestStateTransitions:
    """Validate that business rules enforce correct transitions."""

    def test_valid_transitions_map(self):
        """Ensure every estado is a key in VALID_TRANSITIONS."""
        for estado in EstadoDenuncia:
            assert estado in VALID_TRANSITIONS

    def test_terminal_states_have_no_transitions(self):
        assert VALID_TRANSITIONS[EstadoDenuncia.RESUELTO] == set()
        assert VALID_TRANSITIONS[EstadoDenuncia.DESCARTADO] == set()

    def test_pendiente_can_go_to_en_revision(self):
        assert EstadoDenuncia.EN_REVISION in VALID_TRANSITIONS[EstadoDenuncia.PENDIENTE]

    def test_pendiente_can_go_to_descartado(self):
        assert EstadoDenuncia.DESCARTADO in VALID_TRANSITIONS[EstadoDenuncia.PENDIENTE]

    def test_en_revision_can_go_to_resuelto(self):
        assert EstadoDenuncia.RESUELTO in VALID_TRANSITIONS[EstadoDenuncia.EN_REVISION]

    def test_service_rejects_invalid_transition(
        self,
        db: Session,
        service: DenunciaService,
        sample_create_data: DenunciaCreate,
        user_with_id: uuid.UUID,
    ):
        """pendiente -> resuelto should be rejected."""
        denuncia = service.create(db, sample_create_data)

        with pytest.raises(Exception) as exc_info:
            service.update(
                db,
                denuncia.id,
                DenunciaUpdate(estado=EstadoDenuncia.RESUELTO),
                operator_id=user_with_id,
            )
        assert "invalida" in str(exc_info.value.detail).lower()

    def test_service_allows_valid_transition(
        self,
        db: Session,
        service: DenunciaService,
        sample_create_data: DenunciaCreate,
        user_with_id: uuid.UUID,
    ):
        """pendiente -> en_revision should succeed."""
        denuncia = service.create(db, sample_create_data)

        updated = service.update(
            db,
            denuncia.id,
            DenunciaUpdate(
                estado=EstadoDenuncia.EN_REVISION,
                comentario="Asignado a revision",
            ),
            operator_id=user_with_id,
        )
        assert updated.estado == EstadoDenuncia.EN_REVISION

    def test_service_creates_historial_on_transition(
        self,
        db: Session,
        service: DenunciaService,
        sample_create_data: DenunciaCreate,
        user_with_id: uuid.UUID,
    ):
        denuncia = service.create(db, sample_create_data)

        updated = service.update(
            db,
            denuncia.id,
            DenunciaUpdate(
                estado=EstadoDenuncia.EN_REVISION,
                comentario="Checking it out",
            ),
            operator_id=user_with_id,
        )

        db.refresh(updated)
        assert len(updated.historial) == 1
        assert updated.historial[0].comentario == "Checking it out"


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────


class TestDenunciaService:
    """Service-layer tests."""

    def test_create_commits_and_returns(
        self,
        db: Session,
        service: DenunciaService,
        sample_create_data: DenunciaCreate,
    ):
        denuncia = service.create(db, sample_create_data)
        assert denuncia.id is not None
        assert denuncia.estado == EstadoDenuncia.PENDIENTE

    def test_get_by_id_raises_on_missing(
        self, db: Session, service: DenunciaService
    ):
        with pytest.raises(Exception) as exc_info:
            service.get_by_id(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_list_denuncias(
        self,
        db: Session,
        service: DenunciaService,
        sample_create_data: DenunciaCreate,
    ):
        service.create(db, sample_create_data)
        items, total = service.list_denuncias(db, page=1, limit=10)
        assert total >= 1
        assert len(items) >= 1

    def test_get_stats(
        self,
        db: Session,
        service: DenunciaService,
        sample_create_data: DenunciaCreate,
    ):
        service.create(db, sample_create_data)
        stats = service.get_stats(db)
        assert "total" in stats
        assert "por_estado" in stats
