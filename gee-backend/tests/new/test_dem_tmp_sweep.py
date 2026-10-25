"""GEO-5 regression: stale ``*.tmp.tif`` DEM downloads must be swept.

``download_dem_impl`` streams the GEE GeoTIFF to ``<output>.tmp.tif`` and only
unlinks it on the success path; a worker OOM/SIGKILL mid-download orphans a
full-size temp DEM and nothing anywhere removed them — repeated crashes
exhaust the geo-worker disk and every tile 404s.

The sweep runs at DEM-pipeline start (``prepare_full_pipeline_dem_impl``,
under the per-area advisory lock) with a conservative mtime threshold: the
download itself is bounded by the 300 s GEE fetch, so 1 h covers clock skew
and worker restarts with a 12x margin while never touching a live download.
These tests pin the sweep's contract directly.
"""

from __future__ import annotations

import os
import time

from app.domains.geo.processing_wbt_support import sweep_stale_dem_tmp_impl

_MAX_AGE = 3600.0


def _age_to(path, now: float, age_seconds: float) -> None:
    stamp = now - age_seconds
    os.utime(path, (stamp, stamp))


def test_stale_tmp_tif_deleted_fresh_kept(tmp_path) -> None:
    """RED pre-fix: no sweep existed, so the stale file survived forever."""
    stale = tmp_path / "dem_raw.tmp.tif"
    stale.write_bytes(b"x" * 16)
    _age_to(stale, time.time(), 2 * _MAX_AGE)  # two hours old

    fresh = tmp_path / "dem_utm.tmp.tif"
    fresh.write_bytes(b"x" * 16)  # in-flight download, seconds old

    deleted = sweep_stale_dem_tmp_impl(tmp_path, max_age_seconds=_MAX_AGE)

    assert not stale.exists(), "a 2 h-old orphaned tmp DEM must be swept"
    assert fresh.exists(), "a fresh tmp DEM (possible live download) must survive"
    assert deleted == [str(stale)]


def test_boundary_file_exactly_at_threshold_is_swept(tmp_path) -> None:
    """Staleness is `age >= max_age`: a file exactly at the threshold is stale."""
    boundary = tmp_path / "dem_raw.tmp.tif"
    boundary.write_bytes(b"x" * 16)
    now = 1_000_000.0
    _age_to(boundary, now, _MAX_AGE)  # exactly 1 h old

    deleted = sweep_stale_dem_tmp_impl(tmp_path, max_age_seconds=_MAX_AGE, now_fn=lambda: now)

    assert not boundary.exists()
    assert deleted == [str(boundary)]


def test_only_the_exact_tmp_pattern_is_touched(tmp_path) -> None:
    """Old regular rasters, non-tmp files and nested dirs are none of our business."""
    regular = tmp_path / "dem_raw.tif"  # final output, same prefix, no .tmp
    regular.write_bytes(b"x" * 16)
    _age_to(regular, time.time(), 24 * _MAX_AGE)

    other_suffix = tmp_path / "basins.tmp"  # .tmp but not .tmp.tif
    other_suffix.write_bytes(b"x" * 16)
    _age_to(other_suffix, time.time(), 24 * _MAX_AGE)

    nested_dir = tmp_path / "output"
    nested_dir.mkdir()
    nested = nested_dir / "hand.tmp.tif"  # sweep is single-level by design
    nested.write_bytes(b"x" * 16)
    _age_to(nested, time.time(), 24 * _MAX_AGE)

    deleted = sweep_stale_dem_tmp_impl(tmp_path, max_age_seconds=_MAX_AGE)

    assert deleted == []
    assert regular.exists()
    assert other_suffix.exists()
    assert nested.exists()


def test_missing_directory_is_not_an_error(tmp_path) -> None:
    assert sweep_stale_dem_tmp_impl(tmp_path / "nope") == []


# ── Wiring: the sweep runs at full-DEM-pipeline start, under the area lock ─────


def _run_pipeline(monkeypatch, tmp_path, *, acquired: bool):
    """Drive run_full_dem_pipeline with a recording lock, sweep and impl."""
    import contextlib
    from unittest.mock import MagicMock

    import app.domains.geo.tasks as tasks_mod

    calls: list[str] = []

    @contextlib.contextmanager
    def fake_lock(_area_id):
        calls.append("lock")
        yield acquired

    sweep = MagicMock(side_effect=lambda *a, **k: calls.append("sweep") or [])

    def _impl(**_kwargs):
        calls.append("impl")
        return {"job_id": None, "status": "completed", "outputs": {}}

    impl = MagicMock(side_effect=_impl)
    monkeypatch.setattr(tasks_mod, "_area_execution_lock", fake_lock)
    monkeypatch.setattr(tasks_mod, "sweep_stale_dem_tmp_impl", sweep)
    monkeypatch.setattr(tasks_mod, "run_full_dem_pipeline_impl", impl)
    result = tasks_mod.run_full_dem_pipeline(area_id="area1")
    return result, calls, sweep, impl


def test_full_dem_pipeline_sweeps_tmp_at_start_under_lock(monkeypatch, tmp_path) -> None:
    result, calls, sweep, _impl = _run_pipeline(monkeypatch, tmp_path, acquired=True)

    assert result["status"] == "completed"
    sweep.assert_called_once()  # sweep happens while the lock is held…
    assert calls == ["lock", "sweep", "impl"]  # …before the pipeline impl runs


def test_no_sweep_when_the_area_lock_is_not_acquired(monkeypatch, tmp_path) -> None:
    result, calls, sweep, impl = _run_pipeline(monkeypatch, tmp_path, acquired=False)

    assert result["status"] == "skipped"
    sweep.assert_not_called()  # a skipped run must not touch the filesystem
    impl.assert_not_called()
    assert calls == ["lock"]
