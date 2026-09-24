"""Unit contracts for the Celery Beat process liveness probe."""

from __future__ import annotations

from pathlib import Path

from app import beat_healthcheck


def test_beat_process_alive_requires_celery_and_beat(tmp_path: Path) -> None:
    (tmp_path / "1").mkdir()
    (tmp_path / "1" / "cmdline").write_bytes(b"python\x00-m\x00app.beat_healthcheck\x00")
    (tmp_path / "2").mkdir()
    (tmp_path / "2" / "cmdline").write_bytes(b"celery\x00-A\x00app.core.celery_app\x00worker\x00")
    assert beat_healthcheck.beat_process_alive(tmp_path) is False

    (tmp_path / "3").mkdir()
    (tmp_path / "3" / "cmdline").write_bytes(
        b"celery\x00-A\x00app.core.celery_app\x00beat\x00--loglevel=info\x00"
    )
    assert beat_healthcheck.beat_process_alive(tmp_path) is True


def test_beat_process_alive_skips_unreadable_and_non_pid(tmp_path: Path) -> None:
    (tmp_path / "self").mkdir()
    (tmp_path / "self" / "cmdline").write_bytes(b"celery\x00beat\x00")
    (tmp_path / "9").mkdir()
    # Missing cmdline → OSError path
    assert beat_healthcheck.beat_process_alive(tmp_path) is False


def test_main_exit_codes(monkeypatch) -> None:
    monkeypatch.setattr(beat_healthcheck, "beat_process_alive", lambda: True)
    assert beat_healthcheck.main() == 0
    monkeypatch.setattr(beat_healthcheck, "beat_process_alive", lambda: False)
    assert beat_healthcheck.main() == 1
