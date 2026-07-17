"""Admin endpoints — user management (list, set role, force-revoke)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.models import User, UserRole
from app.auth.refresh_tokens import revoke_all_for_user
from app.auth.schemas import UserRead
from app.db.session import get_async_db
from app.shared.audit_log import write_audit_entry_async

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


class ForceRevokeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    revoked_sessions: int
    new_revocation_epoch: int
    message: str


@router.post(
    "/{user_id}/force-revoke",
    response_model=ForceRevokeResponse,
)
async def force_revoke_user(
    user_id: uuid.UUID,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: AsyncSession = Depends(get_async_db),
) -> ForceRevokeResponse:
    """Force-revoke EVERY session and refresh token for ``user_id``.

    Admin-only counterpart to ``/auth/jwt/logout-all`` — the same two-
    layer revocation (refresh tokens revoked + JWT ``revocation_epoch``
    bumped) applied to ANOTHER user. Use cases:

      - **Fired employee**: cut operator/admin access on the spot
        without coordinating with the person.
      - **Compromised account**: freeze a suspected-leaked credential
        before the attacker uses any remaining 15-min JWT window.
      - **Administrative suspension**: legal / disciplinary action
        before the underlying ``is_active=False`` cycle.

    Audit trail (Ley 25.326 §21): writes an ``audit_log`` row with
    ``action='user.force-revoke'``, ``resource='user_id=<target>'``,
    and ``user_id=<acting admin>`` so future ARCO requests OR
    internal incident reviews can answer "who revoked whom and when".

    Returns the count of refresh tokens revoked + the new
    ``revocation_epoch`` so the admin UI can show a confirmation.
    """
    # Verify the target exists. We do NOT collapse 404 into 400
    # because admins are trusted to know who they're targeting —
    # the enumeration concern that drives 404=400 on public auth
    # endpoints doesn't apply.
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró usuario con id {user_id}",
        )

    # Defensive guard: an admin force-revoking THEMSELVES is almost
    # certainly a mistake. Same workflow exists on /auth/jwt/logout-all
    # for the self path. Block here so the admin doesn't accidentally
    # lock themselves out mid-incident.
    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Para revocar tu propia sesión usá /auth/jwt/logout-all. "
                "Este endpoint es solo para revocar a otros usuarios."
            ),
        )

    # Three-layer revocation (3vr Opus-alt H1 fix-forward expands
    # the original two-layer set):
    # 1) Refresh tokens — caller commits, so revoke_all_for_user
    #    no longer commits internally. The whole operation is one
    #    atomic transaction so a failure in step 2/3/4 rolls
    #    back the token revocation too.
    revoked = await revoke_all_for_user(db, target.id)

    # 2) Pending email_codes (Phase 5 / F5-E). Without this, an
    #    attacker who triggered a "forgot password" before the
    #    admin's force-revoke could still use that 15-min code to
    #    reset the password and log back in — the force-revoke
    #    would be silently bypassed. Invalidate BOTH purposes so
    #    a pending verify code can't be used either.
    from app.auth.email_codes import (
        RESET_PURPOSE,
        VERIFY_PURPOSE,
        invalidate_open_codes_for_user,
    )

    await invalidate_open_codes_for_user(db, user_id=target.id, purpose=RESET_PURPOSE)
    await invalidate_open_codes_for_user(db, user_id=target.id, purpose=VERIFY_PURPOSE)

    # 3) Bump revocation_epoch atomically (SQL-side increment so a
    #    concurrent token issuance reads the post-bump value).
    await db.execute(
        update(User)
        .where(User.id == target.id)  # type: ignore[arg-type]
        .values(revocation_epoch=User.revocation_epoch + 1)
    )

    # Re-read to surface the new epoch back to the caller.
    refresh_result = await db.execute(
        select(User.revocation_epoch).where(User.id == target.id)  # type: ignore[arg-type]
    )
    new_epoch = int(refresh_result.scalar_one())

    # 4) Ley 25.326 audit trail. ``audit_log.user_id`` is the admin
    #    via FK with ``ON DELETE SET NULL`` — if the admin is later
    #    deleted (off-boarding / GDPR), the FK clears but we want
    #    the trail to survive. So we ALSO embed the admin's email
    #    in the ``resource`` column at write-time (3vr Opus-alt H2
    #    fix-forward). The resource is bounded to 512 chars; the
    #    helper truncates if needed.
    await write_audit_entry_async(
        db,
        user_id=admin.id,
        action="user.force-revoke",
        resource=(
            f"user_id={target.id} target_email={target.email} acting_admin_email={admin.email}"
        ),
        client_ip=request.client.host if request.client else None,
    )

    await db.commit()

    return ForceRevokeResponse(
        user_id=target.id,
        email=target.email,
        revoked_sessions=revoked,
        new_revocation_epoch=new_epoch,
        message=(
            f"Sesión revocada para {target.email}. "
            f"{revoked} refresh-token(s) marcado(s) como revoked, "
            f"revocation_epoch ahora = {new_epoch}. "
            "El usuario debe iniciar sesión de nuevo."
        ),
    )
