"""
Tests for the visualization router — HTTP layer TDD (tasks 4.1–4.9).

Strategy: direct function calls with mocked VisualizationService — same
pattern as test_hydrology_router.py. This avoids full TestClient + JWT
stack while still validating endpoint logic, response media types, and
error propagation.

TDD cycle: RED → GREEN → REFACTOR
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import Response


# ---------------------------------------------------------------------------
# Stub pyvista so renderer.py can be imported without a display
# ---------------------------------------------------------------------------

def _make_pyvista_stub() -> types.ModuleType:
    pv = types.ModuleType("pyvista")

    class _StructuredGrid:
        def __init__(self, *a, **kw):
            self._data: dict = {}
        def __setitem__(self, k, v): self._data[k] = v
        def __getitem__(self, k): return self._data[k]

    class _PolyData:
        def __init__(self, *a, **kw):
            self.lines = None
            self.points = None

    class _Plotter:
        def __init__(self, *a, **kw): ...
        def add_mesh(self, *a, **kw): ...
        def screenshot(self, *a, **kw): return b"PNG_BYTES"
        def open_movie(self, path, *a, **kw): ...
        def write_frame(self, *a, **kw): ...
        def close(self, *a, **kw): ...
        def set_position(self, *a, **kw): ...

    pv.StructuredGrid = _StructuredGrid
    pv.PolyData = _PolyData
    pv.Plotter = _Plotter
    pv.start_xvfb = MagicMock()
    return pv


sys.modules.setdefault("pyvista", _make_pyvista_stub())


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

def _make_service(
    cuencas_bytes: bytes = b"PNG_CUENCAS",
    escorrentia_bytes: bytes = b"PNG_ESCORRENTIA",
    riesgo_bytes: bytes = b"PNG_RIESGO",
    animacion_bytes: bytes = b"MP4_ANIMACION",
) -> MagicMock:
    """Build a mock VisualizationService with configurable return values."""
    svc = MagicMock()
    svc.render_cuencas.return_value = cuencas_bytes
    svc.render_escorrentia.return_value = escorrentia_bytes
    svc.render_riesgo.return_value = riesgo_bytes
    svc.render_animacion.return_value = animacion_bytes
    return svc


# ---------------------------------------------------------------------------
# Task 4.1 / 4.2 — GET /cuencas → 200 + image/png
# ---------------------------------------------------------------------------

class TestRenderCuencasEndpoint:
    """GET /render/cuencas — tasks 4.1 & 4.2."""

    def test_returns_response_object(self):
        """Endpoint must return a Response (not a dict or model)."""
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = _make_service()
        result = render_cuencas(
            dem_path="/data/dem.tif",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert isinstance(result, Response)

    def test_response_status_200(self):
        """Endpoint must return HTTP 200."""
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = _make_service()
        result = render_cuencas(
            dem_path="/data/dem.tif",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.status_code == 200

    def test_response_content_type_is_png(self):
        """Endpoint must set Content-Type: image/png."""
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = _make_service()
        result = render_cuencas(
            dem_path="/data/dem.tif",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.media_type == "image/png"

    def test_response_body_contains_service_bytes(self):
        """Response body must be exactly what the service returns."""
        from app.domains.geo.visualization.router import render_cuencas

        expected = b"FAKE_PNG_CONTENT"
        mock_svc = _make_service(cuencas_bytes=expected)
        result = render_cuencas(
            dem_path="/data/dem.tif",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.body == expected

    def test_delegates_to_service_with_correct_args(self):
        """Endpoint must call service.render_cuencas(db, dem_path)."""
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = _make_service()
        mock_db = MagicMock()

        render_cuencas(
            dem_path="/data/dem.tif",
            db=mock_db,
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_cuencas.assert_called_once()
        call_args = mock_svc.render_cuencas.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == Path("/data/dem.tif")


# ---------------------------------------------------------------------------
# Task 4.3 / 4.4 — GET /escorrentia, /riesgo, /animacion
# ---------------------------------------------------------------------------

class TestRenderEscorrentiaEndpoint:
    """GET /render/escorrentia → 200 + image/png (tasks 4.3 & 4.4)."""

    def test_returns_200_png(self):
        from app.domains.geo.visualization.router import render_escorrentia

        mock_svc = _make_service()
        result = render_escorrentia(
            dem_path="/data/dem.tif",
            fecha="2025-03-15",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert isinstance(result, Response)
        assert result.status_code == 200
        assert result.media_type == "image/png"

    def test_response_body_is_service_bytes(self):
        from app.domains.geo.visualization.router import render_escorrentia

        expected = b"ESCORRENTIA_PNG"
        mock_svc = _make_service(escorrentia_bytes=expected)
        result = render_escorrentia(
            dem_path="/data/dem.tif",
            fecha="2025-03-15",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.body == expected

    def test_delegates_to_service(self):
        from app.domains.geo.visualization.router import render_escorrentia

        mock_svc = _make_service()
        render_escorrentia(
            dem_path="/data/dem.tif",
            fecha="2025-03-15",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_escorrentia.assert_called_once()


class TestRenderRiesgoEndpoint:
    """GET /render/riesgo → 200 + image/png (tasks 4.3 & 4.4)."""

    def test_returns_200_png(self):
        from app.domains.geo.visualization.router import render_riesgo

        mock_svc = _make_service()
        result = render_riesgo(
            dem_path="/data/dem.tif",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert isinstance(result, Response)
        assert result.status_code == 200
        assert result.media_type == "image/png"

    def test_response_body_is_service_bytes(self):
        from app.domains.geo.visualization.router import render_riesgo

        expected = b"RIESGO_PNG"
        mock_svc = _make_service(riesgo_bytes=expected)
        result = render_riesgo(
            dem_path="/data/dem.tif",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.body == expected

    def test_delegates_to_service(self):
        from app.domains.geo.visualization.router import render_riesgo

        mock_svc = _make_service()
        render_riesgo(
            dem_path="/data/dem.tif",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_riesgo.assert_called_once()


class TestRenderAnimacionEndpoint:
    """GET /render/animacion → 200 + video/mp4 (tasks 4.3 & 4.4)."""

    def test_returns_200_mp4(self):
        from app.domains.geo.visualization.router import render_animacion

        mock_svc = _make_service()
        result = render_animacion(
            dem_path="/data/dem.tif",
            fecha="2025-03-15",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert isinstance(result, Response)
        assert result.status_code == 200
        assert result.media_type == "video/mp4"

    def test_response_body_is_service_bytes(self):
        from app.domains.geo.visualization.router import render_animacion

        expected = b"MP4_CONTENT"
        mock_svc = _make_service(animacion_bytes=expected)
        result = render_animacion(
            dem_path="/data/dem.tif",
            fecha="2025-03-15",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.body == expected

    def test_delegates_to_service(self):
        from app.domains.geo.visualization.router import render_animacion

        mock_svc = _make_service()
        render_animacion(
            dem_path="/data/dem.tif",
            fecha="2025-03-15",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_animacion.assert_called_once()

    def test_mp4_content_type_not_png(self):
        """Animation must NOT return image/png — it's video/mp4."""
        from app.domains.geo.visualization.router import render_animacion

        mock_svc = _make_service()
        result = render_animacion(
            dem_path="/data/dem.tif",
            fecha="2025-03-15",
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.media_type != "image/png"
        assert result.media_type == "video/mp4"


# ---------------------------------------------------------------------------
# Task 4.5 / 4.6 — Auth dependency: _require_operator helper exists
# ---------------------------------------------------------------------------

class TestRouterAuthHelpers:
    """Smoke tests for auth helpers — tasks 4.5 & 4.6."""

    def test_require_operator_helper_exists(self):
        """Router must expose _require_operator() helper (lazy import pattern)."""
        from app.domains.geo.visualization import router as viz_router

        assert hasattr(viz_router, "_require_operator"), (
            "_require_operator must exist in visualization router"
        )

    def test_require_operator_returns_callable(self):
        """_require_operator() must return a callable dependency."""
        from app.domains.geo.visualization.router import _require_operator

        dep = _require_operator()
        assert callable(dep)

    def test_get_service_helper_returns_instance(self):
        """_get_service() must return a VisualizationService instance."""
        from app.domains.geo.visualization.router import _get_service
        from app.domains.geo.visualization.service import VisualizationService

        svc = _get_service()
        assert isinstance(svc, VisualizationService)


# ---------------------------------------------------------------------------
# Task 4.7 / 4.8 — HTTPException(404) from service propagates correctly
# ---------------------------------------------------------------------------

class TestDemNotFoundPropagation:
    """Service HTTPException(404) must propagate unmodified — tasks 4.7 & 4.8."""

    def test_cuencas_404_propagates(self):
        """When service raises HTTPException(404), endpoint must not catch it."""
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = MagicMock()
        mock_svc.render_cuencas.side_effect = HTTPException(
            status_code=404, detail="DEM not found: /missing.tif"
        )

        with pytest.raises(HTTPException) as exc_info:
            render_cuencas(
                dem_path="/missing.tif",
                db=MagicMock(),
                _user=MagicMock(),
                _svc=mock_svc,
            )

        assert exc_info.value.status_code == 404
        assert "missing.tif" in exc_info.value.detail

    def test_escorrentia_404_propagates(self):
        from app.domains.geo.visualization.router import render_escorrentia

        mock_svc = MagicMock()
        mock_svc.render_escorrentia.side_effect = HTTPException(
            status_code=404, detail="DEM not found: /missing.tif"
        )

        with pytest.raises(HTTPException) as exc_info:
            render_escorrentia(
                dem_path="/missing.tif",
                fecha="2025-03-15",
                db=MagicMock(),
                _user=MagicMock(),
                _svc=mock_svc,
            )

        assert exc_info.value.status_code == 404

    def test_riesgo_404_propagates(self):
        from app.domains.geo.visualization.router import render_riesgo

        mock_svc = MagicMock()
        mock_svc.render_riesgo.side_effect = HTTPException(
            status_code=404, detail="DEM not found: /missing.tif"
        )

        with pytest.raises(HTTPException) as exc_info:
            render_riesgo(
                dem_path="/missing.tif",
                db=MagicMock(),
                _user=MagicMock(),
                _svc=mock_svc,
            )

        assert exc_info.value.status_code == 404

    def test_animacion_404_propagates(self):
        from app.domains.geo.visualization.router import render_animacion

        mock_svc = MagicMock()
        mock_svc.render_animacion.side_effect = HTTPException(
            status_code=404, detail="DEM not found: /missing.tif"
        )

        with pytest.raises(HTTPException) as exc_info:
            render_animacion(
                dem_path="/missing.tif",
                fecha="2025-03-15",
                db=MagicMock(),
                _user=MagicMock(),
                _svc=mock_svc,
            )

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Task 4.9 — REFACTOR: router is thin (no business logic)
# ---------------------------------------------------------------------------

class TestRouterIsThin:
    """Verify router contains no business logic (task 4.9)."""

    def test_router_has_no_rasterio_import(self):
        """Router must NOT import rasterio — that belongs to service."""
        import importlib
        import importlib.util

        router_path = Path(
            "/home/javier/programacion/consorcio-canalero/gee-backend"
            "/app/domains/geo/visualization/router.py"
        )
        source = router_path.read_text()

        assert "import rasterio" not in source, (
            "Router must not import rasterio — data loading belongs in service.py"
        )

    def test_router_has_no_pyvista_import(self):
        """Router must NOT import pyvista — rendering belongs to renderer."""
        router_path = Path(
            "/home/javier/programacion/consorcio-canalero/gee-backend"
            "/app/domains/geo/visualization/router.py"
        )
        source = router_path.read_text()

        assert "import pyvista" not in source, (
            "Router must not import pyvista — rendering belongs in renderer.py"
        )

    def test_router_delegates_everything_to_service(self):
        """All 4 endpoint handlers must call the service — not do work inline."""
        from app.domains.geo.visualization.router import (
            render_cuencas,
            render_escorrentia,
            render_riesgo,
            render_animacion,
        )

        # Each handler can be called with a mock service — if they skip the
        # service call and do inline work, they would fail or not call the mock.
        for handler, kwargs in [
            (render_cuencas, {"dem_path": "/d.tif", "db": MagicMock(), "_user": MagicMock()}),
            (render_escorrentia, {"dem_path": "/d.tif", "fecha": "", "db": MagicMock(), "_user": MagicMock()}),
            (render_riesgo, {"dem_path": "/d.tif", "db": MagicMock(), "_user": MagicMock()}),
            (render_animacion, {"dem_path": "/d.tif", "fecha": "", "db": MagicMock(), "_user": MagicMock()}),
        ]:
            mock_svc = _make_service()
            handler(**kwargs, _svc=mock_svc)
            # At least one of the render_* methods must have been called
            called = (
                mock_svc.render_cuencas.called
                or mock_svc.render_escorrentia.called
                or mock_svc.render_riesgo.called
                or mock_svc.render_animacion.called
            )
            assert called, f"{handler.__name__} must delegate to service"
