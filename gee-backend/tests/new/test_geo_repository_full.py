"""Comprehensive tests for geo/repository.py — all remaining methods.

Uses real database fixtures (conftest.py pattern) with transaction rollback.
Covers: job CRUD, layer CRUD, approved zoning, and analisis.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

# Import all models with FK dependencies so Base.metadata.create_all works
import app.auth.models  # noqa: F401 — users table (geo_jobs.usuario_id FK)
import app.domains.geo.intelligence.models  # noqa: F401 — zonas_operativas (flood_labels.zona_id FK)
import app.domains.capas.models  # noqa: F401
import app.domains.denuncias.models  # noqa: F401
import app.domains.infraestructura.models  # noqa: F401
import app.domains.monitoring.models  # noqa: F401
import app.domains.padron.models  # noqa: F401
import app.domains.settings.models  # noqa: F401
import app.domains.finanzas.models  # noqa: F401
import app.domains.reuniones.models  # noqa: F401
import app.domains.tramites.models  # noqa: F401

from app.domains.geo.models import (
    AnalisisGeo,
    EstadoGeoJob,
    GeoApprovedZoning,
    GeoJob,
    GeoLayer,
)
from app.domains.geo.intelligence.models import ZonaOperativa
from app.domains.geo.repository import GeoRepository


def _create_zona(db, nombre: str = "Zona Test") -> uuid.UUID:
    """Insert a minimal ZonaOperativa record and return its id."""
    from geoalchemy2.elements import WKTElement

    zona = ZonaOperativa(
        nombre=nombre,
        geometria=WKTElement("POLYGON((-62 -32, -62 -33, -61 -33, -61 -32, -62 -32))", srid=4326),
        cuenca="test_cuenca",
        superficie_ha=500.0,
    )
    db.add(zona)
    db.flush()
    return zona.id


@pytest.fixture
def repo() -> GeoRepository:
    return GeoRepository()


# ──────────────────────────────────────────────
# JOB CRUD
# ──────────────────────────────────────────────


class TestJobCrud:
    def test_create_job(self, db: Session, repo: GeoRepository):
        job = repo.create_job(db, tipo="dem_pipeline", parametros={"test": True})
        assert job.id is not None
        assert job.tipo == "dem_pipeline"
        assert job.estado == EstadoGeoJob.PENDING
        assert job.parametros == {"test": True}

    def test_get_job_by_id(self, db: Session, repo: GeoRepository):
        job = repo.create_job(db, tipo="slope")
        fetched = repo.get_job_by_id(db, job.id)
        assert fetched is not None
        assert fetched.id == job.id

    def test_get_job_by_id_not_found(self, db: Session, repo: GeoRepository):
        result = repo.get_job_by_id(db, uuid.uuid4())
        assert result is None

    def test_get_jobs_paginated(self, db: Session, repo: GeoRepository):
        tipos = ["dem_pipeline", "slope", "aspect", "flow_dir", "twi"]
        for tipo in tipos:
            repo.create_job(db, tipo=tipo)

        items, total = repo.get_jobs(db, page=1, limit=3)
        assert total == 5
        assert len(items) == 3

    def test_get_jobs_with_estado_filter(self, db: Session, repo: GeoRepository):
        repo.create_job(db, tipo="dem_pipeline")
        items, total = repo.get_jobs(db, estado_filter=EstadoGeoJob.PENDING)
        assert total >= 1

    def test_get_jobs_with_tipo_filter(self, db: Session, repo: GeoRepository):
        repo.create_job(db, tipo="slope")
        items, total = repo.get_jobs(db, tipo_filter="slope")
        assert total >= 1

    def test_update_job_status(self, db: Session, repo: GeoRepository):
        job = repo.create_job(db, tipo="dem_pipeline")
        updated = repo.update_job_status(
            db, job.id,
            estado="completed",
            progreso=100,
            resultado={"done": True},
        )
        assert updated is not None
        assert updated.estado == "completed"
        assert updated.progreso == 100

    def test_update_job_status_not_found(self, db: Session, repo: GeoRepository):
        result = repo.update_job_status(db, uuid.uuid4(), estado="completed")
        assert result is None

    def test_update_job_celery_task_id(self, db: Session, repo: GeoRepository):
        job = repo.create_job(db, tipo="slope")
        updated = repo.update_job_status(
            db, job.id, celery_task_id="celery-123"
        )
        assert updated.celery_task_id == "celery-123"

    def test_update_job_error(self, db: Session, repo: GeoRepository):
        job = repo.create_job(db, tipo="aspect")
        updated = repo.update_job_status(
            db, job.id, estado="failed", error="something went wrong"
        )
        assert updated.error == "something went wrong"


# ──────────────────────────────────────────────
# LAYER CRUD
# ──────────────────────────────────────────────


class TestLayerCrud:
    def test_create_layer(self, db: Session, repo: GeoRepository):
        layer = repo.create_layer(
            db,
            nombre="Test DEM",
            tipo="dem_raw",
            fuente="gee",
            archivo_path="/data/dem.tif",
        )
        assert layer.id is not None
        assert layer.tipo == "dem_raw"
        assert layer.srid == 4326

    def test_get_layer_by_id(self, db: Session, repo: GeoRepository):
        layer = repo.create_layer(
            db, nombre="Test", tipo="slope", fuente="dem_pipeline", archivo_path="/x"
        )
        fetched = repo.get_layer_by_id(db, layer.id)
        assert fetched is not None
        assert fetched.nombre == "Test"

    def test_get_layer_by_id_not_found(self, db: Session, repo: GeoRepository):
        result = repo.get_layer_by_id(db, uuid.uuid4())
        assert result is None

    def test_get_layers_paginated(self, db: Session, repo: GeoRepository):
        for i in range(4):
            repo.create_layer(
                db, nombre=f"L{i}", tipo="twi", fuente="gee", archivo_path=f"/l{i}"
            )
        items, total = repo.get_layers(db, page=1, limit=2)
        assert total >= 4
        assert len(items) == 2

    def test_get_layers_with_tipo_filter(self, db: Session, repo: GeoRepository):
        repo.create_layer(
            db, nombre="Slope", tipo="slope", fuente="gee", archivo_path="/s"
        )
        items, total = repo.get_layers(db, tipo_filter="slope")
        assert total >= 1

    def test_get_layers_with_fuente_filter(self, db: Session, repo: GeoRepository):
        repo.create_layer(
            db, nombre="Test", tipo="dem_raw", fuente="manual", archivo_path="/f"
        )
        items, total = repo.get_layers(db, fuente_filter="manual")
        assert total >= 1

    def test_get_layer_by_tipo_and_area(self, db: Session, repo: GeoRepository):
        repo.create_layer(
            db, nombre="Test", tipo="hand", fuente="gee",
            archivo_path="/h", area_id="area_1",
        )
        result = repo.get_layer_by_tipo_and_area(db, "hand", "area_1")
        assert result is not None
        assert result.area_id == "area_1"

    def test_upsert_layer_creates_new(self, db: Session, repo: GeoRepository):
        layer = repo.upsert_layer(
            db, nombre="New", tipo="flow_acc", fuente="gee",
            archivo_path="/new", area_id="area_x",
        )
        assert layer.id is not None

    def test_upsert_layer_updates_existing(self, db: Session, repo: GeoRepository):
        first = repo.create_layer(
            db, nombre="Old", tipo="hand", fuente="gee",
            archivo_path="/old", area_id="area_y",
        )
        updated = repo.upsert_layer(
            db, nombre="Updated", tipo="hand", fuente="dem_pipeline",
            archivo_path="/updated", area_id="area_y",
        )
        assert updated.id == first.id
        assert updated.nombre == "Updated"
        assert updated.archivo_path == "/updated"

    def test_upsert_layer_no_area_id_creates_new(self, db: Session, repo: GeoRepository):
        layer = repo.upsert_layer(
            db, nombre="NoArea", tipo="dem_raw", fuente="gee", archivo_path="/noarea",
        )
        assert layer.id is not None

    def test_delete_layers_by_area_id(self, db: Session, repo: GeoRepository):
        repo.create_layer(
            db, nombre="A", tipo="slope", fuente="gee", archivo_path="/a", area_id="del_area"
        )
        repo.create_layer(
            db, nombre="B", tipo="aspect", fuente="gee", archivo_path="/b", area_id="del_area"
        )
        count = repo.delete_layers_by_area_id(db, "del_area")
        assert count == 2


# ──────────────────────────────────────────────
# APPROVED ZONING
# ──────────────────────────────────────────────


class TestApprovedZoning:
    def test_create_first_version(self, db: Session, repo: GeoRepository):
        zoning = repo.create_approved_zoning_version(
            db,
            feature_collection={"type": "FeatureCollection", "features": []},
            nombre="Test Zoning",
        )
        assert zoning.version == 1
        assert zoning.is_active is True

    def test_new_version_deactivates_previous(self, db: Session, repo: GeoRepository):
        first = repo.create_approved_zoning_version(
            db,
            feature_collection={"type": "FeatureCollection", "features": []},
        )
        second = repo.create_approved_zoning_version(
            db,
            feature_collection={"type": "FeatureCollection", "features": [{"x": 1}]},
        )
        db.refresh(first)
        assert first.is_active is False
        assert second.is_active is True
        assert second.version == 2

    def test_get_active_approved_zoning(self, db: Session, repo: GeoRepository):
        repo.create_approved_zoning_version(
            db,
            feature_collection={"type": "FeatureCollection", "features": []},
        )
        active = repo.get_active_approved_zoning(db)
        assert active is not None
        assert active.is_active is True

    def test_get_active_approved_zoning_with_cuenca(self, db: Session, repo: GeoRepository):
        repo.create_approved_zoning_version(
            db,
            feature_collection={"type": "FeatureCollection", "features": []},
            cuenca="norte",
        )
        active = repo.get_active_approved_zoning(db, cuenca="norte")
        assert active is not None
        assert active.cuenca == "norte"

    def test_list_approved_zonings(self, db: Session, repo: GeoRepository):
        for _ in range(3):
            repo.create_approved_zoning_version(
                db,
                feature_collection={"type": "FeatureCollection", "features": []},
            )
        items = repo.list_approved_zonings(db)
        assert len(items) == 3

    def test_get_approved_zoning_by_id(self, db: Session, repo: GeoRepository):
        zoning = repo.create_approved_zoning_version(
            db,
            feature_collection={"type": "FeatureCollection", "features": []},
        )
        fetched = repo.get_approved_zoning_by_id(db, zoning.id)
        assert fetched is not None

    def test_get_next_version(self, db: Session, repo: GeoRepository):
        repo.create_approved_zoning_version(
            db,
            feature_collection={"type": "FeatureCollection", "features": []},
        )
        next_v = repo.get_next_approved_zoning_version(db)
        assert next_v == 2

    def test_clear_active_approved_zoning(self, db: Session, repo: GeoRepository):
        repo.create_approved_zoning_version(
            db,
            feature_collection={"type": "FeatureCollection", "features": []},
        )
        deleted = repo.clear_active_approved_zoning(db)
        assert deleted == 1

    def test_clear_active_when_none_exists(self, db: Session, repo: GeoRepository):
        deleted = repo.clear_active_approved_zoning(db)
        assert deleted == 0


# ──────────────────────────────────────────────
# ANALISIS GEO
# ──────────────────────────────────────────────


class TestAnalisisGeo:
    def test_create_analisis(self, db: Session, repo: GeoRepository):
        analisis = repo.create_analisis(
            db, tipo="flood", fecha_analisis=date.today(),
        )
        assert analisis.id is not None
        assert analisis.estado == EstadoGeoJob.PENDING

    def test_get_analisis_by_id(self, db: Session, repo: GeoRepository):
        analisis = repo.create_analisis(db, tipo="classification", fecha_analisis=date.today())
        fetched = repo.get_analisis_by_id(db, analisis.id)
        assert fetched is not None

    def test_get_analisis_by_id_not_found(self, db: Session, repo: GeoRepository):
        result = repo.get_analisis_by_id(db, uuid.uuid4())
        assert result is None

    def test_get_analisis_list_paginated(self, db: Session, repo: GeoRepository):
        for _ in range(3):
            repo.create_analisis(db, tipo="flood", fecha_analisis=date.today())
        items, total = repo.get_analisis_list(db, page=1, limit=2)
        assert total >= 3
        assert len(items) == 2

    def test_get_analisis_list_with_filters(self, db: Session, repo: GeoRepository):
        repo.create_analisis(db, tipo="ndvi", fecha_analisis=date.today())
        items, total = repo.get_analisis_list(db, tipo_filter="ndvi")
        assert total >= 1

    def test_update_analisis_status(self, db: Session, repo: GeoRepository):
        analisis = repo.create_analisis(db, tipo="flood", fecha_analisis=date.today())
        updated = repo.update_analisis_status(
            db, analisis.id,
            estado="completed",
            celery_task_id="task-abc",
            resultado={"areas_affected": 5},
        )
        assert updated.estado == "completed"
        assert updated.celery_task_id == "task-abc"

    def test_update_analisis_status_not_found(self, db: Session, repo: GeoRepository):
        result = repo.update_analisis_status(db, uuid.uuid4(), estado="failed")
        assert result is None

    def test_update_analisis_error(self, db: Session, repo: GeoRepository):
        analisis = repo.create_analisis(db, tipo="custom", fecha_analisis=date.today())
        updated = repo.update_analisis_status(
            db, analisis.id, estado="failed", error="GEE timeout"
        )
        assert updated.error == "GEE timeout"
