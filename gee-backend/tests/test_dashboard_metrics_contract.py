"""Contract tests for dashboard metrics and finance execution endpoints."""

from unittest.mock import MagicMock, patch


def test_stats_dashboard_includes_new_reports_week(admin_auth, auth_headers, client):
    service = MagicMock()
    service.get_dashboard_stats.return_value = {
        "ultimo_analisis": {
            "fecha": None,
            "hectareas_inundadas": 0,
            "porcentaje_area": 0,
            "caminos_afectados": 0,
        },
        "denuncias": {
            "pendiente": 2,
            "en_revision": 1,
            "resuelto": 3,
            "rechazado": 0,
            "total": 6,
        },
        "denuncias_nuevas_semana": 4,
        "area_total_ha": 1000,
    }

    with patch("app.api.v1.endpoints.stats.get_supabase_service", return_value=service):
        response = client.get("/api/v1/stats/dashboard", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["denuncias_nuevas_semana"] == 4


def test_finance_budget_execution_endpoint_returns_chart_rows(
    admin_auth, auth_headers, client
):
    service = MagicMock()
    service.get_budget_execution_by_category.return_value = [
        {"rubro": "obras", "proyectado": 120000.0, "real": 90000.0}
    ]

    with patch(
        "app.api.v1.endpoints.finance.get_finance_service", return_value=service
    ):
        response = client.get(
            "/api/v1/finance/presupuestos/ejecucion/2026", headers=auth_headers
        )

    assert response.status_code == 200
    assert response.json() == [
        {"rubro": "obras", "proyectado": 120000.0, "real": 90000.0}
    ]
    service.get_budget_execution_by_category.assert_called_once_with(2026)
