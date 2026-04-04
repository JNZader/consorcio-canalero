"""Tests for the tramites domain (models, repository, service)."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.domains.tramites.models import (
    Tramite,
    TramiteSeguimiento,
    EstadoTramite,
    TipoTramite,
    PrioridadTramite,
    VALID_TRANSITIONS,
)
from app.domains.tramites.repository import TramiteRepository
from app.domains.tramites.schemas import (
    TramiteCreate,
    TramiteUpdate,
    SeguimientoCreate,
)
from app.domains.tramites.service import TramiteService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def repo() -> TramiteRepository:
    return TramiteRepository()


@pytest.fixture
def service(repo: TramiteRepository) -> TramiteService:
    return TramiteService(repository=repo)


@pytest.fixture
def user_with_id(db: Session) -> uuid.UUID:
    """Create a real User row and return its id."""
    from app.auth.models import User, UserRole

    user = User(
        email=f"operator-tramites-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="fakehash",
        nombre="Operator",
        apellido="Tramites",
        role=UserRole.OPERADOR,
    )
    db.add(user)
    db.flush()
    return user.id


@pytest.fixture
def sample_create_data() -> TramiteCreate:
    return TramiteCreate(
        tipo="obra",
        titulo="Reparacion canal principal zona norte",
        descripcion="Se requiere reparacion urgente del canal principal en la zona norte por fisuras.",
        solicitante="Juan Perez",
        prioridad="alta",
    )


# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class TestTramiteModel:
    """Basic ORM smoke tests."""

    def test_create_tramite(self, db: Session, user_with_id: uuid.UUID):
        tramite = Tramite(
            tipo=TipoTramite.OBRA,
            titulo="Test tramite",
            descripcion="Descripcion de prueba para tramite.",
            solicitante="Test User",
            estado=EstadoTramite.INGRESADO,
            prioridad=PrioridadTramite.MEDIA,
            usuario_id=user_with_id,
        )
        db.add(tramite)
        db.flush()

        assert tramite.id is not None
        assert tramite.estado == EstadoTramite.INGRESADO
        assert tramite.created_at is not None

    def test_seguimiento_relationship(self, db: Session, user_with_id: uuid.UUID):
        tramite = Tramite(
            tipo=TipoTramite.PERMISO,
            titulo="Test seguimiento",
            descripcion="Descripcion de prueba para seguimiento.",
            solicitante="Maria Lopez",
            estado=EstadoTramite.INGRESADO,
            prioridad=PrioridadTramite.BAJA,
            usuario_id=user_with_id,
        )
        db.add(tramite)
        db.flush()

        seg = TramiteSeguimiento(
            tramite_id=tramite.id,
            estado_anterior=EstadoTramite.INGRESADO,
            estado_nuevo=EstadoTramite.EN_TRAMITE,
            comentario="Asignado a operador",
            usuario_id=user_with_id,
        )
        db.add(seg)
        db.flush()

        db.refresh(tramite)
        assert len(tramite.seguimiento) == 1
        assert tramite.seguimiento[0].estado_nuevo == EstadoTramite.EN_TRAMITE

    def test_default_estado_is_ingresado(self, db: Session, user_with_id: uuid.UUID):
        tramite = Tramite(
            tipo=TipoTramite.RECLAMO,
            titulo="Reclamo de prueba",
            descripcion="Reclamo por demora en obra cerca del puente.",
            solicitante="Carlos Garcia",
            prioridad=PrioridadTramite.URGENTE,
            usuario_id=user_with_id,
        )
        db.add(tramite)
        db.flush()
        assert tramite.estado == EstadoTramite.INGRESADO


# ──────────────────────────────────────────────
# REPOSITORY TESTS
# ──────────────────────────────────────────────


class TestTramiteRepository:
    """Repository tests against real DB (rolled-back transactions)."""

    def test_create_and_get_by_id(
        self,
        db: Session,
        repo: TramiteRepository,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        created = repo.create(db, sample_create_data, usuario_id=user_with_id)
        db.flush()

        fetched = repo.get_by_id(db, created.id)
        assert fetched is not None
        assert fetched.tipo == "obra"
        assert fetched.titulo == "Reparacion canal principal zona norte"
        assert fetched.solicitante == "Juan Perez"

    def test_get_by_id_returns_none(self, db: Session, repo: TramiteRepository):
        result = repo.get_by_id(db, uuid.uuid4())
        assert result is None

    def test_get_all_pagination(
        self,
        db: Session,
        repo: TramiteRepository,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        for _ in range(5):
            repo.create(db, sample_create_data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_all(db, page=1, limit=3)
        assert total == 5
        assert len(items) == 3

        items2, total2 = repo.get_all(db, page=2, limit=3)
        assert total2 == 5
        assert len(items2) == 2

    def test_get_all_filter_by_estado(
        self,
        db: Session,
        repo: TramiteRepository,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        repo.create(db, sample_create_data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_all(db, estado_filter=EstadoTramite.INGRESADO)
        assert total >= 1

        items_none, total_none = repo.get_all(
            db, estado_filter=EstadoTramite.APROBADO
        )
        assert total_none == 0

    def test_get_all_filter_by_tipo(
        self,
        db: Session,
        repo: TramiteRepository,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        repo.create(db, sample_create_data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_all(db, tipo_filter=TipoTramite.OBRA)
        assert total >= 1

        items_none, total_none = repo.get_all(db, tipo_filter=TipoTramite.PERMISO)
        assert total_none == 0

    def test_get_all_filter_by_prioridad(
        self,
        db: Session,
        repo: TramiteRepository,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        repo.create(db, sample_create_data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_all(
            db, prioridad_filter=PrioridadTramite.ALTA
        )
        assert total >= 1

        items_none, total_none = repo.get_all(
            db, prioridad_filter=PrioridadTramite.BAJA
        )
        assert total_none == 0

    def test_update(
        self,
        db: Session,
        repo: TramiteRepository,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        created = repo.create(db, sample_create_data, usuario_id=user_with_id)
        db.flush()

        update_data = TramiteUpdate(
            estado=EstadoTramite.EN_TRAMITE,
            resolucion="En proceso de revision",
        )
        updated = repo.update(db, created.id, update_data)

        assert updated is not None
        assert updated.estado == EstadoTramite.EN_TRAMITE
        assert updated.resolucion == "En proceso de revision"

    def test_update_nonexistent_returns_none(
        self, db: Session, repo: TramiteRepository
    ):
        update_data = TramiteUpdate(estado=EstadoTramite.EN_TRAMITE)
        result = repo.update(db, uuid.uuid4(), update_data)
        assert result is None

    def test_add_seguimiento(
        self,
        db: Session,
        repo: TramiteRepository,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        created = repo.create(db, sample_create_data, usuario_id=user_with_id)
        db.flush()

        entry = repo.add_seguimiento(
            db,
            tramite_id=created.id,
            estado_anterior=EstadoTramite.INGRESADO,
            estado_nuevo=EstadoTramite.EN_TRAMITE,
            comentario="Revisando el caso",
            usuario_id=user_with_id,
        )
        db.flush()

        assert entry.id is not None
        assert entry.estado_anterior == EstadoTramite.INGRESADO
        assert entry.estado_nuevo == EstadoTramite.EN_TRAMITE

    def test_get_stats(
        self,
        db: Session,
        repo: TramiteRepository,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        repo.create(db, sample_create_data, usuario_id=user_with_id)
        repo.create(db, sample_create_data, usuario_id=user_with_id)
        db.flush()

        stats = repo.get_stats(db)

        assert stats["total"] >= 2
        assert EstadoTramite.INGRESADO in stats["por_estado"]
        assert TipoTramite.OBRA in stats["por_tipo"]
        assert PrioridadTramite.ALTA in stats["por_prioridad"]


# ──────────────────────────────────────────────
# STATE TRANSITION TESTS
# ──────────────────────────────────────────────


class TestStateTransitions:
    """Validate that business rules enforce correct transitions."""

    def test_valid_transitions_map(self):
        """Ensure every estado is a key in VALID_TRANSITIONS."""
        for estado in EstadoTramite:
            assert estado in VALID_TRANSITIONS

    def test_terminal_state_archivado_has_no_transitions(self):
        assert VALID_TRANSITIONS[EstadoTramite.ARCHIVADO] == set()

    def test_ingresado_can_go_to_en_tramite(self):
        assert EstadoTramite.EN_TRAMITE in VALID_TRANSITIONS[EstadoTramite.INGRESADO]

    def test_ingresado_can_go_to_rechazado(self):
        assert EstadoTramite.RECHAZADO in VALID_TRANSITIONS[EstadoTramite.INGRESADO]

    def test_en_tramite_can_go_to_aprobado(self):
        assert EstadoTramite.APROBADO in VALID_TRANSITIONS[EstadoTramite.EN_TRAMITE]

    def test_aprobado_can_go_to_archivado(self):
        assert EstadoTramite.ARCHIVADO in VALID_TRANSITIONS[EstadoTramite.APROBADO]

    def test_rechazado_can_go_back_to_ingresado(self):
        assert EstadoTramite.INGRESADO in VALID_TRANSITIONS[EstadoTramite.RECHAZADO]

    def test_service_rejects_invalid_transition(
        self,
        db: Session,
        service: TramiteService,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        """ingresado -> aprobado should be rejected."""
        tramite = service.create(db, sample_create_data, usuario_id=user_with_id)

        with pytest.raises(Exception) as exc_info:
            service.update(
                db,
                tramite.id,
                TramiteUpdate(estado=EstadoTramite.APROBADO),
                operator_id=user_with_id,
            )
        assert "invalida" in str(exc_info.value.detail).lower()

    def test_service_allows_valid_transition(
        self,
        db: Session,
        service: TramiteService,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        """ingresado -> en_tramite should succeed."""
        tramite = service.create(db, sample_create_data, usuario_id=user_with_id)

        updated = service.update(
            db,
            tramite.id,
            TramiteUpdate(
                estado=EstadoTramite.EN_TRAMITE,
                comentario="Asignado a revision",
            ),
            operator_id=user_with_id,
        )
        assert updated.estado == EstadoTramite.EN_TRAMITE

    def test_service_creates_seguimiento_on_transition(
        self,
        db: Session,
        service: TramiteService,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        tramite = service.create(db, sample_create_data, usuario_id=user_with_id)

        updated = service.update(
            db,
            tramite.id,
            TramiteUpdate(
                estado=EstadoTramite.EN_TRAMITE,
                comentario="Checking it out",
            ),
            operator_id=user_with_id,
        )

        db.refresh(updated)
        assert len(updated.seguimiento) == 1
        assert updated.seguimiento[0].comentario == "Checking it out"

    def test_service_sets_fecha_resolucion_on_aprobado(
        self,
        db: Session,
        service: TramiteService,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        tramite = service.create(db, sample_create_data, usuario_id=user_with_id)

        # ingresado -> en_tramite
        service.update(
            db,
            tramite.id,
            TramiteUpdate(estado=EstadoTramite.EN_TRAMITE),
            operator_id=user_with_id,
        )

        # en_tramite -> aprobado
        updated = service.update(
            db,
            tramite.id,
            TramiteUpdate(estado=EstadoTramite.APROBADO),
            operator_id=user_with_id,
        )

        assert updated.fecha_resolucion is not None


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────


class TestTramiteService:
    """Service-layer tests."""

    def test_create_commits_and_returns(
        self,
        db: Session,
        service: TramiteService,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        tramite = service.create(db, sample_create_data, usuario_id=user_with_id)
        assert tramite.id is not None
        assert tramite.estado == EstadoTramite.INGRESADO

    def test_get_by_id_raises_on_missing(
        self, db: Session, service: TramiteService
    ):
        with pytest.raises(Exception) as exc_info:
            service.get_by_id(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_list_tramites(
        self,
        db: Session,
        service: TramiteService,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        service.create(db, sample_create_data, usuario_id=user_with_id)
        items, total = service.list_tramites(db, page=1, limit=10)
        assert total >= 1
        assert len(items) >= 1

    def test_get_stats(
        self,
        db: Session,
        service: TramiteService,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        service.create(db, sample_create_data, usuario_id=user_with_id)
        stats = service.get_stats(db)
        assert "total" in stats
        assert "por_estado" in stats
        assert "por_prioridad" in stats

    def test_add_seguimiento_without_state_change(
        self,
        db: Session,
        service: TramiteService,
        sample_create_data: TramiteCreate,
        user_with_id: uuid.UUID,
    ):
        tramite = service.create(db, sample_create_data, usuario_id=user_with_id)

        seg = service.add_seguimiento(
            db,
            tramite.id,
            SeguimientoCreate(comentario="Nota de seguimiento sin cambio de estado"),
            operator_id=user_with_id,
        )

        assert seg.id is not None
        assert seg.estado_anterior == EstadoTramite.INGRESADO
        assert seg.estado_nuevo == EstadoTramite.INGRESADO
        assert seg.comentario == "Nota de seguimiento sin cambio de estado"
