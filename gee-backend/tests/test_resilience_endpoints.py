from unittest.mock import MagicMock, patch


def test_visualizations_does_not_require_gee(client):
    with patch(
        "app.api.v1.endpoints.image_explorer.get_image_explorer",
        side_effect=AssertionError("get_image_explorer should not be used"),
    ):
        response = client.get("/api/v1/images/visualizations")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_cors_header_present_on_error_response(client):
    with patch(
        "app.api.v1.endpoints.image_explorer.get_image_explorer",
        side_effect=RuntimeError("gee down"),
    ):
        response = client.get(
            "/api/v1/images/sentinel2?target_date=2026-01-01",
            headers={"Origin": "http://localhost:4321"},
        )

    assert response.status_code == 500
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:4321"
    )


def test_infrastructure_service_assets_without_gee_init():
    mock_query = MagicMock()
    mock_query.execute.return_value = MagicMock(data=[])
    mock_query.eq.return_value = mock_query

    mock_db = MagicMock()
    mock_db.client.table.return_value.select.return_value = mock_query

    with (
        patch(
            "app.services.infrastructure_service.get_supabase_service",
            return_value=mock_db,
        ),
        patch(
            "app.services.infrastructure_service.initialize_gee",
            side_effect=AssertionError("initialize_gee should not run"),
        ),
    ):
        from app.services.infrastructure_service import InfrastructureService

        service = InfrastructureService()
        data = service.get_all_assets()

    assert data == []
