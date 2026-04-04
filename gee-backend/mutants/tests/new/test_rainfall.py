"""
Tests for the rainfall data layer.

Covers: RainfallRecord model, unique constraints, and repository CRUD/aggregation.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.models import User  # noqa: F401 — register users table for FK resolution
from app.domains.geo.intelligence.models import ZonaOperativa  # noqa: F401 — register zonas_operativas table
from app.domains.geo.models import RainfallRecord
from app.domains.geo.repository import GeoRepository


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


# ── Repository tests ─────────────────────────────


class TestRainfallRepository:
    """GeoRepository rainfall CRUD and aggregation operations."""

    def setup_method(self):
        self.repo = GeoRepository()

    # ── insert_rainfall_record ──

    def test_insert_rainfall_record(self, db):
        zona_id = _create_zona(db)
        record = self.repo.insert_rainfall_record(
            db,
            zona_operativa_id=zona_id,
            record_date=date(2025, 5, 1),
            precipitation_mm=8.3,
            source="CHIRPS",
        )

        assert record.id is not None
        assert record.precipitation_mm == 8.3
        assert record.date == date(2025, 5, 1)

    # ── bulk_upsert_rainfall ──

    def test_bulk_upsert_rainfall_insert(self, db):
        zona_id = _create_zona(db)
        records = [
            {
                "zona_operativa_id": zona_id,
                "date": date(2025, 6, 1),
                "precipitation_mm": 5.0,
                "source": "CHIRPS",
            },
            {
                "zona_operativa_id": zona_id,
                "date": date(2025, 6, 2),
                "precipitation_mm": 10.0,
                "source": "CHIRPS",
            },
        ]

        count = self.repo.bulk_upsert_rainfall(db, records)
        assert count == 2

    def test_bulk_upsert_rainfall_updates_on_duplicate(self, db):
        zona_id = _create_zona(db)
        original = [
            {
                "zona_operativa_id": zona_id,
                "date": date(2025, 7, 1),
                "precipitation_mm": 5.0,
                "source": "CHIRPS",
            },
        ]
        self.repo.bulk_upsert_rainfall(db, original)

        # Upsert with new precipitation value
        updated = [
            {
                "zona_operativa_id": zona_id,
                "date": date(2025, 7, 1),
                "precipitation_mm": 99.0,
                "source": "CHIRPS",
            },
        ]
        count = self.repo.bulk_upsert_rainfall(db, updated)
        assert count == 1

        # Verify the value was updated
        results = self.repo.get_rainfall_by_zone(
            db, zona_id, start_date=date(2025, 7, 1), end_date=date(2025, 7, 1)
        )
        assert len(results) == 1
        assert results[0].precipitation_mm == 99.0

    def test_bulk_upsert_rainfall_empty_list(self, db):
        count = self.repo.bulk_upsert_rainfall(db, [])
        assert count == 0

    # ── get_rainfall_by_zone ──

    def test_get_rainfall_by_zone(self, db):
        zona_id = _create_zona(db)
        for day in range(1, 6):
            self.repo.insert_rainfall_record(
                db,
                zona_operativa_id=zona_id,
                record_date=date(2025, 8, day),
                precipitation_mm=float(day * 2),
            )

        results = self.repo.get_rainfall_by_zone(db, zona_id)
        assert len(results) == 5
        # Ordered by date asc
        assert results[0].date < results[-1].date

    def test_get_rainfall_by_zone_date_range_filter(self, db):
        zona_id = _create_zona(db)
        for day in range(1, 11):
            self.repo.insert_rainfall_record(
                db,
                zona_operativa_id=zona_id,
                record_date=date(2025, 9, day),
                precipitation_mm=1.0,
            )

        results = self.repo.get_rainfall_by_zone(
            db, zona_id, start_date=date(2025, 9, 3), end_date=date(2025, 9, 7)
        )
        assert len(results) == 5
        assert results[0].date == date(2025, 9, 3)
        assert results[-1].date == date(2025, 9, 7)

    def test_get_rainfall_by_zone_empty_results(self, db):
        results = self.repo.get_rainfall_by_zone(db, uuid.uuid4())
        assert results == []

    # ── get_rainfall_daily_max ──

    def test_get_rainfall_daily_max(self, db):
        zona1 = _create_zona(db, "Zona 1")
        zona2 = _create_zona(db, "Zona 2")

        # Day 1: zona1=5, zona2=10 → max=10
        self.repo.insert_rainfall_record(
            db, zona_operativa_id=zona1, record_date=date(2025, 10, 1), precipitation_mm=5.0,
        )
        self.repo.insert_rainfall_record(
            db, zona_operativa_id=zona2, record_date=date(2025, 10, 1), precipitation_mm=10.0,
        )
        # Day 2: zona1=20 → max=20
        self.repo.insert_rainfall_record(
            db, zona_operativa_id=zona1, record_date=date(2025, 10, 2), precipitation_mm=20.0,
        )

        results = self.repo.get_rainfall_daily_max(
            db, start_date=date(2025, 10, 1), end_date=date(2025, 10, 2)
        )

        assert len(results) == 2
        day1 = next(r for r in results if r["date"] == "2025-10-01")
        day2 = next(r for r in results if r["date"] == "2025-10-02")
        assert day1["precipitation_mm"] == 10.0
        assert day2["precipitation_mm"] == 20.0

    # ── get_rainfall_summary ──

    def test_get_rainfall_summary(self, db):
        zona_id = _create_zona(db)
        values = [0.0, 5.0, 10.0, 0.0, 15.0]
        for i, mm in enumerate(values):
            self.repo.insert_rainfall_record(
                db,
                zona_operativa_id=zona_id,
                record_date=date(2025, 11, i + 1),
                precipitation_mm=mm,
            )

        summaries = self.repo.get_rainfall_summary(
            db, start_date=date(2025, 11, 1), end_date=date(2025, 11, 5)
        )

        assert len(summaries) == 1
        s = summaries[0]
        assert s["zona_operativa_id"] == zona_id
        assert s["total_mm"] == 30.0
        assert s["max_mm"] == 15.0
        assert s["avg_mm"] == pytest.approx(6.0, abs=0.01)

    def test_get_rainfall_summary_filter_by_zone(self, db):
        zona1 = _create_zona(db, "Z1")
        zona2 = _create_zona(db, "Z2")

        self.repo.insert_rainfall_record(
            db, zona_operativa_id=zona1, record_date=date(2025, 12, 1), precipitation_mm=10.0,
        )
        self.repo.insert_rainfall_record(
            db, zona_operativa_id=zona2, record_date=date(2025, 12, 1), precipitation_mm=20.0,
        )

        summaries = self.repo.get_rainfall_summary(
            db,
            start_date=date(2025, 12, 1),
            end_date=date(2025, 12, 1),
            zona_operativa_id=zona1,
        )
        assert len(summaries) == 1
        assert summaries[0]["total_mm"] == 10.0

    # ── get_accumulated_rainfall ──

    def test_get_accumulated_rainfall(self, db):
        zona_id = _create_zona(db)
        # Insert 7 days of rainfall
        for day in range(1, 8):
            self.repo.insert_rainfall_record(
                db,
                zona_operativa_id=zona_id,
                record_date=date(2026, 1, day),
                precipitation_mm=10.0,
            )

        # 2-day window ending on Jan 7 → includes Jan 6 and Jan 7
        acc_2d = self.repo.get_accumulated_rainfall(
            db, zona_id, reference_date=date(2026, 1, 7), window_days=2
        )
        assert acc_2d == 20.0

        # 7-day window ending on Jan 7 → includes Jan 1-7
        acc_7d = self.repo.get_accumulated_rainfall(
            db, zona_id, reference_date=date(2026, 1, 7), window_days=7
        )
        assert acc_7d == 70.0

    def test_get_accumulated_rainfall_no_data(self, db):
        result = self.repo.get_accumulated_rainfall(
            db, uuid.uuid4(), reference_date=date(2026, 2, 1), window_days=7
        )
        assert result == 0.0

    def test_get_accumulated_rainfall_partial_window(self, db):
        """Window larger than available data returns only what exists."""
        zona_id = _create_zona(db)
        self.repo.insert_rainfall_record(
            db, zona_operativa_id=zona_id, record_date=date(2026, 3, 5), precipitation_mm=25.0,
        )

        # 30-day window but only 1 record exists
        result = self.repo.get_accumulated_rainfall(
            db, zona_id, reference_date=date(2026, 3, 5), window_days=30
        )
        assert result == 25.0
