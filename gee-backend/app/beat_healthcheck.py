"""Dependency-free liveness probe for Celery Beat containers.

The backend image HEALTHCHECK probes HTTP ``/live`` on :8000. Beat does not
run Uvicorn, so that probe always fails and marks a working scheduler
unhealthy. This module only checks that a ``celery … beat`` process is alive
via ``/proc`` — stdlib only, no curl/wget/pgrep.
"""

from __future__ import annotations

import pathlib


def beat_process_alive(proc_root: pathlib.Path | None = None) -> bool:
    """Return whether a Celery Beat process is visible under ``/proc``."""
    root = pathlib.Path("/proc") if proc_root is None else proc_root
    try:
        entries = root.iterdir()
    except OSError:
        return False

    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if b"celery" in cmdline and b"beat" in cmdline:
            return True
    return False


def main() -> int:
    """Return the process exit status expected by Docker healthchecks."""
    return 0 if beat_process_alive() else 1


if __name__ == "__main__":
    raise SystemExit(main())
