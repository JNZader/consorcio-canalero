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
    import hmac
    import logging
    import os
    import secrets
    from urllib.parse import urlencode

    from fastapi import Depends, Request
    from fastapi.responses import JSONResponse, RedirectResponse
    from google.auth.transport import requests as google_auth_requests
    from google.oauth2 import id_token as google_id_token
    from httpx_oauth.clients.google import GoogleOAuth2

    # OAuth anti-CSRF: the authorize endpoint mints a random ``state`` nonce,
    # drops it into a short-lived HttpOnly cookie, and passes it to Google.
    # The callback rejects the request unless Google's ``state`` matches the
    # cookie (constant-time). Without this, an attacker can forge the
    # callback URL and make a victim sign in as the attacker's Google account.
    _OAUTH_STATE_COOKIE = "oauth_state"
    _OAUTH_STATE_MAX_AGE = 600  # 10 minutes — generous for slow Google flows.

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

    def _verify_google_id_token(raw_id_token: str) -> dict:
        """Verify Google ID token signature and expected claims."""
        id_info = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_auth_requests.Request(),
            settings.google_oauth_client_id,
        )

        issuer = id_info.get("iss")
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise ValueError("Invalid Google token issuer")

        if id_info.get("email_verified") is not True:
            raise ValueError("Google account email is not verified")

        return id_info

    # ── Custom OAuth endpoints (authorize + callback) ──
    # We don't use fastapi-users' get_oauth_router because BearerTransport
    # returns JSON on callback — but the browser needs a redirect to the frontend.
    from app.auth.dependencies import get_jwt_strategy
    from app.auth.models import User, UserRole
    from app.db.session import get_async_db
    from sqlalchemy import select as sa_select
    from sqlalchemy.ext.asyncio import AsyncSession

    def _is_https_request(request: Request) -> bool:
        """True when the request was served over HTTPS (incl. via X-Forwarded-Proto)."""
        if request.url.scheme == "https":
            return True
        forwarded = request.headers.get("x-forwarded-proto", "")
        return forwarded.lower().split(",", 1)[0].strip() == "https"

    @router.get("/auth/google/authorize", tags=["auth"])
    async def google_oauth_authorize(request: Request):
        """
        Generate Google OAuth authorization URL.
        Returns JSON with authorization_url for the frontend to redirect to.
        """
        redirect_url = _static_redirect_url
        if not redirect_url:
            redirect_url = str(request.url_for("google_oauth_callback"))

        state_nonce = secrets.token_urlsafe(32)
        authorization_url = await google_oauth_client.get_authorization_url(
            redirect_url,
            state=state_nonce,
            scope=[
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
            ],
        )

        response = JSONResponse({"authorization_url": authorization_url})
        response.set_cookie(
            key=_OAUTH_STATE_COOKIE,
            value=state_nonce,
            max_age=_OAUTH_STATE_MAX_AGE,
            httponly=True,
            # SameSite=lax is required: the callback is reached via top-level
            # navigation from accounts.google.com, so SameSite=strict would
            # strip the cookie. ``none`` would weaken the CSRF protection.
            samesite="lax",
            secure=_is_https_request(request),
            path="/",
        )
        return response

    def _clear_state_cookie(response: RedirectResponse) -> None:
        """Delete the oauth_state cookie after a callback (success or fail)."""
        response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")

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
        then redirects to the frontend with a JWT in the URL fragment.
        """
        frontend_callback = f"{settings.frontend_url.rstrip('/')}/auth/callback"

        # CSRF check: the ``state`` Google echoed back MUST match the nonce
        # we put in the ``oauth_state`` cookie during /authorize. Do this
        # before touching the ``code`` so a forged callback never reaches
        # the token-exchange step. ``hmac.compare_digest`` to dodge any
        # timing-side-channel that could leak the cookie value.
        cookie_state = request.cookies.get(_OAUTH_STATE_COOKIE)
        if (
            not cookie_state
            or not state
            or not hmac.compare_digest(cookie_state, state)
        ):
            _oauth_logger.warning("Google OAuth state mismatch — possible CSRF attempt")
            response = RedirectResponse(
                url=f"{frontend_callback}?{urlencode({'error': 'invalid_state', 'error_description': 'OAuth state verification failed. Please retry the login.'})}"
            )
            _clear_state_cookie(response)
            return response

        if error:
            _oauth_logger.error("Google OAuth error: %s - %s", error, error_description)
            params = urlencode(
                {"error": error, "error_description": error_description or ""}
            )
            response = RedirectResponse(url=f"{frontend_callback}?{params}")
            _clear_state_cookie(response)
            return response

        if not code:
            response = RedirectResponse(
                url=f"{frontend_callback}?{urlencode({'error': 'missing_code'})}"
            )
            _clear_state_cookie(response)
            return response

        try:
            # Determine the redirect_url (must match what was used for authorize)
            redirect_url = _static_redirect_url
            if not redirect_url:
                redirect_url = str(request.url_for("google_oauth_callback"))

            # Exchange authorization code for Google access token
            oauth_token = await google_oauth_client.get_access_token(code, redirect_url)

            # Verify the id_token to get user info (no People API needed)
            id_token = oauth_token.get("id_token")
            if not id_token:
                response = RedirectResponse(
                    url=f"{frontend_callback}?{urlencode({'error': 'no_id_token', 'error_description': 'Google did not return an id_token'})}"
                )
                _clear_state_cookie(response)
                return response

            id_info = _verify_google_id_token(id_token)
            account_email = id_info.get("email")
            if not account_email:
                response = RedirectResponse(
                    url=f"{frontend_callback}?{urlencode({'error': 'no_email'})}"
                )
                _clear_state_cookie(response)
                return response

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
                _oauth_logger.info(
                    "Created new user via Google OAuth: %s", account_email
                )

            if not user.is_active:
                response = RedirectResponse(
                    url=f"{frontend_callback}?{urlencode({'error': 'inactive_user'})}"
                )
                _clear_state_cookie(response)
                return response

            # Generate JWT token
            strategy = get_jwt_strategy()
            token = await strategy.write_token(user)

            _oauth_logger.info("Google OAuth login successful for %s", account_email)
            response = RedirectResponse(
                # Use the URL fragment so the browser can read the token, but it is
                # not sent back to servers or captured in standard request logs.
                url=f"{frontend_callback}#{urlencode({'access_token': token})}"
            )
            _clear_state_cookie(response)
            return response

        except Exception as exc:
            _oauth_logger.exception("Google OAuth callback failed: %s", exc)
            response = RedirectResponse(
                url=f"{frontend_callback}?{urlencode({'error': 'auth_failed', 'error_description': str(exc)})}"
            )
            _clear_state_cookie(response)
            return response
