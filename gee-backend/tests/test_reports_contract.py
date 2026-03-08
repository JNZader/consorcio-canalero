"""Contract tests for reports resolve endpoint."""

from uuid import uuid4


def test_resolve_report_uses_canonical_contract(
    client, admin_auth, auth_headers, mock_supabase_service
):
    report_id = str(uuid4())
    payload = {
        "report_id": report_id,
        "resolution": {
            "status": "resolved",
            "comment": "Incidente mitigado",
            "resolved_by": "operator-123",
        },
    }

    mock_supabase_service.get_report.return_value = {
        "id": report_id,
        "estado": "en_revision",
    }
    mock_supabase_service.update_report.return_value = {
        "id": report_id,
        "estado": "resuelto",
        "resuelto_at": "2026-01-10T09:30:00Z",
    }

    response = client.post(
        f"/api/v1/reports/{report_id}/resolve",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == report_id
    assert body["status"] == "resolved"
    assert body["resolved_at"] == "2026-01-10T09:30:00Z"
    assert body["resolved_by"] == "operator-123"

    mock_supabase_service.update_report.assert_called_once_with(
        report_id,
        {
            "estado": "resuelto",
            "resolucion_descripcion": "Incidente mitigado",
        },
        "test-user-id",
    )


def test_resolve_report_rejects_path_payload_mismatch(
    client, admin_auth, auth_headers, mock_supabase_service
):
    response = client.post(
        "/api/v1/reports/report-in-path/resolve",
        headers=auth_headers,
        json={
            "report_id": "different-id",
            "resolution": {
                "status": "resolved",
                "comment": "No-op",
                "resolved_by": "operator-123",
            },
        },
    )

    assert response.status_code == 400


def test_resolve_report_rejects_invalid_status(client, admin_auth, auth_headers):
    response = client.post(
        f"/api/v1/reports/{uuid4()}/resolve",
        headers=auth_headers,
        json={
            "report_id": str(uuid4()),
            "resolution": {
                "status": "done",
                "comment": "No-op",
                "resolved_by": "operator-123",
            },
        },
    )

    assert response.status_code == 422
