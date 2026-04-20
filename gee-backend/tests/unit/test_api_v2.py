"""Tests for api/v2 — admin, public, and router assembly.

Uses direct function calls with mocked dependencies.
Covers: route registration, public endpoints, admin user management.
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
def mock_async_db():
    db = AsyncMock()
    return db


@pytest.fixture()
def mock_admin():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@test.com"
    user.role = "admin"
    return user


# ══════════════════════════════════════════════
# API V2 ROUTER ASSEMBLY
# ══════════════════════════════════════════════


class TestApiRouterAssembly:
    def test_api_router_includes_all_domains(self):
        from app.api.v2.router import api_router

        route_paths = set()
        for route in api_router.routes:
            path = getattr(route, "path", "")
            if path:
                route_paths.add(path)

        # Check some key prefixes exist in the routes
        assert any("/padron" in p for p in route_paths)
        assert any("/settings" in p for p in route_paths)

    def test_api_router_has_public_routes(self):
        from app.api.v2.router import api_router

        route_paths = set()
        for route in api_router.routes:
            path = getattr(route, "path", "")
            if path:
                route_paths.add(path)

        assert any("/public" in p for p in route_paths)

    def test_api_router_has_admin_routes(self):
        from app.api.v2.router import api_router

        route_paths = set()
        for route in api_router.routes:
            path = getattr(route, "path", "")
            if path:
                route_paths.add(path)

        assert any("/admin" in p for p in route_paths)


# ══════════════════════════════════════════════
# PUBLIC ROUTER ENDPOINTS
# ══════════════════════════════════════════════


class TestPublicLayerList:
    def test_returns_public_layers(self, mock_db):
        from app.api.v2.public import list_public_layers
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        repo.get_public.return_value = []

        result = list_public_layers(mock_db, repo)
        assert result == []


class TestPublicLayerDetail:
    def test_raises_404_for_nonexistent(self, mock_db):
        from app.api.v2.public import get_public_layer
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        repo.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_public_layer(uuid.uuid4(), mock_db, repo)
        assert exc_info.value.status_code == 404

    def test_raises_404_for_private_layer(self, mock_db):
        from app.api.v2.public import get_public_layer
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        mock_capa = MagicMock()
        mock_capa.es_publica = False
        mock_capa.visible = True
        repo.get_by_id.return_value = mock_capa

        with pytest.raises(HTTPException) as exc_info:
            get_public_layer(uuid.uuid4(), mock_db, repo)
        assert exc_info.value.status_code == 404

    def test_raises_404_for_hidden_public_layer(self, mock_db):
        from app.api.v2.public import get_public_layer
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        mock_capa = MagicMock()
        mock_capa.es_publica = True
        mock_capa.visible = False
        repo.get_by_id.return_value = mock_capa

        with pytest.raises(HTTPException) as exc_info:
            get_public_layer(uuid.uuid4(), mock_db, repo)
        assert exc_info.value.status_code == 404


class TestPublicStats:
    def test_returns_stats(self, mock_db):
        from app.api.v2.public import get_public_stats

        mock_db.execute.return_value.scalar_one.return_value = 10

        result = get_public_stats(mock_db)
        assert result.total_denuncias == 10
        assert result.total_sugerencias == 10
        assert result.total_capas_publicas == 10


class TestCreateAnonymousDenuncia:
    def test_creates_denuncia(self, mock_db):
        from app.api.v2.public import create_anonymous_denuncia
        from app.domains.denuncias.schemas import DenunciaCreate
        from app.domains.denuncias.service import DenunciaService

        service = MagicMock(spec=DenunciaService)
        mock_denuncia = MagicMock()
        mock_denuncia.id = uuid.uuid4()
        mock_denuncia.estado = "pendiente"
        service.create.return_value = mock_denuncia

        payload = DenunciaCreate(
            tipo="desborde", descripcion="Canal desbordado en la zona norte afectando caminos rurales",
            latitud=-33.7, longitud=-63.9,
        )
        result = create_anonymous_denuncia(payload, mock_db, service)
        assert result.id == mock_denuncia.id
        assert "Gracias" in result.message


class TestCheckDenunciaStatus:
    def test_returns_status(self, mock_db):
        from app.api.v2.public import check_denuncia_status
        from app.domains.denuncias.service import DenunciaService

        service = MagicMock(spec=DenunciaService)
        mock_denuncia = MagicMock()
        mock_denuncia.estado = "pendiente"
        mock_denuncia.created_at = datetime.now(timezone.utc)
        service.get_by_id.return_value = mock_denuncia

        result = check_denuncia_status(uuid.uuid4(), mock_db, service)
        assert result.estado == "pendiente"


class TestPublicSugerencias:
    def test_create_anonymous_sugerencia(self, mock_db):
        from app.api.v2.public import create_anonymous_sugerencia
        from app.domains.monitoring.schemas import SugerenciaCreate
        from app.domains.monitoring.service import MonitoringService

        service = MagicMock(spec=MonitoringService)
        mock_result = MagicMock()
        service.create_sugerencia.return_value = mock_result

        payload = SugerenciaCreate(tipo="canal_nuevo", titulo="Test sugerencia", descripcion="Sugerencia test detallada con suficiente texto")
        result = create_anonymous_sugerencia(payload, mock_db, service)
        assert result == mock_result


# Batch 5 (2026-04-20): `TestPublicIncorporatedChannels` was retired along
# with the `GET /api/v2/public/sugerencias/canales-existentes` endpoint and
# the `get_incorporated_channel_feature_collection` service method. Pilar Azul
# (`useCanales` in the frontend) replaced this path entirely.


# ══════════════════════════════════════════════
# ADMIN PUBLISH ENDPOINTS
# ══════════════════════════════════════════════


class TestAdminPublishLayer:
    def test_publish_layer(self, mock_db, mock_admin):
        from app.api.v2.public import publish_layer
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        mock_capa = MagicMock()
        mock_capa.es_publica = False
        repo.get_by_id.return_value = mock_capa

        result = publish_layer(uuid.uuid4(), mock_db, repo, _user=mock_admin)
        assert mock_capa.es_publica is True

    def test_publish_already_public_raises_409(self, mock_db, mock_admin):
        from app.api.v2.public import publish_layer
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        mock_capa = MagicMock()
        mock_capa.es_publica = True
        repo.get_by_id.return_value = mock_capa

        with pytest.raises(HTTPException) as exc_info:
            publish_layer(uuid.uuid4(), mock_db, repo, _user=mock_admin)
        assert exc_info.value.status_code == 409

    def test_publish_nonexistent_raises_404(self, mock_db, mock_admin):
        from app.api.v2.public import publish_layer
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        repo.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            publish_layer(uuid.uuid4(), mock_db, repo, _user=mock_admin)
        assert exc_info.value.status_code == 404


class TestAdminUnpublishLayer:
    def test_unpublish_layer(self, mock_db, mock_admin):
        from app.api.v2.public import unpublish_layer
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        mock_capa = MagicMock()
        mock_capa.es_publica = True
        repo.get_by_id.return_value = mock_capa

        result = unpublish_layer(uuid.uuid4(), mock_db, repo, _user=mock_admin)
        assert mock_capa.es_publica is False

    def test_unpublish_not_public_raises_409(self, mock_db, mock_admin):
        from app.api.v2.public import unpublish_layer
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        mock_capa = MagicMock()
        mock_capa.es_publica = False
        repo.get_by_id.return_value = mock_capa

        with pytest.raises(HTTPException) as exc_info:
            unpublish_layer(uuid.uuid4(), mock_db, repo, _user=mock_admin)
        assert exc_info.value.status_code == 409


class TestAdminLayersList:
    def test_list_layers_with_status(self, mock_db, mock_admin):
        from app.api.v2.public import list_layers_with_publish_status
        from app.domains.capas.repository import CapasRepository

        repo = MagicMock(spec=CapasRepository)
        repo.get_all.return_value = []

        result = list_layers_with_publish_status(mock_db, repo, _user=mock_admin)
        assert result == []


# ══════════════════════════════════════════════
# ADMIN USER MANAGEMENT
# ══════════════════════════════════════════════


class TestAdminListUsers:
    @pytest.mark.asyncio
    async def test_returns_users(self, mock_async_db, mock_admin):
        from app.api.v2.admin import list_users

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_async_db.execute.return_value = mock_result

        result = await list_users(mock_admin, mock_async_db)
        assert result == []


class TestAdminSetRole:
    @pytest.mark.asyncio
    async def test_sets_role_successfully(self, mock_async_db, mock_admin):
        from app.api.v2.admin import set_user_role, SetRoleRequest
        from app.auth.models import UserRole

        mock_user = MagicMock()
        mock_user.email = "user@test.com"
        mock_user.role = UserRole.CIUDADANO

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_async_db.execute.return_value = mock_result

        body = SetRoleRequest(email="user@test.com", role=UserRole.OPERADOR)
        result = await set_user_role(body, mock_admin, mock_async_db)
        assert result.email == "user@test.com"
        assert "actualizado" in result.message.lower()

    @pytest.mark.asyncio
    async def test_raises_404_for_unknown_user(self, mock_async_db, mock_admin):
        from app.api.v2.admin import set_user_role, SetRoleRequest
        from app.auth.models import UserRole

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_db.execute.return_value = mock_result

        body = SetRoleRequest(email="nobody@test.com", role=UserRole.OPERADOR)
        with pytest.raises(HTTPException) as exc_info:
            await set_user_role(body, mock_admin, mock_async_db)
        assert exc_info.value.status_code == 404


# ══════════════════════════════════════════════
# SCHEMA CONTRACTS
# ══════════════════════════════════════════════


class TestAdminSchemas:
    def test_set_role_request(self):
        from app.api.v2.admin import SetRoleRequest
        from app.auth.models import UserRole

        req = SetRoleRequest(email="test@example.com", role=UserRole.ADMIN)
        assert req.email == "test@example.com"
        assert req.role == UserRole.ADMIN

    def test_set_role_response(self):
        from app.api.v2.admin import SetRoleResponse
        from app.auth.models import UserRole

        resp = SetRoleResponse(
            email="test@example.com",
            role=UserRole.OPERADOR,
            message="Updated",
        )
        assert resp.role == UserRole.OPERADOR


class TestPublicSchemaContracts:
    def test_public_stats_response(self):
        from app.api.v2.public_schemas import PublicStatsResponse

        resp = PublicStatsResponse(
            total_denuncias=10,
            total_sugerencias=5,
            total_capas_publicas=3,
        )
        assert resp.total_denuncias == 10

    def test_publish_layer_response(self):
        from app.api.v2.public_schemas import PublishLayerResponse

        fields = set(PublishLayerResponse.model_fields.keys())
        assert "id" in fields
        assert "es_publica" in fields
        assert "publicacion_fecha" in fields
