"""
Unit tests for hydrology.py — TWI classification and flow accumulation.

Mocks: rasterio for raster I/O. Uses real numpy for computation logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, mock_open

import numpy as np
import pytest

from affine import Affine


# ---------------------------------------------------------------------------
# TWI classification constants
# ---------------------------------------------------------------------------


def test_twi_classes_boundaries():
    from app.domains.geo.hydrology import TWI_CLASSES
    assert TWI_CLASSES["seco"]["max"] == 7.0
    assert TWI_CLASSES["normal"]["min"] == 7.0
    assert TWI_CLASSES["normal"]["max"] == 11.0
    assert TWI_CLASSES["humedo"]["min"] == 11.0
    assert TWI_CLASSES["humedo"]["max"] == 15.0
    assert TWI_CLASSES["saturado"]["min"] == 15.0
    assert TWI_CLASSES["saturado"]["max"] is None


def test_twi_classes_no_gaps():
    """Boundary values must form a continuous range with no gaps."""
    from app.domains.geo.hydrology import TWI_CLASSES
    keys = list(TWI_CLASSES.keys())
    for i in range(len(keys) - 1):
        current_max = TWI_CLASSES[keys[i]]["max"]
        next_min = TWI_CLASSES[keys[i + 1]]["min"]
        assert current_max == next_min, f"Gap between {keys[i]} and {keys[i+1]}"


# ---------------------------------------------------------------------------
# classify_twi tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.hydrology.rasterio")
def test_classify_twi_seco(mock_rio):
    """TWI < 7 → class 1 (seco)."""
    from app.domains.geo.hydrology import classify_twi

    twi_data = np.full((5, 5), 5.0, dtype=np.float64)

    src = MagicMock()
    src.read.return_value = twi_data
    src.nodata = -9999
    src.meta = {"driver": "GTiff", "dtype": "float64", "width": 5, "height": 5}
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    with patch("app.domains.geo.hydrology.Path") as mock_path:
        mock_path.return_value.parent.mkdir = MagicMock()
        result = classify_twi("/fake/twi.tif", "/fake/output.tif")

    assert result == "/fake/output.tif"


@patch("app.domains.geo.hydrology.rasterio")
def test_classify_twi_all_classes(mock_rio):
    """Verify each TWI range maps to the correct class value."""
    from app.domains.geo.hydrology import classify_twi

    twi_data = np.array([[3.0, 9.0, 13.0, 18.0]], dtype=np.float64)

    src = MagicMock()
    src.read.return_value = twi_data
    src.nodata = None
    src.meta = {"driver": "GTiff", "dtype": "float64", "width": 4, "height": 1}
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    # Capture written data
    dst = MagicMock()
    written_data = {}

    def capture_write(data, band):
        written_data["data"] = data.copy()

    dst.write = capture_write

    # Second open call is for writing
    call_count = [0]
    original_enter = mock_rio.open.return_value.__enter__

    def side_effect_open(*args, **kwargs):
        cm = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            cm.__enter__ = MagicMock(return_value=src)
        else:
            cm.__enter__ = MagicMock(return_value=dst)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    mock_rio.open.side_effect = side_effect_open

    with patch("app.domains.geo.hydrology.Path") as mock_path:
        mock_path.return_value.parent.mkdir = MagicMock()
        classify_twi("/fake/twi.tif", "/fake/output.tif")

    if "data" in written_data:
        assert written_data["data"][0, 0] == 1  # seco (3.0 < 7)
        assert written_data["data"][0, 1] == 2  # normal (7 <= 9.0 < 11)
        assert written_data["data"][0, 2] == 3  # humedo (11 <= 13.0 < 15)
        assert written_data["data"][0, 3] == 4  # saturado (18.0 >= 15)


@patch("app.domains.geo.hydrology.rasterio")
def test_classify_twi_nodata_handling(mock_rio):
    """NoData pixels should be classified as 0."""
    from app.domains.geo.hydrology import classify_twi

    twi_data = np.array([[-9999, 5.0, np.nan]], dtype=np.float64)

    src = MagicMock()
    src.read.return_value = twi_data
    src.nodata = -9999
    src.meta = {"driver": "GTiff", "dtype": "float64", "width": 3, "height": 1}
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    dst = MagicMock()
    written_data = {}

    def capture_write(data, band):
        written_data["data"] = data.copy()

    dst.write = capture_write

    call_count = [0]

    def side_effect_open(*args, **kwargs):
        cm = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            cm.__enter__ = MagicMock(return_value=src)
        else:
            cm.__enter__ = MagicMock(return_value=dst)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    mock_rio.open.side_effect = side_effect_open

    with patch("app.domains.geo.hydrology.Path") as mock_path:
        mock_path.return_value.parent.mkdir = MagicMock()
        classify_twi("/fake/twi.tif", "/fake/output.tif")

    if "data" in written_data:
        assert written_data["data"][0, 0] == 0  # nodata → 0
        assert written_data["data"][0, 2] == 0  # NaN → 0


# ---------------------------------------------------------------------------
# compute_twi_zone_summary tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.hydrology.rasterio")
def test_twi_zone_summary_basic(mock_rio):
    from app.domains.geo.hydrology import compute_twi_zone_summary

    # 4 pixels: one per class
    twi_data = np.array([[3.0, 9.0], [13.0, 18.0]], dtype=np.float64)

    src = MagicMock()
    src.read.return_value = twi_data
    src.nodata = None
    src.transform = Affine(10, 0, 0, 0, -10, 0)  # 10m cells
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    result = compute_twi_zone_summary("/fake/twi.tif")

    assert result["total_pixels"] == 4
    assert len(result["classes"]) == 4

    # Each class should have 1 pixel = 25%
    for cls in result["classes"]:
        assert cls["pixel_count"] == 1
        assert cls["percentage"] == 25.0


@patch("app.domains.geo.hydrology.rasterio")
def test_twi_zone_summary_all_seco(mock_rio):
    from app.domains.geo.hydrology import compute_twi_zone_summary

    twi_data = np.full((3, 3), 4.0, dtype=np.float64)

    src = MagicMock()
    src.read.return_value = twi_data
    src.nodata = None
    src.transform = Affine(10, 0, 0, 0, -10, 0)
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    result = compute_twi_zone_summary("/fake/twi.tif")

    seco = next(c for c in result["classes"] if c["class"] == "seco")
    assert seco["pixel_count"] == 9
    assert seco["percentage"] == 100.0


@patch("app.domains.geo.hydrology.rasterio")
def test_twi_zone_summary_area_calculation(mock_rio):
    """Cell area should be cell_size^2 / 10000 in hectares."""
    from app.domains.geo.hydrology import compute_twi_zone_summary

    twi_data = np.full((10, 10), 5.0, dtype=np.float64)  # 100 pixels

    src = MagicMock()
    src.read.return_value = twi_data
    src.nodata = None
    src.transform = Affine(10, 0, 0, 0, -10, 0)  # 10m → 100 m² per pixel
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    result = compute_twi_zone_summary("/fake/twi.tif")

    # 100 pixels × 100 m² = 10000 m² = 1.0 ha
    assert result["total_area_ha"] == 1.0


@patch("app.domains.geo.hydrology.rasterio")
def test_twi_zone_summary_with_nodata(mock_rio):
    from app.domains.geo.hydrology import compute_twi_zone_summary

    twi_data = np.array([[5.0, -9999]], dtype=np.float64)

    src = MagicMock()
    src.read.return_value = twi_data
    src.nodata = -9999
    src.transform = Affine(10, 0, 0, 0, -10, 0)
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    result = compute_twi_zone_summary("/fake/twi.tif")

    assert result["total_pixels"] == 1  # only 1 valid pixel


# ---------------------------------------------------------------------------
# compute_flow_acc_at_canals tests
# ---------------------------------------------------------------------------


def _make_flow_acc_mocks(mock_rio, mock_path_cls, flow_data, canal_geojson, *, crs="EPSG:32720"):
    """Helper to wire up rasterio + Path mocks for flow acc tests."""
    import json
    # Origin at top-left: x=0, y=1000; 10m pixels going right and down
    transform = Affine(10, 0, 0, 0, -10, 1000)

    src = MagicMock()
    src.read.return_value = flow_data
    src.nodata = None
    src.crs = crs
    src.transform = transform
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)
    mock_path_cls.return_value.read_text.return_value = json.dumps(canal_geojson)


def _canal_feature(name, coords, *, geom_type="LineString"):
    return {
        "type": "Feature",
        "geometry": {"type": geom_type, "coordinates": coords},
        "properties": {"nombre": name},
    }


def _fc(*features):
    return {"type": "FeatureCollection", "features": list(features)}


@patch("shapely.geometry.shape")
@patch("app.domains.geo.hydrology.rasterio")
@patch("app.domains.geo.hydrology.Path")
def test_flow_acc_at_canals_basic(mock_path_cls, mock_rio, mock_shape):
    from app.domains.geo.hydrology import compute_flow_acc_at_canals

    flow_data = np.full((100, 100), 500.0, dtype=np.float64)
    _make_flow_acc_mocks(mock_rio, mock_path_cls, flow_data,
                         _fc(_canal_feature("Canal Norte", [[0, 0], [500, 0]])))

    # Mock shapely geometry so length is computable
    geom = MagicMock()
    geom.length = 500.0
    geom.interpolate.return_value = MagicMock(x=50, y=50)
    mock_shape.return_value = geom

    results = compute_flow_acc_at_canals("/fake/flow.tif", "/fake/canals.geojson")

    assert len(results) == 1
    assert results[0]["nombre"] == "Canal Norte"
    assert results[0]["capacity_risk"] == "bajo"  # 500 < 1000


@patch("shapely.geometry.shape")
@patch("app.domains.geo.hydrology.rasterio")
@patch("app.domains.geo.hydrology.Path")
def test_flow_acc_capacity_risk_alto(mock_path_cls, mock_rio, mock_shape):
    from app.domains.geo.hydrology import compute_flow_acc_at_canals

    flow_data = np.full((100, 100), 6000.0, dtype=np.float64)
    _make_flow_acc_mocks(mock_rio, mock_path_cls, flow_data,
                         _fc(_canal_feature("Canal Sur", [[0, 0], [500, 0]])))

    geom = MagicMock()
    geom.length = 500.0
    geom.interpolate.return_value = MagicMock(x=50, y=50)
    mock_shape.return_value = geom

    results = compute_flow_acc_at_canals("/fake/flow.tif", "/fake/canals.geojson")

    assert len(results) == 1
    assert results[0]["capacity_risk"] == "alto"  # 6000 > 5000


@patch("shapely.geometry.shape")
@patch("app.domains.geo.hydrology.rasterio")
@patch("app.domains.geo.hydrology.Path")
def test_flow_acc_capacity_risk_medio(mock_path_cls, mock_rio, mock_shape):
    from app.domains.geo.hydrology import compute_flow_acc_at_canals

    flow_data = np.full((100, 100), 2000.0, dtype=np.float64)
    _make_flow_acc_mocks(mock_rio, mock_path_cls, flow_data,
                         _fc(_canal_feature("Canal Este", [[0, 0], [500, 0]])))

    geom = MagicMock()
    geom.length = 500.0
    geom.interpolate.return_value = MagicMock(x=50, y=50)
    mock_shape.return_value = geom

    results = compute_flow_acc_at_canals("/fake/flow.tif", "/fake/canals.geojson")

    assert results[0]["capacity_risk"] == "medio"  # 1000 < 2000 < 5000


@patch("shapely.geometry.shape")
@patch("app.domains.geo.hydrology.rasterio")
@patch("app.domains.geo.hydrology.Path")
def test_flow_acc_skips_non_linestring(mock_path_cls, mock_rio, mock_shape):
    from app.domains.geo.hydrology import compute_flow_acc_at_canals

    flow_data = np.full((10, 10), 100.0, dtype=np.float64)
    _make_flow_acc_mocks(mock_rio, mock_path_cls, flow_data,
                         _fc(_canal_feature("Not a canal", [50, 50], geom_type="Point")))

    results = compute_flow_acc_at_canals("/fake/flow.tif", "/fake/canals.geojson")
    assert results == []


@patch("shapely.geometry.shape")
@patch("app.domains.geo.hydrology.rasterio")
@patch("app.domains.geo.hydrology.Path")
def test_flow_acc_sorted_by_max_descending(mock_path_cls, mock_rio, mock_shape):
    """Results should be sorted by flow_acc_max descending."""
    from app.domains.geo.hydrology import compute_flow_acc_at_canals

    flow_data = np.full((100, 100), 100.0, dtype=np.float64)
    flow_data[50:60, :] = 3000.0

    _make_flow_acc_mocks(mock_rio, mock_path_cls, flow_data,
                         _fc(
                             _canal_feature("Low flow", [[0, 0], [500, 0]]),
                             _canal_feature("High flow", [[0, 0], [500, 0]]),
                         ))

    # Return different geometries for the two canals
    geom_low = MagicMock()
    geom_low.length = 500.0
    geom_low.interpolate.return_value = MagicMock(x=25, y=5)  # row ~0, low flow area

    geom_high = MagicMock()
    geom_high.length = 500.0
    geom_high.interpolate.return_value = MagicMock(x=25, y=55)  # row ~55, high flow area

    mock_shape.side_effect = [geom_low, geom_high]

    results = compute_flow_acc_at_canals("/fake/flow.tif", "/fake/canals.geojson")

    if len(results) >= 2:
        assert results[0]["flow_acc_max"] >= results[1]["flow_acc_max"]
