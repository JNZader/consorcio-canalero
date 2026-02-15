"""
Pytest configuration and fixtures for gee-backend tests.

Provides:
- FastAPI test client
- Mocked Supabase service
- Mocked GEE service
- Test environment variables
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from typing import Generator, Dict, Any

# Set test environment variables BEFORE importing app modules
os.environ.update(
    {
        "SUPABASE_URL": "http://localhost:54321",
        "SUPABASE_KEY": "test-anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
        "SUPABASE_JWT_SECRET": "test-jwt-secret-at-least-32-chars-long",
        "GEE_PROJECT_ID": "test-project",
        "REDIS_URL": "redis://localhost:6379/0",
        "CORS_ORIGINS": "http://localhost:3000,http://localhost:4321",
        "DEBUG": "true",
        "FRONTEND_URL": "http://localhost:4321",
    }
)

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.main import app


# ===========================================
# Test Client Fixtures
# ===========================================


@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    """
    Synchronous test client for FastAPI.
    Use for simple endpoint tests.
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
async def async_client() -> AsyncClient:
    """
    Async test client for FastAPI.
    Use for testing async endpoints.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ===========================================
# Mock Supabase Service
# ===========================================


@pytest.fixture
def mock_supabase_service():
    """
    Mock Supabase service for testing without real database.
    """
    with patch("app.services.supabase_service.get_supabase_service") as mock:
        service = MagicMock()

        # Mock report methods
        service.create_report.return_value = {
            "id": "test-report-id",
            "tipo": "desborde",
            "descripcion": "Test description",
            "latitud": -33.7,
            "longitud": -63.9,
            "estado": "pendiente",
            "created_at": "2024-01-15T10:00:00Z",
        }

        service.get_reports.return_value = {
            "items": [
                {
                    "id": "report-1",
                    "tipo": "desborde",
                    "estado": "pendiente",
                    "created_at": "2024-01-15T10:00:00Z",
                }
            ],
            "total": 1,
            "page": 1,
        }

        service.get_report.return_value = {
            "id": "test-report-id",
            "tipo": "desborde",
            "descripcion": "Test description",
            "estado": "pendiente",
        }

        service.update_report.return_value = {
            "id": "test-report-id",
            "estado": "en_revision",
        }

        # Mock layer methods
        service.get_layers.return_value = [
            {
                "id": "layer-1",
                "nombre": "Cuencas",
                "tipo": "polygon",
                "visible": True,
            }
        ]

        service.create_layer.return_value = {
            "id": "new-layer-id",
            "nombre": "Nueva Capa",
        }

        # Mock analysis methods
        service.get_analysis_history.return_value = {
            "items": [],
            "total": 0,
            "page": 1,
            "limit": 10,
            "pages": 0,
        }

        service.save_analysis.return_value = {
            "id": "analysis-id",
            "created_at": "2024-01-15T10:00:00Z",
        }

        # Mock photo upload
        service.upload_report_photo.return_value = (
            "https://storage.example.com/photo.jpg"
        )

        mock.return_value = service
        yield service


# ===========================================
# Mock GEE Service
# ===========================================


@pytest.fixture
def mock_gee_service():
    """
    Mock Google Earth Engine service for testing without real GEE.
    """
    with (
        patch("app.services.gee_service.initialize_gee") as mock_init,
        patch("app.services.gee_service.GEEFloodDetector") as mock_detector,
    ):
        # Mock initialization
        mock_init.return_value = True

        # Mock flood detector
        detector_instance = MagicMock()
        detector_instance.detect_floods.return_value = {
            "hectareas_inundadas": 1500.5,
            "porcentaje_area": 12.3,
            "caminos_afectados": 25,
            "imagenes_procesadas": 10,
            "stats_cuencas": {
                "cuenca_1": {"hectareas": 500, "porcentaje": 15.0},
                "cuenca_2": {"hectareas": 1000, "porcentaje": 10.0},
            },
            "geojson": {
                "type": "FeatureCollection",
                "features": [],
            },
        }

        mock_detector.return_value = detector_instance

        yield {
            "init": mock_init,
            "detector": mock_detector,
            "instance": detector_instance,
        }


# ===========================================
# Mock JWT/Auth
# ===========================================


@pytest.fixture
def mock_auth():
    """
    Mock authentication for testing protected endpoints.
    """
    with (
        patch("app.auth.verify_supabase_token") as mock_verify,
        patch("app.auth.get_user_role") as mock_role,
    ):
        # Default to authenticated admin user
        mock_verify.return_value = MagicMock(
            sub="test-user-id",
            email="admin@test.com",
            role="admin",
            exp=9999999999,
        )
        mock_role.return_value = "admin"

        yield {
            "verify_token": mock_verify,
            "get_role": mock_role,
        }


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """
    Returns authentication headers for protected endpoints.
    """
    return {"Authorization": "Bearer test-jwt-token"}


@pytest.fixture
def admin_auth(mock_auth):
    """
    Configure mock auth as admin user.
    """
    mock_auth["get_role"].return_value = "admin"
    return mock_auth


@pytest.fixture
def operator_auth(mock_auth):
    """
    Configure mock auth as operator user.
    """
    mock_auth["get_role"].return_value = "operador"
    return mock_auth


@pytest.fixture
def citizen_auth(mock_auth):
    """
    Configure mock auth as regular citizen user.
    """
    mock_auth["get_role"].return_value = "ciudadano"
    return mock_auth


# ===========================================
# Test Data Fixtures
# ===========================================


@pytest.fixture
def sample_report() -> Dict[str, Any]:
    """
    Sample report data for testing.
    """
    return {
        "tipo": "desborde",
        "descripcion": "Canal desbordado en la zona norte, afectando caminos rurales.",
        "latitud": -33.7,
        "longitud": -63.9,
        "cuenca": "cuenca_1",
    }


@pytest.fixture
def sample_flood_detection_request() -> Dict[str, Any]:
    """
    Sample flood detection request for testing.
    """
    return {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "cuencas": ["cuenca_1", "cuenca_2"],
        "threshold": -15,
    }


@pytest.fixture
def sample_layer() -> Dict[str, Any]:
    """
    Sample layer data for testing.
    """
    return {
        "nombre": "Test Layer",
        "descripcion": "Layer for testing",
        "tipo": "polygon",
        "visible": True,
        "orden": 1,
        "estilo": {
            "color": "#ff0000",
            "weight": 2,
            "fillColor": "#ff0000",
            "fillOpacity": 0.3,
        },
    }


# ===========================================
# Cleanup Fixtures
# ===========================================


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """
    Reset rate limiting between tests.

    Clears the in-memory storage of the distributed rate limiter.
    """
    from app.core.rate_limit import get_rate_limiter

    rate_limiter = get_rate_limiter()
    # Clear in-memory store (synchronous operation for fixture)
    rate_limiter._memory_store.clear()
    yield
    # Clear again after test
    rate_limiter._memory_store.clear()
