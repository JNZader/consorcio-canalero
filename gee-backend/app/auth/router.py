"""Auth router — JWT login/register + Google OAuth."""

from fastapi import APIRouter

from app.auth.dependencies import auth_backend, fastapi_users
from app.auth.schemas import UserCreate, UserRead, UserUpdate
from app.config import settings

router = APIRouter()

# JWT auth routes: /auth/jwt/login, /auth/jwt/logout
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

# Register route: /auth/register
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

# Password reset: /auth/forgot-password, /auth/reset-password
router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)

# Email verification: /auth/request-verify-token, /auth/verify
router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)

# User management: /users/me, /users/{id}
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

# Google OAuth (only if configured)
if settings.google_oauth_client_id:
    import logging
    import os
    from urllib.parse import urlencode

    from fastapi import Depends, Request
    from fastapi.responses import RedirectResponse
    from httpx_oauth.clients.google import GoogleOAuth2

    _oauth_logger = logging.getLogger(__name__)

    google_oauth_client = GoogleOAuth2(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
    )

    # Build the OAuth callback URL (where Google redirects back to).
    # Priority: API_BASE_URL setting > COOLIFY_URL env var > auto-detect at request time
    def _get_oauth_redirect_url() -> str | None:
        if settings.api_base_url:
            return f"{settings.api_base_url.rstrip('/')}/api/v2/auth/google/callback"
        coolify_url = os.environ.get("COOLIFY_URL", "")
        if coolify_url:
            return f"{coolify_url.rstrip('/')}/api/v2/auth/google/callback"
        return None

    _static_redirect_url = _get_oauth_redirect_url()

    # ── Custom OAuth endpoints (authorize + callback) ──
    # We don't use fastapi-users' get_oauth_router because BearerTransport
    # returns JSON on callback — but the browser needs a redirect to the frontend.
    from jose import jwt as jose_jwt

    from app.auth.dependencies import get_jwt_strategy
    from app.auth.models import User, UserRole
    from app.db.session import get_async_db
    from sqlalchemy import select as sa_select
    from sqlalchemy.ext.asyncio import AsyncSession

    @router.get("/auth/google/authorize", tags=["auth"])
    async def google_oauth_authorize(request: Request):
        """
        Generate Google OAuth authorization URL.
        Returns JSON with authorization_url for the frontend to redirect to.
        """
        redirect_url = _static_redirect_url
        if not redirect_url:
            redirect_url = str(request.url_for("google_oauth_callback"))

        authorization_url = await google_oauth_client.get_authorization_url(
            redirect_url,
            scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
        )
        return {"authorization_url": authorization_url}

    @router.get("/auth/google/callback", tags=["auth"])
    async def google_oauth_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
        session: AsyncSession = Depends(get_async_db),
    ):
        """
        Google OAuth callback — exchanges code for token, finds/creates user,
        then redirects to the frontend with a JWT in the query string.
        """
        frontend_callback = f"{settings.frontend_url.rstrip('/')}/auth/callback"

        if error:
            _oauth_logger.error("Google OAuth error: %s - %s", error, error_description)
            params = urlencode({"error": error, "error_description": error_description or ""})
            return RedirectResponse(url=f"{frontend_callback}?{params}")

        if not code:
            return RedirectResponse(
                url=f"{frontend_callback}?{urlencode({'error': 'missing_code'})}"
            )

        try:
            # Determine the redirect_url (must match what was used for authorize)
            redirect_url = _static_redirect_url
            if not redirect_url:
                redirect_url = str(request.url_for("google_oauth_callback"))

            # Exchange authorization code for Google access token
            oauth_token = await google_oauth_client.get_access_token(code, redirect_url)

            # Decode the id_token to get user info (no People API needed)
            id_token = oauth_token.get("id_token")
            if not id_token:
                return RedirectResponse(
                    url=f"{frontend_callback}?{urlencode({'error': 'no_id_token', 'error_description': 'Google did not return an id_token'})}"
                )

            # Decode without verification — we already trust Google's token endpoint
            id_info = jose_jwt.get_unverified_claims(id_token)
            account_email = id_info.get("email")
            account_id = id_info.get("sub")

            if not account_email:
                return RedirectResponse(
                    url=f"{frontend_callback}?{urlencode({'error': 'no_email'})}"
                )

            # Find existing user by email
            result = await session.execute(
                sa_select(User).where(User.email == account_email)
            )
            user = result.scalar_one_or_none()

            if user is None:
                # Create new user (auto-registered via Google)
                import uuid as _uuid

                user = User(
                    id=_uuid.uuid4(),
                    email=account_email,
                    hashed_password="!google-oauth",  # Cannot login with password
                    is_active=True,
                    is_verified=True,  # Google already verified the email
                    is_superuser=False,
                    nombre="",
                    apellido="",
                    telefono="",
                    role=UserRole.CIUDADANO,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                _oauth_logger.info("Created new user via Google OAuth: %s", account_email)

            if not user.is_active:
                return RedirectResponse(
                    url=f"{frontend_callback}?{urlencode({'error': 'inactive_user'})}"
                )

            # Generate JWT token
            strategy = get_jwt_strategy()
            token = await strategy.write_token(user)

            _oauth_logger.info("Google OAuth login successful for %s", account_email)
            return RedirectResponse(
                url=f"{frontend_callback}?{urlencode({'access_token': token})}"
            )

        except Exception as exc:
            _oauth_logger.exception("Google OAuth callback failed: %s", exc)
            return RedirectResponse(
                url=f"{frontend_callback}?{urlencode({'error': 'auth_failed', 'error_description': str(exc)})}"
            )
