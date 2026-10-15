"""The stored profile: round-trip, retention, and "second call does not resample".

The service seam is patched on purpose: this module is about the cache contract,
not about rasterio sampling (covered by ``test_elevation_profile.py``). The
GeoTIFF is real so the CRS round-trip stays real.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import event, update
from sqlalchemy.orm import sessionmaker

from app.domains.geo import elevation_profile_cache as cache_module
from app.domains.geo import elevation_profile_service as svc
from app.domains.geo.models import ElevationProfileCache
from app.domains.geo.elevation_profile_cache import (
    build_cache_key,
    build_source_identity,
    read_cached_profile,
    write_cached_profile,
)

GEOM = {"type": "LineString", "coordinates": [[-62.7, -32.6], [-62.702, -32.6]]}
PAYLOAD = {"puntos": [{"distance_m": 0.0, "elevation_m": 120.0}], "length_m": 0.0}

_factory = None


@pytest.fixture
def cache_env(test_engine, monkeypatch):
    """Bind the cache to the test engine: it commits in a session of its own.

    Rows stay behind on purpose — keys are unique per test and the test database
    is dropped with the session.
    """
    global _factory
    _factory = sessionmaker(bind=test_engine)
    monkeypatch.setattr(cache_module, "_session_factory", _factory)
    yield _factory


def _age_row(cache_key: str, days: int) -> None:
    """Push created_at into the past, committed: the prune runs in its own session."""
    with _factory() as session:
        session.execute(
            update(ElevationProfileCache)
            .where(ElevationProfileCache.cache_key == cache_key)
            .values(created_at=datetime.now(timezone.utc) - timedelta(days=days))
        )
        session.commit()


def _dem(tmp_path):
    path = tmp_path / "dem_filled.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-62.71, -32.59, 0.01, 0.01),
        nodata=-999999,
    ) as dst:
        dst.write(np.array([[120.0, 121.0], [119.0, 118.0]], dtype="float32"), 1)
    return path


def test_write_then_read_round_trips_the_payload(cache_env) -> None:
    identity = "series:v1|dem_filled:1:1|mde_ar:absent"
    key = build_cache_key(GEOM, identity)

    assert read_cached_profile(key) is None

    write_cached_profile(cache_key=key, source_identity=identity, payload=PAYLOAD)

    assert read_cached_profile(key) == PAYLOAD


def test_two_writers_for_the_same_key_both_land(cache_env) -> None:
    """R2-001: an atomic upsert, so a concurrent pair cannot raise or lose a write."""
    identity = "series:v1|dem_filled:race:1|mde_ar:absent"
    key = build_cache_key(GEOM, identity)
    newer = {**PAYLOAD, "length_m": 1.0}

    write_cached_profile(cache_key=key, source_identity=identity, payload=PAYLOAD)
    write_cached_profile(cache_key=key, source_identity=identity, payload=newer)

    assert read_cached_profile(key) == newer


def test_write_prunes_rows_older_than_the_retention_window(cache_env) -> None:
    stale_identity = "series:v1|dem_filled:old:1|mde_ar:absent"
    stale_key = build_cache_key(GEOM, stale_identity)
    write_cached_profile(cache_key=stale_key, source_identity=stale_identity, payload=PAYLOAD)
    _age_row(stale_key, days=120)

    fresh_identity = "series:v1|dem_filled:new:2|mde_ar:absent"
    fresh_key = build_cache_key(GEOM, fresh_identity)
    write_cached_profile(cache_key=fresh_key, source_identity=fresh_identity, payload=PAYLOAD)

    assert read_cached_profile(stale_key) is None
    assert read_cached_profile(fresh_key) == PAYLOAD


def test_second_identical_call_is_a_hit_and_does_not_resample(
    cache_env, db_session_factory, monkeypatch, tmp_path
) -> None:
    dem = _dem(tmp_path)
    calls = {"n": 0}

    def fake_profile(_linea, _path):
        calls["n"] += 1
        return {
            "puntos": [{"distance_m": 0.0, "elevation_m": 120.0}],
            "_vertices_xy": [(-62.7, -32.6)],
        }

    monkeypatch.setattr(svc, "_resultados", lambda _db, _area_id: [{"filled_dem": str(dem)}])
    monkeypatch.setattr(svc, "resolver_dem_filled", lambda _rows: str(dem))
    monkeypatch.setattr(svc, "perfil_desde_linea_metrica", fake_profile)

    db = db_session_factory()
    first = svc.perfil_de_geojson(db, geometry=GEOM)
    second = svc.perfil_de_geojson(db, geometry=GEOM)

    assert first["cache"] == "miss"
    assert second["cache"] == "hit"
    assert calls["n"] == 1, "the cached call must not touch the sampler"
    assert second["puntos"] == first["puntos"]
    assert second["puntos"][0]["lon"] == pytest.approx(-62.7)
    assert "_vertices_xy" not in second


def test_new_dem_run_invalidates_the_stored_profile(
    cache_env, db_session_factory, monkeypatch, tmp_path
) -> None:
    dem = _dem(tmp_path)
    calls = {"n": 0}

    def fake_profile(_linea, _path):
        calls["n"] += 1
        return {
            "puntos": [{"distance_m": 0.0, "elevation_m": 120.0 + calls["n"]}],
            "_vertices_xy": [(-62.7, -32.6)],
        }

    monkeypatch.setattr(svc, "_resultados", lambda _db, _area_id: [{"filled_dem": str(dem)}])
    monkeypatch.setattr(svc, "resolver_dem_filled", lambda _rows: str(dem))
    monkeypatch.setattr(svc, "perfil_desde_linea_metrica", fake_profile)

    db = db_session_factory()
    assert svc.perfil_de_geojson(db, geometry=GEOM)["cache"] == "miss"
    assert svc.perfil_de_geojson(db, geometry=GEOM)["cache"] == "hit"

    # A new DEM run rewrites the raster: same path, new content.
    dem.write_bytes(dem.read_bytes() + b"# new run")

    third = svc.perfil_de_geojson(db, geometry=GEOM)
    assert third["cache"] == "miss", "a rewritten DEM must not be served from cache"
    assert calls["n"] == 2


def test_gee_comparison_is_never_served_from_the_cache(
    cache_env, db_session_factory, monkeypatch, tmp_path
) -> None:
    dem = _dem(tmp_path)
    calls = {"n": 0}

    def fake_profile(_linea, _path):
        calls["n"] += 1
        return {
            "puntos": [{"distance_m": 0.0, "elevation_m": 120.0}],
            "_vertices_xy": [(-62.7, -32.6)],
        }

    monkeypatch.setattr(svc, "_resultados", lambda _db, _area_id: [{"filled_dem": str(dem)}])
    monkeypatch.setattr(svc, "resolver_dem_filled", lambda _rows: str(dem))
    monkeypatch.setattr(svc, "perfil_desde_linea_metrica", fake_profile)

    db = db_session_factory()
    plain = svc.perfil_de_geojson(db, geometry=GEOM)
    gee_first = svc.perfil_de_geojson(db, geometry=GEOM, compare_dems=True)
    gee_second = svc.perfil_de_geojson(db, geometry=GEOM, compare_dems=True)

    assert plain["cache"] == "miss"
    assert "cache" not in gee_first
    assert "cache" not in gee_second
    assert calls["n"] == 3, "GEE comparisons always recompute"

    identity = build_source_identity(str(dem))
    assert read_cached_profile(build_cache_key(GEOM, identity)) == {
        key: value for key, value in plain.items() if key != "cache"
    }


def _spy_caller_transaction(db) -> list[str]:
    """Record every commit or rollback the caller's own session performs."""
    events: list[str] = []
    event.listen(db, "before_commit", lambda _session: events.append("commit"))
    event.listen(db, "after_rollback", lambda _session: events.append("rollback"))
    return events


def _stage_pending_row(db, cache_key: str) -> None:
    """Work already pending in the caller's transaction, flushed but uncommitted."""
    db.add(ElevationProfileCache(cache_key=cache_key, source_identity="pending", payload={}))
    db.flush()


def _stub_sampling(monkeypatch, dem) -> None:
    """The cache contract is the subject here; rasterio sampling is covered elsewhere."""

    def fake_profile(_linea, _path):
        return {
            "puntos": [{"distance_m": 0.0, "elevation_m": 120.0}],
            "_vertices_xy": [(-62.7, -32.6)],
        }

    monkeypatch.setattr(svc, "_resultados", lambda _db, _area_id: [{"filled_dem": str(dem)}])
    monkeypatch.setattr(svc, "resolver_dem_filled", lambda _rows: str(dem))
    monkeypatch.setattr(svc, "perfil_desde_linea_metrica", fake_profile)


def test_a_failing_cache_read_serves_the_profile_and_spares_the_caller(
    cache_env, db_session_factory, monkeypatch, tmp_path
) -> None:
    """R3-TransactionManagement: a cache read error belongs to the cache, not the caller."""
    dem = _dem(tmp_path)
    _stub_sampling(monkeypatch, dem)

    def boom(*_args, **_kwargs):
        raise RuntimeError("cache read is down")

    monkeypatch.setattr(svc, "read_cached_profile", boom)

    db = db_session_factory()
    _stage_pending_row(db, "pending-after-read-failure")
    events = _spy_caller_transaction(db)

    served = svc.perfil_de_geojson(db, geometry=GEOM)

    assert served["puntos"], "a degraded cache must still serve the profile"
    assert events == [], "the cache must not commit or roll back the caller's session"
    assert db.get(ElevationProfileCache, "pending-after-read-failure") is not None, (
        "the caller's pending work must survive a cache failure"
    )


def test_a_failing_cache_write_serves_the_profile_and_spares_the_caller(
    cache_env, db_session_factory, monkeypatch, tmp_path
) -> None:
    """The response is already computed when the write fails; it must still be served."""
    dem = _dem(tmp_path)
    _stub_sampling(monkeypatch, dem)

    def boom(**_kwargs):
        raise RuntimeError("cache write is down")

    monkeypatch.setattr(svc, "read_cached_profile", lambda _cache_key: None)
    monkeypatch.setattr(svc, "write_cached_profile", boom)

    db = db_session_factory()
    _stage_pending_row(db, "pending-after-write-failure")
    events = _spy_caller_transaction(db)

    served = svc.perfil_de_geojson(db, geometry=GEOM)

    assert served["cache"] == "miss"
    assert served["puntos"]
    assert events == []
    assert db.get(ElevationProfileCache, "pending-after-write-failure") is not None


def test_a_successful_cache_write_does_not_commit_the_callers_session(
    cache_env, db_session_factory, monkeypatch, tmp_path
) -> None:
    """The cache commits in a session of its own; the caller's transaction stays its own."""
    dem = _dem(tmp_path)
    _stub_sampling(monkeypatch, dem)
    monkeypatch.setattr(svc, "read_cached_profile", lambda _cache_key: None)

    db = db_session_factory()
    _stage_pending_row(db, "pending-after-successful-write")
    events = _spy_caller_transaction(db)

    served = svc.perfil_de_geojson(db, geometry=GEOM)

    assert served["cache"] == "miss"
    assert events == [], "the cache must never commit the caller's session"
    assert db.get(ElevationProfileCache, "pending-after-successful-write") is not None
    identity = build_source_identity(str(dem))
    assert read_cached_profile(build_cache_key(GEOM, identity)) is not None, (
        "the write must have landed in the cache's own session"
    )
