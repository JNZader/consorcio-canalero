"""Audit log for catastro / zonas queries (Phase 4 / F4-H, Ley 25.326).

The catastro and zonificación tables identify natural persons through
their cuenta number → name → property location chain. Ley 25.326 §21
requires the data controller to maintain trazabilidad of who consulted
those records and when, so a future ARCO request from a titular can be
answered with "your data was viewed by these users on these dates".

The audit table is intentionally append-only (no UPDATE, no DELETE
from the application). Operators can purge it on a separate retention
policy via a dedicated cron task (out of scope for this commit).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base, UUIDMixin


class AuditLog(UUIDMixin, Base):
    """One row per sensitive data access (catastro lookup, zona query)."""

    __tablename__ = "audit_log"

    # Append-only — no ``TimestampMixin`` because we own the timestamp
    # and don't want SQLAlchemy's ``onupdate=`` to mutate it.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # ``None`` when the access was unauthenticated (rare — most
    # catastro queries require an operator role).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The action category. Free text but kept short for index health.
    # Use one of: "catastro.get", "catastro.list", "zona.intersect",
    # "padron.get", "padron.list", "denuncias.geom.read".
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # The resource the action touched. Format depends on the action:
    #   - ``catastro.get`` → ``nro_cuenta=190119253334``
    #   - ``catastro.list`` → ``bbox=-62.7,-32.6,-62.5,-32.4``
    #   - ``zona.intersect`` → ``cuenca=ml,zone=norte``
    # Bounded to 512 chars; longer payloads truncate.
    resource: Mapped[str] = mapped_column(String(512), nullable=False)

    # Coarse client fingerprint for forensics.
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


def write_audit_entry_sync(
    session: Session,
    *,
    user_id: uuid.UUID | None,
    action: str,
    resource: str,
    client_ip: str | None = None,
) -> None:
    """Append one row. Caller commits or rolls back."""
    from datetime import timezone

    entry = AuditLog(
        occurred_at=datetime.now(tz=timezone.utc),
        user_id=user_id,
        action=action,
        resource=resource[:512],
        client_ip=(client_ip or "")[:64] or None,
    )
    session.add(entry)


async def write_audit_entry_async(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    resource: str,
    client_ip: str | None = None,
) -> None:
    """Async variant for endpoints on the async engine."""
    from datetime import timezone

    entry = AuditLog(
        occurred_at=datetime.now(tz=timezone.utc),
        user_id=user_id,
        action=action,
        resource=resource[:512],
        client_ip=(client_ip or "")[:64] or None,
    )
    session.add(entry)
