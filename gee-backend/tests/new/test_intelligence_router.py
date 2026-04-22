"""Tests for geo/intelligence/router.py — covers helper functions and
schema models for uncovered endpoint lines.

Strategy: direct function calls with mocked deps for maximum line coverage.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.domains.geo.intelligence.schemas import (
    CompositeAnalysisRequest,
    CriticidadRequest,
    EscorrentiaRequest,
    ZonificacionRequest,
)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_criticidad_request(self):
        req = CriticidadRequest(
            zona_id=uuid.uuid4(),
            pendiente_media=0.5,
            acumulacion_media=0.8,
            twi_medio=0.6,
            proximidad_canal_m=150.0,
            historial_inundacion=0.3,
        )
        assert req.proximidad_canal_m == 150.0
        assert req.historial_inundacion == 0.3
        assert req.pesos is None

    def test_escorrentia_request(self):
        req = EscorrentiaRequest(
            punto_inicio=[-63.0, -32.0],
            lluvia_mm=50.0,
        )
        assert len(req.punto_inicio) == 2

    def test_zonificacion_request(self):
        lid = uuid.uuid4()
        req = ZonificacionRequest(
            dem_layer_id=lid,
            threshold=1000,
        )
        assert req.dem_layer_id == lid

    def test_composite_analysis_request(self):
        req = CompositeAnalysisRequest(area_id="zona_principal")
        assert req.weights_flood is None
        assert req.weights_drainage is None


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestLazyImports:
    def test_get_intel_service_returns_module(self):
        from app.domains.geo.intelligence.router import _get_intel_service

        svc = _get_intel_service()
        assert hasattr(svc, "get_dashboard") or hasattr(svc, "calculate_hci_for_zone")

    def test_get_repo_returns_repository(self):
        from app.domains.geo.intelligence.router import _get_repo

        repo = _get_repo()
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        assert isinstance(repo, IntelligenceRepository)

    def test_require_operator_returns_callable(self):
        from app.domains.geo.intelligence.router import _require_operator

        dep = _require_operator()
        assert callable(dep)

    def test_require_admin_returns_callable(self):
        from app.domains.geo.intelligence.router import _require_admin

        dep = _require_admin()
        assert callable(dep)


# ---------------------------------------------------------------------------
# Dashboard logic (inline test of the mat-view branch)
# ---------------------------------------------------------------------------


class TestDashboardLogic:
    """Test the dashboard aggregation logic directly."""

    def test_dashboard_with_mv_stats(self):
        """Simulate dashboard with materialized view stats."""
        from app.domains.geo.intelligence.router import get_dashboard

        mock_repo = MagicMock()
        mock_repo.get_dashboard_stats.return_value = {
            "total_zonas_operativas": 10,
            "total_conflictos": 3,
            "total_alertas_activas": 2,
        }
        mock_repo.get_alertas_resumen.return_value = []
        mock_repo.get_hci_por_zona.return_value = (
            [
                {"nivel_riesgo": "bajo"},
                {"nivel_riesgo": "medio"},
                {"nivel_riesgo": "alto"},
                {"nivel_riesgo": "critico"},
            ],
            4,
        )

        with (
            patch("app.domains.geo.intelligence.router.get_db"),
            patch("app.domains.geo.intelligence.router._require_operator"),
        ):
            result = get_dashboard(
                use_mv=True,
                db=MagicMock(),
                repo=mock_repo,
                _user=MagicMock(),
            )

        assert result["conflictos_activos"] == 3
        assert result["alertas_activas"] == 2
        assert result["zonas_por_nivel"]["alto"] == 1
        assert result["porcentaje_area_riesgo"] == 30.0  # 3/10 * 100

    def test_dashboard_mv_empty_falls_back(self):
        """When MV is empty, should fall back to live computation."""
        from app.domains.geo.intelligence.router import get_dashboard

        mock_repo = MagicMock()
        mock_repo.get_dashboard_stats.return_value = {}
        mock_repo.get_alertas_resumen.return_value = []

        mock_service = MagicMock()
        mock_service.get_dashboard.return_value = {
            "porcentaje_area_riesgo": 0,
            "canales_criticos": 0,
            "caminos_vulnerables": 0,
            "conflictos_activos": 0,
            "alertas_activas": 0,
            "zonas_por_nivel": {},
            "evolucion_temporal": [],
        }

        with patch(
            "app.domains.geo.intelligence.router._get_intel_service",
            return_value=mock_service,
        ):
            result = get_dashboard(
                use_mv=True,
                db=MagicMock(),
                repo=mock_repo,
                _user=MagicMock(),
            )
        mock_service.get_dashboard.assert_called_once()

    def test_dashboard_live_mode(self):
        """use_mv=False should go directly to live service."""
        from app.domains.geo.intelligence.router import get_dashboard

        mock_service = MagicMock()
        mock_service.get_dashboard.return_value = {"porcentaje_area_riesgo": 50}

        with patch(
            "app.domains.geo.intelligence.router._get_intel_service",
            return_value=mock_service,
        ):
            result = get_dashboard(
                use_mv=False,
                db=MagicMock(),
                repo=MagicMock(),
                _user=MagicMock(),
            )
        assert result["porcentaje_area_riesgo"] == 50


# ---------------------------------------------------------------------------
# HCI endpoints
# ---------------------------------------------------------------------------


class TestHCIEndpoints:
    def test_calculate_hci_success(self):
        from app.domains.geo.intelligence.router import calculate_hci

        mock_service = MagicMock()
        mock_service.calculate_hci_for_zone.return_value = {
            "zona_id": str(uuid.uuid4()),
            "hci": 0.75,
            "nivel": "alto",
        }

        payload = CriticidadRequest(
            zona_id=uuid.uuid4(),
            pendiente_media=0.5,
            acumulacion_media=0.8,
            twi_medio=0.6,
            proximidad_canal_m=150.0,
            historial_inundacion=0.3,
        )

        with patch(
            "app.domains.geo.intelligence.router._get_intel_service",
            return_value=mock_service,
        ):
            result = calculate_hci(payload, db=MagicMock(), _user=MagicMock())
        assert result["hci"] == 0.75

    def test_calculate_hci_not_found(self):
        from app.domains.geo.intelligence.router import calculate_hci

        mock_service = MagicMock()
        mock_service.calculate_hci_for_zone.side_effect = ValueError("Zone not found")

        payload = CriticidadRequest(
            zona_id=uuid.uuid4(),
            pendiente_media=0.5,
            acumulacion_media=0.8,
            twi_medio=0.6,
            proximidad_canal_m=150.0,
            historial_inundacion=0.3,
        )

        with patch(
            "app.domains.geo.intelligence.router._get_intel_service",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                calculate_hci(payload, db=MagicMock(), _user=MagicMock())
            assert exc_info.value.status_code == 404

    def test_list_hci_with_mv(self):
        from app.domains.geo.intelligence.router import list_hci

        mock_repo = MagicMock()
        mock_repo.get_hci_por_zona.return_value = (
            [{"zona": "z1", "hci": 0.5}],
            1,
        )

        result = list_hci(
            zona_id=None,
            page=1,
            limit=20,
            use_mv=True,
            cuenca=None,
            db=MagicMock(),
            repo=mock_repo,
            _user=MagicMock(),
        )
        assert result["total"] == 1

    def test_list_hci_without_mv(self):
        from app.domains.geo.intelligence.router import list_hci

        mock_repo = MagicMock()
        mock_repo.get_indices_hidricos.return_value = ([], 0)

        result = list_hci(
            zona_id=None,
            page=1,
            limit=20,
            use_mv=False,
            cuenca=None,
            db=MagicMock(),
            repo=mock_repo,
            _user=MagicMock(),
        )
        assert result["total"] == 0


# ---------------------------------------------------------------------------
# Simple endpoint function calls
# ---------------------------------------------------------------------------


class TestSimpleEndpoints:
    def test_refresh_views(self):
        from app.domains.geo.intelligence.router import refresh_views

        mock_repo = MagicMock()
        mock_repo.refresh_materialized_views.return_value = ["view_a", "view_b"]
        result = refresh_views(db=MagicMock(), repo=mock_repo, _user=MagicMock())
        assert result["status"] == "refreshed"

    def test_list_conflictos(self):
        from app.domains.geo.intelligence.router import list_conflictos

        mock_repo = MagicMock()
        mock_repo.get_conflictos.return_value = ([], 0)
        result = list_conflictos(
            tipo=None, severidad=None, page=1, limit=20,
            db=MagicMock(), repo=mock_repo, _user=MagicMock(),
        )
        assert result["total"] == 0

    def test_detect_conflictos(self):
        from app.domains.geo.intelligence.router import detect_conflictos

        mock_task = MagicMock()
        mock_task.id = "task-123"
        with patch(
            "app.domains.geo.intelligence.tasks.task_detect_all_conflicts"
        ) as mock_fn:
            mock_fn.delay.return_value = mock_task
            result = detect_conflictos(db=MagicMock(), _user=MagicMock())
        assert result["task_id"] == "task-123"

    def test_escorrentia_missing_layers(self):
        from app.domains.geo.intelligence.router import run_escorrentia

        payload = EscorrentiaRequest(punto_inicio=[-63.0, -32.0], lluvia_mm=50.0)

        mock_geo_repo = MagicMock()
        mock_geo_repo.get_layers.return_value = ([], 0)

        with patch(
            "app.domains.geo.repository.GeoRepository",
            return_value=mock_geo_repo,
        ):
            with pytest.raises(HTTPException) as exc_info:
                run_escorrentia(payload, db=MagicMock(), _user=MagicMock())
            assert exc_info.value.status_code == 400

    def test_list_zonas(self):
        from app.domains.geo.intelligence.router import list_zonas

        mock_repo = MagicMock()
        mock_repo.get_zonas.return_value = ([], 0)
        result = list_zonas(
            cuenca=None, page=1, limit=50,
            db=MagicMock(), repo=mock_repo, _user=MagicMock(),
        )
        assert result["total"] == 0

    def test_generate_zonas(self):
        from app.domains.geo.intelligence.router import generate_zonas

        payload = ZonificacionRequest(dem_layer_id=uuid.uuid4(), threshold=500)
        mock_task = MagicMock()
        mock_task.id = "task-456"
        with patch(
            "app.domains.geo.intelligence.tasks.task_generate_zonification"
        ) as mock_fn:
            mock_fn.delay.return_value = mock_task
            result = generate_zonas(payload, db=MagicMock(), _user=MagicMock())
        assert result["task_id"] == "task-456"

    def test_batch_calculate_hci(self):
        from app.domains.geo.intelligence.router import batch_calculate_hci

        mock_task = MagicMock()
        mock_task.id = "task-789"
        with patch(
            "app.domains.geo.intelligence.tasks.task_calculate_hci_all_zones"
        ) as mock_fn:
            mock_fn.delay.return_value = mock_task
            result = batch_calculate_hci(db=MagicMock(), _user=MagicMock())
        assert result["task_id"] == "task-789"

    def test_get_canal_priorities(self):
        from app.domains.geo.intelligence.router import get_canal_priorities

        result = get_canal_priorities(db=MagicMock(), _user=MagicMock())
        assert "items" in result

    def test_get_road_risks(self):
        from app.domains.geo.intelligence.router import get_road_risks

        result = get_road_risks(db=MagicMock(), _user=MagicMock())
        assert "items" in result

    def test_list_alertas(self):
        from app.domains.geo.intelligence.router import list_alertas

        mock_repo = MagicMock()
        mock_repo.get_alertas_activas.return_value = []
        result = list_alertas(db=MagicMock(), repo=mock_repo, _user=MagicMock())
        assert result["total"] == 0

    def test_evaluate_alertas(self):
        from app.domains.geo.intelligence.router import evaluate_alertas

        mock_service = MagicMock()
        mock_service.check_alerts.return_value = {"alerts_created": 0}
        with patch(
            "app.domains.geo.intelligence.router._get_intel_service",
            return_value=mock_service,
        ):
            result = evaluate_alertas(db=MagicMock(), _user=MagicMock())
        assert result["alerts_created"] == 0

    def test_deactivate_alerta_found(self):
        from app.domains.geo.intelligence.router import deactivate_alerta

        mock_repo = MagicMock()
        alerta = SimpleNamespace(id=uuid.uuid4(), activa=False)
        mock_repo.deactivate_alerta.return_value = alerta
        db = MagicMock()
        result = deactivate_alerta(
            alerta_id=uuid.uuid4(), db=db, repo=mock_repo, _user=MagicMock()
        )
        db.commit.assert_called_once()

    def test_deactivate_alerta_not_found(self):
        from app.domains.geo.intelligence.router import deactivate_alerta

        mock_repo = MagicMock()
        mock_repo.deactivate_alerta.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            deactivate_alerta(
                alerta_id=uuid.uuid4(), db=MagicMock(),
                repo=mock_repo, _user=MagicMock(),
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Composite analysis endpoints
# ---------------------------------------------------------------------------


class TestCompositeEndpoints:
    def test_trigger_composite_analysis(self):
        from app.domains.geo.intelligence.router import trigger_composite_analysis

        payload = CompositeAnalysisRequest(area_id="zona_principal")
        mock_task = MagicMock()
        mock_task.id = "comp-task-1"
        with patch("app.domains.geo.tasks.composite_analysis_task") as mock_fn:
            mock_fn.delay.return_value = mock_task
            result = trigger_composite_analysis(
                payload, db=MagicMock(), _user=MagicMock()
            )
        assert result["task_id"] == "comp-task-1"

    def test_get_composite_stats_not_found(self):
        from app.domains.geo.intelligence.router import get_composite_stats

        mock_repo = MagicMock()
        mock_repo.get_composite_stats_by_area.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            get_composite_stats(
                area_id="nonexistent", tipo=None,
                db=MagicMock(), repo=mock_repo, _user=MagicMock(),
            )
        assert exc_info.value.status_code == 404
