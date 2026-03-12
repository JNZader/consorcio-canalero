from unittest.mock import MagicMock, patch


def test_get_reports_passes_filters_to_service(client, mock_auth, auth_headers):
    db = MagicMock()
    db.get_reports.return_value = {"items": [], "total": 0, "page": 1, "limit": 20}

    with patch("app.api.v1.endpoints.reports.get_supabase_service", return_value=db):
        response = client.get(
            "/api/v1/reports?page=2&limit=10&status=en_revision&cuenca=norte&tipo=desborde&assigned_to=op-1",
            headers=auth_headers,
        )

    assert response.status_code == 200
    db.get_reports.assert_called_once_with(
        page=2,
        limit=10,
        status="en_revision",
        cuenca="norte",
        tipo="desborde",
        assigned_to="op-1",
    )


def test_get_report_returns_404_when_missing(client, mock_auth, auth_headers):
    db = MagicMock()
    db.get_report.return_value = None

    with patch("app.api.v1.endpoints.reports.get_supabase_service", return_value=db):
        response = client.get("/api/v1/reports/missing", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REPORT_NOT_FOUND"


def test_update_report_converts_enums_and_updates(client, admin_auth, auth_headers):
    db = MagicMock()
    db.get_report.return_value = {"id": "rep-1", "estado": "pendiente"}
    db.update_report.return_value = {"id": "rep-1", "estado": "en_revision"}

    with patch("app.api.v1.endpoints.reports.get_supabase_service", return_value=db):
        response = client.put(
            "/api/v1/reports/rep-1",
            headers=auth_headers,
            json={"estado": "en_revision", "prioridad": "alta"},
        )

    assert response.status_code == 200
    db.update_report.assert_called_once_with(
        "rep-1",
        {"estado": "en_revision", "prioridad": "alta"},
        "test-user-id",
    )


def test_assign_report_sets_revision_state_and_notes(client, admin_auth, auth_headers):
    db = MagicMock()
    db.get_report.return_value = {"id": "rep-1"}
    db.update_report.return_value = {"id": "rep-1", "estado": "en_revision"}

    with patch("app.api.v1.endpoints.reports.get_supabase_service", return_value=db):
        response = client.post(
            "/api/v1/reports/rep-1/assign",
            headers=auth_headers,
            json={"operador_id": "op-2", "notas": "prioridad alta"},
        )

    assert response.status_code == 200
    db.update_report.assert_called_once_with(
        "rep-1",
        {
            "asignado_a": "op-2",
            "estado": "en_revision",
            "notas_internas": "prioridad alta",
        },
        "test-user-id",
    )


def test_resolve_report_defaults_resolved_by_to_current_user(
    client, admin_auth, auth_headers
):
    db = MagicMock()
    db.get_report.return_value = {"id": "rep-1", "estado": "en_revision"}
    db.update_report.return_value = {
        "id": "rep-1",
        "estado": "rechazado",
        "updated_at": "2026-03-01T10:00:00Z",
    }

    with patch("app.api.v1.endpoints.reports.get_supabase_service", return_value=db):
        response = client.post(
            "/api/v1/reports/rep-1/resolve",
            headers=auth_headers,
            json={
                "report_id": "rep-1",
                "resolution": {"status": "rejected", "comment": "No corresponde"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["resolved_by"] == "test-user-id"
