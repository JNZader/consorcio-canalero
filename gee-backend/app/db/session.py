"""SQLAlchemy engine and session factory (sync + async for fastapi-users)."""

import os
import sys
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

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
# asyncpg's default behaviour is to keep a per-connection ``PreparedStatement``
# cache. The statement name lives on a SPECIFIC postgres backend
# connection — when PgBouncer is in transaction-pool mode the next
# transaction is likely to land on a different postgres connection
# that has never seen that name, so the second use raises
# ``InvalidSqlStatementNameError``. Setting both caches to 0 forces
# asyncpg to send fresh SQL on every call. This is slower than
# prepared statements on direct-to-postgres setups (which is why
# we toggle it on a flag, not on by default).
_async_connect_args: dict[str, object] = {}
if settings.use_pgbouncer:
    _async_connect_args["statement_cache_size"] = 0
    _async_connect_args["prepared_statement_cache_size"] = 0

async_engine = create_async_engine(
    _async_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    # Phase 3 / F3-K: matches the sync pool. Same per-process sizing
    # rule: 20+20 on backend uvicorn workers, 5+5 inside celery forks.
    pool_size=_POOL_SIZE,
    max_overflow=_MAX_OVERFLOW,
    connect_args=_async_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
