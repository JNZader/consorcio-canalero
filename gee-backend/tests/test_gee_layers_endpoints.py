from unittest.mock import MagicMock, patch


def test_list_gee_layers_returns_cached_json(client):
    with patch("app.api.v1.endpoints.gee_layers.get_available_layers", return_value=[{"id": "zona"}]):
        response = client.get("/api/v1/gee/layers")

    assert response.status_code == 200
    assert response.json() == [{"id": "zona"}]


def test_get_gee_layer_success(client):
    with patch(
        "app.api.v1.endpoints.gee_layers.get_layer_geojson",
        return_value={"type": "FeatureCollection", "features": []},
    ), patch("app.api.v1.endpoints.gee_layers._gee_initialized", True):
        response = client.get("/api/v1/gee/layers/zona")

    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"


def test_get_gee_layer_not_found_maps_value_error(client):
    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_layer_geojson",
        side_effect=ValueError("missing"),
    ):
        response = client.get("/api/v1/gee/layers/inexistente")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LAYER_NOT_FOUND"


def test_sentinel2_tiles_maps_not_found_and_init_errors(client):
    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", False), patch(
        "app.api.v1.endpoints.gee_layers.initialize_gee",
        side_effect=RuntimeError("gee down"),
    ):
        init_response = client.get("/api/v1/gee/layers/tiles/sentinel2?start_date=2026-01-01&end_date=2026-01-31")

    assert init_response.status_code == 503

    gee_service = MagicMock()
    gee_service.get_sentinel2_tiles.return_value = {"error": "No images"}
    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_gee_service", return_value=gee_service
    ):
        missing_response = client.get(
            "/api/v1/gee/layers/tiles/sentinel2?start_date=2026-01-01&end_date=2026-01-31"
        )

    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "SENTINEL2_NOT_FOUND"


def test_consorcios_and_caminos_endpoints(client):
    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_consorcios_camineros",
        return_value=[{"codigo": "CC1"}],
    ):
        response = client.get("/api/v1/gee/layers/caminos/consorcios")

    assert response.status_code == 200
    assert response.json()["total"] == 1

    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_caminos_by_consorcio",
        return_value={"type": "FeatureCollection", "features": []},
    ):
        not_found = client.get("/api/v1/gee/layers/caminos/consorcio/CC404")

    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "CONSORCIO_NOT_FOUND"


def test_caminos_coloreados_and_stats_success(client):
    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_caminos_con_colores",
        return_value={"type": "FeatureCollection", "features": []},
    ), patch(
        "app.api.v1.endpoints.gee_layers.get_estadisticas_consorcios",
        return_value={"totales": {"tramos": 1}},
    ):
        colored = client.get("/api/v1/gee/layers/caminos/coloreados")
        stats = client.get("/api/v1/gee/layers/caminos/estadisticas")

    assert colored.status_code == 200
    assert stats.status_code == 200


def test_get_caminos_por_nombre_and_generic_layer_error_paths(client):
    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_caminos_by_consorcio_nombre",
        return_value={"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}}]},
    ):
        by_name = client.get("/api/v1/gee/layers/caminos/por-nombre?nombre=CONSORCIO NORTE")

    assert by_name.status_code == 200
    assert by_name.json()["type"] == "FeatureCollection"

    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_layer_geojson",
        side_effect=RuntimeError("gee exploded"),
    ):
        failed = client.get("/api/v1/gee/layers/zona")

    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "GEE_LAYER_ERROR"


def test_gee_layers_additional_error_branches(client):
    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_consorcios_camineros",
        side_effect=RuntimeError("service down"),
    ):
        consorcios_error = client.get("/api/v1/gee/layers/caminos/consorcios")

    assert consorcios_error.status_code == 500
    assert consorcios_error.json()["error"]["code"] == "GEE_CONSORCIOS_ERROR"

    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_caminos_con_colores",
        side_effect=RuntimeError("colors failed"),
    ):
        colored_error = client.get("/api/v1/gee/layers/caminos/coloreados")

    assert colored_error.status_code == 500
    assert colored_error.json()["error"]["code"] == "GEE_CAMINOS_ERROR"

    gee_service = MagicMock()
    gee_service.get_sentinel2_tiles.side_effect = RuntimeError("broken")
    with patch("app.api.v1.endpoints.gee_layers._gee_initialized", True), patch(
        "app.api.v1.endpoints.gee_layers.get_gee_service", return_value=gee_service
    ):
        tiles_error = client.get(
            "/api/v1/gee/layers/tiles/sentinel2?start_date=2026-01-01&end_date=2026-01-31"
        )

    assert tiles_error.status_code == 500
    assert tiles_error.json()["error"]["code"] == "GEE_TILES_ERROR"
