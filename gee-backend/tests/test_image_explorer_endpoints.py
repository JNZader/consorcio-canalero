from unittest.mock import MagicMock, patch


def test_image_explorer_returns_503_when_gee_unavailable(client):
    with patch(
        "app.api.v1.endpoints.image_explorer.get_image_explorer",
        side_effect=RuntimeError("gee down"),
    ):
        response = client.get("/api/v1/images/sentinel1?target_date=2026-03-01")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "GEE_UNAVAILABLE"


def test_image_explorer_maps_not_found_and_unexpected_errors(client):
    explorer = MagicMock()
    explorer.get_sentinel2_image.return_value = {"error": "No scenes found"}

    with patch(
        "app.api.v1.endpoints.image_explorer.get_image_explorer", return_value=explorer
    ):
        not_found = client.get("/api/v1/images/sentinel2?target_date=2026-03-01")

    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "SENTINEL2_NOT_FOUND"

    explorer.get_flood_comparison.side_effect = RuntimeError(
        "Traceback /home/user/token should be sanitized"
    )
    with patch(
        "app.api.v1.endpoints.image_explorer.get_image_explorer", return_value=explorer
    ):
        comparison_error = client.get(
            "/api/v1/images/compare?flood_date=2026-03-01&normal_date=2026-02-20"
        )

    assert comparison_error.status_code == 500
    assert comparison_error.json()["error"]["code"] == "IMAGE_COMPARE_ERROR"


def test_historic_flood_tiles_fallback_and_invalid_id(client):
    missing = client.get("/api/v1/images/historic-floods/unknown")
    assert missing.status_code == 404

    explorer = MagicMock()
    explorer.get_sentinel2_image.return_value = {"error": "no optical images"}
    explorer.get_sentinel1_image.return_value = {"tile_url": "https://tiles/sar/{z}/{x}/{y}"}

    with patch(
        "app.api.v1.endpoints.image_explorer.get_image_explorer", return_value=explorer
    ):
        response = client.get("/api/v1/images/historic-floods/feb_2017")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tile_url"] == "https://tiles/sar/{z}/{x}/{y}"
    assert payload["flood_info"]["id"] == "feb_2017"
