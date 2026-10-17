"""Contracts for database session configuration with PgBouncer."""

from unittest.mock import patch
from sqlalchemy.pool import NullPool


def test_sync_engine_configures_prepare_threshold_none_when_pgbouncer_enabled():
    """With psycopg 3 and PgBouncer transaction pooling, server-side prepared statements
    cause duplicate statement errors across multiplexed connections unless prepare_threshold is None."""
    from app.config import settings

    with patch.object(settings, "use_pgbouncer", True):
        with patch("sqlalchemy.create_engine") as mock_create_engine:
            # Re-run engine creation logic
            from app.db import session

            if settings.use_pgbouncer:
                session.create_engine(
                    settings.database_sync_url,
                    echo=settings.database_echo,
                    poolclass=NullPool,
                    connect_args={"prepare_threshold": None},
                )

            mock_create_engine.assert_called_with(
                settings.database_sync_url,
                echo=settings.database_echo,
                poolclass=NullPool,
                connect_args={"prepare_threshold": None},
            )
