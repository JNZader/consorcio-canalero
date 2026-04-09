"""
Tests for the visualization router — HTTP layer TDD (tasks 4.1–4.9).

Strategy: direct function calls with mocked VisualizationService — same
pattern as test_hydrology_router.py. This avoids full TestClient + JWT
stack while still validating endpoint logic, response media types, and
error propagation.

Updated: endpoints now accept only optional area_id (no path params).
Layer resolution happens inside VisualizationService via DB lookup.

TDD cycle: RED → GREEN → REFACTOR
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

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
# GET /cuencas
# ---------------------------------------------------------------------------

class TestRenderCuencasEndpoint:
    """GET /render/cuencas — no path params, optional area_id only."""

    def test_returns_response_object(self):
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = _make_service()
        result = render_cuencas(
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert isinstance(result, Response)

    def test_response_status_200(self):
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = _make_service()
        result = render_cuencas(
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.status_code == 200

    def test_response_content_type_is_png(self):
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = _make_service()
        result = render_cuencas(
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.media_type == "image/png"

    def test_response_body_contains_service_bytes(self):
        from app.domains.geo.visualization.router import render_cuencas

        expected = b"FAKE_PNG_CONTENT"
        mock_svc = _make_service(cuencas_bytes=expected)
        result = render_cuencas(
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.body == expected

    def test_delegates_to_service_with_db_and_area_id(self):
        """Endpoint must call service.render_cuencas(db, area_id)."""
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = _make_service()
        mock_db = MagicMock()

        render_cuencas(
            area_id="test-area",
            db=mock_db,
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_cuencas.assert_called_once()
        call_args = mock_svc.render_cuencas.call_args
        assert call_args[0][0] is mock_db
        assert call_args[0][1] == "test-area"

    def test_delegates_without_area_id(self):
        """area_id=None is passed through to service."""
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = _make_service()
        mock_db = MagicMock()

        render_cuencas(
            area_id=None,
            db=mock_db,
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_cuencas.assert_called_once_with(mock_db, None)


# ---------------------------------------------------------------------------
# GET /escorrentia
# ---------------------------------------------------------------------------

class TestRenderEscorrentiaEndpoint:
    """GET /render/escorrentia → 200 + image/png."""

    def test_returns_200_png(self):
        from app.domains.geo.visualization.router import render_escorrentia

        mock_svc = _make_service()
        result = render_escorrentia(
            lon=-63.0,
            lat=-31.0,
            lluvia_mm=50.0,
            area_id=None,
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
            lon=-63.0,
            lat=-31.0,
            lluvia_mm=50.0,
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.body == expected

    def test_delegates_to_service_with_correct_args(self):
        """Endpoint must pass db, lon, lat, lluvia_mm, area_id to service."""
        from app.domains.geo.visualization.router import render_escorrentia

        mock_svc = _make_service()
        mock_db = MagicMock()

        render_escorrentia(
            lon=-63.0,
            lat=-31.0,
            lluvia_mm=75.0,
            area_id="zone-a",
            db=mock_db,
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_escorrentia.assert_called_once()
        args, kwargs = mock_svc.render_escorrentia.call_args
        assert args[0] is mock_db
        assert args[1] == -63.0
        assert args[2] == -31.0
        assert args[3] == 75.0
        assert args[4] == "zone-a"

    def test_delegates_to_service(self):
        from app.domains.geo.visualization.router import render_escorrentia

        mock_svc = _make_service()
        render_escorrentia(
            lon=-63.0,
            lat=-31.0,
            lluvia_mm=50.0,
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_escorrentia.assert_called_once()


# ---------------------------------------------------------------------------
# GET /riesgo
# ---------------------------------------------------------------------------

class TestRenderRiesgoEndpoint:
    """GET /render/riesgo → 200 + image/png."""

    def test_returns_200_png(self):
        from app.domains.geo.visualization.router import render_riesgo

        mock_svc = _make_service()
        result = render_riesgo(
            area_id=None,
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
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.body == expected

    def test_delegates_to_service_with_correct_args(self):
        from app.domains.geo.visualization.router import render_riesgo

        mock_svc = _make_service()
        mock_db = MagicMock()

        render_riesgo(
            area_id="zone-b",
            db=mock_db,
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_riesgo.assert_called_once()
        args, _ = mock_svc.render_riesgo.call_args
        assert args[0] is mock_db
        assert args[1] == "zone-b"

    def test_delegates_to_service(self):
        from app.domains.geo.visualization.router import render_riesgo

        mock_svc = _make_service()
        render_riesgo(
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_riesgo.assert_called_once()


# ---------------------------------------------------------------------------
# GET /animacion
# ---------------------------------------------------------------------------

class TestRenderAnimacionEndpoint:
    """GET /render/animacion → 200 + video/mp4."""

    def test_returns_200_mp4(self):
        from app.domains.geo.visualization.router import render_animacion

        mock_svc = _make_service()
        result = render_animacion(
            area_id=None,
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
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.body == expected

    def test_delegates_to_service_with_correct_args(self):
        from app.domains.geo.visualization.router import render_animacion

        mock_svc = _make_service()
        mock_db = MagicMock()

        render_animacion(
            area_id="zone-c",
            db=mock_db,
            _user=MagicMock(),
            _svc=mock_svc,
        )

        mock_svc.render_animacion.assert_called_once()
        args, _ = mock_svc.render_animacion.call_args
        assert args[0] is mock_db
        assert args[1] == "zone-c"

    def test_delegates_to_service(self):
        from app.domains.geo.visualization.router import render_animacion

        mock_svc = _make_service()
        render_animacion(
            area_id=None,
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
            area_id=None,
            db=MagicMock(),
            _user=MagicMock(),
            _svc=mock_svc,
        )

        assert result.media_type != "image/png"
        assert result.media_type == "video/mp4"


# ---------------------------------------------------------------------------
# Auth dependency helpers
# ---------------------------------------------------------------------------

class TestRouterAuthHelpers:
    """Smoke tests for auth helpers."""

    def test_require_operator_helper_exists(self):
        from app.domains.geo.visualization import router as viz_router

        assert hasattr(viz_router, "_require_operator")

    def test_require_operator_returns_callable(self):
        from app.domains.geo.visualization.router import _require_operator

        dep = _require_operator()
        assert callable(dep)

    def test_get_service_helper_returns_instance(self):
        from app.domains.geo.visualization.router import _get_service
        from app.domains.geo.visualization.service import VisualizationService

        svc = _get_service()
        assert isinstance(svc, VisualizationService)


# ---------------------------------------------------------------------------
# HTTPException(404) from service propagates correctly
# ---------------------------------------------------------------------------

class TestLayerNotFoundPropagation:
    """Service HTTPException(404) must propagate unmodified."""

    def test_cuencas_404_propagates(self):
        from app.domains.geo.visualization.router import render_cuencas

        mock_svc = MagicMock()
        mock_svc.render_cuencas.side_effect = HTTPException(
            status_code=404,
            detail="No layer of type 'dem_raw' found. Run terrain analysis first.",
        )

        with pytest.raises(HTTPException) as exc_info:
            render_cuencas(
                area_id=None,
                db=MagicMock(),
                _user=MagicMock(),
                _svc=mock_svc,
            )

        assert exc_info.value.status_code == 404
        assert "dem_raw" in exc_info.value.detail

    def test_escorrentia_404_propagates(self):
        from app.domains.geo.visualization.router import render_escorrentia

        mock_svc = MagicMock()
        mock_svc.render_escorrentia.side_effect = HTTPException(
            status_code=404, detail="No layer of type 'flow_dir' found."
        )

        with pytest.raises(HTTPException) as exc_info:
            render_escorrentia(
                lon=-63.0,
                lat=-31.0,
                lluvia_mm=50.0,
                area_id=None,
                db=MagicMock(),
                _user=MagicMock(),
                _svc=mock_svc,
            )

        assert exc_info.value.status_code == 404

    def test_riesgo_404_propagates(self):
        from app.domains.geo.visualization.router import render_riesgo

        mock_svc = MagicMock()
        mock_svc.render_riesgo.side_effect = HTTPException(
            status_code=404, detail="No layer of type 'slope' found."
        )

        with pytest.raises(HTTPException) as exc_info:
            render_riesgo(
                area_id=None,
                db=MagicMock(),
                _user=MagicMock(),
                _svc=mock_svc,
            )

        assert exc_info.value.status_code == 404

    def test_animacion_404_propagates(self):
        from app.domains.geo.visualization.router import render_animacion

        mock_svc = MagicMock()
        mock_svc.render_animacion.side_effect = HTTPException(
            status_code=404, detail="No layer of type 'dem_raw' found."
        )

        with pytest.raises(HTTPException) as exc_info:
            render_animacion(
                area_id=None,
                db=MagicMock(),
                _user=MagicMock(),
                _svc=mock_svc,
            )

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Router is thin — no business logic
# ---------------------------------------------------------------------------

class TestRouterIsThin:
    """Verify router contains no business logic."""

    def test_router_has_no_rasterio_import(self):
        from pathlib import Path

        router_path = Path(
            "/home/javier/programacion/consorcio-canalero/gee-backend"
            "/app/domains/geo/visualization/router.py"
        )
        source = router_path.read_text()

        assert "import rasterio" not in source

    def test_router_has_no_pyvista_import(self):
        from pathlib import Path

        router_path = Path(
            "/home/javier/programacion/consorcio-canalero/gee-backend"
            "/app/domains/geo/visualization/router.py"
        )
        source = router_path.read_text()

        assert "import pyvista" not in source

    def test_router_has_no_path_params(self):
        """Router must NOT accept dem_path, flow_acc_path, etc. as query params."""
        from pathlib import Path

        router_path = Path(
            "/home/javier/programacion/consorcio-canalero/gee-backend"
            "/app/domains/geo/visualization/router.py"
        )
        source = router_path.read_text()

        assert "dem_path" not in source
        assert "flow_acc_path" not in source
        assert "flow_dir_path" not in source
        assert "slope_path" not in source

    def test_router_delegates_everything_to_service(self):
        """All 4 endpoint handlers must call the service."""
        from app.domains.geo.visualization.router import (
            render_cuencas,
            render_escorrentia,
            render_riesgo,
            render_animacion,
        )

        for handler, kwargs in [
            (
                render_cuencas,
                {"area_id": None, "db": MagicMock(), "_user": MagicMock()},
            ),
            (
                render_escorrentia,
                {
                    "lon": -63.0,
                    "lat": -31.0,
                    "lluvia_mm": 50.0,
                    "area_id": None,
                    "db": MagicMock(),
                    "_user": MagicMock(),
                },
            ),
            (
                render_riesgo,
                {"area_id": None, "db": MagicMock(), "_user": MagicMock()},
            ),
            (
                render_animacion,
                {"area_id": None, "db": MagicMock(), "_user": MagicMock()},
            ),
        ]:
            mock_svc = _make_service()
            handler(**kwargs, _svc=mock_svc)
            called = (
                mock_svc.render_cuencas.called
                or mock_svc.render_escorrentia.called
                or mock_svc.render_riesgo.called
                or mock_svc.render_animacion.called
            )
            assert called, f"{handler.__name__} must delegate to service"
