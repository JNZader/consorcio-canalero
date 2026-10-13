"""One PostgreSQL database per pytest-xdist worker.

Workers are separate processes that would otherwise share ``TEST_DATABASE_URL``
and race on DDL. Each worker id (``gw0``, ``gw1``, ...) gets its own database
on the same server. A process that started its own testcontainer already has
a private server, so the caller skips this helper in that case.
"""

from __future__ import annotations

import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

_WORKER_ID = re.compile(r"gw\d+")
_DB_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")


def worker_database_name(database: str, worker_id: str) -> str:
    """Return the database name reserved for this worker. Rejects anything else."""
    if not _WORKER_ID.fullmatch(worker_id):
        raise ValueError(f"id de worker pytest-xdist no reconocido: {worker_id!r}")
    name = f"{database}_{worker_id}"
    if not _DB_NAME.fullmatch(name):
        raise ValueError(f"nombre de base no seguro para el worker: {name!r}")
    return name


def isolate_worker_database(base_url: str, worker_id: str | None) -> tuple[str, str | None]:
    """Create ``{db}_{worker}`` and return its URL. No-op without a worker id."""
    if not worker_id:
        return base_url, None
    parsed = make_url(base_url)
    database = parsed.database or "test_consorcio"
    worker_db = worker_database_name(database, worker_id)
    admin = parsed.set(database="postgres")
    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{worker_db}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{worker_db}"'))
    finally:
        engine.dispose()
    return parsed.set(database=worker_db).render_as_string(hide_password=False), worker_db


def drop_worker_database(base_url: str, worker_db: str | None) -> None:
    """Drop the worker database. Safe to call when isolation was a no-op."""
    if not worker_db or not _DB_NAME.fullmatch(worker_db):
        return
    admin = make_url(base_url).set(database="postgres")
    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{worker_db}" WITH (FORCE)'))
    finally:
        engine.dispose()
