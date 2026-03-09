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


def test_finance_ingresos_and_presupuestos_endpoints(client, mock_auth, auth_headers):
    service = MagicMock()
    service.update_ingreso.return_value = {"id": "ing-1", "fuente": "subsidio"}
    service.get_fuentes_ingreso.return_value = ["subsidio", "otros"]
    service.get_presupuestos.return_value = [{"anio": 2026}]
    service.get_budget_execution_by_category.return_value = [
        {"rubro": "obras", "proyectado": 1000, "real": 800}
    ]

    with patch(
        "app.api.v1.endpoints.finance.get_finance_service", return_value=service
    ):
        update_resp = client.patch(
            "/api/v1/finance/ingresos/ing-1",
            headers=auth_headers,
            json={"fuente": "subsidio"},
        )
        fuentes_resp = client.get("/api/v1/finance/fuentes", headers=auth_headers)
        presup_resp = client.get("/api/v1/finance/presupuestos", headers=auth_headers)
        budget_resp = client.get(
            "/api/v1/finance/presupuestos/ejecucion/2026", headers=auth_headers
        )

    assert update_resp.status_code == 200
    assert fuentes_resp.json() == ["subsidio", "otros"]
    assert presup_resp.json()[0]["anio"] == 2026
    assert budget_resp.json()[0]["rubro"] == "obras"


def test_upload_finance_comprobante_validation_edges(client, mock_auth, auth_headers):
    empty_response = client.post(
        "/api/v1/finance/comprobantes/upload",
        headers=auth_headers,
        files={"file": ("comprobante.png", b"", "image/png")},
        data={"tipo": "gasto"},
    )
    assert empty_response.status_code == 400

    invalid_type = client.post(
        "/api/v1/finance/comprobantes/upload",
        headers=auth_headers,
        files={"file": ("comprobante.png", b"123", "image/png")},
        data={"tipo": "otro"},
    )
    assert invalid_type.status_code == 400

    mismatch = client.post(
        "/api/v1/finance/comprobantes/upload",
        headers=auth_headers,
        files={"file": ("comprobante.pdf", b"%PDF-1.4 test", "image/png")},
        data={"tipo": "gasto"},
    )
    assert mismatch.status_code == 400

    service = MagicMock()
    service.upload_finance_comprobante.return_value = {
        "filename": "ingreso/test.pdf",
        "url": "https://storage.example.com/ingreso/test.pdf",
    }
    with patch(
        "app.api.v1.endpoints.finance.get_finance_service", return_value=service
    ):
        pdf_ok = client.post(
            "/api/v1/finance/comprobantes/upload",
            headers=auth_headers,
            files={"file": ("comprobante.pdf", b"%PDF-1.4 test", "application/pdf")},
            data={"tipo": "ingreso"},
        )
    assert pdf_ok.status_code == 200
    assert pdf_ok.json()["filename"].endswith(".pdf")
