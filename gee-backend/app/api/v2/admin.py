"""Admin endpoints — user management (list, set role)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.models import User, UserRole
from app.auth.schemas import UserRead
from app.db.session import get_async_db

router = APIRouter(prefix="/admin/users", tags=["admin"])


class SetRoleRequest(BaseModel):
    email: EmailStr
    role: UserRole


class SetRoleResponse(BaseModel):
    email: str
    role: UserRole
    message: str


@router.get("", response_model=list[UserRead])
async def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_async_db),
) -> list[User]:
    """List all users with their roles. Requires admin."""
    result = await db.execute(select(User).order_by(User.email))
    return list(result.scalars().all())


@router.post("/set-role", response_model=SetRoleResponse)
async def set_user_role(
    body: SetRoleRequest,
    _admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_async_db),
) -> SetRoleResponse:
    """Update a user's role by email. Requires admin."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró usuario con email: {body.email}",
        )

    user.role = body.role
    await db.commit()
    await db.refresh(user)

    return SetRoleResponse(
        email=user.email,
        role=user.role,
        message=f"Rol actualizado a '{body.role.value}' para {user.email}.",
    )
