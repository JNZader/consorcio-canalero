from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.endpoints import gee_analysis


@pytest.mark.asyncio
async def test_get_advanced_index_tiles_success():
    explorer = MagicMock()
    explorer.get_sentinel2_image.return_value = {"tile_url": "https://tiles/{z}/{x}/{y}"}

    with patch("app.api.v1.endpoints.gee_analysis.get_image_explorer", return_value=explorer):
        result = await gee_analysis.get_advanced_index_tiles(
            target_date=__import__("datetime").date(2026, 1, 15),
            index_type="ndvi",
            max_cloud=20,
            user=MagicMock(),
        )

    assert "tile_url" in result


@pytest.mark.asyncio
async def test_get_advanced_index_tiles_maps_not_found():
    explorer = MagicMock()
    explorer.get_sentinel2_image.return_value = {"error": "No data"}

    with patch("app.api.v1.endpoints.gee_analysis.get_image_explorer", return_value=explorer):
        with pytest.raises(Exception) as exc:
            await gee_analysis.get_advanced_index_tiles(
                target_date=__import__("datetime").date(2026, 1, 15),
                index_type="ndwi",
                max_cloud=30,
                user=MagicMock(),
            )

    assert getattr(exc.value, "code", None) == "INDEX_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_advanced_index_tiles_maps_unexpected_error():
    explorer = MagicMock()
    explorer.get_sentinel2_image.side_effect = RuntimeError("boom")

    with patch("app.api.v1.endpoints.gee_analysis.get_image_explorer", return_value=explorer):
        with pytest.raises(Exception) as exc:
            await gee_analysis.get_advanced_index_tiles(
                target_date=__import__("datetime").date(2026, 1, 15),
                index_type="mndwi",
                max_cloud=30,
                user=MagicMock(),
            )

    assert getattr(exc.value, "code", None) == "GEE_INDEX_ERROR"


@pytest.mark.asyncio
async def test_list_visualizations_returns_explorer_options():
    explorer = MagicMock()
    explorer.get_available_visualizations.return_value = [{"id": "ndvi", "description": "NDVI"}]

    with patch("app.api.v1.endpoints.gee_analysis.get_image_explorer", return_value=explorer):
        result = await gee_analysis.list_visualizations(user=MagicMock())

    assert result[0]["id"] == "ndvi"
