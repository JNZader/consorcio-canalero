"""Auth dependencies — user manager, backends, and role guards."""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.config import settings
from app.db.session import get_db


# --- User database adapter ---


def get_user_db(db: Session = Depends(get_db)) -> SQLAlchemyUserDatabase:
    return SQLAlchemyUserDatabase(db, User)


# --- User manager ---


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret


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
