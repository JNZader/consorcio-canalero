"""Pydantic schema validation contract tests for ALL domains.

Validates that Create/Update schemas enforce constraints and
Response schemas correctly serialize with from_attributes=True.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pytest
from pydantic import ValidationError

# ──────────────────────────────────────────────
# FINANZAS
# ──────────────────────────────────────────────

from app.domains.finanzas.schemas import (
    BudgetExecutionResponse,
    FinancialSummaryResponse,
    GastoCreate,
    GastoListResponse,
    GastoResponse,
    GastoUpdate,
    IngresoCreate,
    IngresoListResponse,
    IngresoResponse,
    IngresoUpdate,
    PresupuestoCreate,
    PresupuestoResponse,
    PresupuestoUpdate,
)


class TestGastoCreate:
    """Contract: GastoCreate validation rules."""

    def test_valid_gasto(self):
        g = GastoCreate(
            descripcion="Compra de materiales",
            monto=Decimal("1500.50"),
            categoria="obras",
            fecha=date(2025, 6, 15),
        )
        assert g.descripcion == "Compra de materiales"
        assert g.monto == Decimal("1500.50")
        assert g.comprobante_url is None
        assert g.proveedor is None

    def test_descripcion_min_length(self):
        with pytest.raises(ValidationError, match="String should have at least 3"):
            GastoCreate(
                descripcion="ab",
                monto=Decimal("100"),
                categoria="obras",
                fecha=date(2025, 1, 1),
            )

    def test_descripcion_max_length(self):
        with pytest.raises(ValidationError):
            GastoCreate(
                descripcion="x" * 2001,
                monto=Decimal("100"),
                categoria="obras",
                fecha=date(2025, 1, 1),
            )

    def test_monto_must_be_positive(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            GastoCreate(
                descripcion="Test gasto",
                monto=Decimal("0"),
                categoria="obras",
                fecha=date(2025, 1, 1),
            )

    def test_monto_negative_rejected(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            GastoCreate(
                descripcion="Test gasto",
                monto=Decimal("-100"),
                categoria="obras",
                fecha=date(2025, 1, 1),
            )

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            GastoCreate()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert {"descripcion", "monto", "categoria", "fecha"} <= missing_fields

    def test_optional_fields_default_none(self):
        g = GastoCreate(
            descripcion="Test",
            monto=Decimal("50"),
            categoria="otros",
            fecha=date(2025, 1, 1),
        )
        assert g.comprobante_url is None
        assert g.proveedor is None

    def test_proveedor_max_length(self):
        with pytest.raises(ValidationError):
            GastoCreate(
                descripcion="Test gasto",
                monto=Decimal("100"),
                categoria="obras",
                fecha=date(2025, 1, 1),
                proveedor="x" * 201,
            )


class TestGastoUpdate:
    """Contract: GastoUpdate partial update schema."""

    def test_all_fields_optional(self):
        g = GastoUpdate()
        assert g.descripcion is None
        assert g.monto is None
        assert g.categoria is None

    def test_partial_update(self):
        g = GastoUpdate(monto=Decimal("200"))
        assert g.monto == Decimal("200")
        assert g.descripcion is None

    def test_monto_must_be_positive_when_provided(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            GastoUpdate(monto=Decimal("0"))


class TestGastoResponse:
    """Contract: GastoResponse serialization from ORM."""

    def _make_orm_obj(self, **overrides) -> Any:
        """Build a mock ORM-like object with attribute access."""

        class FakeGasto:
            pass

        obj = FakeGasto()
        defaults = {
            "id": uuid.uuid4(),
            "descripcion": "Test gasto",
            "monto": Decimal("100.50"),
            "categoria": "obras",
            "fecha": date(2025, 6, 1),
            "comprobante_url": None,
            "proveedor": None,
            "usuario_id": uuid.uuid4(),
            "created_at": datetime(2025, 6, 1, 10, 0, 0),
            "updated_at": datetime(2025, 6, 1, 10, 0, 0),
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            setattr(obj, k, v)
        return obj

    def test_from_orm_object(self):
        obj = self._make_orm_obj()
        resp = GastoResponse.model_validate(obj)
        assert isinstance(resp.id, uuid.UUID)
        assert resp.descripcion == "Test gasto"

    def test_serializes_to_dict(self):
        obj = self._make_orm_obj()
        resp = GastoResponse.model_validate(obj)
        d = resp.model_dump()
        assert "id" in d
        assert "created_at" in d
        assert isinstance(d["fecha"], date)

    def test_uuid_fields_validate(self):
        obj = self._make_orm_obj()
        resp = GastoResponse.model_validate(obj)
        assert isinstance(resp.id, uuid.UUID)
        assert isinstance(resp.usuario_id, uuid.UUID)


class TestGastoListResponse:
    """Contract: GastoListResponse lightweight serialization."""

    def test_from_orm_object(self):
        class FakeGasto:
            id = uuid.uuid4()
            descripcion = "Desc"
            monto = Decimal("50")
            categoria = "otros"
            fecha = date(2025, 1, 1)
            proveedor = None
            created_at = datetime(2025, 1, 1)

        resp = GastoListResponse.model_validate(FakeGasto())
        assert resp.proveedor is None


class TestIngresoCreate:
    """Contract: IngresoCreate validation."""

    def test_valid_ingreso(self):
        i = IngresoCreate(
            descripcion="Cuota mensual",
            monto=Decimal("5000"),
            categoria="cuotas",
            fecha=date(2025, 3, 1),
        )
        assert i.consorcista_id is None

    def test_descripcion_min_length(self):
        with pytest.raises(ValidationError, match="at least 3"):
            IngresoCreate(
                descripcion="ab",
                monto=Decimal("100"),
                categoria="cuotas",
                fecha=date(2025, 1, 1),
            )

    def test_monto_must_be_positive(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            IngresoCreate(
                descripcion="Test ingreso",
                monto=Decimal("0"),
                categoria="cuotas",
                fecha=date(2025, 1, 1),
            )

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            IngresoCreate()
        errors = exc_info.value.errors()
        missing = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert {"descripcion", "monto", "categoria", "fecha"} <= missing

    def test_consorcista_id_accepts_uuid(self):
        uid = uuid.uuid4()
        i = IngresoCreate(
            descripcion="Test",
            monto=Decimal("100"),
            categoria="cuotas",
            fecha=date(2025, 1, 1),
            consorcista_id=uid,
        )
        assert i.consorcista_id == uid


class TestIngresoUpdate:
    """Contract: IngresoUpdate partial update."""

    def test_all_optional(self):
        u = IngresoUpdate()
        assert u.descripcion is None
        assert u.monto is None

    def test_monto_positive_when_provided(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            IngresoUpdate(monto=Decimal("-10"))


class TestIngresoResponse:
    """Contract: IngresoResponse from ORM."""

    def test_from_orm(self):
        class FakeIngreso:
            id = uuid.uuid4()
            descripcion = "Cuota"
            monto = Decimal("5000")
            categoria = "cuotas"
            fecha = date(2025, 1, 1)
            consorcista_id = None
            comprobante_url = None
            usuario_id = uuid.uuid4()
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = IngresoResponse.model_validate(FakeIngreso())
        assert isinstance(resp.id, uuid.UUID)


class TestPresupuestoCreate:
    """Contract: PresupuestoCreate budget validation."""

    def test_valid_presupuesto(self):
        p = PresupuestoCreate(
            anio=2025,
            rubro="mantenimiento",
            monto_proyectado=Decimal("50000"),
        )
        assert p.anio == 2025

    def test_anio_range(self):
        with pytest.raises(ValidationError, match="greater than or equal to 2000"):
            PresupuestoCreate(
                anio=1999, rubro="test", monto_proyectado=Decimal("100")
            )
        with pytest.raises(ValidationError, match="less than or equal to 2100"):
            PresupuestoCreate(
                anio=2101, rubro="test", monto_proyectado=Decimal("100")
            )

    def test_monto_proyectado_non_negative(self):
        p = PresupuestoCreate(
            anio=2025, rubro="test", monto_proyectado=Decimal("0")
        )
        assert p.monto_proyectado == Decimal("0")
        with pytest.raises(ValidationError):
            PresupuestoCreate(
                anio=2025, rubro="test", monto_proyectado=Decimal("-1")
            )

    def test_rubro_min_length(self):
        with pytest.raises(ValidationError, match="at least 2"):
            PresupuestoCreate(
                anio=2025, rubro="x", monto_proyectado=Decimal("100")
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError) as exc_info:
            PresupuestoCreate()
        errors = exc_info.value.errors()
        missing = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert {"anio", "rubro", "monto_proyectado"} <= missing


class TestPresupuestoUpdate:
    def test_all_optional(self):
        u = PresupuestoUpdate()
        assert u.monto_proyectado is None

    def test_monto_non_negative_when_provided(self):
        with pytest.raises(ValidationError):
            PresupuestoUpdate(monto_proyectado=Decimal("-1"))


class TestPresupuestoResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            anio = 2025
            rubro = "obras"
            monto_proyectado = Decimal("50000")
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = PresupuestoResponse.model_validate(Fake())
        assert resp.anio == 2025


class TestFinancialReports:
    def test_budget_execution_response(self):
        r = BudgetExecutionResponse(
            rubro="obras", proyectado=Decimal("10000"), real=Decimal("8000")
        )
        assert r.rubro == "obras"

    def test_financial_summary(self):
        s = FinancialSummaryResponse(
            anio=2025,
            total_ingresos=Decimal("100000"),
            total_gastos=Decimal("80000"),
            balance=Decimal("20000"),
        )
        assert s.balance == Decimal("20000")


# ──────────────────────────────────────────────
# GEO
# ──────────────────────────────────────────────

from app.domains.geo.models import TipoGeoJob
from app.domains.geo.schemas import (
    AnalisisGeoCreate,
    AnalisisGeoListResponse,
    AnalisisGeoResponse,
    DemPipelineRequest,
    DemPipelineResponse,
    FloodEventCreate,
    FloodEventListResponse,
    FloodEventResponse,
    FloodLabelCreate,
    FloodLabelResponse,
    GeoJobCreate,
    GeoJobListResponse,
    GeoJobResponse,
    GeoLayerListResponse,
    GeoLayerResponse,
    TrainingResultResponse,
)


class TestGeoJobCreate:
    def test_valid_job(self):
        j = GeoJobCreate(tipo=TipoGeoJob.DEM_PIPELINE)
        assert j.tipo == TipoGeoJob.DEM_PIPELINE
        assert j.parametros == {}

    def test_invalid_tipo_rejected(self):
        with pytest.raises(ValidationError):
            GeoJobCreate(tipo="nonexistent_tipo")

    def test_all_enum_values_accepted(self):
        for t in TipoGeoJob:
            j = GeoJobCreate(tipo=t)
            assert j.tipo == t

    def test_parametros_default_empty(self):
        j = GeoJobCreate(tipo=TipoGeoJob.SLOPE)
        assert j.parametros == {}

    def test_parametros_with_data(self):
        j = GeoJobCreate(
            tipo=TipoGeoJob.DEM_PIPELINE,
            parametros={"area_id": "zona_1", "threshold": 500},
        )
        assert j.parametros["area_id"] == "zona_1"


class TestGeoJobResponse:
    def test_from_orm(self):
        class FakeJob:
            id = uuid.uuid4()
            tipo = "dem_pipeline"
            estado = "completed"
            celery_task_id = "abc-123"
            parametros = {"area_id": "test"}
            resultado = {"output": "ok"}
            error = None
            progreso = 100
            usuario_id = uuid.uuid4()
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = GeoJobResponse.model_validate(FakeJob())
        assert resp.progreso == 100
        assert resp.estado == "completed"

    def test_progreso_default_zero(self):
        resp = GeoJobResponse(
            id=uuid.uuid4(),
            tipo="slope",
            estado="pending",
            created_at=datetime(2025, 1, 1),
            updated_at=datetime(2025, 1, 1),
        )
        assert resp.progreso == 0


class TestGeoLayerResponse:
    def test_from_orm(self):
        class FakeLayer:
            id = uuid.uuid4()
            nombre = "DEM Layer"
            tipo = "dem"
            fuente = "gee"
            archivo_path = "/data/dem.tif"
            formato = "GeoTIFF"
            srid = 4326
            bbox = [-60.0, -30.0, -59.0, -29.0]
            metadata_extra = None
            area_id = "zona_principal"
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = GeoLayerResponse.model_validate(FakeLayer())
        assert resp.srid == 4326
        assert len(resp.bbox) == 4


class TestAnalisisGeoCreate:
    def test_valid_analisis(self):
        a = AnalisisGeoCreate(tipo="flood", parametros={"method": "otsu"})
        assert a.tipo == "flood"
        assert a.fecha_inicio is None

    def test_missing_tipo(self):
        with pytest.raises(ValidationError):
            AnalisisGeoCreate(parametros={})

    def test_with_dates(self):
        a = AnalisisGeoCreate(
            tipo="ndvi",
            fecha_inicio=datetime(2025, 1, 1),
            fecha_fin=datetime(2025, 6, 1),
        )
        assert a.fecha_inicio < a.fecha_fin


class TestFloodLabelCreate:
    def test_valid_label(self):
        l = FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=True)
        assert l.is_flooded is True

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            FloodLabelCreate()


class TestFloodEventCreate:
    def test_valid_event(self):
        e = FloodEventCreate(
            event_date=date(2025, 3, 15),
            labels=[
                FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=True),
                FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=False),
            ],
        )
        assert len(e.labels) == 2
        assert e.description is None

    def test_labels_min_length(self):
        with pytest.raises(ValidationError, match="too_short"):
            FloodEventCreate(event_date=date(2025, 1, 1), labels=[])

    def test_missing_event_date(self):
        with pytest.raises(ValidationError):
            FloodEventCreate(
                labels=[FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=True)]
            )

    def test_with_description(self):
        e = FloodEventCreate(
            event_date=date(2025, 1, 1),
            description="Heavy rains in region",
            labels=[FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=True)],
        )
        assert e.description == "Heavy rains in region"


class TestFloodEventResponse:
    def test_from_orm(self):
        class FakeLabel:
            id = uuid.uuid4()
            zona_id = uuid.uuid4()
            is_flooded = True
            ndwi_value = 0.35
            extracted_features = {"ndwi_mean": 0.35}

        class FakeEvent:
            id = uuid.uuid4()
            event_date = date(2025, 3, 15)
            description = "Test event"
            satellite_source = "Sentinel-2"
            labels = [FakeLabel()]
            created_at = datetime(2025, 3, 15)
            updated_at = datetime(2025, 3, 15)

        resp = FloodEventResponse.model_validate(FakeEvent())
        assert len(resp.labels) == 1
        assert resp.satellite_source == "Sentinel-2"


class TestFloodEventListResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            event_date = date(2025, 1, 1)
            description = None
            label_count = 5
            created_at = datetime(2025, 1, 1)

        resp = FloodEventListResponse.model_validate(Fake())
        assert resp.label_count == 5


class TestTrainingResultResponse:
    def test_valid_response(self):
        r = TrainingResultResponse(
            events_used=10,
            epochs=100,
            initial_loss=0.693,
            final_loss=0.25,
            weights_before={"ndwi": 1.0, "slope": 0.5},
            weights_after={"ndwi": 1.2, "slope": 0.8},
            bias=-0.5,
            backup_path="/data/backup.json",
        )
        assert r.events_used == 10
        assert r.final_loss < r.initial_loss


class TestDemPipelineRequest:
    def test_defaults(self):
        r = DemPipelineRequest()
        assert r.area_id == "zona_principal"
        assert r.min_basin_area_ha == 5000.0

    def test_min_basin_area_non_negative(self):
        with pytest.raises(ValidationError):
            DemPipelineRequest(min_basin_area_ha=-1.0)


# ──────────────────────────────────────────────
# GEO INTELLIGENCE
# ──────────────────────────────────────────────

from app.domains.geo.intelligence.schemas import (
    AlertaResponse,
    AnalysisRequest,
    AnalysisSummaryResponse,
    BasinRiskRankingResponse,
    CaminoRiesgoResponse,
    CanalPrioridadResponse,
    CanalSuggestionResponse,
    CompositeAnalysisRequest,
    CompositeComparisonItemResponse,
    CompositeComparisonResponse,
    CompositeZonalStatsResponse,
    ConflictoDetectarRequest,
    CriticidadRequest,
    CriticidadResponse,
    DashboardInteligente,
    EscorrentiaRequest,
    EscorrentiaResponse,
    IndiceHidricoResponse,
    PuntoConflictoResponse,
    ZonaOperativaListResponse,
    ZonaOperativaResponse,
    ZonificacionRequest,
    ZonificacionResponse,
)


class TestCriticidadRequest:
    def test_valid_request(self):
        r = CriticidadRequest(
            zona_id=uuid.uuid4(),
            pendiente_media=0.5,
            acumulacion_media=0.7,
            twi_medio=0.3,
            proximidad_canal_m=100.0,
            historial_inundacion=0.8,
        )
        assert 0 <= r.pendiente_media <= 1

    def test_normalized_fields_bounded(self):
        with pytest.raises(ValidationError):
            CriticidadRequest(
                zona_id=uuid.uuid4(),
                pendiente_media=1.5,  # > 1
                acumulacion_media=0.5,
                twi_medio=0.5,
                proximidad_canal_m=100.0,
                historial_inundacion=0.5,
            )

    def test_negative_normalized_rejected(self):
        with pytest.raises(ValidationError):
            CriticidadRequest(
                zona_id=uuid.uuid4(),
                pendiente_media=-0.1,
                acumulacion_media=0.5,
                twi_medio=0.5,
                proximidad_canal_m=100.0,
                historial_inundacion=0.5,
            )

    def test_proximidad_non_negative(self):
        with pytest.raises(ValidationError):
            CriticidadRequest(
                zona_id=uuid.uuid4(),
                pendiente_media=0.5,
                acumulacion_media=0.5,
                twi_medio=0.5,
                proximidad_canal_m=-10.0,
                historial_inundacion=0.5,
            )

    def test_custom_weights(self):
        r = CriticidadRequest(
            zona_id=uuid.uuid4(),
            pendiente_media=0.5,
            acumulacion_media=0.5,
            twi_medio=0.5,
            proximidad_canal_m=100.0,
            historial_inundacion=0.5,
            pesos={"pendiente": 0.3, "twi": 0.7},
        )
        assert r.pesos is not None


class TestCriticidadResponse:
    def test_valid_response(self):
        r = CriticidadResponse(
            zona_id=uuid.uuid4(),
            indice_final=0.72,
            nivel_riesgo="alto",
            componentes={"pendiente": 0.3, "twi": 0.42},
        )
        assert r.nivel_riesgo == "alto"


class TestEscorrentiaRequest:
    def test_valid_request(self):
        r = EscorrentiaRequest(
            punto_inicio=[-60.5, -30.2],
            lluvia_mm=50.0,
        )
        assert len(r.punto_inicio) == 2

    def test_punto_must_have_two_elements(self):
        with pytest.raises(ValidationError):
            EscorrentiaRequest(
                punto_inicio=[-60.5],
                lluvia_mm=50.0,
            )
        with pytest.raises(ValidationError):
            EscorrentiaRequest(
                punto_inicio=[-60.5, -30.2, 100.0],
                lluvia_mm=50.0,
            )

    def test_lluvia_must_be_positive(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            EscorrentiaRequest(punto_inicio=[-60.5, -30.2], lluvia_mm=0)

    def test_lluvia_max(self):
        with pytest.raises(ValidationError, match="less than or equal to 500"):
            EscorrentiaRequest(punto_inicio=[-60.5, -30.2], lluvia_mm=501)


class TestEscorrentiaResponse:
    def test_defaults(self):
        r = EscorrentiaResponse(features=[])
        assert r.type == "FeatureCollection"
        assert r.properties is None


class TestConflictoDetectarRequest:
    def test_defaults(self):
        r = ConflictoDetectarRequest()
        assert r.buffer_m == 50.0
        assert r.flow_acc_threshold == 500.0
        assert r.slope_threshold == 5.0

    def test_buffer_bounds(self):
        with pytest.raises(ValidationError):
            ConflictoDetectarRequest(buffer_m=5)  # < 10
        with pytest.raises(ValidationError):
            ConflictoDetectarRequest(buffer_m=501)  # > 500


class TestZonificacionRequest:
    def test_valid_request(self):
        r = ZonificacionRequest(dem_layer_id=uuid.uuid4())
        assert r.threshold == 2000

    def test_threshold_min(self):
        with pytest.raises(ValidationError):
            ZonificacionRequest(dem_layer_id=uuid.uuid4(), threshold=50)


class TestZonaOperativaResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            nombre = "Zona Norte"
            cuenca = "Cuenca A"
            superficie_ha = 1500.0
            geometria = None
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = ZonaOperativaResponse.model_validate(Fake())
        assert resp.nombre == "Zona Norte"


class TestIndiceHidricoResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            zona_id = uuid.uuid4()
            fecha_calculo = date(2025, 1, 1)
            pendiente_media = 0.3
            acumulacion_media = 0.6
            twi_medio = 0.5
            proximidad_canal_m = 200.0
            historial_inundacion = 0.7
            indice_final = 0.65
            nivel_riesgo = "alto"
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = IndiceHidricoResponse.model_validate(Fake())
        assert resp.nivel_riesgo == "alto"


class TestPuntoConflictoResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            tipo = "intersection"
            descripcion = "Canal crosses road"
            severidad = "alto"
            infraestructura_ids = ["canal-1", "camino-5"]
            acumulacion_valor = 1500.0
            pendiente_valor = 2.5
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = PuntoConflictoResponse.model_validate(Fake())
        assert len(resp.infraestructura_ids) == 2


class TestDashboardInteligente:
    def test_valid_dashboard(self):
        d = DashboardInteligente(
            porcentaje_area_riesgo=35.5,
            canales_criticos=3,
            caminos_vulnerables=2,
            conflictos_activos=5,
            alertas_activas=1,
        )
        assert d.zonas_por_nivel == {}
        assert d.evolucion_temporal == []

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            DashboardInteligente()


class TestCompositeAnalysisRequest:
    def test_valid_request(self):
        r = CompositeAnalysisRequest(area_id="zona_principal")
        assert r.weights_flood is None
        assert r.weights_drainage is None

    def test_with_custom_weights(self):
        r = CompositeAnalysisRequest(
            area_id="zona_1",
            weights_flood={"twi": 0.3, "hand": 0.3, "flow_acc": 0.2, "slope": 0.2},
        )
        assert sum(r.weights_flood.values()) == pytest.approx(1.0)


class TestCompositeZonalStatsResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            zona_id = uuid.uuid4()
            zona_nombre = None
            cuenca = None
            superficie_ha = None
            tipo = "flood_risk"
            mean_score = 0.45
            max_score = 0.85
            p90_score = 0.72
            area_high_risk_ha = 120.5
            weights_used = {"twi": 0.25}
            fecha_calculo = date(2025, 1, 1)

        resp = CompositeZonalStatsResponse.model_validate(Fake())
        assert resp.tipo == "flood_risk"


class TestAnalysisRequest:
    def test_valid_request(self):
        r = AnalysisRequest(area_id="cuenca_norte")
        assert r.tipos is None
        assert r.parameters is None

    def test_with_tipos(self):
        r = AnalysisRequest(
            area_id="cuenca_norte",
            tipos=["hotspot", "gap"],
        )
        assert len(r.tipos) == 2


class TestCanalSuggestionResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            tipo = "hotspot"
            score = 85.5
            metadata_ = {"reason": "high flow"}
            batch_id = uuid.uuid4()
            created_at = datetime(2025, 1, 1)

        resp = CanalSuggestionResponse.model_validate(Fake())
        assert resp.tipo == "hotspot"
        assert resp.score == 85.5


class TestAnalysisSummaryResponse:
    def test_valid_summary(self):
        s = AnalysisSummaryResponse(
            batch_id=uuid.uuid4(),
            total_suggestions=15,
            by_tipo={"hotspot": 5, "gap": 10},
            avg_score=72.3,
            created_at=datetime(2025, 1, 1),
        )
        assert s.total_suggestions == 15


class TestAlertaResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            tipo = "inundacion"
            mensaje = "Risk detected"
            nivel = "alto"
            datos = {"hci": 0.85}
            activa = True
            zona_id = uuid.uuid4()
            created_at = datetime(2025, 1, 1)

        resp = AlertaResponse.model_validate(Fake())
        assert resp.activa is True


class TestBasinRiskRankingResponse:
    def test_with_items(self):
        item = CompositeZonalStatsResponse(
            id=uuid.uuid4(),
            zona_id=uuid.uuid4(),
            tipo="flood_risk",
            mean_score=0.65,
            max_score=0.9,
            p90_score=0.8,
            area_high_risk_ha=200.0,
            fecha_calculo=date(2025, 1, 1),
        )
        ranking = BasinRiskRankingResponse(items=[item], total=1)
        assert ranking.total == 1


class TestCompositeComparisonResponse:
    def test_valid_comparison(self):
        item = CompositeComparisonItemResponse(
            zona_id=uuid.uuid4(),
            tipo="drainage_need",
            current_mean_score=0.65,
            baseline_mean_score=0.55,
            delta_mean_score=0.10,
            current_area_high_risk_ha=200.0,
            baseline_area_high_risk_ha=250.0,
            delta_area_high_risk_ha=-50.0,
        )
        resp = CompositeComparisonResponse(
            area_id="zona_1", tipo="drainage_need", items=[item], total=1
        )
        assert resp.items[0].delta_mean_score == pytest.approx(0.10)


class TestCanalPrioridadResponse:
    def test_valid(self):
        r = CanalPrioridadResponse(
            canal_id="canal-1",
            nombre="Canal Norte",
            prioridad=85.0,
        )
        assert r.detalles is None


class TestCaminoRiesgoResponse:
    def test_valid(self):
        r = CaminoRiesgoResponse(
            camino_id="camino-1",
            nombre="Ruta 5",
            riesgo=72.0,
        )
        assert r.detalles is None


# ──────────────────────────────────────────────
# MONITORING
# ──────────────────────────────────────────────

from app.domains.monitoring.schemas import (
    AnalisisGeeResponse as MonitoringAnalisisGeeResponse,
    DashboardStatsResponse,
    DenunciaStats,
    SugerenciaCreate,
    SugerenciaListResponse,
    SugerenciaResponse,
    SugerenciaUpdate,
)


class TestSugerenciaCreate:
    def test_valid_sugerencia(self):
        s = SugerenciaCreate(
            titulo="Mejorar canal zona norte",
            descripcion="El canal necesita limpieza urgente en la zona norte",
        )
        assert s.categoria is None
        assert s.contacto_email is None

    def test_titulo_min_length(self):
        with pytest.raises(ValidationError, match="at least 5"):
            SugerenciaCreate(titulo="Hi", descripcion="Description ok here")

    def test_descripcion_min_length(self):
        with pytest.raises(ValidationError, match="at least 10"):
            SugerenciaCreate(titulo="Valid title", descripcion="short")

    def test_email_validation(self):
        s = SugerenciaCreate(
            titulo="Valid title",
            descripcion="Valid description here",
            contacto_email="test@example.com",
        )
        assert s.contacto_email == "test@example.com"

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            SugerenciaCreate(
                titulo="Valid title",
                descripcion="Valid description here",
                contacto_email="not-an-email",
            )

    def test_geometry_must_be_feature_collection(self):
        with pytest.raises(ValidationError, match="FeatureCollection"):
            SugerenciaCreate(
                titulo="Valid title",
                descripcion="Valid description here",
                geometry={"type": "Point", "coordinates": [0, 0]},
            )

    def test_geometry_valid_feature_collection(self):
        geom = {
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 0], [1, 1]],
                    }
                }
            ],
        }
        s = SugerenciaCreate(
            titulo="Valid title",
            descripcion="Valid description here",
            geometry=geom,
        )
        assert s.geometry["type"] == "FeatureCollection"

    def test_geometry_rejects_non_linestring(self):
        geom = {
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {
                        "type": "Point",
                        "coordinates": [0, 0],
                    }
                }
            ],
        }
        with pytest.raises(ValidationError, match="LineString"):
            SugerenciaCreate(
                titulo="Valid title",
                descripcion="Valid description here",
                geometry=geom,
            )

    def test_geometry_linestring_needs_two_vertices(self):
        geom = {
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 0]],
                    }
                }
            ],
        }
        with pytest.raises(ValidationError, match="al menos dos vertices"):
            SugerenciaCreate(
                titulo="Valid title",
                descripcion="Valid description here",
                geometry=geom,
            )


class TestSugerenciaUpdate:
    def test_all_optional(self):
        u = SugerenciaUpdate()
        assert u.estado is None
        assert u.respuesta is None


class TestSugerenciaResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            titulo = "Test"
            descripcion = "Test desc"
            categoria = None
            estado = "pendiente"
            contacto_email = None
            contacto_nombre = None
            geometry = None
            respuesta = None
            usuario_id = None
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = SugerenciaResponse.model_validate(Fake())
        assert resp.estado == "pendiente"


class TestDenunciaStats:
    def test_defaults(self):
        d = DenunciaStats()
        assert d.pendiente == 0
        assert d.total == 0

    def test_with_values(self):
        d = DenunciaStats(pendiente=5, en_revision=3, total=8)
        assert d.total == 8


class TestDashboardStatsResponse:
    def test_valid(self):
        d = DashboardStatsResponse(
            denuncias=DenunciaStats(),
        )
        assert d.total_assets == 0
        assert d.total_sugerencias == 0


# ──────────────────────────────────────────────
# REUNIONES
# ──────────────────────────────────────────────

from app.domains.reuniones.schemas import (
    AgendaItemCreate,
    AgendaItemResponse,
    AgendaItemUpdate,
    AgendaReferenciaCreate,
    AgendaReferenciaResponse,
    ReunionCreate,
    ReunionCreateResponse,
    ReunionListResponse,
    ReunionResponse,
    ReunionUpdate,
)


class TestReunionCreate:
    def test_valid_reunion(self):
        r = ReunionCreate(
            titulo="Reunion ordinaria febrero",
            fecha_reunion=datetime(2025, 2, 15, 10, 0),
        )
        assert r.lugar == "Sede Consorcio"
        assert r.tipo == "ordinaria"
        assert r.orden_del_dia_items == []

    def test_titulo_min_length(self):
        with pytest.raises(ValidationError, match="at least 3"):
            ReunionCreate(
                titulo="ab", fecha_reunion=datetime(2025, 1, 1)
            )

    def test_titulo_max_length(self):
        with pytest.raises(ValidationError):
            ReunionCreate(
                titulo="x" * 201, fecha_reunion=datetime(2025, 1, 1)
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            ReunionCreate()

    def test_with_all_fields(self):
        r = ReunionCreate(
            titulo="Test",
            fecha_reunion=datetime(2025, 1, 1),
            lugar="Oficina",
            descripcion="Descripcion",
            tipo="extraordinaria",
            orden_del_dia_items=["Tema 1", "Tema 2"],
        )
        assert len(r.orden_del_dia_items) == 2


class TestReunionUpdate:
    def test_all_optional(self):
        u = ReunionUpdate()
        assert u.titulo is None


class TestAgendaItemCreate:
    def test_valid(self):
        a = AgendaItemCreate(titulo="Punto 1")
        assert a.orden == 0
        assert a.referencias == []

    def test_titulo_min_length(self):
        with pytest.raises(ValidationError, match="at least 2"):
            AgendaItemCreate(titulo="x")

    def test_with_references(self):
        ref = AgendaReferenciaCreate(
            entidad_tipo="denuncia", entidad_id=uuid.uuid4()
        )
        a = AgendaItemCreate(titulo="Punto 1", referencias=[ref])
        assert len(a.referencias) == 1


class TestAgendaItemUpdate:
    def test_all_optional(self):
        u = AgendaItemUpdate()
        assert u.completado is None

    def test_orden_non_negative(self):
        with pytest.raises(ValidationError):
            AgendaItemUpdate(orden=-1)


class TestReunionResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            titulo = "Test"
            fecha_reunion = datetime(2025, 1, 1)
            lugar = "Sede"
            descripcion = None
            tipo = "ordinaria"
            estado = "programada"
            orden_del_dia_items = []
            usuario_id = uuid.uuid4()
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)
            agenda_items = []

        resp = ReunionResponse.model_validate(Fake())
        assert resp.estado == "programada"


class TestReunionCreateResponse:
    def test_valid(self):
        r = ReunionCreateResponse(
            id=uuid.uuid4(), message="Reunion creada", estado="programada"
        )
        assert r.message == "Reunion creada"


# ──────────────────────────────────────────────
# SETTINGS
# ──────────────────────────────────────────────

from app.domains.settings.schemas import (
    BrandingResponse,
    ImagenComparacionParams,
    ImagenMapaParams,
    ImagenMapaResponse,
    SettingResponse,
    SettingsByCategoryResponse,
    SettingUpdate,
)


class TestSettingUpdate:
    def test_valid_update(self):
        u = SettingUpdate(valor="new_value")
        assert u.valor == "new_value"
        assert u.descripcion is None

    def test_valor_required(self):
        with pytest.raises(ValidationError):
            SettingUpdate()


class TestSettingResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            clave = "theme_color"
            valor = "#FF0000"
            categoria = "branding"
            descripcion = "Primary color"
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = SettingResponse.model_validate(Fake())
        assert resp.clave == "theme_color"


class TestBrandingResponse:
    def test_all_none_by_default(self):
        b = BrandingResponse()
        assert b.nombre_organizacion is None
        assert b.logo_url is None
        assert b.color_primario is None


class TestImagenMapaParams:
    def test_valid_params(self):
        p = ImagenMapaParams(
            sensor="Sentinel-2",
            target_date="2025-01-15",
            visualization="rgb",
        )
        assert p.days_buffer == 10

    def test_max_cloud_bounds(self):
        with pytest.raises(ValidationError):
            ImagenMapaParams(
                sensor="Sentinel-2",
                target_date="2025-01-15",
                visualization="rgb",
                max_cloud=101,
            )

    def test_days_buffer_bounds(self):
        with pytest.raises(ValidationError):
            ImagenMapaParams(
                sensor="Sentinel-2",
                target_date="2025-01-15",
                visualization="rgb",
                days_buffer=0,
            )
        with pytest.raises(ValidationError):
            ImagenMapaParams(
                sensor="Sentinel-2",
                target_date="2025-01-15",
                visualization="rgb",
                days_buffer=31,
            )


class TestImagenComparacionParams:
    def test_defaults(self):
        p = ImagenComparacionParams()
        assert p.enabled is False
        assert p.left is None


# ──────────────────────────────────────────────
# TRAMITES
# ──────────────────────────────────────────────

from app.domains.tramites.schemas import (
    SeguimientoCreate,
    SeguimientoResponse,
    TramiteCreate,
    TramiteCreateResponse,
    TramiteListResponse,
    TramiteResponse,
    TramiteUpdate,
)


class TestTramiteCreate:
    def test_valid_tramite(self):
        t = TramiteCreate(
            tipo="obra",
            titulo="Reparacion canal zona norte",
            descripcion="Se requiere reparacion urgente del canal principal",
            solicitante="Juan Perez",
        )
        assert t.prioridad == "media"
        assert t.fecha_ingreso is None

    def test_titulo_min_length(self):
        with pytest.raises(ValidationError, match="at least 5"):
            TramiteCreate(
                tipo="obra",
                titulo="Hi",
                descripcion="Description is ok here",
                solicitante="Juan",
            )

    def test_descripcion_min_length(self):
        with pytest.raises(ValidationError, match="at least 10"):
            TramiteCreate(
                tipo="obra",
                titulo="Valid title",
                descripcion="short",
                solicitante="Juan",
            )

    def test_solicitante_min_length(self):
        with pytest.raises(ValidationError, match="at least 2"):
            TramiteCreate(
                tipo="obra",
                titulo="Valid title",
                descripcion="Valid description here",
                solicitante="J",
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError) as exc_info:
            TramiteCreate()
        errors = exc_info.value.errors()
        missing = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert {"tipo", "titulo", "descripcion", "solicitante"} <= missing


class TestTramiteUpdate:
    def test_all_optional(self):
        u = TramiteUpdate()
        assert u.estado is None
        assert u.comentario is None


class TestSeguimientoCreate:
    def test_valid(self):
        s = SeguimientoCreate(comentario="Avance en la obra del canal")
        assert len(s.comentario) > 5

    def test_comentario_min_length(self):
        with pytest.raises(ValidationError, match="at least 5"):
            SeguimientoCreate(comentario="Hi")


class TestSeguimientoResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            tramite_id = uuid.uuid4()
            estado_anterior = "pendiente"
            estado_nuevo = "en_proceso"
            comentario = "Cambio de estado"
            usuario_id = uuid.uuid4()
            created_at = datetime(2025, 1, 1)

        resp = SeguimientoResponse.model_validate(Fake())
        assert resp.estado_anterior == "pendiente"


class TestTramiteResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            tipo = "obra"
            titulo = "Test"
            descripcion = "Test desc"
            solicitante = "Juan"
            estado = "pendiente"
            prioridad = "media"
            fecha_ingreso = date(2025, 1, 1)
            fecha_resolucion = None
            resolucion = None
            usuario_id = uuid.uuid4()
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)
            seguimiento = []

        resp = TramiteResponse.model_validate(Fake())
        assert resp.seguimiento == []


class TestTramiteCreateResponse:
    def test_valid(self):
        r = TramiteCreateResponse(
            id=uuid.uuid4(), message="Tramite creado", estado="pendiente"
        )
        assert r.estado == "pendiente"


# ──────────────────────────────────────────────
# CAPAS
# ──────────────────────────────────────────────

from app.domains.capas.schemas import (
    CapaCreate,
    CapaListResponse,
    CapaReorder,
    CapaResponse,
    CapaUpdate,
    EstiloCapa,
)


class TestEstiloCapa:
    def test_defaults(self):
        e = EstiloCapa()
        assert e.color == "#3388ff"
        assert e.weight == 2
        assert e.fillOpacity == 0.2

    def test_fill_opacity_bounds(self):
        with pytest.raises(ValidationError):
            EstiloCapa(fillOpacity=1.5)
        with pytest.raises(ValidationError):
            EstiloCapa(fillOpacity=-0.1)

    def test_weight_bounds(self):
        with pytest.raises(ValidationError):
            EstiloCapa(weight=21)
        with pytest.raises(ValidationError):
            EstiloCapa(weight=-1)


class TestCapaCreate:
    def test_valid_capa(self):
        c = CapaCreate(
            nombre="Canales",
            tipo="polygon",
            fuente="local",
        )
        assert c.visible is True
        assert c.es_publica is False
        assert isinstance(c.estilo, EstiloCapa)

    def test_nombre_min_length(self):
        with pytest.raises(ValidationError, match="at least 1"):
            CapaCreate(nombre="", tipo="polygon", fuente="local")

    def test_missing_required(self):
        with pytest.raises(ValidationError) as exc_info:
            CapaCreate()
        errors = exc_info.value.errors()
        missing = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert {"nombre", "tipo", "fuente"} <= missing

    def test_url_max_length(self):
        with pytest.raises(ValidationError):
            CapaCreate(
                nombre="Test",
                tipo="tile",
                fuente="gee",
                url="x" * 1001,
            )


class TestCapaUpdate:
    def test_all_optional(self):
        u = CapaUpdate()
        assert u.nombre is None
        assert u.estilo is None

    def test_orden_non_negative(self):
        with pytest.raises(ValidationError):
            CapaUpdate(orden=-1)


class TestCapaReorder:
    def test_valid_reorder(self):
        ids = [uuid.uuid4(), uuid.uuid4()]
        r = CapaReorder(ordered_ids=ids)
        assert len(r.ordered_ids) == 2


class TestCapaResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            nombre = "Test"
            descripcion = None
            tipo = "polygon"
            fuente = "local"
            url = None
            geojson_data = None
            estilo = {"color": "#ff0000"}
            visible = True
            orden = 0
            es_publica = False
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = CapaResponse.model_validate(Fake())
        assert resp.visible is True


# ──────────────────────────────────────────────
# DENUNCIAS
# ──────────────────────────────────────────────

from app.domains.denuncias.schemas import (
    DenunciaCreate,
    DenunciaCreateResponse,
    DenunciaListResponse,
    DenunciaResponse,
    DenunciaUpdate,
    HistorialResponse,
)


class TestDenunciaCreate:
    def test_valid_denuncia(self):
        d = DenunciaCreate(
            tipo="alcantarilla_tapada",
            descripcion="La alcantarilla esta completamente tapada en la esquina",
            latitud=-30.5,
            longitud=-60.0,
        )
        assert d.cuenca is None
        assert d.foto_url is None

    def test_descripcion_min_length(self):
        with pytest.raises(ValidationError, match="at least 10"):
            DenunciaCreate(
                tipo="otro",
                descripcion="short",
                latitud=-30.0,
                longitud=-60.0,
            )

    def test_latitud_bounds(self):
        with pytest.raises(ValidationError):
            DenunciaCreate(
                tipo="otro",
                descripcion="Valid description here",
                latitud=-91.0,
                longitud=-60.0,
            )
        with pytest.raises(ValidationError):
            DenunciaCreate(
                tipo="otro",
                descripcion="Valid description here",
                latitud=91.0,
                longitud=-60.0,
            )

    def test_longitud_bounds(self):
        with pytest.raises(ValidationError):
            DenunciaCreate(
                tipo="otro",
                descripcion="Valid description here",
                latitud=-30.0,
                longitud=-181.0,
            )
        with pytest.raises(ValidationError):
            DenunciaCreate(
                tipo="otro",
                descripcion="Valid description here",
                latitud=-30.0,
                longitud=181.0,
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError) as exc_info:
            DenunciaCreate()
        errors = exc_info.value.errors()
        missing = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert {"tipo", "descripcion", "latitud", "longitud"} <= missing


class TestDenunciaUpdate:
    def test_all_optional(self):
        u = DenunciaUpdate()
        assert u.estado is None
        assert u.respuesta is None


class TestHistorialResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            denuncia_id = uuid.uuid4()
            estado_anterior = "pendiente"
            estado_nuevo = "en_revision"
            comentario = "Revisando"
            usuario_id = uuid.uuid4()
            created_at = datetime(2025, 1, 1)

        resp = HistorialResponse.model_validate(Fake())
        assert resp.estado_nuevo == "en_revision"


class TestDenunciaResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            tipo = "otro"
            descripcion = "Test"
            latitud = -30.0
            longitud = -60.0
            cuenca = None
            estado = "pendiente"
            contacto_telefono = None
            contacto_email = None
            foto_url = None
            user_id = None
            respuesta = None
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)
            historial = []

        resp = DenunciaResponse.model_validate(Fake())
        assert resp.historial == []


class TestDenunciaCreateResponse:
    def test_valid(self):
        r = DenunciaCreateResponse(
            id=uuid.uuid4(), message="Denuncia creada", estado="pendiente"
        )
        assert r.estado == "pendiente"


# ──────────────────────────────────────────────
# INFRAESTRUCTURA
# ──────────────────────────────────────────────

from app.domains.infraestructura.schemas import (
    AssetCreate,
    AssetListResponse,
    AssetResponse,
    AssetUpdate,
    MantenimientoLogCreate,
    MantenimientoLogResponse,
)


class TestAssetCreate:
    def test_valid_asset(self):
        a = AssetCreate(
            nombre="Canal Norte",
            tipo="canal",
            descripcion="Canal principal de la zona norte del consorcio",
            latitud=-30.5,
            longitud=-60.0,
        )
        assert a.estado_actual == "bueno"
        assert a.longitud_km is None

    def test_nombre_min_length(self):
        with pytest.raises(ValidationError, match="at least 2"):
            AssetCreate(
                nombre="x",
                tipo="canal",
                descripcion="Valid description here",
                latitud=-30.0,
                longitud=-60.0,
            )

    def test_latitud_bounds(self):
        with pytest.raises(ValidationError):
            AssetCreate(
                nombre="Test",
                tipo="canal",
                descripcion="Valid description here",
                latitud=-91.0,
                longitud=-60.0,
            )

    def test_anio_construccion_range(self):
        with pytest.raises(ValidationError):
            AssetCreate(
                nombre="Test",
                tipo="canal",
                descripcion="Valid description here",
                latitud=-30.0,
                longitud=-60.0,
                anio_construccion=1799,
            )
        with pytest.raises(ValidationError):
            AssetCreate(
                nombre="Test",
                tipo="canal",
                descripcion="Valid description here",
                latitud=-30.0,
                longitud=-60.0,
                anio_construccion=2101,
            )

    def test_longitud_km_non_negative(self):
        with pytest.raises(ValidationError):
            AssetCreate(
                nombre="Test",
                tipo="canal",
                descripcion="Valid description here",
                latitud=-30.0,
                longitud=-60.0,
                longitud_km=-1.0,
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError) as exc_info:
            AssetCreate()
        errors = exc_info.value.errors()
        missing = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert {"nombre", "tipo", "descripcion", "latitud", "longitud"} <= missing


class TestAssetUpdate:
    def test_all_optional(self):
        u = AssetUpdate()
        assert u.nombre is None

    def test_anio_range_when_provided(self):
        with pytest.raises(ValidationError):
            AssetUpdate(anio_construccion=1799)


class TestAssetResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            nombre = "Canal"
            tipo = "canal"
            descripcion = "Desc"
            estado_actual = "bueno"
            latitud = -30.0
            longitud = -60.0
            longitud_km = None
            material = None
            anio_construccion = None
            responsable = None
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = AssetResponse.model_validate(Fake())
        assert resp.estado_actual == "bueno"


class TestMantenimientoLogCreate:
    def test_valid(self):
        m = MantenimientoLogCreate(
            tipo_trabajo="Limpieza",
            descripcion="Limpieza general del canal norte del consorcio",
            fecha_trabajo=date(2025, 6, 1),
            realizado_por="Equipo de mantenimiento",
        )
        assert m.costo is None

    def test_tipo_trabajo_min_length(self):
        with pytest.raises(ValidationError, match="at least 3"):
            MantenimientoLogCreate(
                tipo_trabajo="ab",
                descripcion="Valid description here",
                fecha_trabajo=date(2025, 1, 1),
                realizado_por="Juan",
            )

    def test_costo_non_negative(self):
        with pytest.raises(ValidationError):
            MantenimientoLogCreate(
                tipo_trabajo="Limpieza",
                descripcion="Valid description here",
                fecha_trabajo=date(2025, 1, 1),
                realizado_por="Juan",
                costo=-100,
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError) as exc_info:
            MantenimientoLogCreate()
        errors = exc_info.value.errors()
        missing = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert {"tipo_trabajo", "descripcion", "fecha_trabajo", "realizado_por"} <= missing


class TestMantenimientoLogResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            asset_id = uuid.uuid4()
            tipo_trabajo = "Limpieza"
            descripcion = "Desc"
            costo = None
            fecha_trabajo = date(2025, 1, 1)
            realizado_por = "Juan"
            usuario_id = uuid.uuid4()
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = MantenimientoLogResponse.model_validate(Fake())
        assert resp.costo is None


# ──────────────────────────────────────────────
# PADRON
# ──────────────────────────────────────────────

from app.domains.padron.schemas import (
    ConsorcistaCreate,
    ConsorcistaListResponse,
    ConsorcistaResponse,
    ConsorcistaUpdate,
    CsvImportResponse,
)


class TestConsorcistaCreate:
    def test_valid_consorcista(self):
        c = ConsorcistaCreate(
            nombre="Juan",
            apellido="Perez",
            cuit="20-12345678-9",
        )
        assert c.estado == "activo"
        assert c.cuit == "20-12345678-9"

    def test_cuit_digits_only_formatted(self):
        c = ConsorcistaCreate(
            nombre="Juan",
            apellido="Perez",
            cuit="20123456789",
        )
        assert c.cuit == "20-12345678-9"

    def test_invalid_cuit_rejected(self):
        with pytest.raises(ValidationError, match="CUIT"):
            ConsorcistaCreate(
                nombre="Juan",
                apellido="Perez",
                cuit="123",
            )

    def test_invalid_cuit_too_many_digits(self):
        with pytest.raises(ValidationError, match="CUIT"):
            ConsorcistaCreate(
                nombre="Juan",
                apellido="Perez",
                cuit="201234567890",  # 12 digits
            )

    def test_hectareas_non_negative(self):
        with pytest.raises(ValidationError):
            ConsorcistaCreate(
                nombre="Juan",
                apellido="Perez",
                cuit="20-12345678-9",
                hectareas=-1.0,
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError) as exc_info:
            ConsorcistaCreate()
        errors = exc_info.value.errors()
        missing = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert {"nombre", "apellido", "cuit"} <= missing


class TestConsorcistaUpdate:
    def test_all_optional(self):
        u = ConsorcistaUpdate()
        assert u.nombre is None
        assert u.cuit is None

    def test_cuit_validated_when_provided(self):
        u = ConsorcistaUpdate(cuit="20123456789")
        assert u.cuit == "20-12345678-9"

    def test_cuit_none_accepted(self):
        u = ConsorcistaUpdate(cuit=None)
        assert u.cuit is None

    def test_invalid_cuit_rejected(self):
        with pytest.raises(ValidationError, match="CUIT"):
            ConsorcistaUpdate(cuit="bad")


class TestConsorcistaResponse:
    def test_from_orm(self):
        class Fake:
            id = uuid.uuid4()
            nombre = "Juan"
            apellido = "Perez"
            cuit = "20-12345678-9"
            dni = None
            domicilio = None
            localidad = None
            telefono = None
            email = None
            parcela = None
            hectareas = None
            categoria = None
            estado = "activo"
            fecha_ingreso = None
            notas = None
            created_at = datetime(2025, 1, 1)
            updated_at = datetime(2025, 1, 1)

        resp = ConsorcistaResponse.model_validate(Fake())
        assert resp.estado == "activo"


class TestCsvImportResponse:
    def test_valid(self):
        r = CsvImportResponse(
            filename="padron.csv",
            processed=100,
            created=95,
            skipped=5,
            errors=[],
        )
        assert r.processed == 100
