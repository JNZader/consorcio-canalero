"""Auth module — fastapi-users with JWT + Google OAuth."""

from app.auth.dependencies import (
    current_active_user,
    require_admin,
    require_operator as require_admin_or_operator,
    require_role,
)

# Also export as require_authenticated for endpoints that just need login
require_authenticated = current_active_user

__all__ = [
    "current_active_user",
    "require_admin",
    "require_admin_or_operator",
    "require_authenticated",
    "require_role",
]
