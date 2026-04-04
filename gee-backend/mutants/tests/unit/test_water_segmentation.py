"""
Unit tests for water_segmentation.py — pluggable segmentation strategies.

Mocks: torch, smp, rasterio, scipy. No model weights or real rasters needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, mock_open

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# NDWIStrategy tests
# ---------------------------------------------------------------------------


def test_ndwi_strategy_name():
    from app.domains.geo.ml.water_segmentation import NDWIStrategy
    assert NDWIStrategy().name == "ndwi"


def test_ndwi_strategy_no_model_required():
    from app.domains.geo.ml.water_segmentation import NDWIStrategy
    assert NDWIStrategy().requires_model is False


def test_ndwi_basic_computation():
    """NDWI = (green - nir) / (green + nir). Pixels above threshold → water."""
    from app.domains.geo.ml.water_segmentation import NDWIStrategy

    # green=0.6, nir=0.2 → NDWI = 0.5 → above default threshold 0.1
    # Use 20x20 so morphological ops don't erode too much of the interior
    green = np.full((20, 20), 0.6, dtype=np.float32)
    nir = np.full((20, 20), 0.2, dtype=np.float32)

    strategy = NDWIStrategy(threshold=0.1, min_area_px=1)
    mask = strategy.segment({"green": green, "nir": nir}, {})

    assert mask.dtype == np.uint8
    # Interior pixels should all be water (edges may be eroded by morphological ops)
    assert np.sum(mask == 1) > 100  # most of the 400 pixels are water


def test_ndwi_below_threshold():
    """When NDWI is below threshold, all pixels should be 0."""
    from app.domains.geo.ml.water_segmentation import NDWIStrategy

    # green=0.3, nir=0.5 → NDWI = -0.25 → below threshold
    green = np.full((10, 10), 0.3, dtype=np.float32)
    nir = np.full((10, 10), 0.5, dtype=np.float32)

    strategy = NDWIStrategy(threshold=0.1, min_area_px=1)
    mask = strategy.segment({"green": green, "nir": nir}, {})

    assert np.all(mask == 0)


def test_ndwi_zero_denominator():
    """When green + nir = 0, should not raise (division by zero guarded)."""
    from app.domains.geo.ml.water_segmentation import NDWIStrategy

    green = np.zeros((5, 5), dtype=np.float32)
    nir = np.zeros((5, 5), dtype=np.float32)

    strategy = NDWIStrategy(threshold=0.1, min_area_px=1)
    mask = strategy.segment({"green": green, "nir": nir}, {})

    assert mask.shape == (5, 5)
    # 0 / 1e-10 ≈ 0 → below threshold
    assert np.all(mask == 0)


def test_ndwi_removes_small_components():
    """Small connected components below min_area_px should be removed."""
    from app.domains.geo.ml.water_segmentation import NDWIStrategy

    green = np.full((40, 40), 0.3, dtype=np.float32)
    nir = np.full((40, 40), 0.5, dtype=np.float32)
    # Create a single water pixel (isolated, not surviving morphological ops)
    green[20, 20] = 0.8
    nir[20, 20] = 0.1

    strategy = NDWIStrategy(threshold=0.1, min_area_px=5)  # min 5 px
    mask = strategy.segment({"green": green, "nir": nir}, {})

    # A single isolated pixel gets removed by binary_opening (3x3 kernel)
    # plus the min_area_px filter
    assert np.sum(mask) == 0


def test_ndwi_keeps_large_components():
    """Large connected components above min_area_px should be kept."""
    from app.domains.geo.ml.water_segmentation import NDWIStrategy

    # Make everything water
    green = np.full((20, 20), 0.8, dtype=np.float32)
    nir = np.full((20, 20), 0.1, dtype=np.float32)

    strategy = NDWIStrategy(threshold=0.1, min_area_px=10)
    mask = strategy.segment({"green": green, "nir": nir}, {})

    # 400 pixels → above min_area_px=10 → kept
    assert np.sum(mask == 1) > 0


def test_ndwi_custom_threshold():
    """Custom threshold should change classification boundary."""
    from app.domains.geo.ml.water_segmentation import NDWIStrategy

    # NDWI ≈ 0.33
    green = np.full((20, 20), 0.6, dtype=np.float32)
    nir = np.full((20, 20), 0.3, dtype=np.float32)

    low_thresh = NDWIStrategy(threshold=0.2, min_area_px=1)
    high_thresh = NDWIStrategy(threshold=0.5, min_area_px=1)

    mask_low = low_thresh.segment({"green": green, "nir": nir}, {})
    mask_high = high_thresh.segment({"green": green, "nir": nir}, {})

    assert np.sum(mask_low == 1) > 100  # 0.33 > 0.2 → most pixels water
    assert np.all(mask_high == 0)        # 0.33 < 0.5 → no water


# ---------------------------------------------------------------------------
# UNetStrategy tests
# ---------------------------------------------------------------------------


def test_unet_strategy_name():
    from app.domains.geo.ml.water_segmentation import UNetStrategy
    assert UNetStrategy().name == "unet"


def test_unet_requires_model():
    from app.domains.geo.ml.water_segmentation import UNetStrategy
    assert UNetStrategy().requires_model is True


@patch("app.domains.geo.ml.water_segmentation.Path")
def test_unet_model_not_available(mock_path):
    from app.domains.geo.ml.water_segmentation import UNetStrategy

    mock_path.return_value.exists.return_value = False
    strategy = UNetStrategy(model_path="/fake/path.pth")
    assert strategy.model_available is False


@patch("app.domains.geo.ml.water_segmentation.Path")
def test_unet_model_available(mock_path):
    from app.domains.geo.ml.water_segmentation import UNetStrategy

    mock_path.return_value.exists.return_value = True
    strategy = UNetStrategy(model_path="/fake/path.pth")
    assert strategy.model_available is True


@patch("app.domains.geo.ml.water_segmentation.Path")
def test_unet_fallback_to_ndwi_missing_bands(mock_path):
    """U-Net needs 4 bands. With fewer, it falls back to NDWI."""
    mock_path.return_value.exists.return_value = False

    from app.domains.geo.ml.water_segmentation import UNetStrategy

    # Mock torch and smp
    mock_torch = MagicMock()
    mock_smp = MagicMock()

    with patch.dict("sys.modules", {"torch": mock_torch, "segmentation_models_pytorch": mock_smp}):
        strategy = UNetStrategy(model_path="/fake/path.pth")
        strategy._model = MagicMock()  # skip loading

        # Only 2 bands — should fallback to NDWI
        green = np.full((10, 10), 0.6, dtype=np.float32)
        nir = np.full((10, 10), 0.2, dtype=np.float32)

        mask = strategy.segment({"green": green, "nir": nir}, {})
        assert mask.shape == (10, 10)
        assert mask.dtype == np.uint8


# ---------------------------------------------------------------------------
# get_strategy factory tests
# ---------------------------------------------------------------------------


def test_get_strategy_ndwi():
    from app.domains.geo.ml.water_segmentation import get_strategy, NDWIStrategy
    strategy = get_strategy("ndwi")
    assert isinstance(strategy, NDWIStrategy)


def test_get_strategy_unet():
    from app.domains.geo.ml.water_segmentation import get_strategy, UNetStrategy
    strategy = get_strategy("unet")
    assert isinstance(strategy, UNetStrategy)


def test_get_strategy_unknown_raises():
    from app.domains.geo.ml.water_segmentation import get_strategy
    with pytest.raises(ValueError, match="Unknown strategy"):
        get_strategy("random_forest")


# ---------------------------------------------------------------------------
# vectorize_water_mask tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.ml.water_segmentation.rasterio")
@patch("app.domains.geo.ml.water_segmentation.rasterio_shapes")
@patch("app.domains.geo.ml.water_segmentation.shape")
def test_vectorize_water_mask_basic(mock_shape, mock_shapes, mock_rio):
    from app.domains.geo.ml.water_segmentation import vectorize_water_mask

    # Mock rasterio open context
    src = MagicMock()
    src.read.return_value = np.array([[1, 0], [0, 1]], dtype=np.uint8)
    src.transform = MagicMock()
    src.crs = "EPSG:32720"
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    # rasterio_shapes returns (geom_dict, value) pairs
    geom1 = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    mock_shapes.return_value = [(geom1, 1)]

    # shapely shape().area
    mock_shape.return_value.area = 1234.56

    features = vectorize_water_mask("/fake/mask.tif")

    assert len(features) == 1
    assert features[0]["type"] == "Feature"
    assert features[0]["properties"]["class"] == "water"
    assert features[0]["properties"]["area_m2"] == 1234.56


@patch("app.domains.geo.ml.water_segmentation.rasterio")
@patch("app.domains.geo.ml.water_segmentation.rasterio_shapes")
def test_vectorize_water_mask_no_water(mock_shapes, mock_rio):
    from app.domains.geo.ml.water_segmentation import vectorize_water_mask

    src = MagicMock()
    src.read.return_value = np.zeros((10, 10), dtype=np.uint8)
    src.transform = MagicMock()
    src.crs = "EPSG:32720"
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    mock_shapes.return_value = []

    features = vectorize_water_mask("/fake/mask.tif")
    assert features == []


@patch("app.domains.geo.ml.water_segmentation.rasterio")
@patch("app.domains.geo.ml.water_segmentation.rasterio_shapes")
@patch("app.domains.geo.ml.water_segmentation.shape")
def test_vectorize_filters_non_water_values(mock_shape, mock_shapes, mock_rio):
    """Only value==1 polygons should be included."""
    from app.domains.geo.ml.water_segmentation import vectorize_water_mask

    src = MagicMock()
    src.read.return_value = np.array([[1, 0]], dtype=np.uint8)
    src.transform = MagicMock()
    src.crs = "EPSG:32720"
    mock_rio.open.return_value.__enter__ = MagicMock(return_value=src)
    mock_rio.open.return_value.__exit__ = MagicMock(return_value=False)

    geom = {"type": "Polygon", "coordinates": []}
    mock_shapes.return_value = [(geom, 0), (geom, 1)]
    mock_shape.return_value.area = 100.0

    features = vectorize_water_mask("/fake/mask.tif")
    assert len(features) == 1
