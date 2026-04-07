"""User model for fastapi-users with role support."""

import enum
import uuid

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


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
        Enum(
            UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
        default=UserRole.CIUDADANO,
    )


class PreAuthorizedEmail(UUIDMixin, TimestampMixin, Base):
    """Pre-authorized emails for invitation-based role assignment.

    When a user registers with a pre-authorized email, they automatically
    get the assigned role instead of the default 'ciudadano'.
    """

    __tablename__ = "pre_authorized_emails"

    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    claimed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<PreAuthorizedEmail email={self.email} role={self.role.value} claimed={self.claimed}>"
