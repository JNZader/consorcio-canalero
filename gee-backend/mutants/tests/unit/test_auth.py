"""Unit tests for app.auth.schemas — UserRead, UserCreate, UserUpdate."""

import uuid

import pytest
from pydantic import ValidationError

from app.auth.models import UserRole
from app.auth.schemas import UserCreate, UserRead, UserUpdate


# ── UserRead ──────────────────────────────────────


class TestUserRead:
    """Tests for the UserRead response schema."""

    def test_defaults(self):
        user = UserRead(
            id=uuid.uuid4(),
            email="test@example.com",
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        assert user.nombre == ""
        assert user.apellido == ""
        assert user.telefono == ""
        assert user.role == UserRole.CIUDADANO

    def test_with_custom_role(self):
        user = UserRead(
            id=uuid.uuid4(),
            email="admin@example.com",
            is_active=True,
            is_superuser=True,
            is_verified=True,
            role=UserRole.ADMIN,
            nombre="Admin",
            apellido="User",
        )
        assert user.role == UserRole.ADMIN
        assert user.nombre == "Admin"
        assert user.apellido == "User"

    def test_all_roles_valid(self):
        for role in UserRole:
            user = UserRead(
                id=uuid.uuid4(),
                email=f"{role.value}@example.com",
                is_active=True,
                is_superuser=False,
                is_verified=False,
                role=role,
            )
            assert user.role == role

    def test_email_required(self):
        with pytest.raises(ValidationError):
            UserRead(
                id=uuid.uuid4(),
                is_active=True,
                is_superuser=False,
                is_verified=False,
            )


# ── UserCreate ────────────────────────────────────


class TestUserCreate:
    """Tests for the UserCreate registration schema."""

    def test_minimal_creation(self):
        user = UserCreate(email="new@example.com", password="SecurePass123!")
        assert user.email == "new@example.com"
        assert user.nombre == ""
        assert user.apellido == ""
        assert user.telefono == ""

    def test_with_all_fields(self):
        user = UserCreate(
            email="full@example.com",
            password="SecurePass123!",
            nombre="Juan",
            apellido="Perez",
            telefono="+54 351 1234567",
        )
        assert user.nombre == "Juan"
        assert user.apellido == "Perez"
        assert user.telefono == "+54 351 1234567"

    def test_nombre_max_length_exceeded(self):
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="long@example.com",
                password="SecurePass123!",
                nombre="A" * 201,
            )
        assert "nombre" in str(exc_info.value)

    def test_apellido_max_length_exceeded(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="long@example.com",
                password="SecurePass123!",
                apellido="B" * 201,
            )

    def test_telefono_max_length_exceeded(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="long@example.com",
                password="SecurePass123!",
                telefono="9" * 51,
            )

    def test_nombre_at_max_length(self):
        user = UserCreate(
            email="ok@example.com",
            password="SecurePass123!",
            nombre="A" * 200,
        )
        assert len(user.nombre) == 200

    def test_password_required(self):
        with pytest.raises(ValidationError):
            UserCreate(email="nopwd@example.com")


# ── UserUpdate ────────────────────────────────────


class TestUserUpdate:
    """Tests for the UserUpdate partial-update schema."""

    def test_all_none_by_default(self):
        update = UserUpdate()
        assert update.nombre is None
        assert update.apellido is None
        assert update.telefono is None

    def test_partial_update(self):
        update = UserUpdate(nombre="Carlos")
        assert update.nombre == "Carlos"
        assert update.apellido is None

    def test_nombre_max_length(self):
        with pytest.raises(ValidationError):
            UserUpdate(nombre="X" * 201)

    def test_apellido_max_length(self):
        with pytest.raises(ValidationError):
            UserUpdate(apellido="Y" * 201)

    def test_telefono_max_length(self):
        with pytest.raises(ValidationError):
            UserUpdate(telefono="1" * 51)


# ── UserRole enum ─────────────────────────────────


class TestUserRole:
    """Tests for the UserRole enum."""

    def test_values(self):
        assert UserRole.CIUDADANO.value == "ciudadano"
        assert UserRole.OPERADOR.value == "operador"
        assert UserRole.ADMIN.value == "admin"

    def test_is_string_enum(self):
        assert isinstance(UserRole.ADMIN, str)
        assert UserRole.ADMIN == "admin"

    def test_membership(self):
        assert "ciudadano" in [r.value for r in UserRole]
        assert "operador" in [r.value for r in UserRole]
        assert "admin" in [r.value for r in UserRole]
