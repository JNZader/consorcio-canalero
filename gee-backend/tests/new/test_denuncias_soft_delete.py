"""Phase 4 / F4-K — soft-delete + ARCO purge tests.

The DELETE /denuncias/{id}/mine endpoint flips ``deleted_at`` and lets
the row stay for 1 year as evidence of the operator's response. After
that window, the cleanup cron hard-deletes it.

These tests cover the BEHAVIOUR of that pipeline at the repository +
cleanup-task layer. The endpoint itself is auth-gated and exercised
via ``test_auth_gates.py`` (401 unauth + 404 cross-user); proving the
happy path needs a fully-issued JWT, which is out of scope here.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from geoalchemy2.functions import ST_MakePoint, ST_SetSRID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.auth.cleanup_tasks import (
    DELETED_DENUNCIA_GRACE,
    purge_soft_deleted_denuncias,
)
from app.auth.models import User  # noqa: F401  — register the users table
from app.domains.denuncias.models import Denuncia, EstadoDenuncia
from app.domains.denuncias.repository import DenunciaRepository


@pytest.fixture
def user_id(db) -> uuid.UUID:
    from app.auth.models import UserRole

    user = User(
        id=uuid.uuid4(),
        email=f"soft-delete-test-{uuid.uuid4().hex[:8]}@x.test",
        hashed_password="x" * 20,
        is_active=True,
        is_verified=True,
        is_superuser=False,
        role=UserRole.CIUDADANO,
    )
    db.add(user)
    db.flush()
    return user.id


@pytest.fixture
def repo() -> DenunciaRepository:
    return DenunciaRepository()


def _make_denuncia(db, *, user_id: uuid.UUID, deleted_at: datetime | None = None) -> Denuncia:
    """Helper — bypasses the service so we can control ``deleted_at``."""
    denuncia = Denuncia(
        tipo="desborde",
        descripcion="Soft-delete fixture denuncia (≥30 chars OK).",
        latitud=-33.7,
        longitud=-63.9,
        geom=ST_SetSRID(ST_MakePoint(-63.9, -33.7), 4326),
        cuenca="cuenca_1",
        estado=EstadoDenuncia.PENDIENTE,
        contacto_email="x@y.test",
        user_id=user_id,
        deleted_at=deleted_at,
    )
    db.add(denuncia)
    db.flush()
    return denuncia


class TestRepositoryHidesSoftDeleted:
    """The 3 read paths must all filter out ``deleted_at IS NOT NULL``."""

    def test_get_by_id_returns_none_for_soft_deleted(self, db, user_id, repo):
        now = datetime.now(tz=timezone.utc)
        d = _make_denuncia(db, user_id=user_id, deleted_at=now)
        # The fixture itself succeeded — but the read path hides it.
        assert repo.get_by_id(db, d.id) is None

    def test_get_by_id_returns_live_row(self, db, user_id, repo):
        d = _make_denuncia(db, user_id=user_id, deleted_at=None)
        found = repo.get_by_id(db, d.id)
        assert found is not None
        assert found.id == d.id

    def test_get_all_excludes_soft_deleted(self, db, user_id, repo):
        now = datetime.now(tz=timezone.utc)
        _make_denuncia(db, user_id=user_id, deleted_at=None)
        _make_denuncia(db, user_id=user_id, deleted_at=now)
        items, total = repo.get_all(db, page=1, limit=20)
        assert total == 1
        assert len(items) == 1
        assert items[0].deleted_at is None

    def test_get_all_by_user_excludes_soft_deleted(self, db, user_id, repo):
        now = datetime.now(tz=timezone.utc)
        _make_denuncia(db, user_id=user_id, deleted_at=None)
        _make_denuncia(db, user_id=user_id, deleted_at=now)
        items, total = repo.get_all_by_user(db, user_id=user_id, page=1, limit=20)
        assert total == 1
        assert len(items) == 1


class TestPurgeSoftDeletedDenuncias:
    """End-to-end test for the async cleanup task.

    We can't use the sync ``db`` fixture here — ``purge_soft_deleted_denuncias``
    expects an ``AsyncSession`` and commits internally. The fixture's
    transaction wrap would either swallow the commit or rollback the
    purge. Instead we spin up an isolated AsyncEngine pointing at the
    same DB, seed via the AsyncSession, call the real production
    function under test, and clean up after ourselves.

    Net effect: the test exercises the EXACT code path that runs in
    Celery — async session, set-based DELETE, grace-window WHERE
    clause. A refactor that breaks the WHERE shape, the grace window,
    or the async signature fails this test.
    """

    @pytest.mark.asyncio
    async def test_purges_rows_older_than_grace(self):
        """The real async function must purge ONLY rows whose
        ``deleted_at`` is older than the grace window."""
        # Build an async engine from the same DB the sync tests use.
        # ``conftest.py`` set DATABASE_URL on the test container; we
        # convert it to the asyncpg driver explicitly.
        sync_url = os.environ["DATABASE_URL"]
        async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        async_engine = create_async_engine(async_url, echo=False)
        AsyncSessionLocal = sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )

        now = datetime.now(tz=timezone.utc)
        old_deletion = now - DELETED_DENUNCIA_GRACE - timedelta(days=1)
        recent_deletion = now - timedelta(days=1)

        # Seed a user + three denuncias in distinct deletion states.
        from app.auth.models import UserRole
        from sqlalchemy import delete as sa_delete, insert

        user_id_val = uuid.uuid4()
        seeded_ids: list[uuid.UUID] = []

        async with AsyncSessionLocal() as session:
            await session.execute(
                insert(User).values(
                    id=user_id_val,
                    email=f"purge-real-{uuid.uuid4().hex[:8]}@x.test",
                    hashed_password="x" * 20,
                    is_active=True,
                    is_verified=True,
                    is_superuser=False,
                    role=UserRole.CIUDADANO,
                )
            )

            for deleted_at_val in (old_deletion, recent_deletion, None):
                d_id = uuid.uuid4()
                seeded_ids.append(d_id)
                await session.execute(
                    insert(Denuncia).values(
                        id=d_id,
                        tipo="desborde",
                        descripcion="Async purge fixture (≥30 chars).",
                        latitud=-33.7,
                        longitud=-63.9,
                        geom=ST_SetSRID(ST_MakePoint(-63.9, -33.7), 4326),
                        cuenca="cuenca_1",
                        estado=EstadoDenuncia.PENDIENTE,
                        contacto_email="x@y.test",
                        user_id=user_id_val,
                        deleted_at=deleted_at_val,
                    )
                )
            await session.commit()

        d_old_id, d_recent_id, d_live_id = seeded_ids

        # Exercise the ACTUAL production function.
        async with AsyncSessionLocal() as session:
            rowcount = await purge_soft_deleted_denuncias(session)

        try:
            assert rowcount == 1, (
                f"purge_soft_deleted_denuncias should remove EXACTLY the "
                f"one row outside the grace window, got rowcount={rowcount}"
            )
            async with AsyncSessionLocal() as session:
                survivors = (
                    await session.execute(
                        select(Denuncia.id).where(
                            Denuncia.id.in_(seeded_ids)
                        )
                    )
                ).scalars().all()
            survivors_set = set(survivors)
            assert d_old_id not in survivors_set, "expired row should be hard-deleted"
            assert d_recent_id in survivors_set, (
                "recently soft-deleted row is still inside the audit window"
            )
            assert d_live_id in survivors_set, "live row must never be touched"
        finally:
            # Cleanup ourselves — no transaction wrap on async engine.
            async with AsyncSessionLocal() as session:
                await session.execute(
                    sa_delete(Denuncia).where(Denuncia.id.in_(seeded_ids))
                )
                await session.execute(
                    sa_delete(User).where(User.id == user_id_val)
                )
                await session.commit()
            await async_engine.dispose()
