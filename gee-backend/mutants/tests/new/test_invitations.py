"""Tests for the invitation system (PreAuthorizedEmail model + admin endpoints)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import PreAuthorizedEmail, User, UserRole


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_admin(db: Session, email: str | None = None) -> User:
    """Create and flush an admin user."""
    user = User(
        email=email or f"admin-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="fakehash",
        nombre="Admin",
        apellido="Test",
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.flush()
    return user


def _make_invitation(
    db: Session,
    *,
    email: str = "invited@test.com",
    role: UserRole = UserRole.OPERADOR,
    invited_by: uuid.UUID | None = None,
    claimed: bool = False,
) -> PreAuthorizedEmail:
    """Create and flush a pre-authorized email."""
    if invited_by is None:
        admin = _make_admin(db)
        invited_by = admin.id

    invitation = PreAuthorizedEmail(
        email=email,
        role=role,
        invited_by=invited_by,
        claimed=claimed,
    )
    db.add(invitation)
    db.flush()
    return invitation


# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class TestPreAuthorizedEmailModel:
    def test_create_invitation(self, db: Session):
        admin = _make_admin(db)
        invitation = PreAuthorizedEmail(
            email="new@test.com",
            role=UserRole.OPERADOR,
            invited_by=admin.id,
        )
        db.add(invitation)
        db.flush()

        assert invitation.id is not None
        assert invitation.email == "new@test.com"
        assert invitation.role == UserRole.OPERADOR
        assert invitation.claimed is False

    def test_repr(self, db: Session):
        invitation = _make_invitation(db, email="repr@test.com")
        r = repr(invitation)
        assert "repr@test.com" in r
        assert "operador" in r
        assert "False" in r

    def test_unique_email_constraint(self, db: Session):
        admin = _make_admin(db)
        _make_invitation(db, email="dupe@test.com", invited_by=admin.id)

        dupe = PreAuthorizedEmail(
            email="dupe@test.com",
            role=UserRole.ADMIN,
            invited_by=admin.id,
        )
        db.add(dupe)
        with pytest.raises(Exception):  # IntegrityError
            db.flush()

    def test_role_values(self, db: Session):
        admin = _make_admin(db)
        for role in [UserRole.OPERADOR, UserRole.ADMIN]:
            inv = _make_invitation(
                db,
                email=f"{role.value}@test.com",
                role=role,
                invited_by=admin.id,
            )
            assert inv.role == role

    def test_claimed_flag(self, db: Session):
        invitation = _make_invitation(db, claimed=False)
        assert invitation.claimed is False

        invitation.claimed = True
        db.flush()
        db.refresh(invitation)
        assert invitation.claimed is True

    def test_foreign_key_to_users(self, db: Session):
        admin = _make_admin(db)
        invitation = _make_invitation(db, invited_by=admin.id)
        assert invitation.invited_by == admin.id

    def test_timestamps_populated(self, db: Session):
        invitation = _make_invitation(db)
        assert invitation.created_at is not None
        assert invitation.updated_at is not None


# ──────────────────────────────────────────────
# QUERY TESTS (simulating what the endpoints do)
# ──────────────────────────────────────────────


class TestInvitationQueries:
    def test_find_pending_invitations(self, db: Session):
        admin = _make_admin(db)
        _make_invitation(db, email="pending@test.com", invited_by=admin.id, claimed=False)
        _make_invitation(db, email="claimed@test.com", invited_by=admin.id, claimed=True)

        result = db.execute(
            select(PreAuthorizedEmail).where(PreAuthorizedEmail.claimed == False)  # noqa: E712
        )
        pending = result.scalars().all()
        emails = [p.email for p in pending]

        assert "pending@test.com" in emails
        assert "claimed@test.com" not in emails

    def test_find_by_email(self, db: Session):
        _make_invitation(db, email="findme@test.com")

        result = db.execute(
            select(PreAuthorizedEmail).where(PreAuthorizedEmail.email == "findme@test.com")
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.email == "findme@test.com"

    def test_find_by_email_not_found(self, db: Session):
        result = db.execute(
            select(PreAuthorizedEmail).where(PreAuthorizedEmail.email == "ghost@test.com")
        )
        assert result.scalar_one_or_none() is None

    def test_auto_assign_role_flow(self, db: Session):
        """Simulate the on_after_register flow: find pre-auth, assign role, mark claimed."""
        admin = _make_admin(db)
        _make_invitation(
            db, email="newuser@test.com", role=UserRole.OPERADOR, invited_by=admin.id
        )

        # Simulate user registration
        new_user = User(
            email="newuser@test.com",
            hashed_password="fakehash",
            nombre="New",
            apellido="User",
            role=UserRole.CIUDADANO,  # default role
        )
        db.add(new_user)
        db.flush()

        # Simulate on_after_register check
        result = db.execute(
            select(PreAuthorizedEmail).where(
                PreAuthorizedEmail.email == new_user.email,
                PreAuthorizedEmail.claimed == False,  # noqa: E712
            )
        )
        pre_auth = result.scalar_one_or_none()
        assert pre_auth is not None

        # Apply role
        new_user.role = pre_auth.role
        pre_auth.claimed = True
        db.flush()

        db.refresh(new_user)
        db.refresh(pre_auth)

        assert new_user.role == UserRole.OPERADOR
        assert pre_auth.claimed is True

    def test_no_auto_assign_without_preauth(self, db: Session):
        """User without pre-auth keeps default ciudadano role."""
        new_user = User(
            email="regular@test.com",
            hashed_password="fakehash",
            nombre="Regular",
            apellido="User",
            role=UserRole.CIUDADANO,
        )
        db.add(new_user)
        db.flush()

        result = db.execute(
            select(PreAuthorizedEmail).where(
                PreAuthorizedEmail.email == new_user.email,
                PreAuthorizedEmail.claimed == False,  # noqa: E712
            )
        )
        pre_auth = result.scalar_one_or_none()
        assert pre_auth is None

        # Role stays ciudadano
        assert new_user.role == UserRole.CIUDADANO

    def test_claimed_invitation_not_reused(self, db: Session):
        """Once claimed, a pre-auth entry should not be found for new registrations."""
        admin = _make_admin(db)
        _make_invitation(
            db, email="once@test.com", role=UserRole.ADMIN, invited_by=admin.id, claimed=True
        )

        result = db.execute(
            select(PreAuthorizedEmail).where(
                PreAuthorizedEmail.email == "once@test.com",
                PreAuthorizedEmail.claimed == False,  # noqa: E712
            )
        )
        assert result.scalar_one_or_none() is None


# ──────────────────────────────────────────────
# SCHEMA TESTS
# ──────────────────────────────────────────────


class TestInvitationSchemas:
    def test_invitation_read_from_orm(self, db: Session):
        from app.api.v2.admin_invitations import InvitationRead

        invitation = _make_invitation(db, email="schema@test.com")
        read = InvitationRead.model_validate(invitation)
        assert read.email == "schema@test.com"
        assert read.role == UserRole.OPERADOR
        assert read.claimed is False
        assert read.created_at is not None

    def test_invite_request_validation(self):
        from app.api.v2.admin_invitations import InvitationItem, InviteRequest

        req = InviteRequest(
            invitations=[
                InvitationItem(email="a@b.com", role=UserRole.OPERADOR),
                InvitationItem(email="c@d.com", role=UserRole.ADMIN),
            ]
        )
        assert len(req.invitations) == 2

    def test_invite_request_requires_at_least_one(self):
        from pydantic import ValidationError
        from app.api.v2.admin_invitations import InviteRequest

        with pytest.raises(ValidationError):
            InviteRequest(invitations=[])

    def test_invitation_result(self):
        from app.api.v2.admin_invitations import InvitationResult

        result = InvitationResult(
            email="test@test.com", role=UserRole.OPERADOR, status="created"
        )
        assert result.status == "created"
