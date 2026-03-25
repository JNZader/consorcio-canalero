"""Auth dependencies — user manager, backends, and role guards."""

import logging
import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import PreAuthorizedEmail, User, UserRole
from app.config import settings
from app.db.session import get_async_db


# --- User database adapter ---


async def get_user_db(session: AsyncSession = Depends(get_async_db)):
    yield SQLAlchemyUserDatabase(session, User)


# --- User manager ---


logger = logging.getLogger(__name__)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        """Handle forgot-password token generation.

        When SMTP is configured, this should send the reset email.
        For now, we build the reset URL and log it so the admin
        can manually deliver it or test the flow.
        """
        reset_url = f"{settings.frontend_url}/reset-password?token={token}"
        logger.info(
            "Password reset requested for %s — reset URL: %s",
            user.email,
            reset_url,
        )
        # TODO: Send email via SMTP when configured.
        # See PENDIENTES.md: "Necesita configurar envio de email (SMTP o servicio)"

    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        """Check pre-authorized emails and auto-assign role on registration."""
        # Get the async session from the user_db internals
        session: AsyncSession = self.user_db.session

        result = await session.execute(
            select(PreAuthorizedEmail).where(
                PreAuthorizedEmail.email == user.email,
                PreAuthorizedEmail.claimed == False,  # noqa: E712
            )
        )
        pre_auth = result.scalar_one_or_none()

        if pre_auth is not None:
            user.role = pre_auth.role
            pre_auth.claimed = True
            session.add(user)
            await session.commit()


def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> UserManager:
    return UserManager(user_db)


# --- JWT backend ---

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.jwt_secret, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# --- FastAPIUsers instance ---

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# --- Convenience dependencies ---

current_active_user = fastapi_users.current_user(active=True)


def require_role(*roles: UserRole):
    """Dependency that requires the user to have one of the specified roles."""

    def _check(
        user: Annotated[User, Depends(current_active_user)],
    ) -> User:
        if user.role not in roles:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenés permisos para esta acción.",
            )
        return user

    return _check


require_admin = require_role(UserRole.ADMIN)
require_operator = require_role(UserRole.OPERADOR, UserRole.ADMIN)
