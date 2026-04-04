"""Tests for the monitoring domain (models, repository, service)."""

import uuid
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.domains.monitoring.models import (
    AnalisisGee,
    EstadoSugerencia,
    Sugerencia,
    TipoAnalisis,
)
from app.domains.monitoring.repository import MonitoringRepository
from app.domains.monitoring.schemas import SugerenciaCreate, SugerenciaUpdate
from app.domains.monitoring.service import MonitoringService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def repo() -> MonitoringRepository:
    return MonitoringRepository()


@pytest.fixture
def service(repo: MonitoringRepository) -> MonitoringService:
    return MonitoringService(repository=repo)


@pytest.fixture
def sample_sugerencia_data() -> SugerenciaCreate:
    return SugerenciaCreate(
        titulo="Mejorar camino rural zona norte",
        descripcion="El camino entre las parcelas 42 y 55 necesita mantenimiento urgente.",
        categoria="infraestructura",
        contacto_email="vecino@example.com",
        contacto_nombre="Juan Perez",
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


class TestSugerenciaModel:
    """ORM smoke tests for Sugerencia."""

    def test_create_sugerencia(self, db: Session):
        sugerencia = Sugerencia(
            titulo="Test sugerencia titulo largo",
            descripcion="Descripcion detallada de la sugerencia para testing.",
            estado=EstadoSugerencia.PENDIENTE,
        )
        db.add(sugerencia)
        db.flush()

        assert sugerencia.id is not None
        assert sugerencia.estado == EstadoSugerencia.PENDIENTE
        assert sugerencia.created_at is not None

    def test_default_estado_is_pendiente(self, db: Session):
        sugerencia = Sugerencia(
            titulo="Otra sugerencia para testing",
            descripcion="Descripcion de la sugerencia con detalles suficientes.",
        )
        db.add(sugerencia)
        db.flush()
        assert sugerencia.estado == EstadoSugerencia.PENDIENTE

    def test_optional_fields_are_nullable(self, db: Session):
        sugerencia = Sugerencia(
            titulo="Sugerencia sin contacto informacion",
            descripcion="Solo titulo y descripcion, campos opcionales vacios.",
            estado=EstadoSugerencia.PENDIENTE,
        )
        db.add(sugerencia)
        db.flush()

        assert sugerencia.contacto_email is None
        assert sugerencia.contacto_nombre is None
        assert sugerencia.categoria is None
        assert sugerencia.respuesta is None
        assert sugerencia.usuario_id is None


class TestAnalisisGeeModel:
    """ORM smoke tests for AnalisisGee."""

    def test_create_analysis(self, db: Session, user_with_id: uuid.UUID):
        analysis = AnalisisGee(
            tipo=TipoAnalisis.INUNDACION,
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 1, 31),
            resultados={"area_inundada": 1234.5},
            hectareas_afectadas=1234.5,
            porcentaje_area=15.3,
            parametros={"sensor": "Sentinel-2", "cloud_cover": 20},
            usuario_id=user_with_id,
        )
        db.add(analysis)
        db.flush()

        assert analysis.id is not None
        assert analysis.tipo == TipoAnalisis.INUNDACION
        assert analysis.resultados["area_inundada"] == 1234.5
        assert analysis.created_at is not None

    def test_analysis_json_fields(self, db: Session, user_with_id: uuid.UUID):
        params = {"threshold": 0.3, "index": "NDVI"}
        results = {"mean_ndvi": 0.45, "zones": [1, 2, 3]}
        analysis = AnalisisGee(
            tipo=TipoAnalisis.VEGETACION,
            fecha_inicio=date(2026, 2, 1),
            fecha_fin=date(2026, 2, 28),
            resultados=results,
            parametros=params,
            usuario_id=user_with_id,
        )
        db.add(analysis)
        db.flush()

        assert analysis.parametros["threshold"] == 0.3
        assert analysis.resultados["zones"] == [1, 2, 3]


# ──────────────────────────────────────────────
# REPOSITORY TESTS
# ──────────────────────────────────────────────


class TestMonitoringRepository:
    """Repository tests against real DB (rolled-back transactions)."""

    # ── Sugerencias ──

    def test_create_and_get_sugerencia(
        self,
        db: Session,
        repo: MonitoringRepository,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        created = repo.create_sugerencia(db, sample_sugerencia_data)
        db.flush()

        fetched = repo.get_sugerencia_by_id(db, created.id)
        assert fetched is not None
        assert fetched.titulo == "Mejorar camino rural zona norte"
        assert fetched.contacto_email == "vecino@example.com"

    def test_get_sugerencia_returns_none(self, db: Session, repo: MonitoringRepository):
        result = repo.get_sugerencia_by_id(db, uuid.uuid4())
        assert result is None

    def test_get_all_sugerencias_pagination(
        self,
        db: Session,
        repo: MonitoringRepository,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        for _ in range(5):
            repo.create_sugerencia(db, sample_sugerencia_data)
        db.flush()

        items, total = repo.get_all_sugerencias(db, page=1, limit=3)
        assert total == 5
        assert len(items) == 3

        items2, total2 = repo.get_all_sugerencias(db, page=2, limit=3)
        assert total2 == 5
        assert len(items2) == 2

    def test_get_all_sugerencias_filter_by_estado(
        self,
        db: Session,
        repo: MonitoringRepository,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        repo.create_sugerencia(db, sample_sugerencia_data)
        db.flush()

        items, total = repo.get_all_sugerencias(
            db, estado_filter=EstadoSugerencia.PENDIENTE
        )
        assert total >= 1

        items_none, total_none = repo.get_all_sugerencias(
            db, estado_filter=EstadoSugerencia.IMPLEMENTADA
        )
        assert total_none == 0

    def test_get_all_sugerencias_filter_by_categoria(
        self,
        db: Session,
        repo: MonitoringRepository,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        repo.create_sugerencia(db, sample_sugerencia_data)
        db.flush()

        items, total = repo.get_all_sugerencias(
            db, categoria_filter="infraestructura"
        )
        assert total >= 1

        items_none, total_none = repo.get_all_sugerencias(
            db, categoria_filter="nonexistent"
        )
        assert total_none == 0

    def test_update_sugerencia(
        self,
        db: Session,
        repo: MonitoringRepository,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        created = repo.create_sugerencia(db, sample_sugerencia_data)
        db.flush()

        update_data = SugerenciaUpdate(
            estado=EstadoSugerencia.REVISADA,
            respuesta="Estamos evaluando la sugerencia",
        )
        updated = repo.update_sugerencia(db, created.id, update_data)

        assert updated is not None
        assert updated.estado == EstadoSugerencia.REVISADA
        assert updated.respuesta == "Estamos evaluando la sugerencia"

    def test_update_nonexistent_returns_none(
        self, db: Session, repo: MonitoringRepository
    ):
        update_data = SugerenciaUpdate(estado=EstadoSugerencia.REVISADA)
        result = repo.update_sugerencia(db, uuid.uuid4(), update_data)
        assert result is None

    # ── Analyses ──

    def test_save_and_get_analysis(
        self,
        db: Session,
        repo: MonitoringRepository,
        user_with_id: uuid.UUID,
    ):
        data = {
            "tipo": TipoAnalisis.INUNDACION,
            "fecha_inicio": date(2026, 3, 1),
            "fecha_fin": date(2026, 3, 15),
            "resultados": {"hectareas": 500},
            "hectareas_afectadas": 500.0,
            "porcentaje_area": 12.5,
            "parametros": {"cloud_cover": 10},
            "usuario_id": user_with_id,
        }
        created = repo.save_analysis(db, data)
        db.flush()

        fetched = repo.get_analysis_by_id(db, created.id)
        assert fetched is not None
        assert fetched.tipo == TipoAnalisis.INUNDACION
        assert fetched.hectareas_afectadas == pytest.approx(500.0)

    def test_get_analysis_returns_none(self, db: Session, repo: MonitoringRepository):
        result = repo.get_analysis_by_id(db, uuid.uuid4())
        assert result is None

    def test_analysis_history_pagination(
        self,
        db: Session,
        repo: MonitoringRepository,
        user_with_id: uuid.UUID,
    ):
        for i in range(4):
            repo.save_analysis(
                db,
                {
                    "tipo": TipoAnalisis.VEGETACION,
                    "fecha_inicio": date(2026, 1, 1),
                    "fecha_fin": date(2026, 1, 31),
                    "resultados": {"run": i},
                    "parametros": {},
                    "usuario_id": user_with_id,
                },
            )
        db.flush()

        items, total = repo.get_analysis_history(db, page=1, limit=2)
        assert total == 4
        assert len(items) == 2

    def test_analysis_history_filter_by_tipo(
        self,
        db: Session,
        repo: MonitoringRepository,
        user_with_id: uuid.UUID,
    ):
        repo.save_analysis(
            db,
            {
                "tipo": TipoAnalisis.SAR,
                "fecha_inicio": date(2026, 1, 1),
                "fecha_fin": date(2026, 1, 31),
                "resultados": {},
                "parametros": {},
                "usuario_id": user_with_id,
            },
        )
        db.flush()

        items, total = repo.get_analysis_history(
            db, tipo_filter=TipoAnalisis.SAR
        )
        assert total >= 1

        items_none, total_none = repo.get_analysis_history(
            db, tipo_filter=TipoAnalisis.CLASIFICACION
        )
        assert total_none == 0

    def test_get_latest_analyses(
        self,
        db: Session,
        repo: MonitoringRepository,
        user_with_id: uuid.UUID,
    ):
        for i in range(3):
            repo.save_analysis(
                db,
                {
                    "tipo": TipoAnalisis.INUNDACION,
                    "fecha_inicio": date(2026, 1, 1),
                    "fecha_fin": date(2026, 1, 31),
                    "resultados": {"run": i},
                    "parametros": {},
                    "usuario_id": user_with_id,
                },
            )
        db.flush()

        latest = repo.get_latest_analyses(db, limit=2)
        assert len(latest) == 2

    # ── Dashboard Stats ──

    def test_get_dashboard_stats(
        self,
        db: Session,
        repo: MonitoringRepository,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        # Create a sugerencia so there's data
        repo.create_sugerencia(db, sample_sugerencia_data)
        db.flush()

        stats = repo.get_dashboard_stats(db)

        assert "denuncias" in stats
        assert "total_assets" in stats
        assert "total_tramites" in stats
        assert "total_sugerencias" in stats
        assert stats["total_sugerencias"] >= 1
        assert "resumen_financiero" in stats
        assert "balance" in stats["resumen_financiero"]
        assert "latest_analyses" in stats


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────


class TestMonitoringService:
    """Service-layer tests."""

    def test_create_sugerencia(
        self,
        db: Session,
        service: MonitoringService,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        sugerencia = service.create_sugerencia(db, sample_sugerencia_data)
        assert sugerencia.id is not None
        assert sugerencia.estado == EstadoSugerencia.PENDIENTE

    def test_get_sugerencia_raises_on_missing(
        self, db: Session, service: MonitoringService
    ):
        with pytest.raises(Exception) as exc_info:
            service.get_sugerencia(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_list_sugerencias(
        self,
        db: Session,
        service: MonitoringService,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        service.create_sugerencia(db, sample_sugerencia_data)
        items, total = service.list_sugerencias(db, page=1, limit=10)
        assert total >= 1
        assert len(items) >= 1

    def test_update_sugerencia(
        self,
        db: Session,
        service: MonitoringService,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        created = service.create_sugerencia(db, sample_sugerencia_data)
        updated = service.update_sugerencia(
            db,
            created.id,
            SugerenciaUpdate(
                estado=EstadoSugerencia.IMPLEMENTADA,
                respuesta="Implementado en marzo 2026",
            ),
        )
        assert updated.estado == EstadoSugerencia.IMPLEMENTADA
        assert updated.respuesta == "Implementado en marzo 2026"

    def test_update_sugerencia_raises_on_missing(
        self, db: Session, service: MonitoringService
    ):
        with pytest.raises(Exception) as exc_info:
            service.update_sugerencia(
                db, uuid.uuid4(), SugerenciaUpdate(estado=EstadoSugerencia.REVISADA)
            )
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_get_analysis_raises_on_missing(
        self, db: Session, service: MonitoringService
    ):
        with pytest.raises(Exception) as exc_info:
            service.get_analysis(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    def test_save_and_list_analyses(
        self,
        db: Session,
        service: MonitoringService,
        user_with_id: uuid.UUID,
    ):
        analysis = service.save_analysis(
            db,
            {
                "tipo": TipoAnalisis.CLASIFICACION,
                "fecha_inicio": date(2026, 3, 1),
                "fecha_fin": date(2026, 3, 15),
                "resultados": {"classes": 4},
                "parametros": {"method": "random_forest"},
                "usuario_id": user_with_id,
            },
        )
        assert analysis.id is not None

        items, total = service.list_analyses(db, page=1, limit=10)
        assert total >= 1

    def test_get_dashboard_stats(
        self,
        db: Session,
        service: MonitoringService,
        sample_sugerencia_data: SugerenciaCreate,
    ):
        service.create_sugerencia(db, sample_sugerencia_data)
        stats = service.get_dashboard_stats(db)
        assert "total_sugerencias" in stats
        assert stats["total_sugerencias"] >= 1
