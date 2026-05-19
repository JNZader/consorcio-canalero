"""User model for fastapi-users with role support."""

import enum
import uuid
from datetime import datetime
from typing import Optional

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
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


class RefreshToken(UUIDMixin, TimestampMixin, Base):
    """Rotating refresh tokens (Phase 2 / F2-K).

    Each refresh token belongs to a ``family`` — a chain of tokens
    issued for a single login session. When the SPA exchanges a refresh
    token for a new access token, we mint a new refresh token in the
    same family and mark the old one ``revoked``. If a revoked token
    is ever re-used (replay), we kill the whole family: that's the
    signal that the cookie was stolen.

    The raw token never lands in the DB — we store its SHA-256 hash so
    a DB read can't be turned into impersonation.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 hex of the raw token — 64 chars. We look up by this hash.
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Coarse client fingerprint — useful for the "logged in from these
    # devices" list. Not load-bearing; truncated to keep storage tight.
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RefreshToken user_id={self.user_id} family={self.family_id} "
            f"revoked={self.revoked} expires_at={self.expires_at}>"
        )
