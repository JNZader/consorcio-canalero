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
                "user_email_hash": hashlib.sha256(user.email.lower().encode("utf-8")).hexdigest()[
                    :12
                ],
                "token_fingerprint": token_fingerprint,
            },
        )

        # Phase 5 / F5-E: stand the SMTP body off the JWT token.
        # When ``settings.use_one_time_codes`` is enabled, generate a
        # short code, persist the mapping in ``email_codes``, send
        # the email with the code (not the token). The SPA exchanges
        # the code for the original token via
        # ``POST /auth/exchange-code``. Provider logs that retain
        # the body for 30+ days now only see a 15-min one-shot code.
        #
        # When disabled (DEFAULT), the legacy token-in-URL path runs
        # so existing SPA versions keep working — flip the flag in
        # ``.env`` once the frontend ships the ``?code=`` handler.
        from app.shared.email import build_reset_email, send_email

        if settings.use_one_time_codes:
            from app.auth.email_codes import (
                RESET_PURPOSE,
                create_code_for_token,
                invalidate_open_codes_for_user,
            )
            from typing import cast

            sqlalchemy_user_db = cast("SQLAlchemyUserDatabase[User, uuid.UUID]", self.user_db)
            session: AsyncSession = sqlalchemy_user_db.session
            # Invalidate any prior unconsumed reset codes for this user
            # so "forgot password" pressed twice doesn't leave two
            # simultaneously valid codes in flight (3vr Sonnet finding).
            await invalidate_open_codes_for_user(session, user_id=user.id, purpose=RESET_PURPOSE)
            code = await create_code_for_token(
                session, user=user, purpose=RESET_PURPOSE, token=token
            )
            await session.commit()

            template = build_reset_email(code=code, frontend_url=settings.frontend_url)
            try:
                await send_email(to_email=user.email, **template)
            except Exception:
                # SMTP delivery failed — the code row would be a leak
                # (user can never receive it, but it's still valid for
                # 15 min). Roll back the row so the user can retry
                # cleanly. (3vr Opus-alt H2 fix.)
                from app.auth.email_codes import EmailCode
                from sqlalchemy import delete as sa_delete

                await session.execute(sa_delete(EmailCode).where(EmailCode.code == code))
                await session.commit()
                raise
        else:
            # Legacy path — embeds the token in the URL. The frontend
            # still uses this until F5-E rollout flips the flag.
            template = build_reset_email(code=token, frontend_url=settings.frontend_url)
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
                "user_email_hash": hashlib.sha256(user.email.lower().encode("utf-8")).hexdigest()[
                    :12
                ],
                "token_fingerprint": token_fingerprint,
            },
        )
        # Phase 5 / F5-E: same hardening as ``on_after_forgot_password``,
        # gated behind the ``USE_ONE_TIME_CODES`` flag.
        from app.shared.email import build_verification_email, send_email

        if settings.use_one_time_codes:
            from app.auth.email_codes import (
                VERIFY_PURPOSE,
                create_code_for_token,
                invalidate_open_codes_for_user,
            )
            from typing import cast

            sqlalchemy_user_db = cast("SQLAlchemyUserDatabase[User, uuid.UUID]", self.user_db)
            session: AsyncSession = sqlalchemy_user_db.session
            await invalidate_open_codes_for_user(session, user_id=user.id, purpose=VERIFY_PURPOSE)
            code = await create_code_for_token(
                session, user=user, purpose=VERIFY_PURPOSE, token=token
            )
            await session.commit()

            template = build_verification_email(code=code, frontend_url=settings.frontend_url)
            try:
                await send_email(to_email=user.email, **template)
            except Exception:
                # Same SMTP-failure rollback as the reset path.
                from app.auth.email_codes import EmailCode
                from sqlalchemy import delete as sa_delete

                await session.execute(sa_delete(EmailCode).where(EmailCode.code == code))
                await session.commit()
                raise
        else:
            # Legacy path — token in URL, same as pre-F5-E.
            template = build_verification_email(code=token, frontend_url=settings.frontend_url)
            await send_email(to_email=user.email, **template)

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        """Check pre-authorized emails and auto-assign role on registration."""
        # Get the async session from the user_db internals.
        # fastapi-users-db-sqlalchemy stores it on ``.session``, but the
        # ``BaseUserDatabase`` Protocol fastapi-users exposes does not
        # declare the attribute, so mypy can't see it. We know the
        # concrete adapter we use (SQLAlchemyUserDatabase) — narrow with
        # a runtime-safe cast.
        from typing import cast

        sqlalchemy_user_db = cast("SQLAlchemyUserDatabase[User, uuid.UUID]", self.user_db)
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


class RevocableJWTStrategy(JWTStrategy[User, uuid.UUID]):
    """JWTStrategy extension that honours ``User.revocation_epoch``.

    Phase 5 / F5-F. The default fastapi-users JWTStrategy issues
    stateless tokens that survive until natural expiry — a 15-min
    blast radius after ``/auth/jwt/logout-all`` invalidates the
    refresh family. This extension bakes the user's current epoch
    into every issued token and refuses tokens whose embedded epoch
    is below the current user value.

    Implementation cost: one extra integer comparison per request,
    on a User row that was already going to be loaded for auth.
    """

    async def write_token(self, user: User) -> str:
        # Import locally — ``fastapi_users.jwt`` is the recommended
        # public surface for ``generate_jwt`` per the upstream source.
        from fastapi_users.jwt import generate_jwt

        data = {
            "sub": str(user.id),
            "aud": self.token_audience,
            # Embed the epoch at issue time. Reading user.revocation_epoch
            # with ``or 0`` defends against legacy rows that somehow
            # lost their NOT NULL constraint (defensive — the column
            # is ``nullable=False`` with ``server_default='0'``).
            "epoch": int(getattr(user, "revocation_epoch", 0) or 0),
        }
        return generate_jwt(
            data,
            self.encode_key,
            self.lifetime_seconds,
            algorithm=self.algorithm,
        )

    async def read_token(
        self,
        token: str | None,
        user_manager: BaseUserManager[User, uuid.UUID],
    ) -> User | None:
        # Delegate the JWT-validation half (signature, expiry,
        # audience) to the upstream implementation. It returns the
        # user — or None — after a fresh DB load.
        user = await super().read_token(token, user_manager)
        if user is None or token is None:
            return user

        # We need the epoch claim, which the parent doesn't expose.
        # Decode again with the same secret — cheap, the parent
        # already validated the signature so this is just JSON
        # extraction.
        import jwt as _jwt
        from fastapi_users.jwt import decode_jwt

        try:
            data = decode_jwt(
                token,
                self.decode_key,
                self.token_audience,
                algorithms=[self.algorithm],
            )
        except _jwt.PyJWTError:
            # Should never happen — parent already accepted the token.
            # Fail closed.
            return None

        token_epoch = int(data.get("epoch", 0))
        user_epoch = int(getattr(user, "revocation_epoch", 0) or 0)

        if token_epoch < user_epoch:
            # Token was issued before the last ``logout-all`` bump.
            # Treat as invalid; the caller falls through to 401.
            return None

        return user


def get_jwt_strategy() -> JWTStrategy:
    # Phase 2 / F2-K: access tokens are short-lived (15 min). The SPA
    # refreshes them via the refresh-token cookie set on login. With
    # ``access`` this short, a stolen token has a 15-min blast radius
    # before the user can ``logout-all`` to revoke the whole token
    # family. Phase 5 / F5-F additionally closes that residual window
    # by checking the embedded ``epoch`` claim against the user's
    # ``revocation_epoch`` on every request.
    return RevocableJWTStrategy(
        secret=settings.jwt_secret,
        lifetime_seconds=900,
    )


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
