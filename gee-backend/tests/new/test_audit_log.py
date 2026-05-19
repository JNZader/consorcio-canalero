"""Tests for the audit_log shared module (Phase 4 / F4-H).

The audit log persists evidence for Ley 25.326 trazabilidad — when a
future ARCO request lands the operator must be able to answer "your
data was viewed by these users on these dates". The contract here:

  - the helper appends ONE row per call (idempotency is the caller's
    responsibility, not ours);
  - ``resource`` and ``client_ip`` are bounded by the column widths
    (512 / 64) regardless of what the caller passes;
  - the caller owns the commit boundary — these helpers only ``.add()``,
    never ``.commit()`` or ``.flush()``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

# Force registration of the ``users`` table in ``Base.metadata`` before
# ``audit_log`` is loaded — the FK ``audit_log.user_id → users.id`` needs
# the target table to be visible at CREATE TABLE time, otherwise the
# session fixture's ``Base.metadata.create_all(...)`` raises
# NoReferencedTableError.
from app.auth.models import User  # noqa: F401
from app.shared.audit_log import AuditLog, write_audit_entry_sync


@pytest.fixture
def user_id(db) -> uuid.UUID:
    """Insert a minimal ``users`` row so the FK on ``audit_log.user_id``
    is satisfied at flush time, and return its UUID."""
    from app.auth.models import UserRole

    user = User(
        id=uuid.uuid4(),
        email=f"audit-test-{uuid.uuid4()}@x.test",
        hashed_password="x" * 20,
        is_active=True,
        is_verified=True,
        is_superuser=False,
        role=UserRole.OPERADOR,
    )
    db.add(user)
    db.flush()
    return user.id


class TestWriteAuditEntrySync:
    def test_appends_a_single_row(self, db, user_id):
        write_audit_entry_sync(
            db,
            user_id=user_id,
            action="padron.get",
            resource="consorcista_id=abc-123",
            client_ip="10.0.0.1",
        )
        db.flush()
        rows = db.execute(select(AuditLog)).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.user_id == user_id
        assert row.action == "padron.get"
        assert row.resource == "consorcista_id=abc-123"
        assert row.client_ip == "10.0.0.1"

    def test_occurred_at_is_utc_now(self, db, user_id):
        before = datetime.now(tz=timezone.utc)
        write_audit_entry_sync(
            db,
            user_id=user_id,
            action="padron.get",
            resource="r",
        )
        db.flush()
        row = db.execute(select(AuditLog)).scalar_one()
        after = datetime.now(tz=timezone.utc)
        # Timestamp must be within the [before, after] window, with TZ.
        assert row.occurred_at.tzinfo is not None
        assert before - timedelta(seconds=1) <= row.occurred_at <= after + timedelta(seconds=1)

    def test_allows_null_user_id(self, db):
        """Unauthenticated accesses still get logged (rare but legal)."""
        write_audit_entry_sync(
            db,
            user_id=None,
            action="public.scan",
            resource="path=/x",
        )
        db.flush()
        row = db.execute(select(AuditLog)).scalar_one()
        assert row.user_id is None

    def test_truncates_resource_to_512_chars(self, db, user_id):
        """The DB column caps at 512; the helper must NOT raise on a
        longer payload — it must truncate. Otherwise a malformed log
        attempt would bring down a real query path."""
        long_resource = "x" * 1000
        write_audit_entry_sync(
            db,
            user_id=user_id,
            action="catastro.list",
            resource=long_resource,
        )
        db.flush()
        row = db.execute(select(AuditLog)).scalar_one()
        assert len(row.resource) == 512
        assert row.resource == "x" * 512

    def test_truncates_client_ip_to_64_chars(self, db, user_id):
        """An IP shouldn't reach 64 chars, but a forged ``X-Forwarded-For``
        could carry a long chain. The helper truncates instead of
        raising."""
        long_ip = "1.2.3.4," * 20  # 160 chars
        write_audit_entry_sync(
            db,
            user_id=user_id,
            action="padron.get",
            resource="r",
            client_ip=long_ip,
        )
        db.flush()
        row = db.execute(select(AuditLog)).scalar_one()
        assert row.client_ip is not None
        assert len(row.client_ip) == 64

    def test_empty_client_ip_becomes_null(self, db, user_id):
        """Empty string → NULL keeps the analytics simpler (no need to
        filter ``WHERE client_ip != ''``). Same for absent header."""
        write_audit_entry_sync(
            db,
            user_id=user_id,
            action="padron.get",
            resource="r",
            client_ip="",
        )
        db.flush()
        row = db.execute(select(AuditLog)).scalar_one()
        assert row.client_ip is None

    def test_client_ip_defaults_to_none(self, db, user_id):
        write_audit_entry_sync(
            db,
            user_id=user_id,
            action="padron.get",
            resource="r",
        )
        db.flush()
        row = db.execute(select(AuditLog)).scalar_one()
        assert row.client_ip is None

    def test_does_not_commit(self, db, user_id):
        """The caller owns the commit boundary. If we committed inside
        the helper, two writes in the same request would each create
        their own transaction and a later rollback couldn't undo the
        audit row — that's a bug, not a feature."""
        write_audit_entry_sync(
            db,
            user_id=user_id,
            action="padron.get",
            resource="r",
        )
        # Without an explicit ``db.flush()`` the row is in the session
        # but not yet in the DB. The fixture rollback should drop it.
        # We verify by checking ``session.new``.
        pending = [obj for obj in db.new if isinstance(obj, AuditLog)]
        assert len(pending) == 1
