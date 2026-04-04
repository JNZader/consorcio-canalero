"""
Tests for Phase 2: AnalisisGeo model, schemas, and GEE task decorators.

These tests validate model construction, schema validation, and that
Celery tasks are properly decorated — no PostgreSQL required.
"""

import uuid
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.domains.geo.models import (
    AnalisisGeo,
    EstadoGeoJob,
    TipoAnalisisGee,
)
from app.domains.geo.schemas import (
    AnalisisGeoCreate,
    AnalisisGeoResponse,
)


# ── Model construction ──────────────────────────────


class TestAnalisisGeoModel:
    """Test AnalisisGeo SQLAlchemy model instantiation."""

    def test_create_with_required_fields(self):
        analisis = AnalisisGeo(
            tipo=TipoAnalisisGee.FLOOD,
            fecha_analisis=date(2026, 3, 1),
        )
        assert analisis.tipo == TipoAnalisisGee.FLOOD
        assert analisis.fecha_analisis == date(2026, 3, 1)
        assert analisis.fecha_inicio is None
        assert analisis.fecha_fin is None

    def test_create_with_all_fields(self):
        uid = uuid.uuid4()
        analisis = AnalisisGeo(
            tipo=TipoAnalisisGee.CLASSIFICATION,
            fecha_analisis=date(2026, 3, 1),
            fecha_inicio=datetime(2026, 1, 1, 0, 0),
            fecha_fin=datetime(2026, 3, 1, 23, 59),
            parametros={"method": "fusion", "max_cloud": 40},
            resultado={"status": "completed", "ndvi": {"tile_url": "http://..."}},
            estado=EstadoGeoJob.COMPLETED,
            error=None,
            celery_task_id="abc-123",
            usuario_id=uid,
        )
        assert analisis.tipo == TipoAnalisisGee.CLASSIFICATION
        assert analisis.fecha_inicio == datetime(2026, 1, 1, 0, 0)
        assert analisis.fecha_fin == datetime(2026, 3, 1, 23, 59)
        assert analisis.parametros["method"] == "fusion"
        assert analisis.usuario_id == uid

    def test_classification_enum_value_exists(self):
        assert TipoAnalisisGee.CLASSIFICATION.value == "classification"

    def test_all_tipo_analisis_values(self):
        expected = {"flood", "vegetation", "classification", "ndvi", "custom", "sar_temporal"}
        actual = {e.value for e in TipoAnalisisGee}
        assert expected == actual


# ── Schema validation ───────────────────────────────


class TestAnalisisGeoCreateSchema:
    """Test AnalisisGeoCreate Pydantic schema."""

    def test_valid_minimal(self):
        schema = AnalisisGeoCreate(tipo="flood")
        assert schema.tipo == "flood"
        assert schema.parametros == {}
        assert schema.fecha_inicio is None
        assert schema.fecha_fin is None

    def test_valid_with_dates(self):
        schema = AnalisisGeoCreate(
            tipo="classification",
            parametros={"max_cloud": 40},
            fecha_inicio=datetime(2026, 1, 1),
            fecha_fin=datetime(2026, 3, 1),
        )
        assert schema.fecha_inicio == datetime(2026, 1, 1)
        assert schema.fecha_fin == datetime(2026, 3, 1)

    def test_missing_tipo_raises(self):
        with pytest.raises(ValidationError):
            AnalisisGeoCreate()


class TestAnalisisGeoResponseSchema:
    """Test AnalisisGeoResponse includes new fields."""

    def test_response_includes_fecha_fields(self):
        fields = AnalisisGeoResponse.model_fields
        assert "fecha_inicio" in fields
        assert "fecha_fin" in fields


# ── Celery task decorators ──────────────────────────


class TestGeeTaskDecorators:
    """Verify that GEE Celery tasks are properly decorated."""

    def test_analyze_flood_task_is_celery_task(self):
        from app.domains.geo.gee_tasks import analyze_flood_task

        assert hasattr(analyze_flood_task, "delay")
        assert hasattr(analyze_flood_task, "apply_async")
        assert analyze_flood_task.name == "gee.analyze_flood"

    def test_supervised_classification_task_is_celery_task(self):
        from app.domains.geo.gee_tasks import supervised_classification_task

        assert hasattr(supervised_classification_task, "delay")
        assert hasattr(supervised_classification_task, "apply_async")
        assert supervised_classification_task.name == "gee.supervised_classification"
