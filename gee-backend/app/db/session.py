"""SQLAlchemy engine and session factory (sync + async for fastapi-users)."""

import os
import sys
from collections.abc import AsyncGenerator, Generator
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings


# Phase 3.1 / post-3vr: celery-worker imports this same module per
# forked process (prefork pool). The Phase 3 sizing was correct for
# the backend (2 workers × 40 connections = 80) but doubled when
# celery-worker (2 forks × 40 = 80) joined the same shared postgres,
# pushing the stack to 160 against a typical max_connections=100. The
# Celery path is I/O-light — one connection per task — so a much
# smaller pool is plenty.
#
# Phase 3.2 / post-3vr again: only inspect ``sys.argv[0]`` (the
# executable) so ``pytest tests/celery_something`` doesn't false-
# positive into the Celery pool. ``celery`` workers always invoke
# the ``celery`` binary directly (or ``python -m celery``); in the
# ``-m`` case ``sys.argv[0]`` becomes the ``runpy`` shim's path
# which still ends in ``/celery/__main__.py``, so the basename
# check below handles both.
_argv0_basename = os.path.basename(sys.argv[0] if sys.argv else "").lower()
_IS_CELERY_PROCESS = _argv0_basename in {"celery", "celery.exe", "__main__.py"} and any(
    "celery" in arg for arg in sys.argv[:3]
)
_POOL_SIZE = 5 if _IS_CELERY_PROCESS else 20
_MAX_OVERFLOW = 5 if _IS_CELERY_PROCESS else 20


# --- Sync engine (for domain services, repositories, migrations) ---
#
# Phase 4 / F4-F: when PgBouncer transaction-pool is in front of postgres,
# SQLAlchemy's own connection pool is redundant (PgBouncer is already
# multiplexing). Worse, holding pooled connections inflates PgBouncer's
# ``max_client_conn`` budget unnecessarily. Switch to ``NullPool``
# (per the SA docs https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#asyncpg-prepared-statement-name)
# so each request opens a fresh PgBouncer client connection that
# returns to the pool the moment the work is done.

if settings.use_pgbouncer:
    engine = create_engine(
        settings.database_url,
        echo=settings.database_echo,
        poolclass=NullPool,
    )
else:
    engine = create_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
        # See module-level note on ``_IS_CELERY_PROCESS`` — backend keeps
        # the 20+20 pool sized for FastAPI's 40-thread default; celery
        # forks see 5+5 because they only hold one connection per task.
        pool_size=_POOL_SIZE,
        max_overflow=_MAX_OVERFLOW,
    )

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a sync database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Async engine (required by fastapi-users) ---

_async_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

# Phase 4 / F4-F: PgBouncer transaction-pool compatibility.
#
# Direct-to-postgres: asyncpg's per-connection ``PreparedStatement``
# cache is a net win — fewer round-trips on hot queries.
#
# PgBouncer transaction mode: two distinct problems.
#
#   1. ``statement_cache_size=0`` alone is NOT enough. SQLAlchemy's
#      asyncpg dialect ALWAYS calls ``connection.prepare()`` under the
#      hood (statement_cache_size only governs whether asyncpg holds
#      a reference to the result). PgBouncer multiplexes the next
#      transaction to a possibly-fresh postgres backend, so the
#      enumerated default prepared-statement name collides →
#      ``DuplicatePreparedStatementError`` or
##     ``InvalidSqlStatementNameError`` in the wild.
#      Fix: pass ``prepared_statement_name_func`` to generate a
#      unique name per call. (SA docs, post-#6467.)
#
#   2. SQLAlchemy's connection pool layered over PgBouncer's pool is
#      redundant and inflates ``max_client_conn`` accounting.
#      Fix: ``poolclass=NullPool`` — each request opens a fresh
#      PgBouncer client connection and releases it on close.
#
# Both fixes are interlocked: NullPool without the name_func still
# blows up; name_func without NullPool keeps the pool active and is
# wasteful but functional.
_async_connect_args: dict[str, object] = {}
if settings.use_pgbouncer:
    _async_connect_args["statement_cache_size"] = 0
    _async_connect_args["prepared_statement_name_func"] = (
        lambda: f"__asyncpg_{uuid4()}__"
    )

if settings.use_pgbouncer:
    async_engine = create_async_engine(
        _async_url,
        echo=settings.database_echo,
        poolclass=NullPool,
        connect_args=_async_connect_args,
    )
else:
    async_engine = create_async_engine(
        _async_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
        # Phase 3 / F3-K: matches the sync pool. Same per-process sizing
        # rule: 20+20 on backend uvicorn workers, 5+5 inside celery forks.
        pool_size=_POOL_SIZE,
        max_overflow=_MAX_OVERFLOW,
    )

AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
