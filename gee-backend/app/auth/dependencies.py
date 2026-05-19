"""Auth dependencies — user manager, backends, and role guards."""

import hashlib
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

        SECURITY: never log the token or the reset URL. The token is a
        valid one-shot credential that lets ANYONE with read-access to
        the logs reset this account's password. Until SMTP is wired,
        operators can manually request a token via the admin panel (or
        via a CLI command) for the user — never via the application log.
        """
        # Build the reset URL but do NOT log it. Use the hashed token id
        # so the log entry still helps correlate "user X requested reset
        # at time T" with any later support ticket, without leaking the
        # secret itself.
        token_fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        logger.info(
            "Password reset requested",
            extra={
                "user_email_hash": hashlib.sha256(
                    user.email.lower().encode("utf-8")
                ).hexdigest()[:12],
                "token_fingerprint": token_fingerprint,
            },
        )

        # Phase 2 / F2-J: ship the actual email when SMTP is configured.
        # ``send_email`` is a silent no-op when ``SMTP_HOST`` is empty,
        # so this path is safe on dev / unconfigured installs.
        from app.shared.email import build_reset_email, send_email

        template = build_reset_email(token=token, frontend_url=settings.frontend_url)
        await send_email(to_email=user.email, **template)

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        """Ship the verification email when ``request-verify-token`` fires.

        Same redaction policy as the password-reset flow: NEVER log the
        token. The email helper degrades to a logged no-op on installs
        without SMTP, so dev / unconfigured installs see the user
        registered but stuck "pending verify" until the operator
        manually verifies them.
        """
        token_fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        logger.info(
            "Email verification requested",
            extra={
                "user_email_hash": hashlib.sha256(
                    user.email.lower().encode("utf-8")
                ).hexdigest()[:12],
                "token_fingerprint": token_fingerprint,
            },
        )
        from app.shared.email import build_verification_email, send_email

        template = build_verification_email(
            token=token, frontend_url=settings.frontend_url
        )
        await send_email(to_email=user.email, **template)

    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        """Check pre-authorized emails and auto-assign role on registration."""
        # Get the async session from the user_db internals.
        # fastapi-users-db-sqlalchemy stores it on ``.session``, but the
        # ``BaseUserDatabase`` Protocol fastapi-users exposes does not
        # declare the attribute, so mypy can't see it. We know the
        # concrete adapter we use (SQLAlchemyUserDatabase) — narrow with
        # a runtime-safe cast.
        from typing import cast

        sqlalchemy_user_db = cast(
            "SQLAlchemyUserDatabase[User, uuid.UUID]", self.user_db
        )
        session: AsyncSession = sqlalchemy_user_db.session

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

        # Phase 2 / F2-J: send the verification email automatically on
        # register so the citizen doesn't have to call a separate
        # ``request-verify-token`` endpoint. ``request_verify`` mints
        # the token and triggers ``on_after_request_verify`` above.
        # Wrapped in try/except so an SMTP outage can't fail the
        # registration itself — the citizen exists, they can re-request
        # the verification mail later.
        try:
            await self.request_verify(user, request)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Auto-verify email failed (user is registered anyway)",
                extra={"error": str(exc)},
            )


def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> UserManager:
    return UserManager(user_db)


# --- JWT backend ---

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    # Phase 2 / F2-K: access tokens are short-lived (15 min). The SPA
    # refreshes them via the refresh-token cookie set on login. With
    # ``access`` this short, a stolen token has a 15-min blast radius
    # before the user can ``logout-all`` to revoke the whole token
    # family.
    return JWTStrategy(secret=settings.jwt_secret, lifetime_seconds=900)


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
