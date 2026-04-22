"""
Tests for the rainfall data layer.

Covers: RainfallRecord model and unique constraints.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.models import User  # noqa: F401 — register users table for FK resolution
from app.domains.geo.intelligence.models import ZonaOperativa  # noqa: F401 — register zonas_operativas table
from app.domains.geo.models import RainfallRecord


# ── Helpers ────────────────────────────────────────


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


# ── Model tests ──────────────────────────────────


class TestRainfallRecordModel:
    """RainfallRecord SQLAlchemy model creation and constraints."""

    def test_create_rainfall_record(self, db):
        zona_id = _create_zona(db)
        record = RainfallRecord(
            zona_operativa_id=zona_id,
            date=date(2025, 3, 15),
            precipitation_mm=12.5,
            source="CHIRPS",
        )
        db.add(record)
        db.flush()

        assert record.id is not None
        assert record.zona_operativa_id == zona_id
        assert record.date == date(2025, 3, 15)
        assert record.precipitation_mm == 12.5
        assert record.source == "CHIRPS"

    def test_rainfall_record_default_source(self, db):
        zona_id = _create_zona(db)
        record = RainfallRecord(
            zona_operativa_id=zona_id,
            date=date(2025, 3, 16),
            precipitation_mm=5.0,
        )
        db.add(record)
        db.flush()

        assert record.source == "CHIRPS"

    def test_unique_constraint_zona_date_source(self, db):
        """Duplicate (zona_operativa_id, date, source) raises IntegrityError."""
        zona_id = _create_zona(db)

        r1 = RainfallRecord(
            zona_operativa_id=zona_id,
            date=date(2025, 4, 1),
            precipitation_mm=10.0,
            source="CHIRPS",
        )
        db.add(r1)
        db.flush()

        r2 = RainfallRecord(
            zona_operativa_id=zona_id,
            date=date(2025, 4, 1),
            precipitation_mm=15.0,
            source="CHIRPS",
        )
        db.add(r2)
        with pytest.raises(IntegrityError):
            db.flush()

    def test_different_source_same_zona_date_allowed(self, db):
        """Same zona+date but different source is allowed."""
        zona_id = _create_zona(db)

        r1 = RainfallRecord(
            zona_operativa_id=zona_id,
            date=date(2025, 4, 2),
            precipitation_mm=10.0,
            source="CHIRPS",
        )
        r2 = RainfallRecord(
            zona_operativa_id=zona_id,
            date=date(2025, 4, 2),
            precipitation_mm=12.0,
            source="GPM",
        )
        db.add_all([r1, r2])
        db.flush()

        assert r1.id != r2.id
