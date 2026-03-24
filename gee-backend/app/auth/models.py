"""User model for fastapi-users with role support."""

import enum

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    CIUDADANO = "ciudadano"
    OPERADOR = "operador"
    ADMIN = "admin"


class User(SQLAlchemyBaseUserTableUUID, TimestampMixin, Base):
    """User model with role-based access control."""

    __tablename__ = "users"

    nombre: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    apellido: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    telefono: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UserRole.CIUDADANO,
    )
