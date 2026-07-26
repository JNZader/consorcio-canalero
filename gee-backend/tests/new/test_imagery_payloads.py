"""Imagery payload builders: date windows, stretch policy and sensor routing.

Every builder receives the explorer and ``ee`` injected, so the whole thing
runs against doubles — no credentials, no network.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domains.geo.gee_service_imagery_support import (
    LANDSAT_SENSORS,
    build_available_dates_payload,
    build_landsat_collection,
    build_landsat_payload,
    build_landsat_scenes_payload,
    build_sentinel1_collection,
    build_sentinel1_payload,
    build_sentinel2_collection,
    build_sentinel2_payload,
    build_sentinel2_tiles_payload,
    collection_dates,
)

from tests.new.imagery_ee_double import FakeEE, FakeExplorer, map_id, percentile_stats

TARGET = date(2015, 3, 15)


def _landsat_fake(*, count: int = 3, stats: dict | None = None) -> FakeEE:
    overrides: dict = {
        "size.getInfo": count,
        "getMapId": map_id(),
    }
    if stats is not None:
        overrides["reduceRegion.getInfo"] = stats
    return FakeEE(overrides)


# ── filterDate is END-EXCLUSIVE: builders must add one day ─────────────────


def test_landsat_payload_window_includes_the_buffer_edge_day() -> None:
    fake = _landsat_fake(stats=percentile_stats(["B4", "B3", "B2"], 0.05, 0.3))
    explorer = FakeExplorer(fake, dates=["2015-03-14"])

    build_landsat_payload(
        explorer,
        fake,
        sensor="landsat8",
        target_date=TARGET,
        days_buffer=10,
        max_cloud=80,
        visualization="rgb",
        use_median=False,
    )

    window = explorer.landsat_calls[0]
    assert window["start_date"] == TARGET - timedelta(days=10)
    # +1 day so a scene landing exactly on target+buffer is NOT dropped.
    assert window["end_date"] == TARGET + timedelta(days=11)
    assert window["end_date"] > TARGET + timedelta(days=10)


def test_landsat_scenes_payload_window_includes_the_buffer_edge_day() -> None:
    fake = FakeEE({"size.getInfo": 0})
    explorer = FakeExplorer(fake)

    build_landsat_scenes_payload(
        explorer,
        fake,
        sensor="landsat8",
        target_date=TARGET,
        days_buffer=2,
        max_cloud=80,
        visualization="rgb",
    )

    assert explorer.landsat_calls[0]["end_date"] == TARGET + timedelta(days=3)


def test_sentinel2_payload_window_includes_the_buffer_edge_day() -> None:
    fake = FakeEE({"size.getInfo": 0})
    explorer = FakeExplorer(fake)

    build_sentinel2_payload(
        explorer,
        target_date=TARGET,
        days_buffer=5,
        max_cloud=40,
        visualization="rgb",
        use_median=True,
    )

    window = explorer.sentinel2_calls[0]
    assert window["start_date"] == TARGET - timedelta(days=5)
    assert window["end_date"] == TARGET + timedelta(days=6)


def test_sentinel1_payload_window_includes_the_buffer_edge_day() -> None:
    fake = FakeEE({"size.getInfo": 0})
    explorer = FakeExplorer(fake)

    build_sentinel1_payload(explorer, target_date=TARGET, days_buffer=7, visualization="vv")

    window = explorer.sentinel1_calls[0]
    assert window["start_date"] == TARGET - timedelta(days=7)
    assert window["end_date"] == TARGET + timedelta(days=8)


def test_landsat_collection_passes_the_window_to_filter_date_as_iso() -> None:
    fake = FakeEE()

    build_landsat_collection(
        fake, fake.FeatureCollection("zona"), "landsat8", date(2015, 3, 5), date(2015, 3, 26), 80
    )

    assert fake.one_call_to("filterDate").args == ("2015-03-05", "2015-03-26")
    assert fake.one_call_to("ImageCollection").args == (LANDSAT_SENSORS["landsat8"]["collection"],)
    assert fake.one_call_to("Filter.lt").args == ("CLOUD_COVER", 80)


def test_sentinel2_collection_picks_toa_or_sr_and_filters_cloud_percentage() -> None:
    fake = FakeEE()
    zona = fake.FeatureCollection("zona")

    toa_name, _ = build_sentinel2_collection(
        fake, zona, date(2017, 2, 1), date(2017, 3, 1), 40, use_toa=True
    )
    sr_name, _ = build_sentinel2_collection(
        fake, zona, date(2024, 2, 1), date(2024, 3, 1), 40, use_toa=False
    )

    assert toa_name == "COPERNICUS/S2_HARMONIZED"
    assert sr_name == "COPERNICUS/S2_SR_HARMONIZED"
    assert fake.calls_to("Filter.lt")[0].args == ("CLOUDY_PIXEL_PERCENTAGE", 40)


def test_sentinel1_collection_filters_iw_mode_and_vv_polarisation() -> None:
    fake = FakeEE()

    build_sentinel1_collection(
        fake, fake.FeatureCollection("zona"), date(2024, 1, 1), date(2024, 1, 10)
    )

    assert fake.one_call_to("ImageCollection").args == ("COPERNICUS/S1_GRD",)
    assert fake.one_call_to("Filter.eq").args == ("instrumentMode", "IW")
    assert fake.one_call_to("Filter.listContains").args == (
        "transmitterReceiverPolarisation",
        "VV",
    )


# ── stretch policy: percentile stretch ONLY on single-date scenes ──────────


def test_scene_mode_applies_the_percentile_stretch() -> None:
    bands = LANDSAT_SENSORS["landsat8"]["rgb"]
    fake = _landsat_fake(stats=percentile_stats(bands, 0.05, 0.3))
    explorer = FakeExplorer(fake, dates=["2015-03-14"])

    payload = build_landsat_payload(
        explorer,
        fake,
        sensor="landsat8",
        target_date=TARGET,
        days_buffer=10,
        max_cloud=80,
        visualization="rgb",
        use_median=False,
    )

    assert payload["composition_mode"] == "scene"
    vis_params = fake.one_call_to("getMapId").args[0]
    assert vis_params["min"] == [0.05, 1.05, 2.05]
    assert vis_params["max"] == [0.3, 1.3, 2.3]
    assert vis_params["gamma"] == 1.1


def test_composite_mode_does_not_stretch_the_bands() -> None:
    """Stretching each band of a multi-date composite gives neon colours."""
    bands = LANDSAT_SENSORS["landsat8"]["rgb"]
    fake = _landsat_fake(stats=percentile_stats(bands, 0.05, 0.3))
    explorer = FakeExplorer(fake, dates=["2015-03-14", "2015-03-20"])

    payload = build_landsat_payload(
        explorer,
        fake,
        sensor="landsat8",
        target_date=TARGET,
        days_buffer=10,
        max_cloud=80,
        visualization="rgb",
        use_median=True,
    )

    assert payload["composition_mode"] == "composite"
    assert not fake.called("reduceRegion")
    vis_params = fake.one_call_to("getMapId").args[0]
    assert vis_params["min"] == 0
    assert vis_params["max"] == LANDSAT_SENSORS["landsat8"]["max"]
    assert "gamma" not in vis_params


def test_landsat7_gap_fill_composite_does_not_stretch_either() -> None:
    fake = _landsat_fake(stats=percentile_stats(LANDSAT_SENSORS["landsat7"]["rgb"], 0.05, 0.3))
    explorer = FakeExplorer(fake, dates=["2015-03-10", "2015-03-14", "2015-03-20", "2015-03-25"])

    payload = build_landsat_payload(
        explorer,
        fake,
        sensor="landsat7",
        target_date=TARGET,
        days_buffer=10,
        max_cloud=80,
        visualization="rgb",
        use_median=True,
    )

    assert payload["composition_mode"] == "composite"
    assert not fake.called("reduceRegion")
    assert "SLC-off" in payload["notes"]


def test_index_visualizations_never_stretch() -> None:
    fake = _landsat_fake(stats=percentile_stats(["B3", "B5"], 0.05, 0.3))
    explorer = FakeExplorer(fake, dates=["2015-03-14"])

    payload = build_landsat_payload(
        explorer,
        fake,
        sensor="landsat8",
        target_date=TARGET,
        days_buffer=10,
        max_cloud=80,
        visualization="ndwi",
        use_median=False,
    )

    assert payload["composition_mode"] == "scene"
    assert not fake.called("reduceRegion")
    vis_params = fake.one_call_to("getMapId").args[0]
    assert vis_params["palette"] == ["brown", "white", "blue"]
    assert fake.one_call_to("normalizedDifference").args == (["B3", "B5"],)


def test_landsat7_gap_fill_only_touches_the_bands_the_render_reads() -> None:
    """Cost guard: filling unused bands rate-limited the tile server."""
    fake = _landsat_fake()
    explorer = FakeExplorer(fake, dates=["2015-03-10", "2015-03-14", "2015-03-20", "2015-03-25"])

    build_landsat_payload(
        explorer,
        fake,
        sensor="landsat7",
        target_date=TARGET,
        days_buffer=10,
        max_cloud=80,
        visualization="ndwi",
        use_median=True,
    )

    needed = LANDSAT_SENSORS["landsat7"]["ndwi"]
    selected = [call.args[0] for call in fake.calls_to("select") if call.args]
    assert needed in selected
    assert all(not isinstance(arg, list) or arg == needed for arg in selected)
    # Base scene + at most 2 fill dates (never the whole window).
    assert len(explorer.landsat_calls) <= 1 + 3


def test_landsat_payload_reports_no_images_without_touching_the_map() -> None:
    fake = FakeEE({"size.getInfo": 0})
    explorer = FakeExplorer(fake)

    payload = build_landsat_payload(
        explorer,
        fake,
        sensor="landsat5",
        target_date=TARGET,
        days_buffer=10,
        max_cloud=80,
        visualization="rgb",
        use_median=True,
    )

    assert "error" in payload
    assert payload["max_cloud"] == 80
    assert payload["days_buffer"] == 10
    assert not fake.called("getMapId")


def test_landsat_payload_echoes_the_effective_search_params() -> None:
    fake = _landsat_fake()
    explorer = FakeExplorer(fake, dates=["2015-03-14", "2015-03-10"])

    payload = build_landsat_payload(
        explorer,
        fake,
        sensor="landsat8",
        target_date=TARGET,
        days_buffer=10,
        max_cloud=80,
        visualization="ndwi",
        use_median=True,
    )

    assert payload["sensor"] == "Landsat 8"
    assert payload["collection"] == LANDSAT_SENSORS["landsat8"]["collection"]
    assert payload["days_buffer"] == 10
    assert payload["max_cloud"] == 80
    assert payload["images_count"] == 3
    assert payload["tile_url"].startswith("https://earthengine.example/")


# ── Sentinel-2 payload ─────────────────────────────────────────────────────


def test_sentinel2_uses_toa_before_2019_and_sr_after() -> None:
    fake = FakeEE({"size.getInfo": 0})
    explorer = FakeExplorer(fake)

    build_sentinel2_payload(
        explorer,
        target_date=date(2017, 2, 20),
        days_buffer=10,
        max_cloud=40,
        visualization="rgb",
        use_median=True,
    )
    build_sentinel2_payload(
        explorer,
        target_date=date(2024, 2, 20),
        days_buffer=10,
        max_cloud=40,
        visualization="rgb",
        use_median=True,
    )

    assert explorer.sentinel2_calls[0]["use_toa"] is True
    assert explorer.sentinel2_calls[1]["use_toa"] is False


def test_sentinel2_composite_uses_median_and_cloudscore() -> None:
    fake = FakeEE({"size.getInfo": 4, "getMapId": map_id()})
    explorer = FakeExplorer(fake, dates=["2024-02-18"])

    payload = build_sentinel2_payload(
        explorer,
        target_date=date(2024, 2, 20),
        days_buffer=10,
        max_cloud=40,
        visualization="rgb",
        use_median=True,
    )

    assert explorer.cloudscore_calls == 1
    assert fake.called("median")
    assert not fake.called("mosaic")
    assert payload["sensor"] == "Sentinel-2"
    assert payload["collection"] == "COPERNICUS/S2_SR_HARMONIZED"


def test_sentinel2_scene_uses_mosaic_not_median() -> None:
    fake = FakeEE({"size.getInfo": 4, "getMapId": map_id()})
    explorer = FakeExplorer(fake, dates=["2024-02-18"])

    build_sentinel2_payload(
        explorer,
        target_date=date(2024, 2, 20),
        days_buffer=10,
        max_cloud=40,
        visualization="rgb",
        use_median=False,
    )

    assert fake.called("mosaic")
    assert not fake.called("median")


def test_sentinel2_never_applies_a_percentile_stretch() -> None:
    fake = FakeEE({"size.getInfo": 4, "getMapId": map_id()})
    explorer = FakeExplorer(fake, dates=["2024-02-18"])

    build_sentinel2_payload(
        explorer,
        target_date=date(2024, 2, 20),
        days_buffer=10,
        max_cloud=40,
        visualization="rgb",
        use_median=False,
    )

    assert not fake.called("reduceRegion")
    vis_params = fake.one_call_to("getMapId").args[0]
    assert vis_params == {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}


@pytest.mark.parametrize(
    ("visualization", "expected_bands"),
    [
        ("ndwi", ["B3", "B8"]),
        ("mndwi", ["B3", "B11"]),
        ("ndvi", ["B8", "B4"]),
        ("inundacion", ["B3", "B8"]),
    ],
)
def test_sentinel2_index_visualizations_use_the_right_band_pair(
    visualization: str, expected_bands: list
) -> None:
    fake = FakeEE({"size.getInfo": 4, "getMapId": map_id()})
    explorer = FakeExplorer(fake, dates=["2024-02-18"])

    build_sentinel2_payload(
        explorer,
        target_date=date(2024, 2, 20),
        days_buffer=10,
        max_cloud=40,
        visualization=visualization,
        use_median=True,
    )

    assert fake.one_call_to("normalizedDifference").args == (expected_bands,)


def test_sentinel2_reports_no_images_found() -> None:
    fake = FakeEE({"size.getInfo": 0})
    explorer = FakeExplorer(fake)

    payload = build_sentinel2_payload(
        explorer,
        target_date=date(2024, 2, 20),
        days_buffer=10,
        max_cloud=40,
        visualization="rgb",
        use_median=True,
    )

    assert "error" in payload
    assert not fake.called("getMapId")


def test_sentinel2_tiles_payload_filters_and_renders_true_colour() -> None:
    fake = FakeEE({"size.getInfo": 2, "getMapId": map_id()})

    payload = build_sentinel2_tiles_payload(
        fake,
        fake.FeatureCollection("zona"),
        start_date=date(2024, 2, 1),
        end_date=date(2024, 3, 1),
        max_cloud=30,
    )

    assert payload["imagenes_disponibles"] == 2
    assert fake.one_call_to("filterDate").args == ("2024-02-01", "2024-03-01")
    assert fake.one_call_to("getMapId").args[0]["bands"] == ["B4", "B3", "B2"]


def test_sentinel2_tiles_payload_reports_empty_window() -> None:
    fake = FakeEE({"size.getInfo": 0})

    payload = build_sentinel2_tiles_payload(
        fake,
        fake.FeatureCollection("zona"),
        start_date=date(2024, 2, 1),
        end_date=date(2024, 3, 1),
        max_cloud=30,
    )

    assert payload["error"] == "No se encontraron imagenes Sentinel-2"


# ── Sentinel-1 payload ─────────────────────────────────────────────────────


def test_sentinel1_flood_visualization_thresholds_backscatter() -> None:
    fake = FakeEE({"size.getInfo": 2, "getMapId": map_id()})
    explorer = FakeExplorer(fake, dates=["2024-02-18"])

    payload = build_sentinel1_payload(
        explorer, target_date=date(2024, 2, 20), days_buffer=6, visualization="vv_flood"
    )

    assert fake.one_call_to("lt").args == (-15,)
    assert payload["visualization_description"] == "Deteccion de agua (SAR < -15 dB)"
    assert fake.one_call_to("getMapId").args[0] == {"palette": ["00FFFF"]}
    assert payload["max_cloud"] is None


def test_sentinel1_default_visualization_is_raw_backscatter() -> None:
    fake = FakeEE({"size.getInfo": 2, "getMapId": map_id()})
    explorer = FakeExplorer(fake, dates=["2024-02-18"])

    payload = build_sentinel1_payload(
        explorer, target_date=date(2024, 2, 20), days_buffer=6, visualization="vv"
    )

    assert fake.one_call_to("getMapId").args[0] == {"min": -25, "max": 0}
    assert payload["sensor"] == "Sentinel-1"


def test_sentinel1_reports_no_images_found() -> None:
    fake = FakeEE({"size.getInfo": 0})
    explorer = FakeExplorer(fake)

    payload = build_sentinel1_payload(
        explorer, target_date=date(2024, 2, 20), days_buffer=6, visualization="vv"
    )

    assert "error" in payload
    assert not fake.called("getMapId")


# ── build_available_dates_payload: normalisation + routing ─────────────────


def test_available_dates_normalises_the_sensor_to_lowercase() -> None:
    fake = FakeEE()
    explorer = FakeExplorer(fake, dates=["2024-02-03", "2024-02-18"])

    payload = build_available_dates_payload(
        explorer, year=2024, month=2, sensor="SENTINEL2", max_cloud=60
    )

    assert payload["sensor"] == "sentinel2"
    assert payload["dates"] == ["2024-02-03", "2024-02-18"]
    assert payload["total"] == 2
    assert len(explorer.sentinel2_calls) == 1


@pytest.mark.parametrize("sensor", ["landsat8", "LANDSAT7", "Landsat5"])
def test_available_dates_routes_landsat_sensors(sensor: str) -> None:
    fake = FakeEE()
    explorer = FakeExplorer(fake, dates=[])

    payload = build_available_dates_payload(
        explorer, year=2015, month=3, sensor=sensor, max_cloud=60
    )

    assert explorer.landsat_calls[0]["sensor"] == sensor.lower()
    assert payload["sensor"] == sensor.lower()
    assert payload["dates"] == []
    assert payload["total"] == 0


def test_available_dates_routes_sentinel1() -> None:
    fake = FakeEE()
    explorer = FakeExplorer(fake, dates=["2024-02-03"])

    build_available_dates_payload(explorer, year=2024, month=2, sensor="sentinel1", max_cloud=60)

    assert len(explorer.sentinel1_calls) == 1
    assert not explorer.sentinel2_calls
    assert not explorer.landsat_calls


def test_available_dates_window_covers_the_whole_month_end_exclusive() -> None:
    fake = FakeEE()
    explorer = FakeExplorer(fake, dates=[])

    build_available_dates_payload(explorer, year=2024, month=2, sensor="sentinel1", max_cloud=60)

    window = explorer.sentinel1_calls[0]
    assert window["start_date"] == date(2024, 2, 1)
    # 2024 is a leap year: the 29th must be inside the window.
    assert window["end_date"] == date(2024, 3, 1)


def test_available_dates_uses_toa_for_pre_2019_sentinel2() -> None:
    fake = FakeEE()
    explorer = FakeExplorer(fake, dates=[])

    build_available_dates_payload(explorer, year=2017, month=2, sensor="sentinel2", max_cloud=60)
    build_available_dates_payload(explorer, year=2024, month=2, sensor="sentinel2", max_cloud=60)

    assert explorer.sentinel2_calls[0]["use_toa"] is True
    assert explorer.sentinel2_calls[1]["use_toa"] is False


def test_available_dates_returns_a_structured_error_for_unsupported_sensor() -> None:
    fake = FakeEE()
    explorer = FakeExplorer(fake, dates=["2024-02-03"])

    payload = build_available_dates_payload(
        explorer, year=2024, month=2, sensor="modis", max_cloud=60
    )

    assert payload["error"] == "Sensor no soportado: modis"
    assert payload["dates"] == []
    assert payload["total"] == 0
    assert payload["sensor"] == "modis"
    assert not explorer.sentinel1_calls
    assert not explorer.sentinel2_calls
    assert not explorer.landsat_calls


# ── collection_dates ───────────────────────────────────────────────────────


def test_collection_dates_sorts_and_tolerates_empty() -> None:
    assert collection_dates("col", lambda _c: ["2024-02-18", "2024-02-03"]) == [
        "2024-02-03",
        "2024-02-18",
    ]
    assert collection_dates("col", lambda _c: []) == []
    assert collection_dates("col", lambda _c: None) == []
