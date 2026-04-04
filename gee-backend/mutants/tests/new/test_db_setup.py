"""Smoke tests to verify database and model setup."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.base import Base


class TestDatabaseSetup:
    """Verify PostgreSQL + PostGIS connection and schema creation."""

    def test_database_connection(self, db: Session):
        """Database is reachable and responds to queries."""
        result = db.execute(text("SELECT 1"))
        assert result.scalar() == 1

    def test_postgis_extension(self, db: Session):
        """PostGIS extension is installed and working."""
        result = db.execute(text("SELECT PostGIS_Version()"))
        version = result.scalar()
        assert version is not None
        assert "3." in version  # PostGIS 3.x

    def test_tables_created(self, db: Session):
        """All model tables exist in the database."""
        # Import models to register them with Base
        from app.auth.models import User  # noqa: F401

        table_names = set(Base.metadata.tables.keys())
        assert "users" in table_names

    def test_user_model_crud(self, db: Session):
        """User model can be created and queried."""
        from app.auth.models import User, UserRole

        user = User(
            email="test@example.com",
            hashed_password="fakehash",
            nombre="Test",
            apellido="User",
            role=UserRole.CIUDADANO,
        )
        db.add(user)
        db.flush()

        queried = db.query(User).filter_by(email="test@example.com").first()
        assert queried is not None
        assert queried.nombre == "Test"
        assert queried.role == UserRole.CIUDADANO
        assert queried.id is not None
