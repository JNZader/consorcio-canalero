"""Tests for padron, settings, intelligence, and auth routers.

Uses direct function calls with mocked dependencies — no TestClient needed.
Covers endpoint logic, validation, auth guards, and response shapes.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    db = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.flush = MagicMock()
    return db


@pytest.fixture()
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@test.com"
    return user


# ══════════════════════════════════════════════
# PADRON ROUTER
# ══════════════════════════════════════════════


class TestPadronGetStats:
    def test_returns_stats_dict(self, mock_db, mock_user):
        from app.domains.padron.router import get_stats
        from app.domains.padron.service import PadronService

        service = MagicMock(spec=PadronService)
        service.get_stats.return_value = {"total": 100, "activos": 90}

        result = get_stats(mock_db, service, _user=mock_user)
        assert result["total"] == 100
        service.get_stats.assert_called_once_with(mock_db)


class TestPadronListConsorcistas:
    def test_returns_paginated_list(self, mock_db):
        from app.domains.padron.router import list_consorcistas
        from app.domains.padron.service import PadronService

        service = MagicMock(spec=PadronService)
        service.list_consorcistas.return_value = ([], 0)

        result = list_consorcistas(
            page=1, limit=20, estado=None, categoria=None,
            search=None, db=mock_db, service=service,
        )
        assert result["total"] == 0
        assert result["items"] == []
        assert result["page"] == 1

    def test_passes_filters_to_service(self, mock_db):
        from app.domains.padron.router import list_consorcistas
        from app.domains.padron.service import PadronService

        service = MagicMock(spec=PadronService)
        service.list_consorcistas.return_value = ([], 0)

        list_consorcistas(
            page=2, limit=10, estado="activo", categoria="propietario",
            search="perez", db=mock_db, service=service,
        )
        service.list_consorcistas.assert_called_once_with(
            mock_db, page=2, limit=10, estado="activo",
            categoria="propietario", search="perez",
        )


class TestPadronGetConsorcista:
    def test_returns_consorcista(self, mock_db):
        from app.domains.padron.router import get_consorcista
        from app.domains.padron.service import PadronService

        service = MagicMock(spec=PadronService)
        mock_consorcista = MagicMock()
        service.get_by_id.return_value = mock_consorcista

        cid = uuid.uuid4()
        result = get_consorcista(cid, mock_db, service)
        assert result == mock_consorcista
        service.get_by_id.assert_called_once_with(mock_db, cid)


class TestPadronCreateConsorcista:
    def test_creates_and_returns(self, mock_db, mock_user):
        from app.domains.padron.router import create_consorcista
        from app.domains.padron.schemas import ConsorcistaCreate
        from app.domains.padron.service import PadronService

        service = MagicMock(spec=PadronService)
        mock_result = MagicMock()
        service.create.return_value = mock_result

        payload = ConsorcistaCreate(
            nombre="Juan", apellido="Perez",
            cuit="20-12345678-9", estado="activo",
        )
        result = create_consorcista(payload, mock_db, service, _user=mock_user)
        assert result == mock_result


class TestPadronUpdateConsorcista:
    def test_updates_and_returns(self, mock_db, mock_user):
        from app.domains.padron.router import update_consorcista
        from app.domains.padron.schemas import ConsorcistaUpdate
        from app.domains.padron.service import PadronService

        service = MagicMock(spec=PadronService)
        mock_result = MagicMock()
        service.update.return_value = mock_result

        cid = uuid.uuid4()
        payload = ConsorcistaUpdate(nombre="Updated")
        result = update_consorcista(cid, payload, mock_db, service, _user=mock_user)
        assert result == mock_result
        service.update.assert_called_once_with(mock_db, cid, payload)


class TestPadronImport:
    @pytest.mark.asyncio
    async def test_rejects_empty_filename(self, mock_db, mock_user):
        from app.domains.padron.router import import_consorcistas
        from app.domains.padron.service import PadronService

        service = MagicMock(spec=PadronService)
        file = MagicMock()
        file.filename = None

        with pytest.raises(HTTPException) as exc_info:
            await import_consorcistas(file=file, db=mock_db, service=service, _user=mock_user)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_unsupported_format(self, mock_db, mock_user):
        from app.domains.padron.router import import_consorcistas
        from app.domains.padron.service import PadronService

        service = MagicMock(spec=PadronService)
        file = MagicMock()
        file.filename = "test.pdf"

        with pytest.raises(HTTPException) as exc_info:
            await import_consorcistas(file=file, db=mock_db, service=service, _user=mock_user)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_empty_file(self, mock_db, mock_user):
        from app.domains.padron.router import import_consorcistas
        from app.domains.padron.service import PadronService

        service = MagicMock(spec=PadronService)
        file = MagicMock()
        file.filename = "test.csv"
        file.read = AsyncMock(return_value=b"")

        with pytest.raises(HTTPException) as exc_info:
            await import_consorcistas(file=file, db=mock_db, service=service, _user=mock_user)
        assert exc_info.value.status_code == 400


# ══════════════════════════════════════════════
# SETTINGS ROUTER
# ══════════════════════════════════════════════


class TestSettingsGetAll:
    def test_returns_all_settings(self, mock_db, mock_user):
        from app.domains.settings.router import get_all_settings
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        service.get_all_settings.return_value = []
        result = get_all_settings(mock_db, service, _user=mock_user)
        assert result == []


class TestSettingsGetByKey:
    def test_returns_setting(self, mock_db, mock_user):
        from app.domains.settings.router import get_setting_by_key
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        mock_setting = MagicMock()
        service.get_setting_full.return_value = mock_setting

        result = get_setting_by_key("general/nombre", mock_db, service, _user=mock_user)
        assert result == mock_setting

    def test_raises_404_when_not_found(self, mock_db, mock_user):
        from app.domains.settings.router import get_setting_by_key
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        service.get_setting_full.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_setting_by_key("nonexistent/key", mock_db, service, _user=mock_user)
        assert exc_info.value.status_code == 404


class TestSettingsUpdateByKey:
    def test_updates_setting(self, mock_db, mock_user):
        from app.domains.settings.router import update_setting
        from app.domains.settings.schemas import SettingUpdate
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        mock_result = MagicMock()
        service.update_setting.return_value = mock_result

        payload = SettingUpdate(valor="new_value")
        result = update_setting("general/nombre", payload, mock_db, service, _user=mock_user)
        assert result == mock_result

    def test_raises_404_when_not_found(self, mock_db, mock_user):
        from app.domains.settings.router import update_setting
        from app.domains.settings.schemas import SettingUpdate
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        service.update_setting.return_value = None

        payload = SettingUpdate(valor="x")
        with pytest.raises(HTTPException) as exc_info:
            update_setting("bad/key", payload, mock_db, service, _user=mock_user)
        assert exc_info.value.status_code == 404


class TestSettingsGetByCategory:
    def test_returns_settings_by_category(self, mock_db, mock_user):
        from app.domains.settings.router import get_settings_by_category
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        service.get_settings_by_category.return_value = []

        result = get_settings_by_category("branding", mock_db, service, _user=mock_user)
        assert result.categoria == "branding"
        assert result.settings == []


class TestPublicBranding:
    def test_returns_branding_response(self, mock_db):
        from app.domains.settings.router import get_public_branding
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        service.get_setting.side_effect = lambda db, key: {
            "general/nombre_organizacion": "Consorcio Test",
            "branding/logo_url": "/logo.png",
            "branding/color_primario": "#1976D2",
            "branding/color_secundario": "#424242",
        }.get(key)

        result = get_public_branding(mock_db, service)
        assert result.nombre_organizacion == "Consorcio Test"
        assert result.logo_url == "/logo.png"


class TestPublicMapaImagen:
    def test_returns_none_when_not_set(self, mock_db):
        from app.domains.settings.router import get_public_mapa_imagen
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        service.get_setting.return_value = None

        result = get_public_mapa_imagen(mock_db, service)
        assert result.imagen_principal is None
        assert result.imagen_comparacion is None


class TestSaveMapaImagenPrincipal:
    def test_saves_and_returns(self, mock_db, mock_user):
        from app.domains.settings.router import save_mapa_imagen_principal
        from app.domains.settings.schemas import ImagenMapaParams
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        service.get_setting.return_value = None

        payload = ImagenMapaParams(
            sensor="sentinel2", target_date="2025-06-01",
            visualization="rgb", days_buffer=10,
        )
        result = save_mapa_imagen_principal(payload, mock_db, service, _user=mock_user)
        service.upsert_setting.assert_called_once()
        assert result.imagen_principal is not None


class TestSaveMapaImagenComparacion:
    def test_saves_and_returns(self, mock_db, mock_user):
        from app.domains.settings.router import save_mapa_imagen_comparacion
        from app.domains.settings.schemas import ImagenComparacionParams
        from app.domains.settings.service import SettingsService

        service = MagicMock(spec=SettingsService)
        service.get_setting.return_value = None

        payload = ImagenComparacionParams(enabled=True)
        result = save_mapa_imagen_comparacion(payload, mock_db, service, _user=mock_user)
        service.upsert_setting.assert_called_once()
        assert result.imagen_comparacion is not None


# ══════════════════════════════════════════════
# INTELLIGENCE ROUTER
# ══════════════════════════════════════════════


class TestIntelligenceRefreshViews:
    def test_refresh_returns_status(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import refresh_views
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.refresh_materialized_views.return_value = {"v1": "ok"}

        result = refresh_views(mock_db, repo, _user=mock_user)
        assert result["status"] == "refreshed"


class TestIntelligenceDashboard:
    @patch("app.domains.geo.intelligence.router._get_intel_service")
    def test_falls_back_to_live_when_mv_empty(self, mock_svc, mock_db, mock_user):
        from app.domains.geo.intelligence.router import get_dashboard
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.get_dashboard_stats.return_value = None  # empty MV

        mock_service = MagicMock()
        mock_service.get_dashboard.return_value = {"porcentaje_area_riesgo": 0}
        mock_svc.return_value = mock_service

        result = get_dashboard(use_mv=True, db=mock_db, repo=repo, _user=mock_user)
        mock_service.get_dashboard.assert_called_once()

    @patch("app.domains.geo.intelligence.router._get_intel_service")
    def test_live_mode_when_use_mv_false(self, mock_svc, mock_db, mock_user):
        from app.domains.geo.intelligence.router import get_dashboard
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        mock_service = MagicMock()
        mock_service.get_dashboard.return_value = {"porcentaje_area_riesgo": 5}
        mock_svc.return_value = mock_service

        result = get_dashboard(use_mv=False, db=mock_db, repo=repo, _user=mock_user)
        mock_service.get_dashboard.assert_called_once()


class TestIntelligenceHci:
    def test_list_hci_live_mode(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import list_hci
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.get_indices_hidricos.return_value = ([], 0)

        result = list_hci(
            zona_id=None, page=1, limit=20, use_mv=False,
            cuenca=None, db=mock_db, repo=repo, _user=mock_user,
        )
        assert result["total"] == 0

    def test_list_hci_mv_mode(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import list_hci
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.get_hci_por_zona.return_value = ([], 0)

        result = list_hci(
            zona_id=None, page=1, limit=20, use_mv=True,
            cuenca="norte", db=mock_db, repo=repo, _user=mock_user,
        )
        assert result["total"] == 0
        repo.get_hci_por_zona.assert_called_once()


class TestIntelligenceConflictos:
    def test_list_conflictos(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import list_conflictos
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.get_conflictos.return_value = ([], 0)

        result = list_conflictos(
            tipo=None, severidad=None, page=1, limit=20,
            db=mock_db, repo=repo, _user=mock_user,
        )
        assert result["total"] == 0


class TestIntelligenceZonas:
    def test_list_zonas(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import list_zonas
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.get_zonas.return_value = ([], 0)

        result = list_zonas(
            cuenca=None, page=1, limit=50, db=mock_db, repo=repo, _user=mock_user,
        )
        assert result["total"] == 0


class TestIntelligenceAlertas:
    def test_list_alertas(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import list_alertas
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.get_alertas_activas.return_value = []

        result = list_alertas(mock_db, repo, _user=mock_user)
        assert result["total"] == 0

    def test_deactivate_alerta_not_found(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import deactivate_alerta
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.deactivate_alerta.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            deactivate_alerta(uuid.uuid4(), mock_db, repo, _user=mock_user)
        assert exc_info.value.status_code == 404


class TestIntelligenceCanalPriority:
    def test_get_canal_priorities_placeholder(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import get_canal_priorities

        result = get_canal_priorities(mock_db, _user=mock_user)
        assert "items" in result
        assert result["items"] == []


class TestIntelligenceRoadRisk:
    def test_get_road_risks_placeholder(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import get_road_risks

        result = get_road_risks(mock_db, _user=mock_user)
        assert "items" in result


class TestIntelligenceSuggestions:
    def test_get_suggestion_results_empty(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import get_suggestion_results
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.get_latest_batch.return_value = None

        result = get_suggestion_results(
            tipo=None, page=1, limit=20, db=mock_db, repo=repo, _user=mock_user,
        )
        assert result["items"] == []
        assert result["batch_id"] is None

    def test_get_suggestion_summary_empty(self, mock_db, mock_user):
        from app.domains.geo.intelligence.router import get_suggestion_summary
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = MagicMock(spec=IntelligenceRepository)
        repo.get_summary.return_value = None

        result = get_suggestion_summary(
            batch_id=None, db=mock_db, repo=repo, _user=mock_user,
        )
        assert result["total_suggestions"] == 0


class TestIntelligenceDispatchTasks:
    @patch("app.domains.geo.intelligence.tasks.task_detect_all_conflicts")
    def test_detect_conflictos_returns_task_id(self, mock_task, mock_db, mock_user):
        from app.domains.geo.intelligence.router import detect_conflictos

        mock_task.delay.return_value = MagicMock(id="task-123")
        result = detect_conflictos(mock_db, _user=mock_user)
        assert result["task_id"] == "task-123"

    @patch("app.domains.geo.intelligence.tasks.task_generate_zonification")
    def test_generate_zonas_returns_task_id(self, mock_task, mock_db, mock_user):
        from app.domains.geo.intelligence.router import generate_zonas
        from app.domains.geo.intelligence.schemas import ZonificacionRequest

        mock_task.delay.return_value = MagicMock(id="task-456")
        payload = ZonificacionRequest(dem_layer_id=uuid.uuid4(), threshold=1000)
        result = generate_zonas(payload, mock_db, _user=mock_user)
        assert result["task_id"] == "task-456"

    @patch("app.domains.geo.intelligence.tasks.task_calculate_hci_all_zones")
    def test_batch_hci_returns_task_id(self, mock_task, mock_db, mock_user):
        from app.domains.geo.intelligence.router import batch_calculate_hci

        mock_task.delay.return_value = MagicMock(id="task-789")
        result = batch_calculate_hci(mock_db, _user=mock_user)
        assert result["task_id"] == "task-789"


# ══════════════════════════════════════════════
# AUTH ROUTER
# ══════════════════════════════════════════════


class TestAuthRouterStructure:
    """Test that the auth router assembles correctly."""

    def test_auth_router_has_routes(self):
        from app.auth.router import router

        route_paths = [r.path for r in router.routes]
        # JWT routes
        assert "/auth/jwt/login" in route_paths
        assert "/auth/jwt/logout" in route_paths
        # Register
        assert "/auth/register" in route_paths
        # Users
        assert "/users/me" in route_paths

    def test_auth_router_tags(self):
        from app.auth.router import router

        all_tags = set()
        for route in router.routes:
            tags = getattr(route, "tags", [])
            all_tags.update(tags)
        assert "auth" in all_tags
        assert "users" in all_tags


class TestAuthSchemas:
    def test_user_read_schema_fields(self):
        from app.auth.schemas import UserRead

        fields = set(UserRead.model_fields.keys())
        assert "id" in fields
        assert "email" in fields

    def test_user_create_schema_fields(self):
        from app.auth.schemas import UserCreate

        fields = set(UserCreate.model_fields.keys())
        assert "email" in fields
        assert "password" in fields
