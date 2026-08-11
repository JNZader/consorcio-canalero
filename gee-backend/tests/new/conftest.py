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
        # Normalize URL: strip driver suffix so session.py's async conversion
        # (postgresql:// → postgresql+asyncpg://) works correctly.
        url = container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        return url, container
    except Exception:
        # Docker not running, permission error, image pull failure, etc.
        return None, None


def _resolve_database_url() -> tuple[str, object | None]:
    """Pick the best available database URL or abort.

    TEST_DATABASE_URL wins over testcontainers: spinning a container when the
    developer (or CI) already pointed us at a database wastes ~5s per pytest
    invocation and, before the atexit hook below, leaked one container per run.
    Under mutation testing — which re-invokes pytest once per mutant — that was
    a container bomb.
    """
    fallback = os.environ.get("TEST_DATABASE_URL")
    if fallback:
        return fallback, None

    url, container = _try_testcontainers()
    if url:
        return url, container

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


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001 — pytest hook signature
    """Stop the testcontainer even when no test requested ``test_engine``.

    The fixture's teardown only runs if something used it, so a DB-free run
    (the imagery tests need no database at all) used to leave one orphan
    container per pytest invocation. Under mutation testing, which re-invokes
    pytest once per mutant, that is a container bomb. Idempotent: stopping an
    already-stopped container is a no-op.
    """
    if _container is not None:
        try:
            _container.stop()
        except Exception:  # pragma: no cover — teardown must never fail a run
            pass


os.environ.update(
    {
        "DATABASE_URL": _db_url,
        "DATABASE_ECHO": "false",
        "JWT_SECRET": "test-jwt-secret-at-least-32-characters-long-for-testing",
        "REDIS_URL": "redis://localhost:6379/1",
        "CORS_ORIGINS": "http://localhost:3000,http://localhost:5173",
        "DEBUG": "true",
        "FRONTEND_URL": "http://localhost:5173",
        # Phase 4 / F4-D: writable photo path for the TestClient-based
        # auth-gate tests. The production default ``/app/uploads`` is
        # not writable from a local dev shell.
        "UPLOADS_ROOT": "/tmp/consorcio-test-uploads",
    }
)

from app.db.base import Base  # noqa: E402

# Eagerly import every model module so ``Base.metadata`` knows about
# every table BEFORE ``create_all`` runs in the ``test_engine``
# fixture. Without this, models that aren't transitively imported by
# ``app.main`` (e.g. ``EmailCode`` from F5-E) miss the create_all
# pass and their tables vanish from the test schema.
#
# ``intelligence.models`` (``zonas_operativas``) is required here even
# though nothing in this eager list references it directly: it is the
# target of an FK column on ``app.domains.geo.models.FloodLabel``
# (``zonas_operativas.id``). ``Base.metadata.create_all``'s dependency
# sort resolves that FK by table name against ``Base.metadata`` at
# call time, so if ``geo.models`` gets imported (by a test body, e.g.
# via ``rainfall.repository``'s own ``GeoApprovedZoning`` import) BEFORE
# ``intelligence.models`` is ever imported by anything, the sort raises
# ``NoReferencedTableError`` -- this is exactly the collection-order
# accident LI1-001 (review-ledger.md) surfaced when standalone runs of
# ``test_rainfall_backfill.py`` started requesting the ``db`` fixture:
# its first test (no ``db``) imports ``tasks`` -> ``repository`` ->
# ``geo.models`` in its body before the *second* test's ``db`` fixture
# triggers this module's ``create_all()``.
from app.auth import email_codes as _email_codes_model  # noqa: F401, E402
from app.domains.geo.intelligence import models as _geo_intelligence_models  # noqa: F401, E402
from app.domains.geo.rainfall import models as _rainfall_models  # noqa: F401, E402
from app.domains.settings import models as _settings_models  # noqa: F401, E402
from app.shared import audit_log as _audit_log_model  # noqa: F401, E402
from app.shared import celery_outbox as _celery_outbox_model  # noqa: F401, E402


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
