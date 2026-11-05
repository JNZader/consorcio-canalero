"""DOM wave-3: presupuestos, analisis_gee, proxima reunion, ARCO stats, and the smaller domain guards."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from geoalchemy2.functions import ST_MakePoint, ST_SetSRID
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.domains.capas.schemas import CapaCreate, CapaUpdate
from app.domains.denuncias.models import Denuncia, EstadoDenuncia
from app.domains.denuncias.repository import DenunciaRepository
from app.domains.denuncias.schemas import DenunciaUpdate, HistorialResponse
from app.domains.denuncias.service import DenunciaService
from app.domains.finanzas.models import Ingreso
from app.domains.finanzas.schemas import (
    GastoResponse,
    GastoUpdate,
    IngresoResponse,
    PresupuestoCreate,
    PresupuestoUpdate,
)
from app.domains.finanzas.service import FinanzasService
from app.domains.monitoring.models import AnalisisGee, EstadoSugerencia, Sugerencia, TipoAnalisis
from app.domains.monitoring.repository import MonitoringRepository
from app.domains.monitoring.schemas import AnalisisGeeResponse, SugerenciaUpdate
from app.domains.monitoring.service import MonitoringService
from app.domains.padron.models import Consorcista
from app.domains.padron.schemas import ConsorcistaCreate, ConsorcistaUpdate
from app.domains.reuniones.schemas import ReunionCreate, ReunionResponse, ReunionUpdate
from app.domains.settings.repository import SettingsRepository
from app.domains.settings.schemas import BrandingResponse, SettingUpdate
from app.domains.settings.service import SettingsService
from app.domains.tramites.schemas import (
    SeguimientoResponse,
    TramiteCreate,
    TramiteResponse,
    TramiteUpdate,
)
from app.domains.tramites.service import TramiteService
from app.shared.audit_log import AuditLog
from app.shared.local_date import hoy_argentina


def _user(db: Session) -> uuid.UUID:
    user = User(
        email=f"dom-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="fakehash",
        nombre="Op",
        apellido="Test",
        role=UserRole.OPERADOR,
    )
    db.add(user)
    db.flush()
    return user.id


def _denuncia(db: Session, user_id: uuid.UUID, *, deleted_at: datetime | None = None) -> Denuncia:
    row = Denuncia(
        tipo="desborde",
        descripcion="Denuncia de prueba para estadisticas DOM.",
        latitud=-33.7,
        longitud=-63.9,
        geom=ST_SetSRID(ST_MakePoint(-63.9, -33.7), 4326),
        estado=EstadoDenuncia.PENDIENTE,
        user_id=user_id,
        deleted_at=deleted_at,
    )
    db.add(row)
    db.flush()
    return row


def _sugerencia(
    db: Session,
    *,
    estado: EstadoSugerencia = EstadoSugerencia.PENDIENTE,
    fecha_reunion: date | None = None,
) -> Sugerencia:
    row = Sugerencia(
        titulo="Arreglar el puente del km 4",
        descripcion="La losa del puente del km 4 esta partida.",
        estado=estado,
        fecha_reunion=fecha_reunion,
    )
    db.add(row)
    db.flush()
    return row


def _consorcista(db: Session) -> Consorcista:
    row = Consorcista(
        nombre="Ana",
        apellido="Diaz",
        cuit=f"20-{uuid.uuid4().hex[:8]}",
    )
    db.add(row)
    db.flush()
    return row


class TestPresupuestoConflict:
    def test_duplicate_post_is_409_and_patch_updates_the_line(self, db: Session):
        service = FinanzasService()
        payload = PresupuestoCreate(
            anio=2091, rubro="mantenimiento", monto_proyectado=Decimal("10.00")
        )
        created = service.create_presupuesto(db, payload)

        with pytest.raises(HTTPException) as exc:
            service.create_presupuesto(db, payload)
        assert exc.value.status_code == 409

        updated = service.update_presupuesto(
            db,
            created.id,
            PresupuestoUpdate(monto_proyectado=Decimal("25.50")),
        )
        assert updated.monto_proyectado == Decimal("25.50")

        with pytest.raises(HTTPException) as missing:
            service.update_presupuesto(
                db, uuid.uuid4(), PresupuestoUpdate(monto_proyectado=Decimal("1"))
            )
        assert missing.value.status_code == 404

    def test_integrity_error_after_the_precheck_is_still_409(self, db: Session, monkeypatch):
        service = FinanzasService()
        payload = PresupuestoCreate(anio=2092, rubro="obras", monto_proyectado=Decimal("10.00"))
        service.create_presupuesto(db, payload)
        monkeypatch.setattr(service.repo, "get_by_anio_rubro", lambda *_args, **_kwargs: None)

        with pytest.raises(HTTPException) as exc:
            service.create_presupuesto(db, payload)
        assert exc.value.status_code == 409
        assert service.repo.get_presupuestos(db, year_filter=2092)


class TestAnalisisGeeUserDelete:
    def test_delete_usuario_nulls_analisis_gee(self, db: Session):
        user_id = _user(db)
        analysis = AnalisisGee(
            tipo=TipoAnalisis.INUNDACION,
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 1, 31),
            resultados={},
            parametros={},
            usuario_id=user_id,
        )
        db.add(analysis)
        db.flush()

        user = db.get(User, user_id)
        assert user is not None
        db.delete(user)
        db.flush()
        db.expire_all()

        stored = db.get(AnalisisGee, analysis.id)
        assert stored is not None
        assert stored.usuario_id is None
        assert AnalisisGeeResponse.model_validate(stored).usuario_id is None


class TestProximaReunion:
    def test_orders_future_fecha_reunion_and_skips_unscheduled(self, db: Session):
        hoy = date(2026, 11, 5)
        later = _sugerencia(
            db,
            estado=EstadoSugerencia.PENDIENTE,
            fecha_reunion=hoy + timedelta(days=10),
        )
        sooner = _sugerencia(
            db,
            estado=EstadoSugerencia.REVISADA,
            fecha_reunion=hoy + timedelta(days=1),
        )
        _sugerencia(db, estado=EstadoSugerencia.REVISADA, fecha_reunion=hoy - timedelta(days=1))
        _sugerencia(db, estado=EstadoSugerencia.REVISADA, fecha_reunion=None)
        today = _sugerencia(
            db,
            estado=EstadoSugerencia.DESCARTADA,
            fecha_reunion=hoy,
        )

        rows = MonitoringRepository().get_proxima_reunion(db, hoy=hoy)
        ids = [row.id for row in rows]
        assert ids[:3] == [today.id, sooner.id, later.id]
        assert hoy - timedelta(days=1) not in {row.fecha_reunion for row in rows}


class TestDenunciaStatsExcludeSoftDeleted:
    def test_operator_stats_and_dashboard_skip_deleted(self, db: Session):
        user_id = _user(db)
        denuncias = DenunciaRepository()
        monitoring = MonitoringRepository()
        before_stats = denuncias.get_stats(db)["total"]
        before_dash = monitoring.get_dashboard_stats(db)["denuncias"]["total"]

        _denuncia(db, user_id)
        _denuncia(db, user_id, deleted_at=datetime.now(tz=timezone.utc))

        assert denuncias.get_stats(db)["total"] == before_stats + 1
        dash = monitoring.get_dashboard_stats(db)
        assert dash["denuncias"]["total"] == before_dash + 1


class TestReunionAwareDatetime:
    def test_naive_datetime_is_rejected(self):
        with pytest.raises(ValidationError):
            ReunionCreate(
                titulo="Comision de noviembre",
                fecha_reunion=datetime(2026, 11, 5, 10, 0),
            )
        created = ReunionCreate(
            titulo="Comision de noviembre",
            fecha_reunion=datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc),
        )
        assert created.fecha_reunion.tzinfo is not None

        with pytest.raises(ValidationError):
            ReunionUpdate(fecha_reunion=datetime(2026, 11, 5, 10, 0))


class TestSugerenciaStateMachine:
    def test_illegal_transition_is_400_and_legal_one_is_audited(self, db: Session):
        user_id = _user(db)
        service = MonitoringService()
        row = _sugerencia(db)
        updated = service.update_sugerencia(
            db,
            row.id,
            SugerenciaUpdate(estado="implementada"),
            operator_id=user_id,
        )
        assert updated.estado == EstadoSugerencia.IMPLEMENTADA

        with pytest.raises(HTTPException) as exc:
            service.update_sugerencia(
                db,
                row.id,
                SugerenciaUpdate(estado="descartada"),
                operator_id=user_id,
            )
        assert exc.value.status_code == 400

        audits = list(
            db.execute(select(AuditLog).where(AuditLog.action == "sugerencia.estado")).scalars()
        )
        assert any(str(row.id) in entry.resource for entry in audits)

        with pytest.raises(ValidationError):
            SugerenciaUpdate(estado="no-es-un-estado")


class TestInvalidEnums:
    def test_filters_and_writes_reject_unknown_values(self):
        denuncias = DenunciaService(repository=MagicMock())
        with pytest.raises(HTTPException) as denuncia_exc:
            denuncias.list_denuncias(MagicMock(), estado="foo")
        assert denuncia_exc.value.status_code == 422

        tramites = TramiteService(repository=MagicMock())
        with pytest.raises(HTTPException) as tramite_exc:
            tramites.list_tramites(MagicMock(), tipo="foo")
        assert tramite_exc.value.status_code == 422

        settings = SettingsService(repository=MagicMock())
        with pytest.raises(HTTPException) as settings_exc:
            settings.get_settings_by_category(MagicMock(), "no-existe")
        assert settings_exc.value.status_code == 422

        with pytest.raises(ValidationError):
            ConsorcistaCreate(
                nombre="Ana",
                apellido="Diaz",
                cuit="20-12345678-6",
                estado="foo",
            )
        with pytest.raises(ValidationError):
            TramiteCreate(
                tipo="nope",
                titulo="Titulo de tramite",
                descripcion="Descripcion suficientemente larga.",
                solicitante="Juan Perez",
            )
        with pytest.raises(ValidationError):
            TramiteUpdate(prioridad="nope")
        with pytest.raises(ValidationError):
            CapaCreate(nombre="Capa", tipo="nope", fuente="local")
        with pytest.raises(ValidationError):
            CapaUpdate(fuente="nope")


class TestOptionalUsuarioId:
    def test_response_schemas_accept_a_null_author(self):
        now = datetime.now(tz=timezone.utc)
        gasto = SimpleNamespace(
            id=uuid.uuid4(),
            descripcion="Gasto",
            monto=Decimal("1.00"),
            categoria="obras",
            fecha=date(2026, 1, 1),
            comprobante_url=None,
            proveedor=None,
            usuario_id=None,
            created_at=now,
            updated_at=now,
        )
        assert GastoResponse.model_validate(gasto).usuario_id is None

        ingreso = SimpleNamespace(
            id=uuid.uuid4(),
            descripcion="Ingreso",
            monto=Decimal("1.00"),
            categoria="cuotas",
            fecha=date(2026, 1, 1),
            consorcista_id=None,
            comprobante_url=None,
            usuario_id=None,
            created_at=now,
            updated_at=now,
        )
        assert IngresoResponse.model_validate(ingreso).usuario_id is None

        historial = SimpleNamespace(
            id=uuid.uuid4(),
            denuncia_id=uuid.uuid4(),
            estado_anterior="pendiente",
            estado_nuevo="en_revision",
            comentario=None,
            usuario_id=None,
            created_at=now,
        )
        assert HistorialResponse.model_validate(historial).usuario_id is None

        seguimiento = SimpleNamespace(
            id=uuid.uuid4(),
            tramite_id=uuid.uuid4(),
            estado_anterior="ingresado",
            estado_nuevo="en_tramite",
            comentario="sigue",
            usuario_id=None,
            created_at=now,
        )
        assert SeguimientoResponse.model_validate(seguimiento).usuario_id is None

        tramite = SimpleNamespace(
            id=uuid.uuid4(),
            tipo="obra",
            titulo="Obra",
            descripcion="Descripcion",
            solicitante="Ana",
            estado="ingresado",
            prioridad="media",
            fecha_ingreso=date(2026, 1, 1),
            fecha_resolucion=None,
            resolucion=None,
            usuario_id=None,
            created_at=now,
            updated_at=now,
            seguimiento=[],
        )
        assert TramiteResponse.model_validate(tramite).usuario_id is None

        reunion = SimpleNamespace(
            id=uuid.uuid4(),
            titulo="Comision",
            fecha_reunion=now,
            lugar="Sede",
            descripcion=None,
            tipo="ordinaria",
            estado="planificada",
            orden_del_dia_items=[],
            usuario_id=None,
            created_at=now,
            updated_at=now,
            agenda_items=[],
        )
        assert ReunionResponse.model_validate(reunion).usuario_id is None


class TestPatchExplicitNull:
    def test_explicit_null_on_not_null_columns_is_422(self):
        with pytest.raises(ValidationError):
            DenunciaUpdate(estado=None)
        with pytest.raises(ValidationError):
            GastoUpdate(descripcion=None)
        with pytest.raises(ValidationError):
            ConsorcistaUpdate(nombre=None)
        assert GastoUpdate().descripcion is None
        assert ConsorcistaUpdate(nombre="Ana").cuit is None


class TestIngresoConsorcistaFk:
    def test_unknown_consorcista_is_rejected_and_delete_nulls_the_fk(self, db: Session):
        user_id = _user(db)
        consorcista = _consorcista(db)
        ingreso = Ingreso(
            descripcion="Cuota",
            monto=Decimal("100.00"),
            categoria="cuotas",
            fecha=date(2026, 3, 1),
            consorcista_id=consorcista.id,
            usuario_id=user_id,
        )
        db.add(ingreso)
        db.flush()

        with pytest.raises(IntegrityError):
            with db.begin_nested():
                dangling = Ingreso(
                    descripcion="Huertano",
                    monto=Decimal("50.00"),
                    categoria="otros",
                    fecha=date(2026, 3, 2),
                    consorcista_id=uuid.uuid4(),
                    usuario_id=user_id,
                )
                db.add(dangling)
                db.flush()

        db.delete(consorcista)
        db.flush()
        db.expire_all()
        stored = db.get(Ingreso, ingreso.id)
        assert stored is not None
        assert stored.consorcista_id is None


class TestBrandingAndMapaSettingShape:
    def test_garbage_branding_does_not_break_the_public_read(self, db: Session):
        import app.domains.settings.service as settings_mod

        settings_mod._BRANDING_CACHE = None
        repo = SettingsRepository()
        repo.upsert(
            db,
            clave="branding/logo_url",
            valor={"no": "texto"},
            categoria="branding",
        )
        db.flush()

        service = SettingsService(repository=repo)
        with pytest.raises(HTTPException) as exc:
            service.update_setting(db, "branding/logo_url", {"todavia": "mal"})
        assert exc.value.status_code == 422

        with pytest.raises(HTTPException) as imagen:
            service.update_setting(db, "mapa/imagen_principal", {"sensor": "no"})
        assert imagen.value.status_code == 422

        settings_mod._BRANDING_CACHE = None
        branding = BrandingResponse(**service.get_branding(db))
        assert branding.logo_url is None


class TestSettingsOptimisticLock:
    def test_stale_updated_at_is_409_and_the_echoed_value_writes(self, db: Session):
        repo = SettingsRepository()
        setting = repo.upsert(
            db,
            clave=f"general/dom-{uuid.uuid4().hex[:8]}",
            valor="antes",
            categoria="general",
        )
        db.commit()
        db.refresh(setting)
        service = SettingsService(repository=repo)

        with pytest.raises(HTTPException) as exc:
            service.update_setting(
                db,
                setting.clave,
                "despues",
                expected_updated_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            )
        assert exc.value.status_code == 409

        locked = repo.get_by_key(db, setting.clave, for_update=True)
        assert locked is not None
        updated = service.update_setting(
            db,
            setting.clave,
            "despues",
            expected_updated_at=setting.updated_at,
            actor_id=None,
        )
        assert updated is not None
        assert updated.valor == "despues"
        audits = list(
            db.execute(
                select(AuditLog).where(AuditLog.resource == f"clave={setting.clave}")
            ).scalars()
        )
        assert audits
        assert SettingUpdate(valor="x", expected_updated_at=setting.updated_at).expected_updated_at


class TestTramiteFechaResolucion:
    def test_uses_art_calendar_and_clears_on_reopen(self, db: Session, monkeypatch):
        moment = datetime(2026, 11, 6, 2, 30, tzinfo=timezone.utc)
        assert hoy_argentina(moment) == date(2026, 11, 5)
        monkeypatch.setattr(
            "app.domains.tramites.service.hoy_argentina",
            lambda: date(2026, 11, 5),
        )

        user_id = _user(db)
        service = TramiteService()
        tramite = service.create(
            db,
            TramiteCreate(
                tipo="obra",
                titulo="Solicitud de obra menor",
                descripcion="Descripcion suficientemente larga.",
                solicitante="Juan Perez",
            ),
            usuario_id=user_id,
        )
        service.update(
            db,
            tramite.id,
            TramiteUpdate(estado="en_tramite"),
            operator_id=user_id,
        )
        rejected = service.update(
            db,
            tramite.id,
            TramiteUpdate(estado="rechazado"),
            operator_id=user_id,
        )
        assert rejected.fecha_resolucion == date(2026, 11, 5)

        reopened = service.update(
            db,
            tramite.id,
            TramiteUpdate(estado="ingresado"),
            operator_id=user_id,
        )
        assert reopened.fecha_resolucion is None
