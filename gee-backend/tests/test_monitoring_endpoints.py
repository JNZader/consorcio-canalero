from unittest.mock import MagicMock, patch

from app.api.v1.endpoints import monitoring as monitoring_endpoint


def _reset_dashboard_cache() -> None:
    monitoring_endpoint._dashboard_cache["data"] = None
    monitoring_endpoint._dashboard_cache["expires_at"] = 0


def test_monitoring_dashboard_uses_cache_and_maps_response(client, mock_auth, auth_headers):
    _reset_dashboard_cache()

    service = MagicMock()
    service.get_monitoring_summary.return_value = {
        "estado_general": {
            "area_total_ha": 100,
            "area_problematica_ha": 12,
            "porcentaje_problematico": 12,
        },
        "clasificacion": {"cultivo_sano": {"hectareas": 88}},
        "cuencas_criticas": [{"cuenca": "norte", "porcentaje_problematico": 14}],
        "alertas": [{"tipo": "area_critica"}],
        "total_alertas": 1,
        "periodo": {"inicio": "2026-02-01", "fin": "2026-03-02"},
        "fecha_actualizacion": "2026-03-02T12:00:00Z",
    }

    with patch(
        "app.api.v1.endpoints.monitoring.get_monitoring_service", return_value=service
    ):
        first = client.get("/api/v1/monitoring/dashboard", headers=auth_headers)
        second = client.get("/api/v1/monitoring/dashboard", headers=auth_headers)

    assert first.status_code == 200
    assert second.status_code == 200

    first_payload = first.json()
    second_payload = second.json()

    assert first_payload["from_cache"] is False
    assert second_payload["from_cache"] is True
    assert second_payload["summary"]["area_total_ha"] == 100
    assert second_payload["ranking_cuencas"][0]["cuenca"] == "norte"
    assert service.get_monitoring_summary.call_count == 1


def test_monitoring_dashboard_maps_summary_error_to_app_exception(
    client, mock_auth, auth_headers
):
    _reset_dashboard_cache()

    service = MagicMock()
    service.get_monitoring_summary.return_value = {
        "error": "No se encontraron imagenes Sentinel-2"
    }

    with patch(
        "app.api.v1.endpoints.monitoring.get_monitoring_service", return_value=service
    ):
        response = client.get("/api/v1/monitoring/dashboard", headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MONITORING_DATA_ERROR"
