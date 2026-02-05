"""
Tests for authentication module.

Tests:
- JWT token verification
- Role extraction
- Permission checks
- Protected endpoint access
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from jose import jwt
import time

from app.auth import (
    verify_supabase_token,
    get_user_role,
    get_current_user,
    get_current_user_required,
    require_roles,
    User,
    TokenPayload,
)
from app.config import settings


class TestTokenPayload:
    """Tests for TokenPayload model."""

    def test_token_payload_creation(self):
        """Should create a valid token payload."""
        payload = TokenPayload(
            sub="user-123",
            email="test@example.com",
            role="admin",
            exp=9999999999,
        )

        assert payload.sub == "user-123"
        assert payload.email == "test@example.com"
        assert payload.role == "admin"
        assert payload.exp == 9999999999

    def test_token_payload_optional_fields(self):
        """Should handle optional fields."""
        payload = TokenPayload(
            sub="user-123",
            exp=9999999999,
        )

        assert payload.sub == "user-123"
        assert payload.email is None
        assert payload.role is None


class TestUser:
    """Tests for User model."""

    def test_user_creation(self):
        """Should create a valid user."""
        user = User(
            id="user-123",
            email="test@example.com",
            role="admin",
        )

        assert user.id == "user-123"
        assert user.email == "test@example.com"
        assert user.role == "admin"

    def test_user_default_role(self):
        """Should use ciudadano as default role."""
        user = User(id="user-123")

        assert user.role == "ciudadano"


class TestVerifySupabaseToken:
    """Tests for JWT token verification."""

    @pytest.fixture
    def valid_token(self):
        """Create a valid JWT token for testing."""
        payload = {
            "sub": "test-user-id",
            "email": "test@example.com",
            "role": "admin",
            "exp": int(time.time()) + 3600,  # 1 hour from now
            "aud": "authenticated",
        }
        return jwt.encode(
            payload,
            settings.supabase_jwt_secret,
            algorithm="HS256",
        )

    @pytest.fixture
    def expired_token(self):
        """Create an expired JWT token for testing."""
        payload = {
            "sub": "test-user-id",
            "email": "test@example.com",
            "exp": int(time.time()) - 3600,  # 1 hour ago (expired)
            "aud": "authenticated",
        }
        return jwt.encode(
            payload,
            settings.supabase_jwt_secret,
            algorithm="HS256",
        )

    @pytest.mark.asyncio
    async def test_verify_valid_token(self, valid_token):
        """Should verify a valid token successfully."""
        result = await verify_supabase_token(valid_token)

        assert result is not None
        assert result.sub == "test-user-id"
        assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_verify_expired_token(self, expired_token):
        """Should reject an expired token."""
        result = await verify_supabase_token(expired_token)

        assert result is None

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self):
        """Should reject an invalid token."""
        result = await verify_supabase_token("invalid-token")

        assert result is None

    @pytest.mark.asyncio
    async def test_verify_token_wrong_secret(self):
        """Should reject token signed with wrong secret."""
        payload = {
            "sub": "test-user-id",
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
        }
        wrong_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        result = await verify_supabase_token(wrong_token)

        assert result is None

    @pytest.mark.asyncio
    async def test_verify_token_extracts_role_from_user_metadata(self):
        """Should extract role from user_metadata if not in root."""
        payload = {
            "sub": "test-user-id",
            "user_metadata": {"role": "operador"},
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
        }
        token = jwt.encode(
            payload,
            settings.supabase_jwt_secret,
            algorithm="HS256",
        )

        result = await verify_supabase_token(token)

        assert result is not None
        assert result.role == "operador"


class TestGetUserRole:
    """Tests for fetching user role from database."""

    @pytest.mark.asyncio
    async def test_get_user_role_success(self):
        """Should fetch user role from Supabase."""
        with patch("app.auth.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{"rol": "admin"}]

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            role = await get_user_role("user-123")

            assert role == "admin"

    @pytest.mark.asyncio
    async def test_get_user_role_not_found(self):
        """Should return ciudadano if user not found."""
        with patch("app.auth.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []  # Empty result

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            role = await get_user_role("nonexistent-user")

            assert role == "ciudadano"

    @pytest.mark.asyncio
    async def test_get_user_role_error(self):
        """Should return ciudadano on error."""
        with patch("app.auth.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = Exception("Network error")
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            role = await get_user_role("user-123")

            assert role == "ciudadano"


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self):
        """Should return None when no credentials provided."""
        result = await get_current_user(None)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Should return None for invalid token."""
        credentials = MagicMock()
        credentials.credentials = "invalid-token"

        result = await get_current_user(credentials)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self):
        """Should return user for valid token."""
        payload = {
            "sub": "test-user-id",
            "email": "test@example.com",
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
        }
        valid_token = jwt.encode(
            payload,
            settings.supabase_jwt_secret,
            algorithm="HS256",
        )

        credentials = MagicMock()
        credentials.credentials = valid_token

        with patch("app.auth.get_user_role", return_value="admin"):
            result = await get_current_user(credentials)

        assert result is not None
        assert result.id == "test-user-id"
        assert result.email == "test@example.com"
        assert result.role == "admin"


class TestGetCurrentUserRequired:
    """Tests for get_current_user_required dependency."""

    @pytest.mark.asyncio
    async def test_get_current_user_required_no_credentials(self):
        """Should raise 401 when no credentials provided."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_required(None)

        assert exc_info.value.status_code == 401
        assert "No se proporcionaron credenciales" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_required_invalid_token(self):
        """Should raise 401 for invalid token."""
        from fastapi import HTTPException

        credentials = MagicMock()
        credentials.credentials = "invalid-token"

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_required(credentials)

        assert exc_info.value.status_code == 401
        assert "Token invalido o expirado" in exc_info.value.detail


class TestRequireRoles:
    """Tests for role-based access control."""

    @pytest.mark.asyncio
    async def test_require_roles_allowed(self):
        """Should allow user with required role."""
        role_checker = require_roles(["admin", "operador"])

        user = User(id="user-123", email="admin@test.com", role="admin")

        # This should not raise
        result = await role_checker(user)

        assert result.id == "user-123"
        assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_require_roles_denied(self):
        """Should deny user without required role."""
        from fastapi import HTTPException

        role_checker = require_roles(["admin"])

        user = User(id="user-123", email="citizen@test.com", role="ciudadano")

        with pytest.raises(HTTPException) as exc_info:
            await role_checker(user)

        assert exc_info.value.status_code == 403
        assert "Se requiere rol: admin" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_roles_multiple_allowed(self):
        """Should allow any of the specified roles."""
        role_checker = require_roles(["admin", "operador"])

        operator = User(id="user-123", role="operador")
        admin = User(id="user-456", role="admin")

        # Both should be allowed
        result_op = await role_checker(operator)
        result_admin = await role_checker(admin)

        assert result_op.role == "operador"
        assert result_admin.role == "admin"


class TestProtectedEndpoints:
    """Integration tests for protected endpoints."""

    def test_protected_endpoint_without_auth(self, client):
        """Should return 401 for protected endpoint without auth."""
        response = client.get("/api/v1/reports")

        # Should require authentication
        assert response.status_code in [401, 403]

    def test_protected_endpoint_with_invalid_token(self, client):
        """Should return 401 for invalid token."""
        response = client.get(
            "/api/v1/reports",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401

    def test_protected_endpoint_with_valid_auth(
        self, client, mock_auth, auth_headers, mock_supabase_service
    ):
        """Should allow access with valid authentication."""
        response = client.get("/api/v1/reports", headers=auth_headers)

        # Should succeed (200) or at least not be 401
        assert response.status_code != 401

    def test_admin_only_endpoint_as_citizen(
        self, client, citizen_auth, auth_headers
    ):
        """Should deny citizen access to admin-only endpoints."""
        # Try to access admin endpoint
        response = client.delete(
            "/api/v1/layers/some-layer-id",
            headers=auth_headers,
        )

        # Should be forbidden
        assert response.status_code in [401, 403]

    def test_admin_only_endpoint_as_admin(
        self, client, admin_auth, auth_headers, mock_supabase_service
    ):
        """Should allow admin access to admin endpoints."""
        # Mock the layer deletion
        mock_supabase_service.delete_layer = MagicMock()

        response = client.delete(
            "/api/v1/layers/some-layer-id",
            headers=auth_headers,
        )

        # Should not be forbidden (might be 404 if layer doesn't exist, but not 403)
        assert response.status_code != 403
