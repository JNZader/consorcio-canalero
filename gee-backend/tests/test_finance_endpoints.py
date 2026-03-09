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
