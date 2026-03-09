from unittest.mock import MagicMock, patch


def test_import_consorcistas_success(client, mock_auth, auth_headers):
    service = MagicMock()
    service.import_consorcistas.return_value = {
        "processed": 2,
        "upserted": 2,
        "skipped": 0,
        "errors": [],
    }

    with patch("app.api.v1.endpoints.padron.get_padron_service", return_value=service):
        response = client.post(
            "/api/v1/padron/consorcistas/import",
            headers=auth_headers,
            files={
                "file": (
                    "padron.csv",
                    b"nombre,apellido,cuit\nJuan,Perez,20-12345678-1\n",
                    "text/csv",
                )
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "padron.csv"
    assert payload["upserted"] == 2


def test_import_consorcistas_rejects_extension(client, mock_auth, auth_headers):
    response = client.post(
        "/api/v1/padron/consorcistas/import",
        headers=auth_headers,
        files={"file": ("padron.txt", b"raw", "text/plain")},
    )

    assert response.status_code == 400
    assert "Formato no soportado" in response.json()["detail"]
