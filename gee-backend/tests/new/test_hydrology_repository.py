"""
Tests for FloodFlowRepository — real DB via `db` fixture, transaction rollback.

Covers: upsert (create + idempotency), get_by_zona (ordering), get_latest_by_all_zonas.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.domains.geo.hydrology.models import FloodFlowResult  # noqa: F401 — register table
from app.domains.geo.hydrology.repository import FloodFlowRepository
from app.domains.geo.intelligence.models import ZonaOperativa


# ── Helpers ────────────────────────────────────────────────────────────────


def _create_zona(
    db,
    nombre: str = "Zona Hidro Test",
    superficie_ha: float = 500.0,
    capacidad_m3s: float | None = 10.0,
) -> uuid.UUID:
    """Insert a minimal ZonaOperativa record and return its id."""
    from geoalchemy2.elements import WKTElement

    zona = ZonaOperativa(
        nombre=nombre,
        geometria=WKTElement(
            "POLYGON((-62 -32, -62 -33, -61 -33, -61 -32, -62 -32))", srid=4326
        ),
        cuenca="test_cuenca",
        superficie_ha=superficie_ha,
        capacidad_m3s=capacidad_m3s,
    )
    db.add(zona)
    db.flush()
    return zona.id


def _minimal_data(
    *,
    fecha_calculo: date | None = None,
    tc_minutos: float = 15.0,
    c_escorrentia: float = 0.45,
    c_source: str = "ndvi_sentinel2",
    intensidad_mm_h: float = 20.0,
    area_km2: float = 5.0,
    caudal_m3s: float = 4.2,
    capacidad_m3s: float | None = 10.0,
    porcentaje_capacidad: float | None = 42.0,
    nivel_riesgo: str = "bajo",
) -> dict:
    return {
        "fecha_calculo": fecha_calculo or date(2025, 3, 15),
        "tc_minutos": tc_minutos,
        "c_escorrentia": c_escorrentia,
        "c_source": c_source,
        "intensidad_mm_h": intensidad_mm_h,
        "area_km2": area_km2,
        "caudal_m3s": caudal_m3s,
        "capacidad_m3s": capacidad_m3s,
        "porcentaje_capacidad": porcentaje_capacidad,
        "nivel_riesgo": nivel_riesgo,
    }


# ── Test class ────────────────────────────────────────────────────────────


class TestFloodFlowRepository:
    """Integration tests for FloodFlowRepository using a real database."""

    # ── upsert ────────────────────────────────────────────────────────────

    def test_upsert_creates_record(self, db):
        """Insert a new record — it must exist in DB with expected fields."""
        repo = FloodFlowRepository()
        zona_id = _create_zona(db)
        fecha = date(2025, 3, 10)
        data = _minimal_data(caudal_m3s=3.0, nivel_riesgo="bajo")

        record = repo.upsert(db, zona_id, fecha, data)

        assert record.id is not None
        assert record.zona_id == zona_id
        assert record.fecha_lluvia == fecha
        assert record.caudal_m3s == pytest.approx(3.0)
        assert record.nivel_riesgo == "bajo"

    def test_upsert_is_idempotent(self, db):
        """Insert same (zona_id, fecha_lluvia) twice — only 1 row, latest value wins."""
        from sqlalchemy import select

        repo = FloodFlowRepository()
        zona_id = _create_zona(db)
        fecha = date(2025, 3, 11)

        # First insert
        repo.upsert(db, zona_id, fecha, _minimal_data(caudal_m3s=4.0, nivel_riesgo="bajo"))

        # Second insert — different caudal
        repo.upsert(db, zona_id, fecha, _minimal_data(caudal_m3s=9.5, nivel_riesgo="alto"))

        # Must have exactly 1 row
        rows = db.execute(
            select(FloodFlowResult).where(
                FloodFlowResult.zona_id == zona_id,
                FloodFlowResult.fecha_lluvia == fecha,
            )
        ).scalars().all()

        assert len(rows) == 1
        assert rows[0].caudal_m3s == pytest.approx(9.5)
        assert rows[0].nivel_riesgo == "alto"

    # ── get_by_zona ───────────────────────────────────────────────────────

    def test_get_by_zona_returns_ordered(self, db):
        """Insert 3 records with different dates — result must be DESC by fecha_lluvia."""
        repo = FloodFlowRepository()
        zona_id = _create_zona(db)

        dates = [date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1)]
        for d in dates:
            repo.upsert(db, zona_id, d, _minimal_data())

        records = repo.get_by_zona(db, zona_id, limit=10)

        assert len(records) == 3
        # Verify strictly descending order
        for i in range(len(records) - 1):
            assert records[i].fecha_lluvia > records[i + 1].fecha_lluvia

    def test_get_by_zona_respects_limit(self, db):
        """Limit parameter should cap the number of returned rows."""
        repo = FloodFlowRepository()
        zona_id = _create_zona(db)

        for month in range(1, 6):
            repo.upsert(db, zona_id, date(2025, month, 1), _minimal_data())

        records = repo.get_by_zona(db, zona_id, limit=3)
        assert len(records) == 3

    def test_get_by_zona_returns_empty_for_unknown_zone(self, db):
        """Unknown zona_id must return an empty list, not raise."""
        repo = FloodFlowRepository()
        records = repo.get_by_zona(db, uuid.uuid4(), limit=10)
        assert records == []

    # ── get_latest_by_all_zonas ───────────────────────────────────────────

    def test_get_latest_by_all_zonas(self, db):
        """Insert records for 2 zones — both must appear in the result."""
        repo = FloodFlowRepository()
        zona_a = _create_zona(db, nombre="Zona A")
        zona_b = _create_zona(db, nombre="Zona B")

        repo.upsert(db, zona_a, date(2025, 3, 1), _minimal_data(caudal_m3s=3.0))
        repo.upsert(db, zona_a, date(2025, 3, 5), _minimal_data(caudal_m3s=3.5))
        repo.upsert(db, zona_b, date(2025, 3, 3), _minimal_data(caudal_m3s=7.0))

        results = repo.get_latest_by_all_zonas(db, fecha=date(2025, 3, 10))

        zona_ids = {r.zona_id for r in results}
        assert zona_a in zona_ids
        assert zona_b in zona_ids

        # zona_a should return the latest record (Mar 5, caudal=3.5)
        zona_a_result = next(r for r in results if r.zona_id == zona_a)
        assert zona_a_result.fecha_lluvia == date(2025, 3, 5)
        assert zona_a_result.caudal_m3s == pytest.approx(3.5)

    def test_get_latest_by_all_zonas_respects_upper_bound(self, db):
        """Records after `fecha` must NOT be included."""
        repo = FloodFlowRepository()
        zona_id = _create_zona(db)

        repo.upsert(db, zona_id, date(2025, 1, 1), _minimal_data(caudal_m3s=2.0))
        repo.upsert(db, zona_id, date(2025, 6, 1), _minimal_data(caudal_m3s=9.0))

        # Upper bound excludes Jun 1
        results = repo.get_latest_by_all_zonas(db, fecha=date(2025, 3, 1))

        assert len(results) == 1
        assert results[0].fecha_lluvia == date(2025, 1, 1)
        assert results[0].caudal_m3s == pytest.approx(2.0)
