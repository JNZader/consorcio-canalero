"""Contracts for database session configuration with PgBouncer."""

import importlib
from unittest.mock import patch
from sqlalchemy.pool import NullPool
from app.config import settings


def test_sync_engine_configures_prepare_threshold_none_when_pgbouncer_enabled():
    """With psycopg 3 and PgBouncer transaction pooling, server-side prepared statements
    cause duplicate statement errors across multiplexed connections unless prepare_threshold is None."""
    try:
        with patch.object(settings, "use_pgbouncer", True):
            with (
                patch("sqlalchemy.create_engine") as mock_sync,
                patch("sqlalchemy.ext.asyncio.create_async_engine"),
                patch("sqlalchemy.event.listen"),
            ):
                from app.db import session

                importlib.reload(session)
                assert mock_sync.call_args.kwargs["connect_args"] == {"prepare_threshold": None}
                assert mock_sync.call_args.kwargs["poolclass"] is NullPool
    finally:
        from app.db import session

        importlib.reload(session)
