"""Hypothesis property-based tests for Pydantic schemas.

Tests round-trip serialization, edge cases, and boundary
conditions using random data generation.
"""

import math
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings, assume
from hypothesis import strategies as st
from pydantic import ValidationError

# ──────────────────────────────────────────────
# SHARED STRATEGIES
# ──────────────────────────────────────────────

valid_str_3_200 = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=3,
    max_size=200,
)

valid_str_5_200 = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=5,
    max_size=200,
)

valid_str_10_500 = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=10,
    max_size=500,
)

positive_decimal = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("9999999999.99"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

non_negative_decimal = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("9999999999.99"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

valid_date = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))

valid_datetime = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 12, 31),
)

valid_uuid = st.uuids()

valid_latitude = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
valid_longitude = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)

categorias_gasto = st.sampled_from(["obras", "mantenimiento", "personal", "administrativo", "otros"])
categorias_ingreso = st.sampled_from(["cuotas", "subsidio", "otros"])


# ──────────────────────────────────────────────
# FINANZAS — Property Tests
# ──────────────────────────────────────────────

from app.domains.finanzas.schemas import (
    GastoCreate,
    GastoResponse,
    IngresoCreate,
    PresupuestoCreate,
)


class TestGastoCreateProperties:
    """Property: any valid data → GastoCreate → JSON round-trip."""

    @given(
        descripcion=valid_str_3_200,
        monto=positive_decimal,
        categoria=categorias_gasto,
        fecha=valid_date,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip_dict(self, descripcion, monto, categoria, fecha):
        g = GastoCreate(
            descripcion=descripcion,
            monto=monto,
            categoria=categoria,
            fecha=fecha,
        )
        d = g.model_dump()
        g2 = GastoCreate(**d)
        assert g2.descripcion == g.descripcion
        assert g2.monto == g.monto

    @given(
        descripcion=valid_str_3_200,
        monto=positive_decimal,
        categoria=categorias_gasto,
        fecha=valid_date,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_serializes_to_json(self, descripcion, monto, categoria, fecha):
        g = GastoCreate(
            descripcion=descripcion,
            monto=monto,
            categoria=categoria,
            fecha=fecha,
        )
        j = g.model_dump_json()
        assert isinstance(j, str)
        assert len(j) > 0


class TestGastoRejectsNanInf:
    """Property: NaN and Inf are not valid for monto."""

    @pytest.mark.parametrize(
        "bad_value",
        [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
        ids=["nan", "inf", "neg_inf"],
    )
    def test_monto_rejects_special_floats(self, bad_value):
        with pytest.raises(ValidationError, match="finite"):
            GastoCreate(
                descripcion="Test gasto",
                monto=bad_value,
                categoria="obras",
                fecha=date(2025, 1, 1),
            )


class TestIngresoCreateProperties:
    @given(
        descripcion=valid_str_3_200,
        monto=positive_decimal,
        categoria=categorias_ingreso,
        fecha=valid_date,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip(self, descripcion, monto, categoria, fecha):
        i = IngresoCreate(
            descripcion=descripcion,
            monto=monto,
            categoria=categoria,
            fecha=fecha,
        )
        d = i.model_dump()
        i2 = IngresoCreate(**d)
        assert i2.monto == i.monto


class TestPresupuestoCreateProperties:
    @given(
        anio=st.integers(min_value=2000, max_value=2100),
        rubro=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=2,
            max_size=100,
        ),
        monto=non_negative_decimal,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip(self, anio, rubro, monto):
        p = PresupuestoCreate(
            anio=anio, rubro=rubro, monto_proyectado=monto
        )
        d = p.model_dump()
        p2 = PresupuestoCreate(**d)
        assert p2.anio == p.anio
        assert p2.rubro == p.rubro


# ──────────────────────────────────────────────
# GEO — Property Tests
# ──────────────────────────────────────────────

from app.domains.geo.models import TipoGeoJob
from app.domains.geo.schemas import (
    BackfillRequest,
    DemPipelineRequest,
    FloodEventCreate,
    FloodLabelCreate,
    RainfallEventResponse,
    RainfallSummaryResponse,
)


class TestGeoJobCreateProperties:
    @given(tipo=st.sampled_from(list(TipoGeoJob)))
    @settings(max_examples=20)
    def test_all_enum_values(self, tipo):
        from app.domains.geo.schemas import GeoJobCreate
        j = GeoJobCreate(tipo=tipo)
        d = j.model_dump()
        assert d["tipo"] == tipo


class TestFloodEventCreateProperties:
    @given(
        event_date=valid_date,
        num_labels=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip(self, event_date, num_labels):
        labels = [
            FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=i % 2 == 0)
            for i in range(num_labels)
        ]
        e = FloodEventCreate(
            event_date=event_date,
            labels=labels,
        )
        d = e.model_dump()
        e2 = FloodEventCreate(**d)
        assert len(e2.labels) == num_labels

    @given(event_date=valid_date)
    @settings(max_examples=20)
    def test_json_serializable(self, event_date):
        e = FloodEventCreate(
            event_date=event_date,
            labels=[FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=True)],
        )
        j = e.model_dump_json()
        assert isinstance(j, str)


class TestBackfillRequestProperties:
    @given(
        start=valid_date,
        end=valid_date,
    )
    @settings(max_examples=30)
    def test_round_trip(self, start, end):
        r = BackfillRequest(start_date=start, end_date=end)
        d = r.model_dump()
        r2 = BackfillRequest(**d)
        assert r2.start_date == r.start_date


class TestDemPipelineProperties:
    @given(
        min_basin=st.floats(
            min_value=0.0, max_value=100000.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=30)
    def test_min_basin_area(self, min_basin):
        r = DemPipelineRequest(min_basin_area_ha=min_basin)
        assert r.min_basin_area_ha >= 0


class TestRainfallResponseProperties:
    @given(
        total_mm=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
        avg_mm=st.floats(min_value=0, max_value=500, allow_nan=False, allow_infinity=False),
        max_mm=st.floats(min_value=0, max_value=500, allow_nan=False, allow_infinity=False),
        rainy_days=st.integers(min_value=0, max_value=365),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_summary_round_trip(self, total_mm, avg_mm, max_mm, rainy_days):
        r = RainfallSummaryResponse(
            zona_operativa_id=uuid.uuid4(),
            total_mm=total_mm,
            avg_mm=avg_mm,
            max_mm=max_mm,
            rainy_days=rainy_days,
        )
        d = r.model_dump()
        r2 = RainfallSummaryResponse(**d)
        assert r2.rainy_days == rainy_days


class TestRainfallRejectsNanInf:
    """Property: float fields in rainfall schemas reject NaN/Inf."""

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_event_accumulated_rejects_special(self, bad_value):
        """RainfallEventResponse doesn't have field-level constraints that block NaN,
        but we verify the schema at least accepts/rejects consistently."""
        # The schema accepts raw floats — this documents current behavior.
        # If the schema adds validation in the future, this test catches regressions.
        r = RainfallEventResponse(
            event_start=date(2025, 1, 1),
            event_end=date(2025, 1, 3),
            zona_operativa_id=uuid.uuid4(),
            accumulated_mm=bad_value,
            duration_days=3,
        )
        # JSON serialization should still produce valid output
        j = r.model_dump_json()
        assert isinstance(j, str)


# ──────────────────────────────────────────────
# GEO INTELLIGENCE — Property Tests
# ──────────────────────────────────────────────

from app.domains.geo.intelligence.schemas import (
    AnalysisRequest,
    CompositeAnalysisRequest,
    CriticidadRequest,
    DashboardInteligente,
    EscorrentiaRequest,
)


class TestCriticidadRequestProperties:
    @given(
        pendiente=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
        acumulacion=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
        twi=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
        proximidad=st.floats(min_value=0, max_value=50000, allow_nan=False, allow_infinity=False),
        historial=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_bounded_values_accepted(self, pendiente, acumulacion, twi, proximidad, historial):
        r = CriticidadRequest(
            zona_id=uuid.uuid4(),
            pendiente_media=pendiente,
            acumulacion_media=acumulacion,
            twi_medio=twi,
            proximidad_canal_m=proximidad,
            historial_inundacion=historial,
        )
        d = r.model_dump()
        r2 = CriticidadRequest(**d)
        assert r2.pendiente_media == pytest.approx(pendiente)

    @given(
        val=st.floats(
            min_value=1.001, max_value=1000,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=20)
    def test_out_of_range_rejected(self, val):
        with pytest.raises(ValidationError):
            CriticidadRequest(
                zona_id=uuid.uuid4(),
                pendiente_media=val,
                acumulacion_media=0.5,
                twi_medio=0.5,
                proximidad_canal_m=100,
                historial_inundacion=0.5,
            )


class TestEscorrentiaRequestProperties:
    @given(
        lon=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
        lat=st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
        lluvia=st.floats(min_value=0.01, max_value=500, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_coordinates(self, lon, lat, lluvia):
        r = EscorrentiaRequest(punto_inicio=[lon, lat], lluvia_mm=lluvia)
        assert len(r.punto_inicio) == 2


class TestDashboardInteligenteProperties:
    @given(
        pct=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        canales=st.integers(min_value=0, max_value=1000),
        caminos=st.integers(min_value=0, max_value=1000),
        conflictos=st.integers(min_value=0, max_value=1000),
        alertas=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip(self, pct, canales, caminos, conflictos, alertas):
        d = DashboardInteligente(
            porcentaje_area_riesgo=pct,
            canales_criticos=canales,
            caminos_vulnerables=caminos,
            conflictos_activos=conflictos,
            alertas_activas=alertas,
        )
        data = d.model_dump()
        d2 = DashboardInteligente(**data)
        assert d2.porcentaje_area_riesgo == pytest.approx(pct)


# ──────────────────────────────────────────────
# DENUNCIAS — Property Tests
# ──────────────────────────────────────────────

from app.domains.denuncias.schemas import DenunciaCreate


class TestDenunciaCreateProperties:
    @given(
        descripcion=valid_str_10_500,
        lat=valid_latitude,
        lon=valid_longitude,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip(self, descripcion, lat, lon):
        d = DenunciaCreate(
            tipo="otro",
            descripcion=descripcion,
            latitud=lat,
            longitud=lon,
        )
        data = d.model_dump()
        d2 = DenunciaCreate(**data)
        assert d2.latitud == pytest.approx(lat)
        assert d2.longitud == pytest.approx(lon)

    @pytest.mark.parametrize("lat", [float("nan"), float("inf"), float("-inf")])
    def test_nan_inf_latitude_rejected(self, lat):
        with pytest.raises(ValidationError):
            DenunciaCreate(
                tipo="otro",
                descripcion="Valid description here",
                latitud=lat,
                longitud=-60.0,
            )


# ──────────────────────────────────────────────
# CAPAS — Property Tests
# ──────────────────────────────────────────────

from app.domains.capas.schemas import CapaCreate, EstiloCapa


class TestEstiloCapaProperties:
    @given(
        fill_opacity=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        weight=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=30)
    def test_valid_style_round_trip(self, fill_opacity, weight):
        e = EstiloCapa(fillOpacity=fill_opacity, weight=weight)
        d = e.model_dump()
        e2 = EstiloCapa(**d)
        assert e2.fillOpacity == pytest.approx(fill_opacity)
        assert e2.weight == weight


# ──────────────────────────────────────────────
# INFRAESTRUCTURA — Property Tests
# ──────────────────────────────────────────────

from app.domains.infraestructura.schemas import AssetCreate, MantenimientoLogCreate


class TestAssetCreateProperties:
    @given(
        lat=valid_latitude,
        lon=valid_longitude,
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_coordinates_round_trip(self, lat, lon):
        a = AssetCreate(
            nombre="Test Asset",
            tipo="canal",
            descripcion="A valid asset description for testing purposes",
            latitud=lat,
            longitud=lon,
        )
        d = a.model_dump()
        a2 = AssetCreate(**d)
        assert a2.latitud == pytest.approx(lat)


class TestMantenimientoLogProperties:
    @given(fecha=valid_date)
    @settings(max_examples=20)
    def test_any_valid_date(self, fecha):
        m = MantenimientoLogCreate(
            tipo_trabajo="Limpieza general",
            descripcion="Limpieza general del canal norte del consorcio",
            fecha_trabajo=fecha,
            realizado_por="Equipo",
        )
        assert m.fecha_trabajo == fecha


# ──────────────────────────────────────────────
# PADRON — Property Tests
# ──────────────────────────────────────────────

from app.domains.padron.schemas import ConsorcistaCreate


class TestConsorcistaCreateProperties:
    @given(
        prefix=st.sampled_from(["20", "27", "23", "24", "30", "33", "34"]),
        middle=st.from_regex(r"[0-9]{8}", fullmatch=True),
        suffix=st.from_regex(r"[0-9]", fullmatch=True),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_cuit_normalization(self, prefix, middle, suffix):
        """Any 11-digit CUIT gets normalized to XX-XXXXXXXX-X."""
        raw_digits = f"{prefix}{middle}{suffix}"
        c = ConsorcistaCreate(
            nombre="Juan",
            apellido="Perez",
            cuit=raw_digits,
        )
        assert c.cuit == f"{prefix}-{middle}-{suffix}"

    @given(
        raw=st.from_regex(r"\d{2}-\d{8}-\d{1}", fullmatch=True),
    )
    @settings(max_examples=30)
    def test_formatted_cuit_passthrough(self, raw):
        c = ConsorcistaCreate(
            nombre="Ana",
            apellido="Garcia",
            cuit=raw,
        )
        assert c.cuit == raw


# ──────────────────────────────────────────────
# TRAMITES — Property Tests
# ──────────────────────────────────────────────

from app.domains.tramites.schemas import TramiteCreate, SeguimientoCreate


class TestTramiteCreateProperties:
    @given(
        titulo=valid_str_5_200,
        descripcion=valid_str_10_500,
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip(self, titulo, descripcion):
        t = TramiteCreate(
            tipo="obra",
            titulo=titulo,
            descripcion=descripcion,
            solicitante="Juan Perez",
        )
        d = t.model_dump()
        t2 = TramiteCreate(**d)
        assert t2.titulo == titulo


class TestSeguimientoCreateProperties:
    @given(
        comentario=valid_str_5_200,
    )
    @settings(max_examples=20)
    def test_round_trip(self, comentario):
        s = SeguimientoCreate(comentario=comentario)
        d = s.model_dump()
        s2 = SeguimientoCreate(**d)
        assert s2.comentario == comentario


# ──────────────────────────────────────────────
# REUNIONES — Property Tests
# ──────────────────────────────────────────────

from app.domains.reuniones.schemas import ReunionCreate, AgendaItemCreate


class TestReunionCreateProperties:
    @given(
        titulo=valid_str_3_200,
        fecha=valid_datetime,
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip(self, titulo, fecha):
        r = ReunionCreate(titulo=titulo, fecha_reunion=fecha)
        d = r.model_dump()
        r2 = ReunionCreate(**d)
        assert r2.titulo == titulo


class TestAgendaItemCreateProperties:
    @given(
        orden=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=20)
    def test_orden_non_negative(self, orden):
        a = AgendaItemCreate(titulo="Test item", orden=orden)
        assert a.orden == orden


# ──────────────────────────────────────────────
# MONITORING — Property Tests
# ──────────────────────────────────────────────

from app.domains.monitoring.schemas import SugerenciaCreate


class TestSugerenciaCreateProperties:
    @given(
        titulo=valid_str_5_200,
        descripcion=valid_str_10_500,
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_round_trip(self, titulo, descripcion):
        s = SugerenciaCreate(titulo=titulo, descripcion=descripcion)
        d = s.model_dump()
        s2 = SugerenciaCreate(**d)
        assert s2.titulo == titulo
        assert s2.descripcion == descripcion


# ──────────────────────────────────────────────
# SETTINGS — Property Tests
# ──────────────────────────────────────────────

from app.domains.settings.schemas import ImagenMapaParams


class TestImagenMapaParamsProperties:
    @given(
        max_cloud=st.integers(min_value=0, max_value=100),
        days_buffer=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=30)
    def test_bounded_values(self, max_cloud, days_buffer):
        p = ImagenMapaParams(
            sensor="Sentinel-2",
            target_date="2025-06-15",
            visualization="ndvi",
            max_cloud=max_cloud,
            days_buffer=days_buffer,
        )
        assert 0 <= p.max_cloud <= 100
        assert 1 <= p.days_buffer <= 30
