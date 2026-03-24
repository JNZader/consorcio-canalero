"""
Test fixtures for the new architecture (SQLAlchemy + PostGIS).

Uses a real test database — no mocking for data access.
Each test runs in a transaction that gets rolled back.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Set test env vars BEFORE importing app modules
os.environ.update(
    {
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://consorcio:consorcio_dev@localhost:5432/consorcio_test",
        ),
        "DATABASE_ECHO": "false",
        "JWT_SECRET": "test-jwt-secret-at-least-32-characters-long-for-testing",
        "REDIS_URL": "redis://localhost:6379/1",
        "CORS_ORIGINS": "http://localhost:3000,http://localhost:5173",
        "DEBUG": "true",
        "FRONTEND_URL": "http://localhost:5173",
    }
)

from app.db.base import Base


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
