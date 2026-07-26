"""Band selection and scene metadata for the Landsat imagery path.

``landsat_needed_bands`` is a cost guard: the SLC-off gap fill is
O(bands x fills x kernel^2) per tile, so returning one band too many brought
back the GEE 429s that stalled the tile server.
"""

from __future__ import annotations

import pytest

from app.domains.geo.gee_service_imagery_support import (
    LANDSAT_SENSORS,
    _landsat_scene_metadata,
    landsat_composite_bands,
    landsat_needed_bands,
)

BAND_COMPOSITIONS = ("rgb", "falso_color", "agricultura")
INDEX_VISUALIZATIONS = ("ndwi", "mndwi", "ndvi", "inundacion")


# ── landsat_composite_bands ────────────────────────────────────────────────


@pytest.mark.parametrize("sensor", sorted(LANDSAT_SENSORS))
@pytest.mark.parametrize("visualization", INDEX_VISUALIZATIONS)
def test_composite_bands_is_none_for_index_visualizations(sensor: str, visualization: str) -> None:
    assert landsat_composite_bands(LANDSAT_SENSORS[sensor], visualization) is None


@pytest.mark.parametrize(
    ("sensor", "visualization", "expected"),
    [
        ("landsat8", "rgb", ["B4", "B3", "B2"]),
        ("landsat8", "falso_color", ["B5", "B4", "B3"]),
        ("landsat8", "agricultura", ["B6", "B5", "B2"]),
        ("landsat7", "rgb", ["B3", "B2", "B1"]),
        ("landsat7", "falso_color", ["B4", "B3", "B2"]),
        ("landsat7", "agricultura", ["B5", "B4", "B1"]),
        ("landsat5", "rgb", ["B3", "B2", "B1"]),
        ("landsat5", "falso_color", ["B4", "B3", "B2"]),
        ("landsat5", "agricultura", ["B5", "B4", "B1"]),
    ],
)
def test_composite_bands_per_sensor(sensor: str, visualization: str, expected: list) -> None:
    assert landsat_composite_bands(LANDSAT_SENSORS[sensor], visualization) == expected


def test_composite_bands_defaults_to_rgb_for_unknown_visualization() -> None:
    cfg = LANDSAT_SENSORS["landsat8"]

    assert landsat_composite_bands(cfg, "no-existe") == cfg["rgb"]


def test_composite_bands_returns_a_copy_not_the_config_list() -> None:
    cfg = LANDSAT_SENSORS["landsat8"]

    bands = landsat_composite_bands(cfg, "rgb")
    bands.append("MUTADO")

    assert cfg["rgb"] == ["B4", "B3", "B2"]


# ── landsat_needed_bands: only what the visualization reads ────────────────


@pytest.mark.parametrize("sensor", sorted(LANDSAT_SENSORS))
@pytest.mark.parametrize("visualization", BAND_COMPOSITIONS)
def test_needed_bands_for_compositions_is_exactly_three(sensor: str, visualization: str) -> None:
    cfg = LANDSAT_SENSORS[sensor]

    needed = landsat_needed_bands(cfg, visualization)

    assert len(needed) == 3
    assert needed == landsat_composite_bands(cfg, visualization)


@pytest.mark.parametrize("sensor", sorted(LANDSAT_SENSORS))
@pytest.mark.parametrize("visualization", INDEX_VISUALIZATIONS)
def test_needed_bands_for_indices_is_exactly_two(sensor: str, visualization: str) -> None:
    needed = landsat_needed_bands(LANDSAT_SENSORS[sensor], visualization)

    assert len(needed) == 2
    assert len(set(needed)) == 2


@pytest.mark.parametrize(
    ("sensor", "visualization", "expected"),
    [
        # ndwi and inundacion both derive from the NDWI pair (green, nir).
        ("landsat8", "ndwi", ["B3", "B5"]),
        ("landsat8", "inundacion", ["B3", "B5"]),
        ("landsat8", "mndwi", ["B3", "B6"]),
        # ndvi = nir (false_color[0]) + red (rgb[0]).
        ("landsat8", "ndvi", ["B5", "B4"]),
        ("landsat7", "ndwi", ["B2", "B4"]),
        ("landsat7", "inundacion", ["B2", "B4"]),
        ("landsat7", "mndwi", ["B2", "B5"]),
        ("landsat7", "ndvi", ["B4", "B3"]),
        ("landsat5", "ndwi", ["B2", "B4"]),
        ("landsat5", "mndwi", ["B2", "B5"]),
        ("landsat5", "ndvi", ["B4", "B3"]),
    ],
)
def test_needed_bands_per_sensor_and_index(sensor: str, visualization: str, expected: list) -> None:
    assert landsat_needed_bands(LANDSAT_SENSORS[sensor], visualization) == expected


@pytest.mark.parametrize("sensor", sorted(LANDSAT_SENSORS))
@pytest.mark.parametrize("visualization", BAND_COMPOSITIONS + INDEX_VISUALIZATIONS)
def test_needed_bands_never_exceeds_what_the_render_reads(sensor: str, visualization: str) -> None:
    """Extra bands = extra gap-fill work per tile = GEE 429s."""
    cfg = LANDSAT_SENSORS[sensor]

    needed = landsat_needed_bands(cfg, visualization)

    assert len(needed) <= 3
    assert all(band in _all_sensor_bands(cfg) for band in needed)


def _all_sensor_bands(cfg: dict) -> set:
    bands: set = set()
    for key in ("rgb", "false_color", "agriculture", "ndwi", "mndwi"):
        bands.update(cfg[key])
    return bands


def test_needed_bands_returns_a_copy_for_indices() -> None:
    cfg = LANDSAT_SENSORS["landsat8"]

    needed = landsat_needed_bands(cfg, "ndwi")
    needed.append("MUTADO")

    assert cfg["ndwi"] == ["B3", "B5"]


# ── _landsat_scene_metadata ────────────────────────────────────────────────


def test_scene_metadata_parses_all_known_properties() -> None:
    props = {
        "system:index": "LC08_228083_20150315",
        "system:time_start": 1426377600000,  # 2015-03-15T00:00:00Z
        "CLOUD_COVER": 12.5,
        "WRS_PATH": 228,
        "WRS_ROW": 83,
    }

    metadata = _landsat_scene_metadata(props, "fallback-id")

    assert metadata == {
        "id": "LC08_228083_20150315",
        "date": "2015-03-15",
        "cloud_cover": 12.5,
        "path": 228,
        "row": 83,
    }


def test_scene_metadata_converts_epoch_milliseconds_to_iso_date() -> None:
    metadata = _landsat_scene_metadata({"system:time_start": 0}, "x")

    assert metadata["date"] == "1970-01-01"


def test_scene_metadata_accepts_float_timestamps() -> None:
    metadata = _landsat_scene_metadata({"system:time_start": 1426377600000.0}, "x")

    assert metadata["date"] == "2015-03-15"


def test_scene_metadata_tolerates_missing_properties() -> None:
    metadata = _landsat_scene_metadata({}, "fallback-id")

    assert metadata == {
        "id": "fallback-id",
        "date": None,
        "cloud_cover": None,
        "path": None,
        "row": None,
    }


def test_scene_metadata_falls_back_when_index_is_empty() -> None:
    metadata = _landsat_scene_metadata({"system:index": ""}, "fallback-id")

    assert metadata["id"] == "fallback-id"


def test_scene_metadata_ignores_non_numeric_timestamp() -> None:
    metadata = _landsat_scene_metadata({"system:time_start": "2015-03-15"}, "x")

    assert metadata["date"] is None
