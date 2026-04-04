"""
Unit tests for zonal_stats.py — raster statistics for vector geometries.

Mocks: rasterstats, rasterio, pyproj. No real rasters needed.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# rasterstats may not be installed — inject a mock module so the source
# can be imported without ImportError.
if "rasterstats" not in sys.modules:
    _mock_rasterstats = MagicMock()
    sys.modules["rasterstats"] = _mock_rasterstats


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_supported_stats():
    from app.domains.geo.zonal_stats import SUPPORTED_STATS
    assert "mean" in SUPPORTED_STATS
    assert "min" in SUPPORTED_STATS
    assert "max" in SUPPORTED_STATS
    assert "std" in SUPPORTED_STATS
    assert "count" in SUPPORTED_STATS


# ---------------------------------------------------------------------------
# _reproject_geom tests
# ---------------------------------------------------------------------------


def test_reproject_same_crs_returns_same_geom():
    """When src_crs == dst_crs, geometry is returned unchanged."""
    from app.domains.geo.zonal_stats import _reproject_geom

    geom = MagicMock()
    result = _reproject_geom(geom, "EPSG:4326", "EPSG:4326")
    assert result is geom


@patch("app.domains.geo.zonal_stats.Transformer")
@patch("app.domains.geo.zonal_stats.shapely_transform")
def test_reproject_different_crs(mock_transform, mock_transformer_cls):
    """When CRS differ, reprojection should be applied."""
    from app.domains.geo.zonal_stats import _reproject_geom

    geom = MagicMock()
    transformer = MagicMock()
    mock_transformer_cls.from_crs.return_value = transformer
    mock_transform.return_value = MagicMock(name="reprojected")

    result = _reproject_geom(geom, "EPSG:4326", "EPSG:32720")

    mock_transformer_cls.from_crs.assert_called_once_with("EPSG:4326", "EPSG:32720", always_xy=True)
    mock_transform.assert_called_once_with(transformer.transform, geom)
    assert result is mock_transform.return_value


# ---------------------------------------------------------------------------
# compute_zonal_stats tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.zonal_stats._zonal_stats")
@patch("app.domains.geo.zonal_stats.rasterio")
@patch("app.domains.geo.zonal_stats.Path")
def test_compute_zonal_stats_empty_input(mock_path, mock_rio, mock_zs):
    from app.domains.geo.zonal_stats import compute_zonal_stats

    result = compute_zonal_stats([], "/fake/raster.tif")
    assert result == []
    mock_zs.assert_not_called()


@patch("app.domains.geo.zonal_stats._zonal_stats")
@patch("app.domains.geo.zonal_stats.rasterio")
@patch("app.domains.geo.zonal_stats.Path")
def test_compute_zonal_stats_file_not_found(mock_path, mock_rio, mock_zs):
    from app.domains.geo.zonal_stats import compute_zonal_stats

    mock_path.return_value.exists.return_value = False

    with pytest.raises(FileNotFoundError, match="Raster not found"):
        compute_zonal_stats(
            [{"id": "1", "geometry": "POINT(0 0)"}],
            "/fake/missing.tif",
        )


@patch("app.domains.geo.zonal_stats._zonal_stats")
@patch("app.domains.geo.zonal_stats.rasterio")
@patch("app.domains.geo.zonal_stats.Path")
@patch("app.domains.geo.zonal_stats._reproject_geom")
def test_compute_zonal_stats_with_wkt(mock_reproj, mock_path, mock_rio, mock_zs):
    from app.domains.geo.zonal_stats import compute_zonal_stats

    mock_path.return_value.exists.return_value = True

    src = MagicMock()
    src.crs = "EPSG:32720"
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    reproj_geom = MagicMock()
    reproj_geom.__geo_interface__ = {"type": "Polygon", "coordinates": []}
    mock_reproj.return_value = reproj_geom

    mock_zs.return_value = [{"mean": 123.45678, "count": 50}]

    result = compute_zonal_stats(
        [{"id": "zone-1", "name": "Test Zone", "geometry": "POLYGON((0 0, 1 0, 1 1, 0 0))"}],
        "/fake/raster.tif",
        stats=["mean", "count"],
    )

    assert len(result) == 1
    assert result[0]["id"] == "zone-1"
    assert result[0]["name"] == "Test Zone"
    assert result[0]["mean"] == 123.4568  # rounded to 4 decimals
    assert result[0]["count"] == 50  # int stays int


@patch("app.domains.geo.zonal_stats._zonal_stats")
@patch("app.domains.geo.zonal_stats.rasterio")
@patch("app.domains.geo.zonal_stats.Path")
@patch("app.domains.geo.zonal_stats._reproject_geom")
def test_compute_zonal_stats_with_geojson_dict(mock_reproj, mock_path, mock_rio, mock_zs):
    """Geometry can be a GeoJSON dict, not just WKT string."""
    from app.domains.geo.zonal_stats import compute_zonal_stats

    mock_path.return_value.exists.return_value = True

    src = MagicMock()
    src.crs = "EPSG:4326"
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    reproj_geom = MagicMock()
    reproj_geom.__geo_interface__ = {"type": "Polygon", "coordinates": []}
    mock_reproj.return_value = reproj_geom

    mock_zs.return_value = [{"min": 0.0, "max": 100.0}]

    geom_dict = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}

    result = compute_zonal_stats(
        [{"id": "z1", "geometry": geom_dict}],
        "/fake/raster.tif",
    )

    assert len(result) == 1
    assert result[0]["min"] == 0.0
    assert result[0]["max"] == 100.0


@patch("app.domains.geo.zonal_stats._zonal_stats")
@patch("app.domains.geo.zonal_stats.rasterio")
@patch("app.domains.geo.zonal_stats.Path")
@patch("app.domains.geo.zonal_stats._reproject_geom")
def test_compute_zonal_stats_default_stats(mock_reproj, mock_path, mock_rio, mock_zs):
    """When stats=None, all SUPPORTED_STATS should be used."""
    from app.domains.geo.zonal_stats import compute_zonal_stats, SUPPORTED_STATS

    mock_path.return_value.exists.return_value = True

    src = MagicMock()
    src.crs = "EPSG:4326"
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    reproj_geom = MagicMock()
    reproj_geom.__geo_interface__ = {"type": "Polygon", "coordinates": []}
    mock_reproj.return_value = reproj_geom

    mock_zs.return_value = [{"mean": 5.0}]

    compute_zonal_stats(
        [{"id": "z1", "geometry": "POINT(0 0)"}],
        "/fake/raster.tif",
        stats=None,
    )

    call_kwargs = mock_zs.call_args
    assert call_kwargs.kwargs.get("stats") == SUPPORTED_STATS or call_kwargs[1].get("stats") == SUPPORTED_STATS


@patch("app.domains.geo.zonal_stats._zonal_stats")
@patch("app.domains.geo.zonal_stats.rasterio")
@patch("app.domains.geo.zonal_stats.Path")
@patch("app.domains.geo.zonal_stats._reproject_geom")
def test_compute_zonal_stats_multiple_geometries(mock_reproj, mock_path, mock_rio, mock_zs):
    from app.domains.geo.zonal_stats import compute_zonal_stats

    mock_path.return_value.exists.return_value = True

    src = MagicMock()
    src.crs = "EPSG:4326"
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    reproj_geom = MagicMock()
    reproj_geom.__geo_interface__ = {"type": "Polygon", "coordinates": []}
    mock_reproj.return_value = reproj_geom

    mock_zs.return_value = [
        {"mean": 10.0, "count": 100},
        {"mean": 20.0, "count": 200},
    ]

    result = compute_zonal_stats(
        [
            {"id": "z1", "name": "A", "geometry": "POINT(0 0)"},
            {"id": "z2", "name": "B", "geometry": "POINT(1 1)"},
        ],
        "/fake/raster.tif",
    )

    assert len(result) == 2
    assert result[0]["id"] == "z1"
    assert result[1]["id"] == "z2"
    assert result[0]["mean"] == 10.0
    assert result[1]["mean"] == 20.0


# ---------------------------------------------------------------------------
# compute_stats_for_zones tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.zonal_stats.compute_zonal_stats")
def test_compute_stats_for_zones_wrapper(mock_czs):
    from app.domains.geo.zonal_stats import compute_stats_for_zones

    mock_czs.return_value = [{"id": "1", "mean": 5.0}]

    zone_wkts = [
        ("uuid-1", "POLYGON((0 0, 1 0, 1 1, 0 0))", "Zone A"),
        ("uuid-2", "POLYGON((2 2, 3 2, 3 3, 2 2))", None),
    ]

    result = compute_stats_for_zones(zone_wkts, "/fake/raster.tif")

    call_args = mock_czs.call_args
    geoms = call_args[0][0]
    assert len(geoms) == 2
    assert geoms[0]["id"] == "uuid-1"
    assert geoms[0]["name"] == "Zone A"
    assert geoms[1]["name"] is None


@patch("app.domains.geo.zonal_stats.compute_zonal_stats")
def test_compute_stats_for_zones_custom_stats(mock_czs):
    from app.domains.geo.zonal_stats import compute_stats_for_zones

    mock_czs.return_value = []

    compute_stats_for_zones(
        [("id1", "POINT(0 0)", "Z")],
        "/fake/raster.tif",
        stats=["mean", "std"],
    )

    call_args = mock_czs.call_args
    assert call_args[0][2] == ["mean", "std"]
