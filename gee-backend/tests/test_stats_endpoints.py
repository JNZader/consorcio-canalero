from unittest.mock import MagicMock, patch


def test_stats_dashboard_returns_service_payload(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_dashboard_stats.return_value = {"denuncias": {"pendiente": 3}}

    with patch("app.api.v1.endpoints.stats.get_supabase_service", return_value=service):
        response = client.get("/api/v1/stats/dashboard", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["denuncias"]["pendiente"] == 3


def test_stats_by_cuenca_handles_no_analysis(client):
    service = MagicMock()
    service.get_latest_analysis.return_value = None

    with patch("app.api.v1.endpoints.stats.get_supabase_service", return_value=service):
        response = client.get("/api/v1/stats/by-cuenca")

    assert response.status_code == 200
    assert response.json() == {"message": "No hay analisis disponibles", "cuencas": []}


def test_stats_by_cuenca_parses_json_stats(client):
    service = MagicMock()
    service.get_analysis.return_value = {
        "id": "analysis-1",
        "created_at": "2026-03-01T00:00:00Z",
        "fecha_inicio": "2026-02-01",
        "fecha_fin": "2026-02-28",
        "hectareas_inundadas": 42,
        "porcentaje_area": 3.1,
        "caminos_afectados": 8,
        "stats_cuencas": '{"candil": {"hectareas": 12, "porcentaje": 2.3}}',
    }

    with patch("app.api.v1.endpoints.stats.get_supabase_service", return_value=service):
        response = client.get("/api/v1/stats/by-cuenca?analysis_id=analysis-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_id"] == "analysis-1"
    assert payload["cuencas"][0]["nombre"] == "candil"
    assert payload["cuencas"][0]["hectareas_inundadas"] == 12
    assert payload["total"]["caminos_afectados"] == 8


def test_stats_historical_includes_cuenca_details_when_present(client):
    service = MagicMock()
    service.get_analysis_history.return_value = {
        "items": [
            {
                "id": "a1",
                "created_at": "2026-03-01T00:00:00Z",
                "fecha_inicio": "2026-02-01",
                "fecha_fin": "2026-02-28",
                "hectareas_inundadas": 55,
                "porcentaje_area": 4.2,
                "caminos_afectados": 11,
                "stats_cuencas": {"norte": {"hectareas": 20, "porcentaje": 5.0}},
            }
        ],
        "total": 1,
    }

    with patch("app.api.v1.endpoints.stats.get_supabase_service", return_value=service):
        response = client.get("/api/v1/stats/historical?cuenca=norte&limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["hectareas_cuenca"] == 20
    assert body["items"][0]["porcentaje_cuenca"] == 5.0


def test_stats_export_csv_generates_download_response(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_analysis_history.return_value = {
        "items": [
            {
                "id": "a1",
                "created_at": "2026-03-01T00:00:00Z",
                "fecha_inicio": "2026-02-01",
                "fecha_fin": "2026-02-28",
                "hectareas_inundadas": 100,
                "porcentaje_area": 7.5,
                "caminos_afectados": 14,
                "status": "completed",
                "stats_cuencas": {"candil": {"hectareas": 10, "porcentaje": 2.5}},
            }
        ]
    }

    with patch("app.api.v1.endpoints.stats.get_supabase_service", return_value=service):
        response = client.post(
            "/api/v1/stats/export",
            headers=auth_headers,
            json={"format": "csv", "cuencas": ["candil"]},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=estadisticas_consorcio_" in response.headers[
        "content-disposition"
    ]
    assert "id,fecha_analisis" in response.text
    assert "a1" in response.text


def test_stats_export_non_csv_returns_json_payload(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_analysis_history.return_value = {"items": []}

    with patch("app.api.v1.endpoints.stats.get_supabase_service", return_value=service):
        response = client.post(
            "/api/v1/stats/export",
            headers=auth_headers,
            json={"format": "xlsx"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "xlsx"
    assert "requires additional dependencies" in payload["message"]


def test_stats_summary_maps_dashboard_fields(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_dashboard_stats.return_value = {
        "ultimo_analisis": {
            "fecha": "2026-03-01",
            "hectareas_inundadas": 77,
            "porcentaje_area": 9.1,
            "caminos_afectados": 18,
        },
        "denuncias": {"pendiente": 4, "en_revision": 2, "resuelto": 9},
    }

    with patch("app.api.v1.endpoints.stats.get_supabase_service", return_value=service):
        response = client.get("/api/v1/stats/summary", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["ultimo_analisis"]["hectareas_inundadas"] == 77
    assert body["denuncias"]["pendientes"] == 4
    assert body["denuncias"]["resueltas_total"] == 9
