"""
Tests for public endpoints (no authentication required).

Tests:
- POST /api/v1/public/reports - Create public report
- POST /api/v1/public/upload-photo - Upload photo
- GET /api/v1/public/health - Health check
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import io


class TestPublicHealth:
    """Tests for public health endpoint."""

    def test_health_check_returns_ok(self, client: TestClient):
        """Health check should return status ok."""
        response = client.get("/api/v1/public/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "service" in data

    def test_root_health_check(self, client: TestClient):
        """Root endpoint should return healthy status."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_endpoint(self, client: TestClient):
        """Health endpoint should return healthy."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestCreatePublicReport:
    """Tests for public report creation."""

    def test_create_report_success(
        self, client: TestClient, mock_supabase_service, sample_report
    ):
        """Should create a report with valid data."""
        response = client.post("/api/v1/public/reports", json=sample_report)

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["message"] == "Denuncia creada exitosamente. Gracias por colaborar."
        assert data["estado"] == "pendiente"

    def test_create_report_invalid_tipo(
        self, client: TestClient, mock_supabase_service, sample_report
    ):
        """Should reject report with invalid tipo."""
        sample_report["tipo"] = "invalid_type"

        response = client.post("/api/v1/public/reports", json=sample_report)

        assert response.status_code == 400
        data = response.json()
        assert "Tipo invalido" in data["detail"]
        assert "alcantarilla_tapada" in data["detail"]

    def test_create_report_valid_tipos(
        self, client: TestClient, mock_supabase_service, sample_report
    ):
        """Should accept all valid tipo values."""
        valid_tipos = ["alcantarilla_tapada", "desborde", "camino_danado", "otro"]

        for tipo in valid_tipos:
            sample_report["tipo"] = tipo
            response = client.post("/api/v1/public/reports", json=sample_report)
            assert response.status_code == 200, f"Failed for tipo: {tipo}"

    def test_create_report_missing_required_fields(
        self, client: TestClient, mock_supabase_service
    ):
        """Should reject report with missing required fields."""
        incomplete_report = {
            "tipo": "desborde",
            # Missing descripcion, latitud, longitud
        }

        response = client.post("/api/v1/public/reports", json=incomplete_report)

        assert response.status_code == 422  # Validation error

    def test_create_report_description_too_short(
        self, client: TestClient, mock_supabase_service, sample_report
    ):
        """Should reject report with description less than 10 characters."""
        sample_report["descripcion"] = "Short"

        response = client.post("/api/v1/public/reports", json=sample_report)

        assert response.status_code == 422

    def test_create_report_description_too_long(
        self, client: TestClient, mock_supabase_service, sample_report
    ):
        """Should reject report with description over 2000 characters."""
        sample_report["descripcion"] = "x" * 2001

        response = client.post("/api/v1/public/reports", json=sample_report)

        assert response.status_code == 422

    def test_create_report_invalid_coordinates(
        self, client: TestClient, mock_supabase_service, sample_report
    ):
        """Should reject report with invalid coordinates."""
        # Invalid latitude (out of range)
        sample_report["latitud"] = 100  # Valid range: -90 to 90

        response = client.post("/api/v1/public/reports", json=sample_report)

        assert response.status_code == 422

    def test_create_report_invalid_longitude(
        self, client: TestClient, mock_supabase_service, sample_report
    ):
        """Should reject report with invalid longitude."""
        sample_report["longitud"] = 200  # Valid range: -180 to 180

        response = client.post("/api/v1/public/reports", json=sample_report)

        assert response.status_code == 422

    def test_create_report_with_optional_fields(
        self, client: TestClient, mock_supabase_service, sample_report
    ):
        """Should accept report with optional fields."""
        sample_report["cuenca"] = "cuenca_test"
        sample_report["foto_url"] = "https://example.com/photo.jpg"

        response = client.post("/api/v1/public/reports", json=sample_report)

        assert response.status_code == 200

    def test_create_report_database_error(
        self, client: TestClient, mock_supabase_service, sample_report
    ):
        """Should handle database errors gracefully."""
        mock_supabase_service.create_report.side_effect = Exception("Database error")

        response = client.post("/api/v1/public/reports", json=sample_report)

        assert response.status_code == 500
        assert "Error al crear la denuncia" in response.json()["detail"]


class TestUploadPhoto:
    """Tests for photo upload endpoint."""

    def test_upload_photo_success(self, client: TestClient, mock_supabase_service):
        """Should upload photo successfully."""
        # Create a fake image file
        image_content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"

        response = client.post(
            "/api/v1/public/upload-photo",
            files={"file": ("test.jpg", io.BytesIO(image_content), "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert "photo_url" in data
        assert "filename" in data

    def test_upload_photo_png(self, client: TestClient, mock_supabase_service):
        """Should accept PNG files."""
        # Minimal PNG header
        png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

        response = client.post(
            "/api/v1/public/upload-photo",
            files={"file": ("test.png", io.BytesIO(png_content), "image/png")},
        )

        assert response.status_code == 200

    def test_upload_photo_webp(self, client: TestClient, mock_supabase_service):
        """Should accept WebP files."""
        webp_content = b"RIFF\x00\x00\x00\x00WEBP"

        response = client.post(
            "/api/v1/public/upload-photo",
            files={"file": ("test.webp", io.BytesIO(webp_content), "image/webp")},
        )

        assert response.status_code == 200

    def test_upload_photo_invalid_type(self, client: TestClient, mock_supabase_service):
        """Should reject non-image files."""
        pdf_content = b"%PDF-1.4"

        response = client.post(
            "/api/v1/public/upload-photo",
            files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )

        assert response.status_code == 400
        assert "Tipo de archivo no permitido" in response.json()["detail"]

    def test_upload_photo_too_large(self, client: TestClient, mock_supabase_service):
        """Should reject files larger than 5MB."""
        # Create a file larger than 5MB
        large_content = b"x" * (6 * 1024 * 1024)  # 6MB

        response = client.post(
            "/api/v1/public/upload-photo",
            files={"file": ("large.jpg", io.BytesIO(large_content), "image/jpeg")},
        )

        assert response.status_code == 413
        assert "Archivo muy grande" in response.json()["detail"]

    def test_upload_photo_storage_error(
        self, client: TestClient, mock_supabase_service
    ):
        """Should handle storage errors gracefully."""
        mock_supabase_service.upload_report_photo.side_effect = Exception(
            "Storage error"
        )

        image_content = b"\xff\xd8\xff\xe0JFIF"

        response = client.post(
            "/api/v1/public/upload-photo",
            files={"file": ("test.jpg", io.BytesIO(image_content), "image/jpeg")},
        )

        assert response.status_code == 500
        assert "Error al subir la foto" in response.json()["detail"]


class TestRateLimiting:
    """Tests for rate limiting on public endpoints."""

    def test_rate_limit_not_triggered_under_limit(
        self, client: TestClient, mock_supabase_service
    ):
        """Should allow requests under rate limit."""
        # Make a few requests (under the limit)
        for _ in range(5):
            response = client.get("/api/v1/public/health")
            assert response.status_code == 200

    def test_health_check_bypasses_rate_limit(self, client: TestClient):
        """Health and root endpoints should bypass rate limiting."""
        # Health checks should never be rate limited
        for _ in range(200):
            response = client.get("/health")
            assert response.status_code == 200

        for _ in range(200):
            response = client.get("/")
            assert response.status_code == 200
