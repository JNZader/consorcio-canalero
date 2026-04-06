"""
Tests for FloodFlowService.compute_flood_flow with GEE methods mocked.

All GEE I/O is replaced with controlled return values so tests run
without a live Earth Engine account. The DB fixture is real.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import patch

import pytest

from app.domains.geo.hydrology.models import FloodFlowResult  # noqa: F401 — register table
from app.domains.geo.hydrology.repository import FloodFlowRepository
from app.domains.geo.hydrology.schemas import FloodFlowResponse
from app.domains.geo.hydrology.service import FloodFlowService
from app.domains.geo.intelligence.models import ZonaOperativa

# asyncio_mode = auto in pytest.ini — all async test functions are collected automatically


# ── Constants ─────────────────────────────────────────────────────────────

_SLOPE_DEGREES = 2.0
_NDVI = 0.35          # → C = 0.45 (moderate vegetation band)
_C_SOURCE = "ndvi_sentinel2"
_CANAL_LEN = 800.0    # metres
_FECHA = date(2025, 3, 15)


# ── Helpers ────────────────────────────────────────────────────────────────


def _create_zona(
    db,
    nombre: str = "Zona Servicio Test",
    superficie_ha: float = 500.0,
    capacidad_m3s: float | None = 10.0,
) -> uuid.UUID:
    """Insert a minimal ZonaOperativa with a real polygon geometry."""
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


def _make_service() -> FloodFlowService:
    return FloodFlowService(FloodFlowRepository())


# ── Patch context manager ─────────────────────────────────────────────────

# All tests in this module patch the three GEE methods at the class level
# so no real GEE calls are made. Canal-length is also patched to avoid
# hitting a non-existent 'waterways' table.

_GEE_PATCHES = [
    patch(
        "app.domains.geo.hydrology.service.FloodFlowService.get_slope_from_gee",
        return_value=_SLOPE_DEGREES,
    ),
    patch(
        "app.domains.geo.hydrology.service.FloodFlowService.get_ndvi_and_c",
        return_value=(_NDVI, _C_SOURCE),
    ),
    patch(
        "app.domains.geo.hydrology.service.FloodFlowService.get_canal_length_for_zona",
        return_value=_CANAL_LEN,
    ),
]


# ── Test class ────────────────────────────────────────────────────────────


class TestFloodFlowService:
    """Service-level tests for FloodFlowService.compute_flood_flow."""

    # ── Structural correctness ─────────────────────────────────────────────

    async def test_returns_flood_flow_response_type(self, db):
        """compute_flood_flow must return a FloodFlowResponse instance."""
        zona_id = _create_zona(db)
        service = _make_service()

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            response = await service.compute_flood_flow(db, [zona_id], _FECHA)

        assert isinstance(response, FloodFlowResponse)

    async def test_result_has_valid_tc_and_caudal(self, db):
        """Computed tc_minutos and caudal_m3s must be positive numbers."""
        zona_id = _create_zona(db)
        service = _make_service()

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            response = await service.compute_flood_flow(db, [zona_id], _FECHA)

        assert len(response.results) == 1
        result = response.results[0]
        assert result.tc_minutos > 0
        assert result.caudal_m3s > 0

    async def test_nivel_riesgo_is_valid_value(self, db):
        """nivel_riesgo must be one of the five accepted classifications."""
        zona_id = _create_zona(db)
        service = _make_service()
        valid = {"bajo", "moderado", "alto", "critico", "sin_capacidad"}

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            response = await service.compute_flood_flow(db, [zona_id], _FECHA)

        assert response.results[0].nivel_riesgo in valid

    async def test_result_zona_id_matches_input(self, db):
        """Result zona_id must match the requested zona_id."""
        zona_id = _create_zona(db)
        service = _make_service()

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            response = await service.compute_flood_flow(db, [zona_id], _FECHA)

        assert response.results[0].zona_id == zona_id

    # ── Upsert idempotency ─────────────────────────────────────────────────

    async def test_calling_twice_does_not_duplicate_rows(self, db):
        """Two calls for same (zona_id, fecha_lluvia) must produce 1 DB row."""
        from sqlalchemy import func, select

        zona_id = _create_zona(db)
        service = _make_service()

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            await service.compute_flood_flow(db, [zona_id], _FECHA)

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            await service.compute_flood_flow(db, [zona_id], _FECHA)

        count = db.execute(
            select(func.count()).where(
                FloodFlowResult.zona_id == zona_id,
                FloodFlowResult.fecha_lluvia == _FECHA,
            )
        ).scalar()

        assert count == 1

    # ── Unknown zona → error, not crash ───────────────────────────────────

    async def test_unknown_zona_id_goes_to_errors(self, db):
        """A zona_id that doesn't exist must be collected in response.errors."""
        nonexistent = uuid.uuid4()
        service = _make_service()

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            response = await service.compute_flood_flow(db, [nonexistent], _FECHA)

        assert len(response.results) == 0
        assert len(response.errors) == 1
        assert str(nonexistent) in response.errors[0]["zona_id"]

    # ── Multiple zones ─────────────────────────────────────────────────────

    async def test_multiple_zones_all_processed(self, db):
        """Two valid zone IDs must produce two results with no errors."""
        zona_a = _create_zona(db, nombre="Zona A")
        zona_b = _create_zona(db, nombre="Zona B")
        service = _make_service()

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            response = await service.compute_flood_flow(db, [zona_a, zona_b], _FECHA)

        assert len(response.results) == 2
        assert len(response.errors) == 0

    # ── sin_capacidad classification ───────────────────────────────────────

    async def test_zona_without_capacidad_gets_sin_capacidad(self, db):
        """A zone with capacidad_m3s=None must be classified as 'sin_capacidad'."""
        zona_id = _create_zona(db, capacidad_m3s=None)
        service = _make_service()

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            response = await service.compute_flood_flow(db, [zona_id], _FECHA)

        assert response.results[0].nivel_riesgo == "sin_capacidad"
        assert response.results[0].porcentaje_capacidad is None

    # ── Task 4.5 — superficie_ha = 0 edge case ────────────────────────────

    async def test_zona_with_zero_superficie_handled_gracefully(self, db):
        """superficie_ha=0 must NOT crash the service.

        The service applies `zona.superficie_ha or 1.0`, so zero falls back to
        1.0 ha.  This means area_km2 = 0.01 km² and Q > 0.  The test verifies:
          1. No exception is raised.
          2. A result is returned (not an error).
          3. caudal_m3s > 0 (fallback area is used, not zero).

        Risk note: `or 1.0` means genuine zero-area zones silently use 1 ha.
        A future improvement could raise a warning or skip with an error entry
        rather than silently substituting a fallback.
        """
        zona_id = _create_zona(db, superficie_ha=0.0)
        service = _make_service()

        with _GEE_PATCHES[0], _GEE_PATCHES[1], _GEE_PATCHES[2]:
            response = await service.compute_flood_flow(db, [zona_id], _FECHA)

        # Current behavior: fallback to 1.0 ha → result is produced, no error
        assert len(response.errors) == 0, (
            "superficie_ha=0 should not produce an error (service uses 1.0 ha fallback)"
        )
        assert len(response.results) == 1
        assert response.results[0].caudal_m3s > 0
        # area_km2 must reflect the 1.0 ha fallback (= 0.01 km²)
        assert response.results[0].area_km2 == pytest.approx(0.01)
