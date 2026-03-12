from unittest.mock import MagicMock
import pytest

import app.services.gee_service as gee_service


def test_initialize_gee_uses_key_file_when_present(monkeypatch):
    monkeypatch.setattr(gee_service, "_gee_initialized", False)
    monkeypatch.setattr(gee_service, "_gee_init_error", None)
    monkeypatch.setattr(gee_service.settings, "gee_key_file_path", "/tmp/key.json")
    monkeypatch.setattr(gee_service.settings, "gee_service_account_key", None)

    path_mock = MagicMock()
    path_mock.exists.return_value = True
    monkeypatch.setattr(gee_service, "Path", lambda _p: path_mock)
    monkeypatch.setattr(gee_service.ee, "ServiceAccountCredentials", MagicMock(return_value="creds"))
    initialize_mock = MagicMock()
    monkeypatch.setattr(gee_service.ee, "Initialize", initialize_mock)

    gee_service.initialize_gee()

    initialize_mock.assert_called_once_with("creds", project=gee_service.settings.gee_project_id)
    assert gee_service._gee_initialized is True


def test_initialize_gee_uses_json_key_when_provided(monkeypatch):
    monkeypatch.setattr(gee_service, "_gee_initialized", False)
    monkeypatch.setattr(gee_service, "_gee_init_error", None)
    monkeypatch.setattr(gee_service.settings, "gee_key_file_path", None)
    monkeypatch.setattr(
        gee_service.settings,
        "gee_service_account_key",
        '{"client_email": "svc@example.com"}',
    )
    monkeypatch.setattr(gee_service.ee, "ServiceAccountCredentials", MagicMock(return_value="creds"))
    initialize_mock = MagicMock()
    monkeypatch.setattr(gee_service.ee, "Initialize", initialize_mock)

    gee_service.initialize_gee()

    initialize_mock.assert_called_once_with("creds", project=gee_service.settings.gee_project_id)
    assert gee_service._gee_initialized is True


def test_initialize_gee_raises_cached_error(monkeypatch):
    monkeypatch.setattr(gee_service, "_gee_initialized", False)
    monkeypatch.setattr(gee_service, "_gee_init_error", "boom")

    with pytest.raises(RuntimeError):
        gee_service.initialize_gee()


def test_get_layer_geojson_returns_feature_collection(monkeypatch):
    monkeypatch.setattr(gee_service, "_gee_initialized", True)

    fc = MagicMock()
    fc.getInfo.return_value = {"type": "FeatureCollection", "features": [{"id": 1}]}
    monkeypatch.setattr(gee_service.ee, "FeatureCollection", lambda _path: fc)

    data = gee_service.get_layer_geojson("zona")

    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1


def test_get_layer_geojson_rejects_unknown_layer(monkeypatch):
    monkeypatch.setattr(gee_service, "_gee_initialized", True)

    try:
        gee_service.get_layer_geojson("inexistente")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "inexistente" in str(exc)


def test_get_consorcios_camineros_groups_and_sums_lengths(monkeypatch):
    monkeypatch.setattr(gee_service, "_gee_initialized", True)

    features = {
        "features": [
            {"properties": {"ccn": "C.C. A", "ccc": "CC1", "lzn": "2.5"}},
            {"properties": {"ccn": "C.C. A", "ccc": "CC1", "lzn": 1}},
            {"properties": {"ccn": "C.C. B", "ccc": "CC2", "lzn": "bad"}},
        ]
    }
    caminos_fc = MagicMock()
    caminos_fc.getInfo.return_value = features
    monkeypatch.setattr(gee_service.ee, "FeatureCollection", lambda _path: caminos_fc)

    consorcios = gee_service.get_consorcios_camineros()

    assert consorcios[0]["nombre"] == "C.C. A"
    assert consorcios[0]["tramos"] == 2
    assert consorcios[0]["longitud_total_km"] == 3.5


def test_get_caminos_con_colores_adds_metadata_and_color_properties(monkeypatch):
    monkeypatch.setattr(gee_service, "_gee_initialized", True)

    features = {
        "features": [
            {"properties": {"ccn": "C.C. A", "ccc": "CC1", "lzn": 2}},
            {"properties": {"ccn": "C.C. B", "ccc": "CC2", "lzn": 3}},
        ]
    }
    caminos_fc = MagicMock()
    caminos_fc.getInfo.return_value = features
    monkeypatch.setattr(gee_service.ee, "FeatureCollection", lambda _path: caminos_fc)

    result = gee_service.get_caminos_con_colores()

    assert result["metadata"]["total_tramos"] == 2
    assert result["metadata"]["total_consorcios"] == 2
    assert result["metadata"]["total_km"] == 5.0
    assert all("color" in f["properties"] for f in result["features"])


def test_get_estadisticas_consorcios_aggregates_hierarchy_and_surface(monkeypatch):
    monkeypatch.setattr(gee_service, "_gee_initialized", True)

    features = {
        "features": [
            {
                "properties": {
                    "ccn": "C.C. A",
                    "ccc": "CC1",
                    "lzn": 4,
                    "hct": "Primaria",
                    "rst": "Ripio",
                }
            },
            {
                "properties": {
                    "ccn": "C.C. A",
                    "ccc": "CC1",
                    "lzn": 1,
                    "hct": "Secundaria",
                    "rst": "Tierra",
                }
            },
        ]
    }
    caminos_fc = MagicMock()
    caminos_fc.getInfo.return_value = features
    monkeypatch.setattr(gee_service.ee, "FeatureCollection", lambda _path: caminos_fc)

    result = gee_service.get_estadisticas_consorcios()

    assert result["totales"]["consorcios"] == 1
    assert result["totales"]["tramos"] == 2
    assert result["totales"]["longitud_km"] == 5.0
    consorcio = result["consorcios"][0]
    assert consorcio["por_jerarquia"]["Primaria"]["tramos"] == 1
    assert consorcio["por_superficie"]["Ripio"]["km"] == 4.0


def test_get_caminos_by_consorcio_uses_uppercase_fallback(monkeypatch):
    monkeypatch.setattr(gee_service, "_gee_initialized", True)

    filtered_primary = MagicMock()
    filtered_primary.getInfo.return_value = {"features": []}
    filtered_fallback = MagicMock()
    filtered_fallback.getInfo.return_value = {"features": [{"id": 1}]}

    caminos = MagicMock()
    caminos.filter.side_effect = [filtered_primary, filtered_fallback]
    monkeypatch.setattr(gee_service.ee, "FeatureCollection", lambda _path: caminos)
    monkeypatch.setattr(gee_service.ee.Filter, "eq", lambda *_args: object())

    result = gee_service.get_caminos_by_consorcio("cc269")

    assert len(result["features"]) == 1


def test_get_available_layers_includes_expected_ids():
    layers = gee_service.get_available_layers()

    assert layers[0]["id"] == "zona"
    assert {layer["id"] for layer in layers} >= {"candil", "ml", "noroeste", "norte", "caminos"}
