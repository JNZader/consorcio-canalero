"""Add email_codes table for SMTP-body PII hardening.

Phase 5 / F5-E. Ley 25.326 PII hardening on email-based credential
delivery (password-reset + email-verify).

Background
==========

Pre-F5-E, the SMTP body carried the LONG verify/reset JWT token in
plaintext. Most providers (Brevo, Resend, SES) retain message body
for 30+ days in support logs. A provider breach during that window
exfiltrates valid one-shot credentials. The mechanism is documented
in ``docs/KNOWN_LIMITATIONS.md`` under "SMTP body logging carries
reset / verify tokens".

This migration sets up the substrate for the F5-E fix: the SMTP
body now carries an 8-character alphanumeric CODE, and the SPA
exchanges that code for the real fastapi-users token via
``POST /auth/exchange-code``. Provider logs can keep the code for
as long as they want — once consumed (or expired) it's useless.

Schema
======

  - ``code``:        8-char uppercase alphanumeric (36^8 ≈ 2.8 trillion
                     combos → brute force infeasible at any feasible
                     rate). Indexed UNIQUE for the exchange lookup.
  - ``user_id``:     FK to users.id with ``ON DELETE CASCADE`` (user
                     deletion drops any open codes — no orphans).
  - ``purpose``:     "verify" or "reset" — same code namespace, the
                     SPA must specify which flow it's exchanging.
  - ``token``:       the original fastapi-users JWT this code stands
                     in for. Returned by ``/auth/exchange-code``.
  - ``created_at``:  audit + cron purge.
  - ``expires_at``:  one-time codes expire fast (default 15 min).
                     Indexed for the cron purge.
  - ``consumed_at``: NULL until first ``/auth/exchange-code`` —
                     enforces one-shot semantics.

Revision ID: zz_email_codes
Revises: zz_user_revocation_epoch
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "zz_email_codes"
down_revision = "zz_user_revocation_epoch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True, index=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("email_codes")
