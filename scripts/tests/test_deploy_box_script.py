"""Locks for scripts/deploy-box.sh. The box script is the deploy, not a library."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "deploy-box.sh"
TEXT = SCRIPT.read_text()


def test_defaults_refuse_a_dirty_tree_and_never_run_alembic():
    assert 'ALLOW_DIRTY_TREE="${ALLOW_DIRTY_TREE:-0}"' in TEXT
    assert "alembic upgrade" not in TEXT
    assert "alembic" in TEXT


def test_compose_from_main_is_not_what_gets_deployed():
    assert "git reset --hard origin/main" in TEXT
    assert 'cp -p "$COMPOSE_SAVED" "$COMPOSE_FILE"' in TEXT
    assert "docker compose up -d --build" in TEXT
    for service in ("backend", "worker", "celery-beat", "geo-worker"):
        assert service in TEXT


def test_backup_happens_before_the_reset():
    main = TEXT.split("main() {", 1)[1]
    assert main.index("backup_database") < main.index("reset_tree_and_restore_compose")


def test_a_non_consorcio_container_name_aborts():
    assert "container_name:" in TEXT
    assert "!/^consorcio-/" in TEXT
    assert "hay containers biogas-*" in TEXT


def test_checkout_umask_keeps_the_bind_mount_readable():
    reset = TEXT.split("reset_tree_and_restore_compose() {", 1)[1].split("build_services() {", 1)[0]
    assert reset.index("umask 022") < reset.index("git reset --hard origin/main")
    assert reset.index("git reset --hard origin/main") < reset.index("umask 077")
    assert "umask 077" in TEXT.split("reset_tree_and_restore_compose() {", 1)[0]


def test_health_uses_the_container_probe_not_localhost():
    assert "python -m app.healthcheck" in TEXT
    assert "127.0.0.1:8000/health" not in TEXT.split("wait_for_health()", 1)[1]
