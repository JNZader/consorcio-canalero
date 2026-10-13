"""DB-03 / DB-09: recent revisions downgrade, and the history is not squashed.

``zz_audit_v6_db`` already has a SQL round-trip in
``test_audit_v6_db_migration.py``. This module executes the imagery
revisions that sit just under that head (they had ``downgrade()`` and no
test) and checks the chain is still a long mainline.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.operations import Operations
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.core.health import ALEMBIC_INI_PATH
from tests.new.conocimiento.test_rag_migrations import _create_throwaway_database, _drop_database

RECENT = ("lluvia_ext_003", "lluvia_ext_004", "lluvia_ext_005", "lluvia_ext_006")
MODULES = {
    "lluvia_ext_003": "app.db.migrations.versions.lluvia_ext_003_imagery_candidates",
    "lluvia_ext_004": "app.db.migrations.versions.lluvia_ext_004_shortlist_rank12",
    "lluvia_ext_005": "app.db.migrations.versions.lluvia_ext_005_pre_post_slots",
    "lluvia_ext_006": "app.db.migrations.versions.lluvia_ext_006_landsat9",
}


def _constraint_def(conn, name: str) -> str | None:
    return conn.execute(
        text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :name"),
        {"name": name},
    ).scalar()


@pytest.fixture
def imagery_db():
    from app.config import settings

    fresh_url, dbname = _create_throwaway_database(settings.database_url)
    engine = create_engine(fresh_url)
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_database(settings.database_url, dbname)


def _run(engine, direction: str, revisions: tuple[str, ...]) -> None:
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            for revision in revisions:
                module = importlib.import_module(MODULES[revision])
                getattr(module, direction)()


def test_recent_imagery_revisions_downgrade_to_the_parent_table(imagery_db) -> None:
    _run(imagery_db, "upgrade", RECENT)
    with imagery_db.connect() as conn:
        sensor = _constraint_def(conn, "ck_rainfall_imagery_candidate_sensor")
        assert sensor is not None and "landsat9" in sensor
        assert inspect(imagery_db).has_table("rainfall_event_imagery_candidate")
        columns = {
            column["name"]
            for column in inspect(imagery_db).get_columns("rainfall_event_imagery_candidate")
        }
        assert "slot" in columns

    _run(imagery_db, "downgrade", tuple(reversed(RECENT)))

    assert not inspect(imagery_db).has_table("rainfall_event_imagery_candidate")


def test_downgrade_of_landsat9_restores_the_previous_sensor_check(imagery_db) -> None:
    _run(imagery_db, "upgrade", RECENT)
    _run(imagery_db, "downgrade", ("lluvia_ext_006",))
    with imagery_db.connect() as conn:
        sensor = _constraint_def(conn, "ck_rainfall_imagery_candidate_sensor")
    assert sensor is not None
    assert "landsat9" not in sensor
    assert "landsat8" in sensor


def test_migration_history_is_not_squashed() -> None:
    versions = Path(__file__).resolve().parents[2] / "app" / "db" / "migrations" / "versions"
    scripts = [path for path in versions.glob("*.py") if path.name != "__init__.py"]
    assert len(scripts) >= 80

    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI_PATH)))
    heads = list(script.get_heads())
    assert len(heads) == 1, heads
    mainline = {revision.revision for revision in script.iterate_revisions(heads[0], "base")}
    assert {
        "zz_audit_v6_db",
        "lluvia_ext_006",
        "lluvia_ext_005",
        "lluvia_ext_004",
        "lluvia_ext_003",
    } <= mainline
    audit = script.get_revision("zz_audit_v6_db")
    assert audit is not None
    assert audit.down_revision == "lluvia_ext_006"
