"""The profile cache invalidation contract, without a database.

Every rejection here is the difference between "recompute" and "serve a profile
of a surface that is no longer on disk".
"""

from __future__ import annotations

import os

from app.domains.geo.elevation_profile_cache import (
    SERIES_VERSION,
    build_cache_key,
    build_source_identity,
    canonical_geometry,
    file_identity,
)

GEOM = {"type": "LineString", "coordinates": [[-62.7, -32.6], [-62.702, -32.6]]}


def _dem(tmp_path, body: bytes = b"dem-bytes"):
    path = tmp_path / "dem_filled.tif"
    path.write_bytes(body)
    return path


def test_same_geometry_and_sources_give_the_same_key(tmp_path) -> None:
    identity = build_source_identity(str(_dem(tmp_path)))
    assert build_cache_key(GEOM, identity) == build_cache_key(GEOM, identity)


def test_key_ignores_dict_key_order(tmp_path) -> None:
    identity = build_source_identity(str(_dem(tmp_path)))
    reordered = {"coordinates": GEOM["coordinates"], "type": "LineString"}
    assert canonical_geometry(GEOM) == canonical_geometry(reordered)
    assert build_cache_key(GEOM, identity) == build_cache_key(reordered, identity)


def test_a_different_trace_never_hits(tmp_path) -> None:
    identity = build_source_identity(str(_dem(tmp_path)))
    moved = {
        "type": "LineString",
        "coordinates": [[-62.7, -32.6], [-62.7021, -32.6]],
    }
    assert build_cache_key(GEOM, identity) != build_cache_key(moved, identity)


def test_rewriting_the_dem_invalidates(tmp_path) -> None:
    dem = _dem(tmp_path, b"first-run")
    before = build_source_identity(str(dem))
    dem.write_bytes(b"second-run-longer")
    after = build_source_identity(str(dem))
    assert before != after
    assert build_cache_key(GEOM, before) != build_cache_key(GEOM, after)


def test_touching_the_dem_mtime_invalidates(tmp_path) -> None:
    dem = _dem(tmp_path)
    before = build_source_identity(str(dem))
    stat = os.stat(dem)
    os.utime(dem, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert build_source_identity(str(dem)) != before


def test_mde_ar_appearing_or_changing_invalidates(tmp_path) -> None:
    dem = _dem(tmp_path)
    absent = build_source_identity(str(dem))
    assert "mde_ar:absent" in absent

    mde = tmp_path / "mde_ar.tif"
    mde.write_bytes(b"mosaic")
    present = build_source_identity(str(dem))
    assert "mde_ar:absent" not in present
    assert absent != present

    mde.write_bytes(b"mosaic-rebuilt")
    assert build_source_identity(str(dem)) != present


def test_series_version_is_part_of_the_identity(tmp_path) -> None:
    identity = build_source_identity(str(_dem(tmp_path)))
    assert identity.startswith(f"series:v{SERIES_VERSION}|")


def test_missing_raster_is_reported_as_absent(tmp_path) -> None:
    assert file_identity(tmp_path / "nope.tif") == "absent"
    assert file_identity(tmp_path / "nope.tif") != file_identity(_dem(tmp_path))
