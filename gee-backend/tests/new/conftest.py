"""
Test fixtures for the new architecture (SQLAlchemy + PostGIS).

Uses a real test database — no mocking for data access.
Each test runs in a transaction that gets rolled back.

Database resolution order:
  1. Docker available → testcontainers spins up PostGIS automatically
  2. Docker unavailable + TEST_DATABASE_URL set → use that (local PostgreSQL)
  3. Neither → skip entire test session with a clear message
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def _try_testcontainers() -> tuple[str | None, object | None]:
    """Try to start a PostGIS container. Returns (url, container) or (None, None)."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        return None, None

    try:
        container = PostgresContainer(
            image="postgis/postgis:16-3.4",
            username="test",
            password="test",
            dbname="test_consorcio",
            driver="psycopg2",
        )
        container.start()
        return container.get_connection_url(), container
    except Exception:
        # Docker not running, permission error, image pull failure, etc.
        return None, None


def _resolve_database_url() -> tuple[str, object | None]:
    """Pick the best available database URL or abort."""
    url, container = _try_testcontainers()
    if url:
        return url, container

    fallback = os.environ.get("TEST_DATABASE_URL")
    if fallback:
        return fallback, None

    pytest.exit(
        "\n\nNo database available for tests.\n"
        "  Option 1: Start Docker (testcontainers auto-spins PostGIS).\n"
        "  Option 2: Set TEST_DATABASE_URL to a local PostgreSQL+PostGIS.\n",
        returncode=1,
    )
    raise SystemExit(1)  # unreachable — satisfies type checker


# ---------------------------------------------------------------------------
# Resolve DB URL and set env vars BEFORE importing app modules
# ---------------------------------------------------------------------------
_db_url, _container = _resolve_database_url()

os.environ.update(
    {
        "DATABASE_URL": _db_url,
        "DATABASE_ECHO": "false",
        "JWT_SECRET": "test-jwt-secret-at-least-32-characters-long-for-testing",
        "REDIS_URL": "redis://localhost:6379/1",
        "CORS_ORIGINS": "http://localhost:3000,http://localhost:5173",
        "DEBUG": "true",
        "FRONTEND_URL": "http://localhost:5173",
    }
)

from app.db.base import Base  # noqa: E402


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine and tables once per session."""
    from app.config import settings

    engine = create_engine(settings.database_url, echo=False)

    # Create PostGIS extension and all tables
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()

    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()

    # Stop the testcontainer (if any) after engine disposal
    if _container is not None:
        _container.stop()


@pytest.fixture(scope="function")
def db(test_engine) -> Session:
    """
    Database session that rolls back after each test.
    Ensures test isolation without needing to clean up data.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def db_session_factory(test_engine):
    """Session factory for dependency injection override."""
    connection = test_engine.connect()
    transaction = connection.begin()
    TestSessionLocal = sessionmaker(bind=connection)

    yield TestSessionLocal

    transaction.rollback()
    connection.close()
