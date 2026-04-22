"""
Tests for the flood calibration data layer.

Covers: FloodEvent/FloodLabel models, schemas, and repository CRUD.
"""

import uuid
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.auth.models import User  # noqa: F401 — register users table for FK resolution
from app.domains.geo.intelligence.models import ZonaOperativa  # noqa: F401 — register zonas_operativas table
from app.domains.geo.models import FloodEvent, FloodLabel
from app.domains.geo.schemas import (
    FloodEventCreate,
    FloodEventResponse,
    FloodLabelCreate,
    FloodLabelResponse,
)


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


# ── Model tests (require DB) ─────────────────────────


class TestFloodEventModel:
    """FloodEvent SQLAlchemy model creation and fields."""

    def test_create_flood_event_model(self, db):
        event = FloodEvent(
            event_date=date(2025, 3, 15),
            description="Test flood event",
            satellite_source="COPERNICUS/S2_SR_HARMONIZED",
        )
        db.add(event)
        db.flush()

        assert event.id is not None
        assert event.event_date == date(2025, 3, 15)
        assert event.description == "Test flood event"
        assert event.satellite_source == "COPERNICUS/S2_SR_HARMONIZED"
        assert event.created_at is not None

    def test_flood_event_default_satellite_source(self, db):
        event = FloodEvent(event_date=date(2025, 1, 1))
        db.add(event)
        db.flush()

        assert event.satellite_source == "COPERNICUS/S2_SR_HARMONIZED"

    def test_flood_event_optional_description(self, db):
        event = FloodEvent(event_date=date(2025, 6, 1))
        db.add(event)
        db.flush()

        assert event.description is None


class TestFloodLabelModel:
    """FloodLabel SQLAlchemy model creation and FK relationship."""

    def test_create_flood_label_with_fk(self, db):
        zona_id = _create_zona(db)
        event = FloodEvent(event_date=date(2025, 3, 15))
        db.add(event)
        db.flush()

        label = FloodLabel(
            event_id=event.id,
            zona_id=zona_id,
            is_flooded=True,
            ndwi_value=0.45,
            extracted_features={"hand_mean": 2.1, "twi_mean": 8.5},
        )
        db.add(label)
        db.flush()

        assert label.id is not None
        assert label.event_id == event.id
        assert label.zona_id == zona_id
        assert label.is_flooded is True
        assert label.ndwi_value == 0.45
        assert label.extracted_features["hand_mean"] == 2.1

    def test_flood_label_relationship_back_populates(self, db):
        zona_id = _create_zona(db)
        event = FloodEvent(event_date=date(2025, 3, 15))
        db.add(event)
        db.flush()

        label = FloodLabel(
            event_id=event.id,
            zona_id=zona_id,
            is_flooded=False,
        )
        db.add(label)
        db.flush()

        # Refresh to load relationship
        db.refresh(event)
        assert len(event.labels) == 1
        assert event.labels[0].is_flooded is False

    def test_flood_label_unique_constraint_event_zona(self, db):
        """Duplicate (event_id, zona_id) should raise IntegrityError."""
        from sqlalchemy.exc import IntegrityError

        zona_id = _create_zona(db)
        event = FloodEvent(event_date=date(2025, 3, 15))
        db.add(event)
        db.flush()

        label1 = FloodLabel(event_id=event.id, zona_id=zona_id, is_flooded=True)
        db.add(label1)
        db.flush()

        label2 = FloodLabel(event_id=event.id, zona_id=zona_id, is_flooded=False)
        db.add(label2)
        with pytest.raises(IntegrityError):
            db.flush()


# ── Schema tests (no DB) ────────────────────────────


class TestFloodEventCreateSchema:
    """FloodEventCreate Pydantic schema validation."""

    def test_valid_creation(self):
        schema = FloodEventCreate(
            event_date=date(2025, 5, 1),
            description="Heavy rain event",
            labels=[
                FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=True),
                FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=False),
            ],
        )
        assert schema.event_date == date(2025, 5, 1)
        assert len(schema.labels) == 2

    def test_requires_at_least_one_label(self):
        with pytest.raises(ValidationError, match="too_short"):
            FloodEventCreate(
                event_date=date(2025, 5, 1),
                labels=[],
            )

    def test_labels_field_is_required(self):
        with pytest.raises(ValidationError):
            FloodEventCreate(event_date=date(2025, 5, 1))

    def test_event_date_is_required(self):
        with pytest.raises(ValidationError):
            FloodEventCreate(
                labels=[FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=True)],
            )

    def test_description_is_optional(self):
        schema = FloodEventCreate(
            event_date=date(2025, 5, 1),
            labels=[FloodLabelCreate(zona_id=uuid.uuid4(), is_flooded=True)],
        )
        assert schema.description is None


class TestFloodEventResponseSchema:
    """FloodEventResponse serialization from ORM objects."""

    def test_serialization_from_attributes(self):
        now = datetime.now()
        _event_id = uuid.uuid4()
        _label_id = uuid.uuid4()
        _zona_id = uuid.uuid4()

        # Build fake ORM-like objects using SimpleNamespace to avoid class scope issues
        from types import SimpleNamespace

        fake_label = SimpleNamespace(
            id=_label_id,
            zona_id=_zona_id,
            is_flooded=True,
            ndwi_value=0.32,
            extracted_features=None,
        )
        fake_event = SimpleNamespace(
            id=_event_id,
            event_date=date(2025, 3, 15),
            description="Test",
            satellite_source="COPERNICUS/S2_SR_HARMONIZED",
            labels=[fake_label],
            created_at=now,
            updated_at=now,
        )

        response = FloodEventResponse.model_validate(fake_event)
        assert response.id == _event_id
        assert response.event_date == date(2025, 3, 15)
        assert len(response.labels) == 1
        assert response.labels[0].is_flooded is True
        assert response.labels[0].ndwi_value == 0.32
