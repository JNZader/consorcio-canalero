"""
Tests for the hydrology router endpoints.

Strategy: direct function calls with mocked dependencies — same pattern
used throughout `test_intelligence_router.py`. This avoids the need to
wire up a full TestClient + JWT auth stack for every endpoint test.

For true HTTP-level contract tests (auth headers, query param parsing,
response status codes) a separate integration test suite can be added
once a shared test-client fixture with auth override is available.
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.geo.hydrology.schemas import (
    FloodFlowHistoryResponse,
    FloodFlowRequest,
    FloodFlowResponse,
    ZonaFloodFlowResult,
)


# ── Shared helpers ─────────────────────────────────────────────────────────


def _make_zona_result(zona_id: uuid.UUID | None = None) -> ZonaFloodFlowResult:
    """Build a minimal ZonaFloodFlowResult for mock returns."""
    return ZonaFloodFlowResult(
        zona_id=zona_id or uuid.uuid4(),
        zona_nombre="Zona Test",
        tc_minutos=14.3,
        c_escorrentia=0.45,
        c_source="ndvi_sentinel2",
        intensidad_mm_h=20.0,
        area_km2=5.0,
        caudal_m3s=4.2,
        capacidad_m3s=10.0,
        porcentaje_capacidad=42.0,
        nivel_riesgo="bajo",
        fecha_lluvia=date(2025, 3, 15),
        fecha_calculo=date(2025, 3, 15),
    )


def _make_flood_response(zona_id: uuid.UUID | None = None) -> FloodFlowResponse:
    zona_id = zona_id or uuid.uuid4()
    return FloodFlowResponse(
        total_zonas=1,
        fecha_lluvia=date(2025, 3, 15),
        results=[_make_zona_result(zona_id)],
        errors=[],
    )


# ── Schema validation ─────────────────────────────────────────────────────


class TestFloodFlowRequestSchema:
    """Pydantic schema validation for FloodFlowRequest."""

    def test_valid_request(self):
        zona_id = uuid.uuid4()
        req = FloodFlowRequest(
            zona_ids=[zona_id],
            fecha_lluvia=date(2025, 3, 15),
        )
        assert req.zona_ids == [zona_id]
        assert req.fecha_lluvia == date(2025, 3, 15)

    def test_empty_zona_ids_raises_validation_error(self):
        """min_length=1 on zona_ids must reject an empty list → 422 in HTTP context."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FloodFlowRequest(zona_ids=[], fecha_lluvia=date(2025, 3, 15))

    def test_multiple_zona_ids_accepted(self):
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        req = FloodFlowRequest(zona_ids=ids, fecha_lluvia=date(2025, 3, 15))
        assert len(req.zona_ids) == 3


# ── Endpoint: POST /flood-flow ─────────────────────────────────────────────


class TestComputeFloodFlowEndpoint:
    """Direct-call tests for the compute_flood_flow endpoint function."""

    async def test_post_flood_flow_returns_response(self):
        """Valid payload → service is called and response is returned."""
        from app.domains.geo.hydrology.router import compute_flood_flow

        zona_id = uuid.uuid4()
        expected = _make_flood_response(zona_id)

        mock_service = MagicMock()
        mock_service.compute_flood_flow = AsyncMock(return_value=expected)

        payload = FloodFlowRequest(
            zona_ids=[zona_id],
            fecha_lluvia=date(2025, 3, 15),
        )

        with patch(
            "app.domains.geo.hydrology.router.FloodFlowService",
            return_value=mock_service,
        ):
            result = await compute_flood_flow(
                payload=payload,
                db=MagicMock(),
                _user=MagicMock(),
            )

        assert isinstance(result, FloodFlowResponse)
        assert result.total_zonas == 1
        assert len(result.results) == 1
        mock_service.compute_flood_flow.assert_called_once()

    async def test_post_flood_flow_passes_correct_args(self):
        """Service.compute_flood_flow must receive zona_ids and fecha_lluvia from payload."""
        from app.domains.geo.hydrology.router import compute_flood_flow

        zona_id = uuid.uuid4()
        fecha = date(2025, 4, 1)
        expected = _make_flood_response(zona_id)

        mock_service = MagicMock()
        mock_service.compute_flood_flow = AsyncMock(return_value=expected)

        payload = FloodFlowRequest(zona_ids=[zona_id], fecha_lluvia=fecha)
        mock_db = MagicMock()

        with patch(
            "app.domains.geo.hydrology.router.FloodFlowService",
            return_value=mock_service,
        ):
            await compute_flood_flow(
                payload=payload,
                db=mock_db,
                _user=MagicMock(),
            )

        call_args = mock_service.compute_flood_flow.call_args
        # Positional: db, zona_ids, fecha_lluvia
        assert call_args.args[1] == [zona_id]
        assert call_args.args[2] == fecha

    async def test_post_flood_flow_with_errors_in_response(self):
        """Service can return partial results with errors — endpoint passes them through."""
        from app.domains.geo.hydrology.router import compute_flood_flow

        zona_id = uuid.uuid4()
        bad_zona = uuid.uuid4()
        response_with_errors = FloodFlowResponse(
            total_zonas=2,
            fecha_lluvia=date(2025, 3, 15),
            results=[_make_zona_result(zona_id)],
            errors=[{"zona_id": str(bad_zona), "error": "Zona not found"}],
        )

        mock_service = MagicMock()
        mock_service.compute_flood_flow = AsyncMock(return_value=response_with_errors)

        payload = FloodFlowRequest(
            zona_ids=[zona_id, bad_zona],
            fecha_lluvia=date(2025, 3, 15),
        )

        with patch(
            "app.domains.geo.hydrology.router.FloodFlowService",
            return_value=mock_service,
        ):
            result = await compute_flood_flow(
                payload=payload,
                db=MagicMock(),
                _user=MagicMock(),
            )

        assert len(result.results) == 1
        assert len(result.errors) == 1


# ── Endpoint: GET /flood-flow/{zona_id} ───────────────────────────────────


class TestGetFloodFlowHistoryEndpoint:
    """Direct-call tests for the get_flood_flow_history endpoint function."""

    def test_get_flood_flow_history_returns_response(self):
        """Valid zona_id → repo is called and history response returned."""
        from app.domains.geo.hydrology.router import get_flood_flow_history

        zona_id = uuid.uuid4()
        record = _make_zona_result(zona_id)

        mock_repo = MagicMock()
        mock_repo.get_by_zona.return_value = [
            SimpleNamespace(**record.model_dump())
        ]

        result = get_flood_flow_history(
            zona_id=zona_id,
            limit=10,
            db=MagicMock(),
            repo=mock_repo,
            _user=MagicMock(),
        )

        assert isinstance(result, FloodFlowHistoryResponse)
        assert result.zona_id == zona_id
        assert result.total == 1
        mock_repo.get_by_zona.assert_called_once()

    def test_get_flood_flow_history_empty(self):
        """No records for a zone → total=0 and empty list."""
        from app.domains.geo.hydrology.router import get_flood_flow_history

        mock_repo = MagicMock()
        mock_repo.get_by_zona.return_value = []

        result = get_flood_flow_history(
            zona_id=uuid.uuid4(),
            limit=10,
            db=MagicMock(),
            repo=mock_repo,
            _user=MagicMock(),
        )

        assert result.total == 0
        assert result.records == []

    def test_get_flood_flow_history_respects_limit(self):
        """limit parameter is forwarded to the repository."""
        from app.domains.geo.hydrology.router import get_flood_flow_history

        zona_id = uuid.uuid4()
        mock_repo = MagicMock()
        mock_repo.get_by_zona.return_value = []

        get_flood_flow_history(
            zona_id=zona_id,
            limit=25,
            db=MagicMock(),
            repo=mock_repo,
            _user=MagicMock(),
        )

        mock_repo.get_by_zona.assert_called_once_with(
            mock_repo.get_by_zona.call_args.args[0],  # db mock
            zona_id=zona_id,
            limit=25,
        )


# ── Dependency helpers ─────────────────────────────────────────────────────


class TestRouterHelpers:
    """Smoke tests for the router's lazy-import helpers."""

    def test_get_repo_returns_repository_instance(self):
        from app.domains.geo.hydrology.repository import FloodFlowRepository
        from app.domains.geo.hydrology.router import _get_repo

        repo = _get_repo()
        assert isinstance(repo, FloodFlowRepository)

    def test_require_operator_returns_callable(self):
        from app.domains.geo.hydrology.router import _require_operator

        dep = _require_operator()
        assert callable(dep)
