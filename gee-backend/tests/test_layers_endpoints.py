from unittest.mock import MagicMock, patch


def test_get_layer_not_found_returns_404(client):
    service = MagicMock()
    service.get_layer.return_value = None

    with patch("app.api.v1.endpoints.layers.get_supabase_service", return_value=service):
        response = client.get("/api/v1/layers/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Capa no encontrada"


def test_upload_layer_rejects_invalid_json(client, mock_auth, auth_headers):
    with patch("app.api.v1.endpoints.layers.get_supabase_service", return_value=MagicMock()):
        response = client.post(
            "/api/v1/layers/upload",
            headers=auth_headers,
            files={"file": ("layer.geojson", b"not-json", "application/json")},
            data={"nombre": "Capa Test"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "El archivo no es JSON valido"


def test_upload_layer_validates_geojson_type_and_structure(client, mock_auth, auth_headers):
    with patch("app.api.v1.endpoints.layers.get_supabase_service", return_value=MagicMock()):
        missing_type = client.post(
            "/api/v1/layers/upload",
            headers=auth_headers,
            files={"file": ("layer.geojson", b"{}", "application/json")},
            data={"nombre": "Sin tipo"},
        )

        invalid_type = client.post(
            "/api/v1/layers/upload",
            headers=auth_headers,
            files={
                "file": (
                    "layer.geojson",
                    b'{"type":"InvalidType"}',
                    "application/json",
                )
            },
            data={"nombre": "Tipo invalido"},
        )

        bad_feature_collection = client.post(
            "/api/v1/layers/upload",
            headers=auth_headers,
            files={
                "file": (
                    "layer.geojson",
                    b'{"type":"FeatureCollection","features":"not-list"}',
                    "application/json",
                )
            },
            data={"nombre": "Feature collection invalida"},
        )

    assert missing_type.status_code == 400
    assert "falta campo 'type'" in missing_type.json()["detail"]
    assert invalid_type.status_code == 400
    assert "Tipo GeoJSON invalido" in invalid_type.json()["detail"]
    assert bad_feature_collection.status_code == 400
    assert "debe tener array 'features'" in bad_feature_collection.json()["detail"]


def test_upload_layer_sanitizes_filename_and_creates_layer(client, mock_auth, auth_headers):
    service = MagicMock()
    service.upload_geojson.return_value = "https://storage.example.com/layer.geojson"
    service.create_layer.return_value = {"id": "layer-1", "nombre": "Capa Nueva"}

    content = b'{"type":"FeatureCollection","features":[]}'
    with patch("app.api.v1.endpoints.layers.get_supabase_service", return_value=service):
        response = client.post(
            "/api/v1/layers/upload",
            headers=auth_headers,
            files={"file": ("layer.geojson", content, "application/json")},
            data={
                "nombre": "Zona / Norte 2026!!",
                "descripcion": "desc",
                "tipo": "custom",
                "color": "#00aa00",
                "fillOpacity": "0.25",
            },
        )

    assert response.status_code == 200
    service.upload_geojson.assert_called_once_with("zona__norte_2026.geojson", content)
    created_data = service.create_layer.call_args.args[0]
    assert created_data["created_by"] == "test-user-id"
    assert created_data["geojson_url"].startswith("https://storage.example.com")


def test_update_and_delete_layer_validate_existence(client, mock_auth, auth_headers):
    service = MagicMock()
    service.get_layer.side_effect = [None, {"id": "layer-1"}]

    with patch("app.api.v1.endpoints.layers.get_supabase_service", return_value=service):
        missing_update = client.put(
            "/api/v1/layers/layer-404",
            headers=auth_headers,
            json={"nombre": "nuevo"},
        )
        delete_ok = client.request(
            "DELETE",
            "/api/v1/layers/layer-1",
            headers=auth_headers,
            json={},
        )

    assert missing_update.status_code == 404
    assert delete_ok.status_code == 204
    service.delete_layer.assert_called_once_with("layer-1")


def test_reorder_layers_returns_count(client, mock_auth, auth_headers):
    service = MagicMock()

    with patch("app.api.v1.endpoints.layers.get_supabase_service", return_value=service):
        response = client.post(
            "/api/v1/layers/reorder",
            headers=auth_headers,
            json={"layers": [{"id": "a", "orden": 1}, {"id": "b", "orden": 2}]},
        )

    assert response.status_code == 200
    assert response.json()["count"] == 2
    service.reorder_layers.assert_called_once()
