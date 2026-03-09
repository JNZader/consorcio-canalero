from io import BytesIO
from unittest.mock import MagicMock, patch


def test_list_assets_and_create_asset_delegate_to_service(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_all_assets.return_value = [{"id": "asset-1"}]
    service.create_asset.return_value = {"id": "asset-2", "nombre": "Canal A"}

    with patch(
        "app.api.v1.endpoints.infrastructure.get_infrastructure_service",
        return_value=service,
    ):
        listed = client.get("/api/v1/infrastructure/assets?cuenca=candil", headers=auth_headers)
        created = client.post(
            "/api/v1/infrastructure/assets",
            headers=auth_headers,
            json={"nombre": "Canal A", "tipo": "canal", "cuenca": "candil"},
        )

    assert listed.status_code == 200
    assert listed.json() == [{"id": "asset-1"}]
    service.get_all_assets.assert_called_once_with("candil")

    assert created.status_code == 200
    assert created.json()["id"] == "asset-2"
    service.create_asset.assert_called_once()


def test_intersections_history_and_maintenance_endpoints(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_potential_intersections.return_value = {
        "type": "FeatureCollection",
        "features": [],
    }
    service.get_asset_history.return_value = [{"accion": "inspeccion"}]
    service.add_maintenance_log.return_value = {"id": "m-1", "infraestructura_id": "asset-1"}
    asset_id = "11111111-1111-1111-1111-111111111111"

    with patch(
        "app.api.v1.endpoints.infrastructure.get_infrastructure_service",
        return_value=service,
    ):
        intersections = client.get("/api/v1/infrastructure/potential-intersections", headers=auth_headers)
        history = client.get(f"/api/v1/infrastructure/assets/{asset_id}/history", headers=auth_headers)
        maintenance = client.post(
            "/api/v1/infrastructure/maintenance",
            headers=auth_headers,
            json={"infraestructura_id": asset_id, "tipo_trabajo": "limpieza", "nuevo_estado": "bueno"},
        )

    assert intersections.status_code == 200
    assert intersections.json()["type"] == "FeatureCollection"
    assert history.status_code == 200
    assert history.json()[0]["accion"] == "inspeccion"
    assert maintenance.status_code == 200
    assert maintenance.json()["id"] == "m-1"


def test_export_asset_pdf_and_summary_pdf_return_downloadable_bytes(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_asset_history.return_value = [{"evento": "creado"}]
    service.db.client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": "11111111-1111-1111-1111-111111111111",
        "nombre": "Canal Principal",
    }

    pdf_service = MagicMock()
    pdf_service.create_asset_ficha_pdf.return_value = BytesIO(b"asset-pdf")
    pdf_service.create_emergency_report.return_value = BytesIO(b"summary-pdf")

    with patch(
        "app.api.v1.endpoints.infrastructure.get_infrastructure_service",
        return_value=service,
    ), patch("app.api.v1.endpoints.infrastructure.get_pdf_service", return_value=pdf_service):
        asset_pdf = client.get(
            "/api/v1/infrastructure/assets/11111111-1111-1111-1111-111111111111/export-pdf",
            headers=auth_headers,
        )
        summary_pdf = client.get("/api/v1/infrastructure/export-pdf", headers=auth_headers)

    assert asset_pdf.status_code == 200
    assert asset_pdf.content == b"asset-pdf"
    assert asset_pdf.headers["content-type"] == "application/pdf"
    assert "ficha_activo" in asset_pdf.headers["content-disposition"]

    assert summary_pdf.status_code == 200
    assert summary_pdf.content == b"summary-pdf"
    assert summary_pdf.headers["content-type"] == "application/pdf"
