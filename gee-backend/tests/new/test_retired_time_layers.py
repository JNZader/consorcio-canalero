"""Orphan JRC / Sentinel-2 time layers must 404 before they touch Earth Engine."""

from __future__ import annotations

import pytest

from app.core.exceptions import NotFoundError
from app.domains.geo.router import (
    get_jrc_occurrence,
    get_jrc_year,
    get_sentinel2_annual,
    get_sentinel2_monthly,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        get_jrc_occurrence,
        get_jrc_year,
        get_sentinel2_annual,
        get_sentinel2_monthly,
    ],
)
async def test_retired_time_layer_does_not_call_gee(endpoint) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        await endpoint(year=2015)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "TIME_LAYER_RETIRED"
