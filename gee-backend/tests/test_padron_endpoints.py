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


def test_import_consorcistas_validates_missing_filename_and_empty_file(
    client, mock_auth, auth_headers
):
    missing_name = client.post(
        "/api/v1/padron/consorcistas/import",
        headers=auth_headers,
        files={"file": ("", b"nombre,apellido,cuit\nJuan,Perez,20-12345678-1\n", "text/csv")},
    )
    assert missing_name.status_code == 422

    empty_file = client.post(
        "/api/v1/padron/consorcistas/import",
        headers=auth_headers,
        files={"file": ("padron.csv", b"", "text/csv")},
    )
    assert empty_file.status_code == 400
    assert empty_file.json()["detail"] == "Archivo vacio"


def test_import_consorcistas_maps_service_value_error_to_400(
    client, mock_auth, auth_headers
):
    service = MagicMock()
    service.import_consorcistas.side_effect = ValueError("CSV malformado")

    with patch("app.api.v1.endpoints.padron.get_padron_service", return_value=service):
        response = client.post(
            "/api/v1/padron/consorcistas/import",
            headers=auth_headers,
            files={"file": ("padron.csv", b"nombre,apellido\n", "text/csv")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "CSV malformado"
