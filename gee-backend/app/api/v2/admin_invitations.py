"""Admin endpoints — user invitation management."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.models import PreAuthorizedEmail, User, UserRole
from app.db.session import get_async_db

router = APIRouter(prefix="/admin/invitations", tags=["admin"])


# ──────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────


class InvitationItem(BaseModel):
    email: EmailStr
    role: UserRole


class InviteRequest(BaseModel):
    invitations: list[InvitationItem] = Field(..., min_length=1, max_length=50)


class InvitationResult(BaseModel):
    email: str
    role: UserRole
    status: str  # "created" | "already_invited" | "already_registered"


class InviteResponse(BaseModel):
    results: list[InvitationResult]


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str
    role: UserRole
    claimed: bool
    created_at: datetime


class RevokeResponse(BaseModel):
    email: str
    message: str


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.post("", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def invite_users(
    body: InviteRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_async_db),
) -> InviteResponse:
    """Invite users by pre-authorizing their emails with elevated roles.

    When these users register, they'll automatically receive the assigned role.
    Requires admin.
    """
    results: list[InvitationResult] = []

    for invitation in body.invitations:
        email_lower = invitation.email.lower()

        # Check if already registered
        existing_user = await db.execute(select(User).where(User.email == email_lower))
        if existing_user.scalar_one_or_none() is not None:
            results.append(
                InvitationResult(
                    email=email_lower,
                    role=invitation.role,
                    status="already_registered",
                )
            )
            continue

        # Check if already invited
        existing_invite = await db.execute(
            select(PreAuthorizedEmail).where(PreAuthorizedEmail.email == email_lower)
        )
        if existing_invite.scalar_one_or_none() is not None:
            results.append(
                InvitationResult(
                    email=email_lower,
                    role=invitation.role,
                    status="already_invited",
                )
            )
            continue

        # Create pre-authorization
        pre_auth = PreAuthorizedEmail(
            email=email_lower,
            role=invitation.role,
            invited_by=admin.id,
        )
        db.add(pre_auth)
        results.append(
            InvitationResult(
                email=email_lower,
                role=invitation.role,
                status="created",
            )
        )

    await db.commit()
    return InviteResponse(results=results)


@router.get("", response_model=list[InvitationRead])
async def list_invitations(
    _admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_async_db),
) -> list[InvitationRead]:
    """List all pending (unclaimed) invitations. Requires admin."""
    result = await db.execute(
        select(PreAuthorizedEmail)
        .where(PreAuthorizedEmail.claimed == False)  # noqa: E712
        .order_by(PreAuthorizedEmail.created_at.desc())
    )
    return [InvitationRead.model_validate(row) for row in result.scalars().all()]


@router.delete("/{email}", response_model=RevokeResponse)
async def revoke_invitation(
    email: str,
    _admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_async_db),
) -> RevokeResponse:
    """Revoke a pending invitation by email. Requires admin."""
    email_lower = email.lower()

    result = await db.execute(
        select(PreAuthorizedEmail).where(PreAuthorizedEmail.email == email_lower)
    )
    invitation = result.scalar_one_or_none()

    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró invitación para: {email_lower}",
        )

    if invitation.claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La invitación para {email_lower} ya fue reclamada.",
        )

    await db.execute(
        delete(PreAuthorizedEmail).where(PreAuthorizedEmail.email == email_lower)
    )
    await db.commit()

    return RevokeResponse(
        email=email_lower,
        message=f"Invitación revocada para {email_lower}.",
    )
