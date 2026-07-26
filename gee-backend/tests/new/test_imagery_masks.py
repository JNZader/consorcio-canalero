"""Cloud/haze masking and percentile stretch helpers (optical imagery).

These are the pixel-level filters that decide what actually reaches the map.
They all take ``ee`` injected, so they run here against a recording double and
the assertions are on the exact sequence of Earth Engine operations requested.
"""

from __future__ import annotations

import pytest

from app.domains.geo.gee_service_imagery_support import (
    CLOUD_SCORE_BAND,
    CLOUD_SCORE_CLEAR_THRESHOLD,
    CLOUD_SCORE_PLUS_ID,
    LANDSAT_SENSORS,
    compute_stretch_range,
    mask_clouds_landsat,
    mask_clouds_s2,
    mask_landsat_haze,
    mask_s2_cloudscore,
)

from tests.new.imagery_ee_double import FakeEE, percentile_stats


# ── mask_clouds_landsat: QA_PIXEL bits 1/3/4 ────────────────────────────────


def test_mask_clouds_landsat_reads_qa_pixel_band() -> None:
    fake = FakeEE()
    mask = mask_clouds_landsat(fake)

    mask(fake.Image("scene"))

    assert fake.one_call_to("select").args == ("QA_PIXEL",)


def test_mask_clouds_landsat_uses_dilated_cloud_cloud_and_shadow_bits() -> None:
    fake = FakeEE()
    mask = mask_clouds_landsat(fake)

    mask(fake.Image("scene"))

    bits = [call.args[0] for call in fake.calls_to("bitwiseAnd")]
    # bit1 = dilated cloud, bit3 = cloud, bit4 = cloud shadow.
    assert bits == [1 << 1, 1 << 3, 1 << 4]
    assert bits == [2, 8, 16]


def test_mask_clouds_landsat_keeps_only_uncontaminated_pixels() -> None:
    fake = FakeEE()
    mask = mask_clouds_landsat(fake)

    mask(fake.Image("scene"))

    # The three bit tests are OR-ed, then the mask keeps pixels where the
    # combination is zero (i.e. no cloud flag at all).
    assert len(fake.calls_to("Or")) == 2
    assert fake.one_call_to("eq").args == (0,)
    assert fake.called("updateMask")


# ── mask_landsat_haze: blue band threshold, per sensor ──────────────────────


def test_mask_landsat_haze_drops_pixels_above_threshold() -> None:
    fake = FakeEE()

    mask_landsat_haze("B2")(fake.Image("scene"))

    assert fake.one_call_to("select").args == ("B2",)
    # ``lt(threshold)`` keeps the DARK pixels — i.e. discards blue >= 0.15.
    assert fake.one_call_to("lt").args == (0.15,)
    assert fake.called("updateMask")


def test_mask_landsat_haze_threshold_is_configurable() -> None:
    fake = FakeEE()

    mask_landsat_haze("B1", threshold=0.25)(fake.Image("scene"))

    assert fake.one_call_to("lt").args == (0.25,)


@pytest.mark.parametrize(
    ("sensor", "expected_blue"),
    [("landsat8", "B2"), ("landsat7", "B1"), ("landsat5", "B1")],
)
def test_landsat_blue_band_matches_sensor_config(sensor: str, expected_blue: str) -> None:
    """The haze mask is fed ``cfg['rgb'][2]``; L8 and L5/L7 differ."""
    cfg = LANDSAT_SENSORS[sensor]

    assert cfg["rgb"][2] == expected_blue

    fake = FakeEE()
    mask_landsat_haze(cfg["rgb"][2])(fake.Image("scene"))
    assert fake.one_call_to("select").args == (expected_blue,)


# ── mask_s2_cloudscore: Cloud Score+ link + threshold ───────────────────────


def test_mask_s2_cloudscore_links_cloud_score_plus_collection() -> None:
    fake = FakeEE()

    mask_s2_cloudscore(fake, fake.ImageCollection("COPERNICUS/S2_SR_HARMONIZED"))

    link = fake.one_call_to("linkCollection")
    assert link.args[1] == [CLOUD_SCORE_BAND]
    assert CLOUD_SCORE_PLUS_ID in [call.args[0] for call in fake.calls_to("ImageCollection")]


def test_mask_s2_cloudscore_keeps_pixels_above_clear_threshold() -> None:
    fake = FakeEE()

    mask_s2_cloudscore(fake, fake.ImageCollection("COPERNICUS/S2_SR_HARMONIZED"))

    # ``map`` is applied eagerly by the double, so the per-image ops are logged.
    assert fake.one_call_to("select").args == ("cs",)
    assert fake.one_call_to("gte").args == (CLOUD_SCORE_CLEAR_THRESHOLD,)
    assert CLOUD_SCORE_CLEAR_THRESHOLD == 0.6
    assert fake.called("updateMask")


def test_mask_clouds_s2_rejects_scl_cloud_and_shadow_classes() -> None:
    fake = FakeEE()

    mask_clouds_s2(fake.Image("scene"))

    assert fake.one_call_to("select").args == ("SCL",)
    # 3 = cloud shadow, 8/9 = cloud medium/high probability, 10 = cirrus.
    assert [call.args[0] for call in fake.calls_to("neq")] == [3, 8, 9, 10]
    assert fake.called("updateMask")


# ── compute_stretch_range: percentiles with a hard fallback ────────────────


def test_compute_stretch_range_returns_percentiles_when_stats_are_valid() -> None:
    bands = ["B4", "B3", "B2"]
    fake = FakeEE({"reduceRegion.getInfo": percentile_stats(bands, low=0.05, high=0.30)})

    mins, maxs = compute_stretch_range(
        fake,
        fake.Image("composite"),
        bands,
        fake.FeatureCollection("zona"),
        default_min=0,
        default_max=0.35,
    )

    assert mins == [0.05, 1.05, 2.05]
    assert maxs == [0.30, 1.30, 2.30]


def test_compute_stretch_range_asks_for_2_and_98_percentiles_over_the_zona() -> None:
    bands = ["B4", "B3"]
    fake = FakeEE({"reduceRegion.getInfo": percentile_stats(bands, low=0.05, high=0.30)})
    zona = fake.FeatureCollection("zona")

    compute_stretch_range(
        fake, fake.Image("composite"), bands, zona, default_min=0, default_max=0.35
    )

    assert fake.one_call_to("Reducer.percentile").args == ([2, 98],)
    reduce_call = fake.one_call_to("reduceRegion")
    assert reduce_call.kwargs["geometry"] is zona
    assert reduce_call.kwargs["bestEffort"] is True
    assert fake.one_call_to("select").args == (bands,)


def test_compute_stretch_range_falls_back_when_reduce_region_raises() -> None:
    fake = FakeEE({"reduceRegion.getInfo": RuntimeError("GEE unavailable")})

    result = compute_stretch_range(
        fake,
        fake.Image("composite"),
        ["B4", "B3", "B2"],
        fake.FeatureCollection("zona"),
        default_min=0,
        default_max=0.35,
    )

    assert result == (0, 0.35)


def test_compute_stretch_range_falls_back_when_a_percentile_is_none() -> None:
    stats = percentile_stats(["B4", "B3"], low=0.05, high=0.30)
    stats["B3_p98"] = None
    fake = FakeEE({"reduceRegion.getInfo": stats})

    result = compute_stretch_range(
        fake,
        fake.Image("composite"),
        ["B4", "B3"],
        fake.FeatureCollection("zona"),
        default_min=0,
        default_max=0.35,
    )

    assert result == (0, 0.35)


def test_compute_stretch_range_falls_back_when_a_band_is_missing_from_stats() -> None:
    fake = FakeEE({"reduceRegion.getInfo": {"B4_p2": 0.05, "B4_p98": 0.3}})

    result = compute_stretch_range(
        fake,
        fake.Image("composite"),
        ["B4", "B3"],
        fake.FeatureCollection("zona"),
        default_min=0,
        default_max=0.35,
    )

    assert result == (0, 0.35)


@pytest.mark.parametrize("high", [0.05, 0.01])
def test_compute_stretch_range_falls_back_on_degenerate_range(high: float) -> None:
    """hi <= lo would blow up the render (division by zero / inverted ramp)."""
    fake = FakeEE(
        {"reduceRegion.getInfo": {"B4_p2": 0.05, "B4_p98": high, "B3_p2": 0.1, "B3_p98": 0.9}}
    )

    result = compute_stretch_range(
        fake,
        fake.Image("composite"),
        ["B4", "B3"],
        fake.FeatureCollection("zona"),
        default_min=0,
        default_max=0.35,
    )

    assert result == (0, 0.35)
