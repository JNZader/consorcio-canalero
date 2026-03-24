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

# User management: /users/me, /users/{id}
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

# Google OAuth (only if configured)
if settings.google_oauth_client_id:
    from httpx_oauth.clients.google import GoogleOAuth2

    google_oauth_client = GoogleOAuth2(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
    )

    router.include_router(
        fastapi_users.get_oauth_router(
            google_oauth_client,
            auth_backend,
            settings.jwt_secret,
        ),
        prefix="/auth/google",
        tags=["auth"],
    )
