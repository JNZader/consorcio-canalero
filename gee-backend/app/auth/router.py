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
    from typing import Literal
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

    # Single-use exchange cookie used to hand the JWT back to the SPA.
    # Previously the callback redirected to ``frontend/auth/callback#access_token=...``
    # — the token landed in ``window.location.hash`` (accessible to any
    # script on the page, including browser extensions), in the URL bar
    # (visible over the shoulder), and in browser history. The new flow
    # stores the JWT in a short-lived HttpOnly cookie and lets the SPA
    # call ``POST /auth/jwt/exchange-cookie`` once to read + delete it.
    _OAUTH_EXCHANGE_COOKIE = "oauth_access_token"
    _OAUTH_EXCHANGE_MAX_AGE = 60  # 60 s — the SPA hits the exchange immediately.
    # Narrow the cookie scope to the OAuth endpoints only. Path=/ would
    # make the cookie ride on every backend request, which is both wider
    # than necessary and a small leak surface (any future endpoint that
    # echoes a header could surface it). Both ``set_cookie`` and
    # ``delete_cookie`` MUST use the same Path or the browser won't
    # find the cookie on the callback.
    _OAUTH_STATE_COOKIE_PATH = "/api/v2/auth/google/"

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

    def _is_secure_request(request: Request) -> bool:
        """True when the cookie's ``Secure`` flag MUST be set.

        In production/staging we force ``True`` regardless of headers — the
        backend is only reachable via Caddy/HTTPS in those envs and reading
        ``X-Forwarded-Proto`` would otherwise trust a client-supplied header
        (no ``forwarded_allow_ips`` whitelist is wired today, so any upstream
        that bypasses the reverse proxy could forge it).

        In dev we fall back to the request scheme so HTTP localhost still
        works without a Secure-cookie rejection.
        """
        from app.config import _is_production_env

        if _is_production_env(settings.environment):
            return True
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
        secure = _is_secure_request(request)
        # SameSite policy:
        #  - HTTPS prod (Cloudflare Pages frontend → Hetzner backend, cross-
        #    origin): use ``none`` so the cookie travels on the cross-site
        #    response. ``none`` REQUIRES ``Secure=true`` per spec; we set
        #    both together. The CSRF protection still holds because the
        #    server compares the cookie to Google's echoed state.
        #  - Dev (HTTP localhost, same-origin via Vite proxy): ``lax``
        #    is enough and avoids the ``Secure`` requirement.
        same_site: Literal["lax", "none"] = "none" if secure else "lax"
        response.set_cookie(
            key=_OAUTH_STATE_COOKIE,
            value=state_nonce,
            max_age=_OAUTH_STATE_MAX_AGE,
            httponly=True,
            samesite=same_site,
            secure=secure,
            path=_OAUTH_STATE_COOKIE_PATH,
        )
        return response

    def _clear_state_cookie(response: RedirectResponse) -> None:
        """Delete the oauth_state cookie after a callback (success or fail).

        Path MUST match the set_cookie call, or the browser won't unset it.
        """
        response.delete_cookie(_OAUTH_STATE_COOKIE, path=_OAUTH_STATE_COOKIE_PATH)

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
                # No more URL-fragment token — the SPA reads the JWT
                # from a single-use HttpOnly cookie via
                # ``POST /auth/jwt/exchange-cookie`` after this redirect.
                url=f"{frontend_callback}?via=cookie"
            )
            secure_cookie = _is_secure_request(request)
            response.set_cookie(
                key=_OAUTH_EXCHANGE_COOKIE,
                value=token,
                max_age=_OAUTH_EXCHANGE_MAX_AGE,
                httponly=True,
                # Strict — the redirect that sets this cookie is a
                # top-level navigation initiated by the cross-site Google
                # callback, BUT the immediate next request (the SPA's
                # exchange POST) is same-site (frontend → backend on the
                # same eTLD+1 when using a shared parent domain) so
                # strict is appropriate. Falls back to ``lax`` only when
                # the deploy is cross-origin (HTTPS) so the cookie still
                # travels back from Cloudflare Pages → Hetzner.
                samesite="none" if secure_cookie else "lax",
                secure=secure_cookie,
                # Narrow path so the cookie only travels to the OAuth
                # exchange endpoint. /api/v2/auth/jwt/exchange-cookie.
                path="/api/v2/auth/jwt/",
            )
            _clear_state_cookie(response)
            return response

        except Exception as exc:
            # Log the full exception server-side, but redact the user-visible
            # ``error_description`` — ``str(exc)`` can surface SQLAlchemy
            # internals, file paths, or DSN fragments that don't belong in
            # the browser address bar or history.
            _oauth_logger.exception("Google OAuth callback failed: %s", exc)
            from app.config import _is_production_env

            if _is_production_env(settings.environment):
                description = "OAuth flow failed; please retry."
            else:
                description = str(exc)
            response = RedirectResponse(
                url=f"{frontend_callback}?{urlencode({'error': 'auth_failed', 'error_description': description})}"
            )
            _clear_state_cookie(response)
            return response

    @router.post("/auth/jwt/exchange-cookie", tags=["auth"])
    async def exchange_oauth_cookie(request: Request):
        """Trade the single-use OAuth cookie for an access token in JSON.

        The SPA hits this once after landing on ``/auth/callback?via=cookie``.
        The cookie is read, dropped from the response (browser clears it),
        and the JWT is returned in the response body so the SPA can put
        it in sessionStorage exactly like the password-login flow does.

        Returns 401 (with cookie clear) when the cookie is missing or
        empty — the most common reason is the SPA hit this endpoint
        twice (the cookie was consumed by the first call). The user
        should re-start the Google flow.
        """
        token = request.cookies.get(_OAUTH_EXCHANGE_COOKIE)
        response = JSONResponse(
            {"access_token": token or "", "token_type": "bearer"}
            if token
            else {
                "error": "missing_exchange_cookie",
                "error_description": (
                    "OAuth exchange cookie ausente o expirada (>60 s). "
                    "Reintentá el login con Google."
                ),
            },
            status_code=200 if token else 401,
        )
        response.delete_cookie(_OAUTH_EXCHANGE_COOKIE, path="/api/v2/auth/jwt/")
        return response
