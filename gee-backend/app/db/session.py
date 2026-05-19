"""SQLAlchemy engine and session factory (sync + async for fastapi-users)."""

from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# --- Sync engine (for domain services, repositories, migrations) ---

engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    # Phase 3 / F3-K: pool sized for FastAPI's 40-thread default
    # threadpool. The previous (5 + 10 overflow) tripped
    # ``QueuePool limit overflow`` under bursts of ~15 slow
    # endpoints. With 2 uvicorn workers (F3-J), per-process pool is
    # 20 + 20 → total 80 connections across the container; the
    # shared postgres has max_connections=100 minus the biogas stack
    # so we stay within margin.
    pool_size=20,
    max_overflow=20,
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

async_engine = create_async_engine(
    _async_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    # Phase 3 / F3-K: matches the sync pool. Async endpoints
    # (fastapi-users auth + refresh-token rotate) hold a connection
    # for the duration of the request, so an undersized pool serializes
    # logins under load.
    pool_size=20,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
