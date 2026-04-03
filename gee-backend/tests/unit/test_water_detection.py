"""
Unit tests for water_detection.py — NDWI-based water detection via GEE.

All Earth Engine calls are mocked. No GEE credentials needed.

Note: ee and gee_service are imported INSIDE detect_water_from_gee(),
so we patch them in sys.modules before calling the function.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixture: inject mock ee into sys.modules
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_ee():
    """Put a mock 'ee' module in sys.modules so `import ee` inside the
    function picks it up. Also mock gee_service._ensure_initialized."""
    ee = MagicMock()
    ee.Geometry.side_effect = lambda g: g
    ee.Filter.lt.return_value = MagicMock()
    ee.Kernel.circle.return_value = MagicMock()

    mean_r = MagicMock()
    mean_r.combine.return_value = mean_r
    ee.Reducer.mean.return_value = mean_r
    ee.Reducer.stdDev.return_value = MagicMock()
    ee.Reducer.minMax.return_value = MagicMock()
    ee.Reducer.count.return_value = MagicMock()
    ee.Reducer.sum.return_value = MagicMock()

    old_ee = sys.modules.get("ee")
    sys.modules["ee"] = ee
    with patch("app.domains.geo.gee_service._ensure_initialized"):
        yield ee
    if old_ee is not None:
        sys.modules["ee"] = old_ee
    else:
        sys.modules.pop("ee", None)


def _make_collection(mock_ee, s2_image):
    """Build a chainable ImageCollection mock returning the given s2 image."""
    coll = MagicMock()
    coll.filterBounds.return_value = coll
    coll.filterDate.return_value = coll
    coll.filter.return_value = coll
    coll.sort.return_value = coll
    coll.first.return_value = s2_image
    coll.size.return_value = MagicMock()
    coll.size.return_value.getInfo.return_value = 5
    mock_ee.ImageCollection.return_value = coll
    return coll


def _setup_pixel_counts(mock_ee, total: int, valid: int):
    """Setup ee.Image.constant mock to return pixel count mocks."""
    total_img = MagicMock()
    total_img.rename.return_value = total_img
    total_img.reduceRegion.return_value = MagicMock()
    total_img.reduceRegion.return_value.getInfo.return_value = {"count": total}
    valid_img = MagicMock()
    valid_img.reduceRegion.return_value = MagicMock()
    valid_img.reduceRegion.return_value.getInfo.return_value = {"count": valid}
    total_img.updateMask.return_value = valid_img
    mock_ee.Image.constant.return_value = total_img


def _setup_s2_image(mock_ee, *, image_date="2024-01-15", cloud_pct=5.0):
    """Create an s2 image mock with SCL, band mocks, and date."""
    s2 = MagicMock(name="s2")

    scl = MagicMock()
    scl.eq.return_value = MagicMock()

    band = MagicMock()
    band.divide.return_value = band
    band.updateMask.return_value = band
    band.subtract.return_value = band
    band.add.return_value = band
    band.rename.return_value = band

    water_mask = MagicMock()
    water_mask.focalMode.return_value = MagicMock(updateMask=MagicMock(return_value=MagicMock()))
    water_mask.And.return_value = MagicMock()
    band.gte.return_value = water_mask

    def _select(name):
        if name == "SCL":
            return scl
        return MagicMock(divide=MagicMock(return_value=band))

    s2.select.side_effect = _select

    # SCL mask
    scl_mask = MagicMock()
    mock_ee.Image.return_value = scl_mask
    scl_mask.Or.return_value = scl_mask

    # Date
    date_mock = MagicMock()
    date_mock.format.return_value = MagicMock()
    date_mock.format.return_value.getInfo.return_value = image_date
    mock_ee.Date.return_value = date_mock

    s2.get.return_value = MagicMock()
    s2.get.return_value.getInfo.return_value = cloud_pct

    return s2, band, water_mask


def _setup_area_mocks(mock_ee, *, water=50000, wet=30000, total=500000,
                      ndwi_mean=-0.1, ndwi_std=0.15, ndwi_min=-0.5, ndwi_max=0.6):
    """Setup pixel area reduction mocks."""
    pixel_area = MagicMock()
    mock_ee.Image.pixelArea.return_value = pixel_area
    pixel_area.updateMask.return_value = pixel_area

    reduce_results = [
        {"NDWI": water},
        {"NDWI": wet},
        {"area": total},
        {"NDWI_mean": ndwi_mean, "NDWI_stdDev": ndwi_std,
         "NDWI_min": ndwi_min, "NDWI_max": ndwi_max},
    ]

    reduce_mock = MagicMock()
    reduce_mock.getInfo.side_effect = reduce_results

    mul_result = MagicMock()
    mul_result.reduceRegion.return_value = reduce_mock
    pixel_area.reduceRegion = MagicMock(return_value=reduce_mock)

    return reduce_mock, mul_result


GEOM = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


def test_ndwi_water_threshold_is_positive():
    from app.domains.geo.water_detection import NDWI_WATER_THRESHOLD
    assert NDWI_WATER_THRESHOLD > 0


def test_ndwi_wet_threshold_below_water_threshold():
    from app.domains.geo.water_detection import NDWI_WATER_THRESHOLD, NDWI_WET_THRESHOLD
    assert NDWI_WET_THRESHOLD < NDWI_WATER_THRESHOLD


def test_scl_valid_values_excludes_clouds():
    from app.domains.geo.water_detection import SCL_VALID_VALUES
    for cloud_val in [3, 8, 9, 10]:
        assert cloud_val not in SCL_VALID_VALUES


def test_scl_valid_values_includes_water():
    from app.domains.geo.water_detection import SCL_VALID_VALUES
    assert 6 in SCL_VALID_VALUES


def test_min_valid_pixel_fraction_is_reasonable():
    from app.domains.geo.water_detection import MIN_VALID_PIXEL_FRACTION
    assert 0 < MIN_VALID_PIXEL_FRACTION < 1


# ---------------------------------------------------------------------------
# detect_water_from_gee tests
# ---------------------------------------------------------------------------


def test_detect_water_no_imagery(mock_ee):
    """When the ImageCollection returns None for first(), return no_imagery."""
    from app.domains.geo.water_detection import detect_water_from_gee

    _make_collection(mock_ee, None)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["status"] == "no_imagery"
    assert "date_range" in result


def test_detect_water_insufficient_clear_pixels(mock_ee):
    """When valid pixel fraction is below MIN_VALID_PIXEL_FRACTION, return early."""
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, _, _ = _setup_s2_image(mock_ee, cloud_pct=95.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=50)  # 5% < 10%

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["status"] == "insufficient_clear_pixels"
    assert result["valid_pixel_pct"] == 5.0


def test_detect_water_success(mock_ee):
    """Full success path — produces area stats and NDWI metrics."""
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=5.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=800)  # 80%

    reduce_mock, mul_result = _setup_area_mocks(mock_ee)
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["status"] == "success"
    assert "area" in result
    assert "ndwi" in result
    assert "thresholds" in result
    assert result["thresholds"]["water"] == 0.1
    assert result["thresholds"]["wet"] == -0.05


def test_detect_water_cloud_warning(mock_ee):
    """valid_fraction < 0.50 should produce a cloud warning."""
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=40.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=300)  # 30%

    reduce_mock = MagicMock()
    reduce_mock.getInfo.return_value = {
        "NDWI": 0, "area": 100_000,
        "NDWI_mean": 0, "NDWI_stdDev": 0,
        "NDWI_min": 0, "NDWI_max": 0,
    }

    pixel_area = MagicMock()
    mock_ee.Image.pixelArea.return_value = pixel_area
    pixel_area.updateMask.return_value = pixel_area
    pixel_area.reduceRegion = MagicMock(return_value=reduce_mock)

    mul_result = MagicMock()
    mul_result.reduceRegion.return_value = reduce_mock

    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["status"] == "success"
    assert result["cloud_masking"]["warning"] is not None
    assert "30%" in result["cloud_masking"]["warning"]


def test_detect_water_search_window_uses_days_window(mock_ee):
    """Verify the search window is computed from days_window param."""
    from app.domains.geo.water_detection import detect_water_from_gee

    _make_collection(mock_ee, None)

    result = detect_water_from_gee(GEOM, "2024-06-15", days_window=30)

    assert result["status"] == "no_imagery"
    assert result["date_range"]["start"] == "2024-05-16"
    assert result["date_range"]["end"] == "2024-07-15"


# ---------------------------------------------------------------------------
# detect_water_multi_date tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.water_detection.detect_water_from_gee")
def test_multi_date_all_success(mock_detect):
    from app.domains.geo.water_detection import detect_water_multi_date

    mock_detect.side_effect = [
        {"status": "success", "image_date": "2024-01-01", "area": {"water_ha": 10, "water_pct": 5}},
        {"status": "success", "image_date": "2024-02-01", "area": {"water_ha": 20, "water_pct": 10}},
    ]

    result = detect_water_multi_date(GEOM, ["2024-01-01", "2024-02-01"])

    assert result["dates_requested"] == 2
    assert result["dates_successful"] == 2
    assert result["change"]["trend"] == "increasing"
    assert result["change"]["water_ha_change"] == 10


@patch("app.domains.geo.water_detection.detect_water_from_gee")
def test_multi_date_with_error(mock_detect):
    from app.domains.geo.water_detection import detect_water_multi_date

    mock_detect.side_effect = [
        {"status": "success", "image_date": "2024-01-01", "area": {"water_ha": 10, "water_pct": 5}},
        Exception("GEE quota exceeded"),
    ]

    result = detect_water_multi_date(GEOM, ["2024-01-01", "2024-02-01"])

    assert result["dates_successful"] == 1
    assert result["results"][1]["status"] == "error"
    assert result["change"] is None


@patch("app.domains.geo.water_detection.detect_water_from_gee")
def test_multi_date_stable_trend(mock_detect):
    from app.domains.geo.water_detection import detect_water_multi_date

    mock_detect.side_effect = [
        {"status": "success", "image_date": "2024-01-01", "area": {"water_ha": 10, "water_pct": 5.0}},
        {"status": "success", "image_date": "2024-02-01", "area": {"water_ha": 10.2, "water_pct": 5.1}},
    ]

    result = detect_water_multi_date(GEOM, ["2024-01-01", "2024-02-01"])
    assert result["change"]["trend"] == "stable"


@patch("app.domains.geo.water_detection.detect_water_from_gee")
def test_multi_date_decreasing_trend(mock_detect):
    from app.domains.geo.water_detection import detect_water_multi_date

    mock_detect.side_effect = [
        {"status": "success", "image_date": "2024-01-01", "area": {"water_ha": 20, "water_pct": 15}},
        {"status": "success", "image_date": "2024-02-01", "area": {"water_ha": 5, "water_pct": 3}},
    ]

    result = detect_water_multi_date(GEOM, ["2024-01-01", "2024-02-01"])
    assert result["change"]["trend"] == "decreasing"


@patch("app.domains.geo.water_detection.detect_water_from_gee")
def test_multi_date_no_successful(mock_detect):
    from app.domains.geo.water_detection import detect_water_multi_date

    mock_detect.side_effect = [{"status": "no_imagery", "message": "nope"}]

    result = detect_water_multi_date(GEOM, ["2024-01-01"])

    assert result["dates_successful"] == 0
    assert result["change"] is None


# ---------------------------------------------------------------------------
# Mutation-killing tests — verify EXACT numeric values and boundaries
# ---------------------------------------------------------------------------


def test_min_valid_pixel_fraction_exact_value():
    """Kill mutation: MIN_VALID_PIXEL_FRACTION = 0.10 mutated to 0.15."""
    from app.domains.geo.water_detection import MIN_VALID_PIXEL_FRACTION
    assert MIN_VALID_PIXEL_FRACTION == pytest.approx(0.10)


def test_valid_fraction_boundary_at_exactly_threshold(mock_ee):
    """Kill mutation: valid_fraction < MIN_VALID_PIXEL_FRACTION (< vs <=).

    At exactly 0.10 (10%), the check should PASS (not insufficient).
    If mutated to <=, this would wrongly return insufficient.
    """
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=5.0)
    _make_collection(mock_ee, s2)
    # 100 / 1000 = 0.10 exactly = MIN_VALID_PIXEL_FRACTION
    _setup_pixel_counts(mock_ee, total=1000, valid=100)

    reduce_mock, mul_result = _setup_area_mocks(mock_ee)
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")
    # At exactly the threshold, it should NOT be insufficient
    assert result["status"] == "success"


def test_valid_fraction_just_below_threshold(mock_ee):
    """Just below 0.10 — should return insufficient_clear_pixels."""
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, _, _ = _setup_s2_image(mock_ee, cloud_pct=90.0)
    _make_collection(mock_ee, s2)
    # 99/1000 = 0.099 < 0.10
    _setup_pixel_counts(mock_ee, total=1000, valid=99)

    result = detect_water_from_gee(GEOM, "2024-01-15")
    assert result["status"] == "insufficient_clear_pixels"


def test_valid_fraction_zero_total_pixels(mock_ee):
    """Kill mutation: total_px_val > 0 vs >= 0 — zero total should not divide."""
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, _, _ = _setup_s2_image(mock_ee, cloud_pct=90.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=0, valid=0)

    result = detect_water_from_gee(GEOM, "2024-01-15")
    # valid_fraction = 0, which is < 0.10, so insufficient
    assert result["status"] == "insufficient_clear_pixels"


def test_area_division_not_multiplication(mock_ee):
    """Kill mutation: / 10_000 → * 10_000.

    With known area values, verify total_ha = area / 10000.
    water=50000 m² → 5.0 ha, wet=30000 m² → 3.0 ha, total=500000 m² → 50.0 ha.
    """
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=5.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=800)

    reduce_mock, mul_result = _setup_area_mocks(
        mock_ee, water=50_000, wet=30_000, total=500_000,
    )
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["status"] == "success"
    # total_ha = 500000 / 10000 = 50.0  (NOT 500000 * 10000)
    assert result["area"]["total_ha"] == pytest.approx(50.0)
    # water_ha = 50000 / 10000 = 5.0
    assert result["area"]["water_ha"] == pytest.approx(5.0)
    # wet_ha = 30000 / 10000 = 3.0
    assert result["area"]["wet_ha"] == pytest.approx(3.0)


def test_dry_ha_is_total_minus_water_minus_wet(mock_ee):
    """Kill mutation: total - water - wet vs total + water - wet.

    dry_ha = 50 - 5 - 3 = 42.0 (NOT 50 + 5 - 3 = 52.0)
    """
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=5.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=800)

    reduce_mock, mul_result = _setup_area_mocks(
        mock_ee, water=50_000, wet=30_000, total=500_000,
    )
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    # dry_ha = 50.0 - 5.0 - 3.0 = 42.0
    assert result["area"]["dry_ha"] == pytest.approx(42.0)


def test_water_pct_formula(mock_ee):
    """Kill mutation: water_pct = (water_ha / total_ha) * 100.

    water_pct = (5.0 / 50.0) * 100 = 10.0
    """
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=5.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=800)

    reduce_mock, mul_result = _setup_area_mocks(
        mock_ee, water=50_000, wet=30_000, total=500_000,
    )
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["area"]["water_pct"] == pytest.approx(10.0)
    assert result["area"]["wet_pct"] == pytest.approx(6.0)


def test_water_pct_zero_total_guard(mock_ee):
    """Kill mutation: total_ha > 0 vs >= 0.

    When total_ha is 0, water_pct should be 0 (no division by zero).
    """
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=5.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=800)

    reduce_mock, mul_result = _setup_area_mocks(
        mock_ee, water=0, wet=0, total=0,
    )
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["area"]["water_pct"] == 0
    assert result["area"]["wet_pct"] == 0


def test_cloud_masking_applied_is_true(mock_ee):
    """Kill mutation: cloud_masking 'applied': True → False."""
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=5.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=800)

    reduce_mock, mul_result = _setup_area_mocks(mock_ee)
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["cloud_masking"]["applied"] is True


def test_valid_pixel_pct_is_fraction_times_100(mock_ee):
    """Kill mutation: valid_fraction * 100 vs / 100.

    800/1000 = 0.80 → valid_pixel_pct = 80.0 (NOT 0.008)
    """
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=5.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=800)

    reduce_mock, mul_result = _setup_area_mocks(mock_ee)
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["cloud_masking"]["valid_pixel_pct"] == pytest.approx(80.0)


def test_cloud_warning_at_exactly_050(mock_ee):
    """Kill mutation: valid_fraction < 0.50 boundary.

    At exactly 0.50 (500/1000), NO warning should be set.
    If mutated to <=, this would wrongly produce a warning.
    """
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=15.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=500)  # exactly 0.50

    reduce_mock, mul_result = _setup_area_mocks(mock_ee)
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["status"] == "success"
    assert result["cloud_masking"]["warning"] is None


def test_cloud_warning_just_below_050(mock_ee):
    """Just below 0.50 — warning SHOULD be present."""
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=15.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=499)  # 0.499 < 0.50

    reduce_mock, mul_result = _setup_area_mocks(mock_ee)
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["status"] == "success"
    assert result["cloud_masking"]["warning"] is not None


def test_shared_inputs_true_in_reducer(mock_ee):
    """Kill mutation: sharedInputs=True → False.

    Verify that combine() is called with sharedInputs=True.
    """
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, band, water_mask = _setup_s2_image(mock_ee, cloud_pct=5.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=800)

    reduce_mock, mul_result = _setup_area_mocks(mock_ee)
    water_mask.multiply.return_value = mul_result
    water_mask.And.return_value.multiply = MagicMock(return_value=mul_result)
    band.reduceRegion = MagicMock(return_value=reduce_mock)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    # Verify combine was called with sharedInputs=True (both calls)
    mean_reducer = mock_ee.Reducer.mean.return_value
    combine_calls = mean_reducer.combine.call_args_list
    assert len(combine_calls) >= 1
    for call in combine_calls:
        assert call.kwargs.get("sharedInputs") is True


@patch("app.domains.geo.water_detection.detect_water_from_gee")
def test_multi_date_increasing_boundary(mock_detect):
    """Kill mutation: > vs >= on increasing trend boundary.

    When water_pct difference is exactly +1, it should be 'stable' (not increasing).
    increasing requires > +1, so exactly +1 gives stable.
    """
    from app.domains.geo.water_detection import detect_water_multi_date

    mock_detect.side_effect = [
        {"status": "success", "image_date": "2024-01-01", "area": {"water_ha": 10, "water_pct": 5.0}},
        {"status": "success", "image_date": "2024-02-01", "area": {"water_ha": 12, "water_pct": 6.0}},
    ]

    result = detect_water_multi_date(GEOM, ["2024-01-01", "2024-02-01"])
    # difference is exactly 1.0, which is NOT > 1 but IS >= 1
    # so trend should be "stable" (or "decreasing" check also fails, so "stable")
    assert result["change"]["trend"] == "stable"


@patch("app.domains.geo.water_detection.detect_water_from_gee")
def test_multi_date_decreasing_boundary(mock_detect):
    """Kill mutation: < vs <= on decreasing trend boundary.

    When water_pct difference is exactly -1, it should be 'stable' (not decreasing).
    decreasing requires < -1, so exactly -1 gives stable.
    """
    from app.domains.geo.water_detection import detect_water_multi_date

    mock_detect.side_effect = [
        {"status": "success", "image_date": "2024-01-01", "area": {"water_ha": 12, "water_pct": 6.0}},
        {"status": "success", "image_date": "2024-02-01", "area": {"water_ha": 10, "water_pct": 5.0}},
    ]

    result = detect_water_multi_date(GEOM, ["2024-01-01", "2024-02-01"])
    # difference is exactly -1.0, which is NOT < -1 but IS <= -1
    assert result["change"]["trend"] == "stable"


def test_insufficient_pixels_valid_pixel_pct_formula(mock_ee):
    """Kill mutation: valid_fraction * 100 in insufficient path (L127).

    At 5% valid: valid_pixel_pct = 0.05 * 100 = 5.0
    """
    from app.domains.geo.water_detection import detect_water_from_gee

    s2, _, _ = _setup_s2_image(mock_ee, cloud_pct=95.0)
    _make_collection(mock_ee, s2)
    _setup_pixel_counts(mock_ee, total=1000, valid=50)

    result = detect_water_from_gee(GEOM, "2024-01-15")

    assert result["status"] == "insufficient_clear_pixels"
    assert result["valid_pixel_pct"] == pytest.approx(5.0)
