from unittest.mock import MagicMock, patch


def test_list_finance_categories(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_categorias.return_value = ["combustible", "obras"]

    with patch(
        "app.api.v1.endpoints.finance.get_finance_service", return_value=service
    ):
        response = client.get("/api/v1/finance/categorias", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == ["combustible", "obras"]


def test_update_gasto_category(client, mock_auth, auth_headers):
    service = MagicMock()
    service.update_gasto.return_value = {"id": "gasto-1", "categoria": "insumos"}

    with patch(
        "app.api.v1.endpoints.finance.get_finance_service", return_value=service
    ):
        response = client.patch(
            "/api/v1/finance/gastos/gasto-1",
            headers=auth_headers,
            json={"categoria": "insumos"},
        )

    assert response.status_code == 200
    assert response.json()["categoria"] == "insumos"


def test_list_ingresos(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_ingresos.return_value = [{"id": "ing-1", "fuente": "subsidio"}]

    with patch(
        "app.api.v1.endpoints.finance.get_finance_service", return_value=service
    ):
        response = client.get("/api/v1/finance/ingresos", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()[0]["fuente"] == "subsidio"


def test_create_ingreso(client, mock_auth, auth_headers):
    service = MagicMock()
    service.create_ingreso.return_value = {"id": "ing-1", "descripcion": "Subsidio"}

    with patch(
        "app.api.v1.endpoints.finance.get_finance_service", return_value=service
    ):
        response = client.post(
            "/api/v1/finance/ingresos",
            headers=auth_headers,
            json={
                "descripcion": "Subsidio",
                "monto": 1000,
                "fecha": "2026-03-09",
                "fuente": "subsidio",
            },
        )

    assert response.status_code == 200
    assert response.json()["id"] == "ing-1"


def test_upload_finance_comprobante(client, mock_auth, auth_headers):
    service = MagicMock()
    service.upload_finance_comprobante.return_value = {
        "filename": "gasto/test.png",
        "url": "https://storage.example.com/gasto/test.png",
    }

    png_content = b"\x89PNG\r\n\x1a\n1234"

    with patch(
        "app.api.v1.endpoints.finance.get_finance_service", return_value=service
    ):
        response = client.post(
            "/api/v1/finance/comprobantes/upload",
            headers=auth_headers,
            files={"file": ("comprobante.png", png_content, "image/png")},
            data={"tipo": "gasto"},
        )

    assert response.status_code == 200
    assert response.json()["url"] == "https://storage.example.com/gasto/test.png"


def test_upload_finance_comprobante_rejects_invalid_content_type(
    client, mock_auth, auth_headers
):
    response = client.post(
        "/api/v1/finance/comprobantes/upload",
        headers=auth_headers,
        files={"file": ("malicioso.png", b"not_an_image", "image/png")},
        data={"tipo": "gasto"},
    )

    assert response.status_code == 400
