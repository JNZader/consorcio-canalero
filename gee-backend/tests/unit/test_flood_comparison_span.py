"""Fusion comparison span gate in build_flood_analysis_result."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.domains.geo.gee_tasks_support import build_flood_analysis_result


def test_fusion_builds_comparison_for_next_day_span() -> None:
    explorer = MagicMock()
    explorer.get_sentinel2_image.return_value = {"tile_url": "https://ee/opt"}
    explorer.get_sentinel1_image.return_value = {"tile_url": "https://ee/sar"}
    explorer.get_flood_comparison.return_value = {
        "flood_date": "2024-01-01",
        "normal_date": "2024-01-02",
    }

    result = build_flood_analysis_result(
        explorer=explorer,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
        method="fusion",
    )

    explorer.get_flood_comparison.assert_called_once()
    assert "comparison" in result


def test_fusion_skips_comparison_when_dates_equal() -> None:
    explorer = MagicMock()
    explorer.get_sentinel2_image.return_value = {"tile_url": "https://ee/opt"}
    explorer.get_sentinel1_image.return_value = {"tile_url": "https://ee/sar"}

    result = build_flood_analysis_result(
        explorer=explorer,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
        method="fusion",
    )

    explorer.get_flood_comparison.assert_not_called()
    assert "comparison" not in result
