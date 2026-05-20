"""Add users.revocation_epoch for zero-trust JWT revocation.

Phase 5 / F5-F. Closes the 15-min residual window after a
``/auth/jwt/logout-all`` invocation:

The endpoint currently revokes every refresh-token row for the user,
but JWT access tokens issued in the previous 15 minutes remain valid
until natural expiry (stateless by design — no server-side revocation
list for access tokens). Practical implication: an attacker with a
stolen access token has up to ~15 min to do damage after the user
clicks "logout from all devices".

With ``revocation_epoch``:
  - Every issued JWT embeds the user's current epoch value.
  - On every request the JWT strategy compares the token's epoch
    against ``user.revocation_epoch`` (one extra DB column read, no
    extra query — the user row is already loaded for auth).
  - ``/auth/jwt/logout-all`` increments the user's epoch, so every
    previously-issued token is immediately invalid.

Default 0 so existing tokens issued before this migration land
keep working (their implicit epoch is 0, the user's is 0 → OK).
A future logout-all bumps the user to 1 and the old tokens fail.

Revision ID: zz_user_revocation_epoch
Revises: zz_audit_log
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from alembic import op


revision = "zz_user_revocation_epoch"
down_revision = "zz_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "revocation_epoch",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "revocation_epoch")
