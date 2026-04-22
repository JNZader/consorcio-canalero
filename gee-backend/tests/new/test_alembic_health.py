"""
Tests for the alembic stamp healthcheck.

Prevents regressions of the phantom-revision class of bugs (e.g. someone stamps
prod with a fabricated ID) — see commits fce8c66 / 95f59db / 3b08635.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.health import check_alembic_health_sync


def _mock_db_returning(version_num):
    """Return a MagicMock Session whose SELECT returns the given version_num."""
    db = MagicMock()
    result = MagicMock()
    row = MagicMock()
    row.__getitem__.side_effect = lambda i: version_num
    result.first.return_value = row
    db.execute.return_value = result
    return db


def _mock_db_empty():
    """Return a MagicMock Session whose SELECT returns no row."""
    db = MagicMock()
    result = MagicMock()
    result.first.return_value = None
    db.execute.return_value = result
    return db


class TestAlembicHealth:
    def test_happy_path_current_rev_is_head(self):
        """Current rev exists AND is a head → healthy + is_head=True."""
        db = _mock_db_returning("7e25b857692b")

        script_dir = MagicMock()
        revision_obj = MagicMock()
        revision_obj.revision = "7e25b857692b"
        script_dir.get_revision.return_value = revision_obj
        script_dir.get_heads.return_value = ["7e25b857692b"]

        with (
            patch("alembic.config.Config"),
            patch(
                "alembic.script.ScriptDirectory.from_config", return_value=script_dir
            ),
        ):
            result = check_alembic_health_sync(db)

        assert result["status"] == "healthy"
        assert result["current_rev"] == "7e25b857692b"
        assert result["is_head"] is True
        assert result["heads"] == ["7e25b857692b"]

    def test_current_rev_exists_but_not_head(self):
        """Current rev exists but is NOT a head → healthy + is_head=False (pending migrations)."""
        db = _mock_db_returning("abc123_old_rev")

        script_dir = MagicMock()
        revision_obj = MagicMock()
        revision_obj.revision = "abc123_old_rev"
        script_dir.get_revision.return_value = revision_obj
        script_dir.get_heads.return_value = ["7e25b857692b"]

        with (
            patch("alembic.config.Config"),
            patch(
                "alembic.script.ScriptDirectory.from_config", return_value=script_dir
            ),
        ):
            result = check_alembic_health_sync(db)

        assert result["status"] == "healthy"
        assert result["current_rev"] == "abc123_old_rev"
        assert result["is_head"] is False
        assert result["heads"] == ["7e25b857692b"]

    def test_phantom_revision_raises_commanderror(self):
        """Current rev does NOT exist → unhealthy. alembic raises CommandError for missing revs."""
        db = _mock_db_returning("757bbf64faae")  # the historical phantom rev

        script_dir = MagicMock()
        script_dir.get_revision.side_effect = Exception(
            "Can't locate revision identified by '757bbf64faae'"
        )

        with (
            patch("alembic.config.Config"),
            patch(
                "alembic.script.ScriptDirectory.from_config", return_value=script_dir
            ),
        ):
            result = check_alembic_health_sync(db)

        assert result["status"] == "unhealthy"
        assert "757bbf64faae" in result["error"]
        assert result["current_rev"] == "757bbf64faae"

    def test_phantom_revision_returns_none(self):
        """Current rev returns None (alternate failure mode) → unhealthy."""
        db = _mock_db_returning("ghostrev")

        script_dir = MagicMock()
        script_dir.get_revision.return_value = None

        with (
            patch("alembic.config.Config"),
            patch(
                "alembic.script.ScriptDirectory.from_config", return_value=script_dir
            ),
        ):
            result = check_alembic_health_sync(db)

        assert result["status"] == "unhealthy"
        assert "ghostrev" in result["error"]
        assert result["current_rev"] == "ghostrev"

    def test_alembic_version_table_empty(self):
        """alembic_version exists but is empty → unhealthy."""
        db = _mock_db_empty()

        result = check_alembic_health_sync(db)

        assert result["status"] == "unhealthy"
        assert "empty" in result["error"].lower()

    def test_db_query_failure(self):
        """DB query fails (e.g. table missing) → unhealthy with error surfaced."""
        db = MagicMock()
        db.execute.side_effect = Exception('relation "alembic_version" does not exist')

        result = check_alembic_health_sync(db)

        assert result["status"] == "unhealthy"
        assert "alembic_version" in result["error"]

    def test_script_tree_load_failure(self):
        """Script tree fails to load → unhealthy, current_rev preserved."""
        db = _mock_db_returning("7e25b857692b")

        with patch(
            "alembic.script.ScriptDirectory.from_config",
            side_effect=Exception("alembic.ini not found"),
        ):
            result = check_alembic_health_sync(db)

        assert result["status"] == "unhealthy"
        assert result["current_rev"] == "7e25b857692b"
        assert (
            "alembic" in result["error"].lower() or "script" in result["error"].lower()
        )


class TestAlembicHealthIntegration:
    """Integration: point at the real alembic.ini + a real DB with a valid stamp."""

    def test_real_alembic_tree_with_real_db(self, db):
        """
        Uses the real test DB (which has no alembic_version row because tables are
        created from metadata, not migrations). Validates the function handles
        the empty case gracefully.
        """
        # The test DB is built from Base.metadata, so alembic_version table is
        # missing. The function should report unhealthy (DB query failure).
        result = check_alembic_health_sync(db)
        assert result["status"] == "unhealthy"

    def test_real_alembic_tree_with_stamped_db(self, db):
        """Stamp the test DB with the current head revision and verify healthy."""
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import text

        from app.core.health import ALEMBIC_INI_PATH

        # Resolve the current head dynamically so the test remains valid as
        # migrations are added.
        cfg = Config(str(ALEMBIC_INI_PATH))
        current_head = ScriptDirectory.from_config(cfg).get_current_head()
        assert current_head, "Expected alembic to have a single head"

        # Create alembic_version table and insert the real head stamp.
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        db.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
            {"rev": current_head},
        )
        db.flush()

        result = check_alembic_health_sync(db)
        assert result["status"] == "healthy", f"Expected healthy, got: {result}"
        assert result["current_rev"] == current_head
        assert result["is_head"] is True
        assert current_head in result["heads"]

    def test_real_alembic_tree_with_phantom_stamp(self, db):
        """Stamp the test DB with a fabricated revision and verify unhealthy."""
        from sqlalchemy import text

        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        db.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('757bbf64faae')")
        )
        db.flush()

        result = check_alembic_health_sync(db)
        assert result["status"] == "unhealthy", f"Expected unhealthy, got: {result}"
        assert result["current_rev"] == "757bbf64faae"
        assert "757bbf64faae" in result["error"]


@pytest.mark.asyncio
async def test_async_wrapper_handles_exceptions():
    """The async wrapper catches SessionLocal() failures and returns unhealthy."""
    from app.core.health import check_alembic_health

    with patch("app.core.health.SessionLocal", side_effect=Exception("db boom")):
        result = await check_alembic_health()

    assert result["status"] == "unhealthy"
    assert result["error"] == "alembic_check_failed"
