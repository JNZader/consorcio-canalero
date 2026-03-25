"""Tests for the reuniones domain (models, schemas, service, estado transitions)."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.domains.reuniones.models import (
    AgendaItem,
    AgendaReferencia,
    Reunion,
    EstadoReunion,
    TipoReunion,
    VALID_TRANSITIONS,
)
from app.domains.reuniones.repository import (
    AgendaItemRepository,
    ReunionRepository,
)
from app.domains.reuniones.schemas import (
    AgendaItemCreate,
    AgendaReferenciaCreate,
    ReunionCreate,
    ReunionUpdate,
)
from app.domains.reuniones.service import ReunionService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def repo() -> ReunionRepository:
    return ReunionRepository()


@pytest.fixture
def agenda_repo() -> AgendaItemRepository:
    return AgendaItemRepository()


@pytest.fixture
def service(
    repo: ReunionRepository, agenda_repo: AgendaItemRepository
) -> ReunionService:
    return ReunionService(repository=repo, agenda_repository=agenda_repo)


@pytest.fixture
def user_with_id(db: Session) -> uuid.UUID:
    """Create a real User row and return its id."""
    from app.auth.models import User, UserRole

    user = User(
        email=f"operator-reuniones-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="fakehash",
        nombre="Operator",
        apellido="Reuniones",
        role=UserRole.OPERADOR,
    )
    db.add(user)
    db.flush()
    return user.id


@pytest.fixture
def sample_create_data() -> ReunionCreate:
    return ReunionCreate(
        titulo="Reunion ordinaria de marzo",
        fecha_reunion=datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc),
        lugar="Sede Consorcio",
        descripcion="Temas generales del mes de marzo.",
        tipo="ordinaria",
        orden_del_dia_items=["Lectura de acta anterior", "Informe de tesoreria"],
    )


@pytest.fixture
def sample_reunion(
    db: Session, repo: ReunionRepository, sample_create_data: ReunionCreate, user_with_id: uuid.UUID
) -> Reunion:
    """Create and return a reunion in the database."""
    reunion = repo.create(db, sample_create_data, usuario_id=user_with_id)
    db.flush()
    return reunion


# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class TestReunionModel:
    """Basic ORM smoke tests."""

    def test_create_reunion(self, db: Session, user_with_id: uuid.UUID):
        reunion = Reunion(
            titulo="Test reunion",
            fecha_reunion=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
            lugar="Oficina",
            tipo=TipoReunion.ORDINARIA,
            estado=EstadoReunion.PLANIFICADA,
            orden_del_dia_items=["Punto 1"],
            usuario_id=user_with_id,
        )
        db.add(reunion)
        db.flush()

        assert reunion.id is not None
        assert reunion.estado == EstadoReunion.PLANIFICADA
        assert reunion.tipo == TipoReunion.ORDINARIA
        assert reunion.orden_del_dia_items == ["Punto 1"]

    def test_create_agenda_item(self, db: Session, sample_reunion: Reunion):
        item = AgendaItem(
            reunion_id=sample_reunion.id,
            titulo="Reparacion canal zona norte",
            descripcion="Discutir presupuesto.",
            orden=1,
        )
        db.add(item)
        db.flush()

        assert item.id is not None
        assert item.reunion_id == sample_reunion.id
        assert item.completado is False

    def test_create_agenda_referencia(self, db: Session, sample_reunion: Reunion):
        item = AgendaItem(
            reunion_id=sample_reunion.id,
            titulo="Tema con referencia",
            orden=0,
        )
        db.add(item)
        db.flush()

        ref = AgendaReferencia(
            agenda_item_id=item.id,
            entidad_tipo="tramite",
            entidad_id=uuid.uuid4(),
            metadata_json={"label": "Tramite de obra"},
        )
        db.add(ref)
        db.flush()

        assert ref.id is not None
        assert ref.entidad_tipo == "tramite"

    def test_reunion_repr(self, sample_reunion: Reunion):
        assert "Reunion" in repr(sample_reunion)
        assert "ordinaria" in repr(sample_reunion)

    def test_cascade_delete(self, db: Session, sample_reunion: Reunion):
        """Deleting a reunion should cascade-delete agenda items and referencias."""
        item = AgendaItem(
            reunion_id=sample_reunion.id,
            titulo="Tema a eliminar",
            orden=0,
        )
        db.add(item)
        db.flush()

        ref = AgendaReferencia(
            agenda_item_id=item.id,
            entidad_tipo="reporte",
            entidad_id=uuid.uuid4(),
        )
        db.add(ref)
        db.flush()

        item_id = item.id
        ref_id = ref.id

        db.delete(sample_reunion)
        db.flush()

        assert db.get(AgendaItem, item_id) is None
        assert db.get(AgendaReferencia, ref_id) is None


# ──────────────────────────────────────────────
# SCHEMA VALIDATION TESTS
# ──────────────────────────────────────────────


class TestReunionSchemas:
    """Pydantic schema validation tests."""

    def test_reunion_create_valid(self):
        data = ReunionCreate(
            titulo="Reunion valida",
            fecha_reunion=datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc),
        )
        assert data.lugar == "Sede Consorcio"
        assert data.tipo == "ordinaria"
        assert data.orden_del_dia_items == []

    def test_reunion_create_titulo_too_short(self):
        with pytest.raises(Exception):
            ReunionCreate(
                titulo="AB",
                fecha_reunion=datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc),
            )

    def test_reunion_update_partial(self):
        data = ReunionUpdate(estado="en_curso")
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"estado": "en_curso"}
        assert "titulo" not in dumped

    def test_agenda_item_create_with_referencias(self):
        data = AgendaItemCreate(
            titulo="Tema con refs",
            descripcion="Detalle",
            orden=1,
            referencias=[
                AgendaReferenciaCreate(
                    entidad_tipo="tramite",
                    entidad_id=uuid.uuid4(),
                    metadata={"label": "Tramite X"},
                ),
            ],
        )
        assert len(data.referencias) == 1
        assert data.referencias[0].entidad_tipo == "tramite"


# ──────────────────────────────────────────────
# ESTADO TRANSITION TESTS
# ──────────────────────────────────────────────


class TestEstadoTransitions:
    """Validate the state machine for reuniones."""

    def test_valid_transitions_defined(self):
        """All enum values must have an entry in VALID_TRANSITIONS."""
        for estado in EstadoReunion:
            assert estado in VALID_TRANSITIONS

    def test_planificada_to_en_curso(self):
        assert EstadoReunion.EN_CURSO in VALID_TRANSITIONS[EstadoReunion.PLANIFICADA]

    def test_planificada_to_cancelada(self):
        assert EstadoReunion.CANCELADA in VALID_TRANSITIONS[EstadoReunion.PLANIFICADA]

    def test_en_curso_to_finalizada(self):
        assert EstadoReunion.FINALIZADA in VALID_TRANSITIONS[EstadoReunion.EN_CURSO]

    def test_en_curso_to_cancelada(self):
        assert EstadoReunion.CANCELADA in VALID_TRANSITIONS[EstadoReunion.EN_CURSO]

    def test_finalizada_is_terminal(self):
        assert VALID_TRANSITIONS[EstadoReunion.FINALIZADA] == set()

    def test_cancelada_is_terminal(self):
        assert VALID_TRANSITIONS[EstadoReunion.CANCELADA] == set()

    def test_invalid_planificada_to_finalizada(self):
        assert EstadoReunion.FINALIZADA not in VALID_TRANSITIONS[EstadoReunion.PLANIFICADA]

    def test_service_rejects_invalid_transition(
        self, db: Session, service: ReunionService, sample_reunion: Reunion
    ):
        """Service should raise 400 for invalid estado transitions."""
        from fastapi import HTTPException

        # planificada -> finalizada is invalid
        with pytest.raises(HTTPException) as exc_info:
            service.update(
                db,
                sample_reunion.id,
                ReunionUpdate(estado="finalizada"),
            )
        assert exc_info.value.status_code == 400
        assert "Transicion de estado invalida" in exc_info.value.detail

    def test_service_allows_valid_transition(
        self, db: Session, service: ReunionService, sample_reunion: Reunion
    ):
        """Service should allow valid transitions."""
        updated = service.update(
            db,
            sample_reunion.id,
            ReunionUpdate(estado="en_curso"),
        )
        assert updated.estado == "en_curso"


# ──────────────────────────────────────────────
# REPOSITORY TESTS
# ──────────────────────────────────────────────


class TestReunionRepository:
    """Repository layer tests."""

    def test_get_by_id(
        self, db: Session, repo: ReunionRepository, sample_reunion: Reunion
    ):
        found = repo.get_by_id(db, sample_reunion.id)
        assert found is not None
        assert found.titulo == sample_reunion.titulo

    def test_get_by_id_not_found(self, db: Session, repo: ReunionRepository):
        found = repo.get_by_id(db, uuid.uuid4())
        assert found is None

    def test_get_all_paginated(
        self,
        db: Session,
        repo: ReunionRepository,
        sample_create_data: ReunionCreate,
        user_with_id: uuid.UUID,
    ):
        # Create 3 reuniones
        for i in range(3):
            data = ReunionCreate(
                titulo=f"Reunion {i}",
                fecha_reunion=datetime(2026, 4, 10 + i, 10, 0, tzinfo=timezone.utc),
                tipo="ordinaria",
            )
            repo.create(db, data, usuario_id=user_with_id)
        db.flush()

        items, total = repo.get_all(db, page=1, limit=2)
        assert total == 3
        assert len(items) == 2

    def test_get_all_filter_by_estado(
        self,
        db: Session,
        repo: ReunionRepository,
        sample_reunion: Reunion,
        user_with_id: uuid.UUID,
    ):
        items, total = repo.get_all(db, estado_filter="planificada")
        assert total >= 1
        assert all(r.estado == "planificada" for r in items)

    def test_delete(
        self, db: Session, repo: ReunionRepository, sample_reunion: Reunion
    ):
        assert repo.delete(db, sample_reunion.id) is True
        assert repo.get_by_id(db, sample_reunion.id) is None

    def test_delete_not_found(self, db: Session, repo: ReunionRepository):
        assert repo.delete(db, uuid.uuid4()) is False


# ──────────────────────────────────────────────
# AGENDA ITEM TESTS
# ──────────────────────────────────────────────


class TestAgendaItemRepository:
    """Agenda item repository tests."""

    def test_create_with_referencias(
        self,
        db: Session,
        agenda_repo: AgendaItemRepository,
        sample_reunion: Reunion,
    ):
        data = AgendaItemCreate(
            titulo="Punto importante",
            descripcion="Detalle del punto",
            orden=1,
            referencias=[
                AgendaReferenciaCreate(
                    entidad_tipo="tramite",
                    entidad_id=uuid.uuid4(),
                    metadata={"label": "Tramite obra"},
                ),
                AgendaReferenciaCreate(
                    entidad_tipo="reporte",
                    entidad_id=uuid.uuid4(),
                ),
            ],
        )
        item = agenda_repo.create(db, sample_reunion.id, data)
        db.flush()

        assert item.id is not None
        assert item.titulo == "Punto importante"
        # Reload to check referencias
        loaded = agenda_repo.get_by_id(db, item.id)
        assert loaded is not None
        assert len(loaded.referencias) == 2

    def test_get_by_reunion_id_ordered(
        self,
        db: Session,
        agenda_repo: AgendaItemRepository,
        sample_reunion: Reunion,
    ):
        for i in [3, 1, 2]:
            agenda_repo.create(
                db,
                sample_reunion.id,
                AgendaItemCreate(titulo=f"Punto {i}", orden=i),
            )
        db.flush()

        items = agenda_repo.get_by_reunion_id(db, sample_reunion.id)
        ordenes = [item.orden for item in items]
        assert ordenes == sorted(ordenes)

    def test_delete_agenda_item(
        self,
        db: Session,
        agenda_repo: AgendaItemRepository,
        sample_reunion: Reunion,
    ):
        item = agenda_repo.create(
            db,
            sample_reunion.id,
            AgendaItemCreate(titulo="A eliminar", orden=0),
        )
        db.flush()
        item_id = item.id

        assert agenda_repo.delete(db, item_id) is True
        assert agenda_repo.get_by_id(db, item_id) is None


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────


class TestReunionService:
    """Service layer tests."""

    def test_create_reunion(
        self,
        db: Session,
        service: ReunionService,
        sample_create_data: ReunionCreate,
        user_with_id: uuid.UUID,
    ):
        reunion = service.create(db, sample_create_data, usuario_id=user_with_id)
        assert reunion.id is not None
        assert reunion.estado == "planificada"
        assert reunion.titulo == sample_create_data.titulo

    def test_get_not_found_raises_404(self, db: Session, service: ReunionService):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            service.get_by_id(db, uuid.uuid4())
        assert exc_info.value.status_code == 404

    def test_delete_not_found_raises_404(self, db: Session, service: ReunionService):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            service.delete(db, uuid.uuid4())
        assert exc_info.value.status_code == 404

    def test_add_agenda_item_reunion_not_found(
        self, db: Session, service: ReunionService
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            service.add_agenda_item(
                db,
                uuid.uuid4(),
                AgendaItemCreate(titulo="Test", orden=0),
            )
        assert exc_info.value.status_code == 404
