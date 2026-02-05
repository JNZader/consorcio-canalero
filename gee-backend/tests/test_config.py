"""
Tests for configuration endpoints.

Tests:
- GET /api/v1/config/system - Get system configuration
"""

import pytest
from fastapi.testclient import TestClient
from app import constants


class TestSystemConfig:
    """Tests for system configuration endpoint."""

    def test_get_system_config_success(self, client: TestClient):
        """Should return system configuration with correct structure and values."""
        response = client.get("/api/v1/config/system")

        assert response.status_code == 200
        data = response.json()

        # Check top-level fields
        assert "consorcio_area_ha" in data
        assert "consorcio_km_caminos" in data
        assert "map" in data
        assert "cuencas" in data
        assert "analysis" in data

        # Check consorcio values
        assert data["consorcio_area_ha"] == constants.CONSORCIO_AREA_HA
        assert data["consorcio_km_caminos"] == constants.CONSORCIO_KM_CAMINOS

        # Check map config
        assert data["map"]["center"]["lat"] == constants.MAP_CENTER_LAT
        assert data["map"]["center"]["lng"] == constants.MAP_CENTER_LNG
        assert data["map"]["zoom"] == constants.MAP_DEFAULT_ZOOM
        assert data["map"]["bounds"] == constants.MAP_BOUNDS

        # Check cuencas
        assert len(data["cuencas"]) == len(constants.CUENCA_IDS)
        for cuenca in data["cuencas"]:
            assert cuenca["id"] in constants.CUENCA_IDS
            assert cuenca["nombre"] == constants.CUENCA_NOMBRES[cuenca["id"]]
            assert cuenca["ha"] == constants.CUENCA_AREAS_HA[cuenca["id"]]
            assert cuenca["color"] == constants.CUENCA_COLORS[cuenca["id"]]

        # Check analysis config
        assert data["analysis"]["default_max_cloud"] == constants.DEFAULT_MAX_CLOUD
        assert data["analysis"]["default_days_back"] == constants.DEFAULT_DAYS_BACK
