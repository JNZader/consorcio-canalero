from io import BytesIO
from unittest.mock import MagicMock, patch


def test_reuniones_list_and_get_not_found(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_reuniones.return_value = [
        {"id": "r1", "titulo": "Comision marzo", "estado": "planificada"}
    ]
    service.get_reunion_detalle.return_value = {}

    with patch(
        "app.api.v1.endpoints.management.get_management_service", return_value=service
    ):
        list_response = client.get("/api/v1/management/reuniones", headers=auth_headers)
        detail_response = client.get(
            "/api/v1/management/reuniones/7e5f1d31-a89a-43ad-85f9-8cc6d97f909e",
            headers=auth_headers,
        )

    assert list_response.status_code == 200
    assert list_response.json()[0]["titulo"] == "Comision marzo"
    assert detail_response.status_code == 404


def test_add_seguimiento_injects_usuario_gestion(client, mock_auth, auth_headers):
    service = MagicMock()
    service.add_seguimiento.return_value = {"id": "seg-1"}

    with patch(
        "app.api.v1.endpoints.management.get_management_service", return_value=service
    ):
        response = client.post(
            "/api/v1/management/seguimiento",
            headers=auth_headers,
            json={
                "entidad_tipo": "reporte",
                "entidad_id": "7e5f1d31-a89a-43ad-85f9-8cc6d97f909e",
                "estado_nuevo": "en_revision",
                "comentario": "Se asigna cuadrilla",
            },
        )

    assert response.status_code == 200
    payload = service.add_seguimiento.call_args.args[0]
    assert payload["usuario_gestion"] == "test-user-id"


def test_seguimiento_history_rejects_invalid_entity_type(client, mock_auth, auth_headers):
    response = client.get(
        "/api/v1/management/seguimiento/otro/7e5f1d31-a89a-43ad-85f9-8cc6d97f909e",
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Tipo de entidad invalido"


def test_update_reunion_validates_payload_and_not_found(client, mock_auth, auth_headers):
    service = MagicMock()
    service.update_reunion.return_value = {}

    with patch(
        "app.api.v1.endpoints.management.get_management_service", return_value=service
    ):
        empty_payload = client.patch(
            "/api/v1/management/reuniones/7e5f1d31-a89a-43ad-85f9-8cc6d97f909e",
            headers=auth_headers,
            json={},
        )
        missing_reunion = client.patch(
            "/api/v1/management/reuniones/7e5f1d31-a89a-43ad-85f9-8cc6d97f909e",
            headers=auth_headers,
            json={"titulo": "Reunion actualizada"},
        )

    assert empty_payload.status_code == 400
    assert missing_reunion.status_code == 404


def test_add_agenda_item_maps_referencias(client, mock_auth, auth_headers):
    service = MagicMock()
    service.add_agenda_item.return_value = {"id": "item-1"}

    with patch(
        "app.api.v1.endpoints.management.get_management_service", return_value=service
    ):
        response = client.post(
            "/api/v1/management/reuniones/7e5f1d31-a89a-43ad-85f9-8cc6d97f909e/agenda",
            headers=auth_headers,
            json={
                "item": {
                    "titulo": "Tema 1",
                    "descripcion": "Revisar limpieza",
                    "orden": 1,
                },
                "referencias": [
                    {
                        "tipo_referencia": "reporte",
                        "referencia_id": "2d721f30-f245-4e56-afec-6363733ecf1e",
                        "descripcion": "Desborde Ruta 9",
                    }
                ],
            },
        )

    assert response.status_code == 200
    args = service.add_agenda_item.call_args.args
    assert args[1]["titulo"] == "Tema 1"
    assert args[2][0]["tipo_referencia"] == "reporte"


def test_export_agenda_pdf_handles_not_found_and_success(client, mock_auth, auth_headers):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.single.return_value = query
    query.execute.return_value = MagicMock(data=None)

    service = MagicMock()
    service.db.client.table.return_value = query

    pdf_service = MagicMock()
    pdf_service.create_agenda_pdf.return_value = BytesIO(b"%PDF-1.4 test")

    with (
        patch("app.api.v1.endpoints.management.get_management_service", return_value=service),
        patch("app.api.v1.endpoints.management.get_pdf_service", return_value=pdf_service),
    ):
        missing_response = client.get(
            "/api/v1/management/reuniones/7e5f1d31-a89a-43ad-85f9-8cc6d97f909e/export-pdf",
            headers=auth_headers,
        )

    assert missing_response.status_code == 404

    query.execute.return_value = MagicMock(
        data={"id": "r1", "titulo": "Comision marzo", "fecha_reunion": "2026-03-09"}
    )
    service.get_agenda_detalle.return_value = [{"id": "i1", "titulo": "Tema"}]

    with (
        patch("app.api.v1.endpoints.management.get_management_service", return_value=service),
        patch("app.api.v1.endpoints.management.get_pdf_service", return_value=pdf_service),
    ):
        ok_response = client.get(
            "/api/v1/management/reuniones/7e5f1d31-a89a-43ad-85f9-8cc6d97f909e/export-pdf",
            headers=auth_headers,
        )

    assert ok_response.status_code == 200
    assert ok_response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=agenda_reunion_" in ok_response.headers[
        "content-disposition"
    ]
