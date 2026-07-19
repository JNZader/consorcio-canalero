"""PostgreSQL integration coverage for Celery outbox ownership and retention."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.shared.celery_outbox import (
    CeleryTaskKey,
    CeleryTaskOutbox,
    _claim_due_celery_task,
    _finalize_published,
    enqueue_celery_task,
    publish_due_celery_tasks,
)


pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def outbox_session_factory(test_engine):
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    with factory() as db:
        db.execute(delete(CeleryTaskOutbox))
        db.commit()
    yield factory
    with factory() as db:
        db.execute(delete(CeleryTaskOutbox))
        db.commit()


def _insert(
    factory,
    *,
    task_key: CeleryTaskKey = CeleryTaskKey.COMPUTE_SLOPE,
    celery_task_id: uuid.UUID | None = None,
    next_attempt_at: datetime = NOW,
    raw_task_key: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    fixed_task_id = celery_task_id or uuid.uuid4()
    with factory() as db:
        row = enqueue_celery_task(
            db,
            celery_task_id=fixed_task_id,
            task_key=task_key,
            task_args=["dem.tif", "slope.tif"],
            task_kwargs={"job_id": str(uuid.uuid4())},
        )
        row.next_attempt_at = next_attempt_at
        if raw_task_key is not None:
            row.task_key = raw_task_key
        db.commit()
        return row.id, fixed_task_id


def test_enqueue_commit_rollback_and_unique_task_id(outbox_session_factory) -> None:
    factory = outbox_session_factory
    committed_id, task_id = _insert(factory)

    with factory() as db:
        committed = db.get(CeleryTaskOutbox, committed_id)
        assert committed is not None
        assert committed.celery_task_id == str(task_id)

        rolled_back = enqueue_celery_task(
            db,
            celery_task_id=uuid.uuid4(),
            task_key=CeleryTaskKey.COMPUTE_ASPECT,
        )
        rolled_back_id = rolled_back.id
        db.rollback()

    with factory() as db:
        assert db.get(CeleryTaskOutbox, rolled_back_id) is None
        enqueue_celery_task(
            db,
            celery_task_id=task_id,
            task_key=CeleryTaskKey.COMPUTE_SLOPE,
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_two_concurrent_claimers_have_one_owner(outbox_session_factory) -> None:
    factory = outbox_session_factory
    outbox_id, _ = _insert(factory)
    barrier = Barrier(2)

    def claim_once():
        with factory() as db:
            barrier.wait(timeout=5)
            claim = _claim_due_celery_task(
                db,
                now=NOW,
                lease_for=timedelta(minutes=5),
                outbox_id=outbox_id,
            )
            db.commit()
            return claim

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: claim_once(), range(2)))

    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    assert winners[0].outbox_id == outbox_id


def test_concurrent_claimers_can_take_distinct_rows(outbox_session_factory) -> None:
    factory = outbox_session_factory
    expected_ids = {_insert(factory)[0], _insert(factory)[0]}
    barrier = Barrier(2)

    def claim_once():
        with factory() as db:
            barrier.wait(timeout=5)
            claim = _claim_due_celery_task(
                db,
                now=NOW,
                lease_for=timedelta(minutes=5),
            )
            db.commit()
            return claim

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: claim_once(), range(2)))

    assert {claim.outbox_id for claim in claims if claim is not None} == expected_ids


def test_expired_lease_is_reclaimed_and_old_token_cannot_finalize(
    outbox_session_factory,
) -> None:
    factory = outbox_session_factory
    outbox_id, _ = _insert(factory)

    with factory() as db:
        old_claim = _claim_due_celery_task(
            db,
            now=NOW,
            lease_for=timedelta(seconds=1),
            outbox_id=outbox_id,
        )
        db.commit()
    assert old_claim is not None

    with factory() as db:
        new_claim = _claim_due_celery_task(
            db,
            now=NOW + timedelta(seconds=2),
            lease_for=timedelta(minutes=5),
            outbox_id=outbox_id,
        )
        db.commit()
    assert new_claim is not None
    assert new_claim.lease_id != old_claim.lease_id
    assert new_claim.attempts == 2

    with factory() as db:
        assert _finalize_published(db, claim=old_claim, now=NOW + timedelta(seconds=3)) is False
        db.commit()
    with factory() as db:
        assert _finalize_published(db, claim=new_claim, now=NOW + timedelta(seconds=3)) is True
        db.commit()

    with factory() as db:
        row = db.get(CeleryTaskOutbox, outbox_id)
        assert row is not None
        assert row.published_at == NOW + timedelta(seconds=3)
        assert row.lease_id is None
        assert row.lease_expires_at is None


def test_poison_row_does_not_block_valid_row(outbox_session_factory) -> None:
    factory = outbox_session_factory
    poison_id, _ = _insert(factory, raw_task_key="system.shell")
    valid_id, valid_task_id = _insert(factory)
    task = MagicMock()
    task.name = CeleryTaskKey.COMPUTE_SLOPE.value

    stats = publish_due_celery_tasks(
        batch_size=2,
        cleanup_batch_size=0,
        session_factory=factory,
        now=NOW,
        task_registry={CeleryTaskKey.COMPUTE_SLOPE: task},
    )

    assert stats["claimed"] == 2
    assert stats["failed"] == 1
    assert stats["published"] == 1
    task.apply_async.assert_called_once()
    assert task.apply_async.call_args.kwargs["task_id"] == str(valid_task_id)
    assert task.apply_async.call_args.kwargs["retry"] is False

    with factory() as db:
        poison = db.get(CeleryTaskOutbox, poison_id)
        valid = db.get(CeleryTaskOutbox, valid_id)
        assert poison is not None
        assert poison.published_at is None
        assert poison.lease_id is None
        assert poison.next_attempt_at == NOW + timedelta(seconds=5)
        assert "system.shell" not in (poison.last_error or "")
        assert valid is not None
        assert valid.published_at == NOW


def test_retention_deletes_only_old_published_rows_in_bounded_batch(
    outbox_session_factory,
) -> None:
    factory = outbox_session_factory
    old_ids = {_insert(factory)[0], _insert(factory)[0]}
    fresh_id, _ = _insert(factory)
    pending_id, _ = _insert(factory)

    with factory() as db:
        for outbox_id in old_ids:
            db.get(CeleryTaskOutbox, outbox_id).published_at = NOW - timedelta(days=31)
        db.get(CeleryTaskOutbox, fresh_id).published_at = NOW - timedelta(days=1)
        db.commit()

    stats = publish_due_celery_tasks(
        batch_size=0,
        cleanup_batch_size=1,
        retention=timedelta(days=30),
        session_factory=factory,
        now=NOW,
        task_registry={},
    )

    assert stats["cleaned"] == 1
    with factory() as db:
        remaining_old = db.scalar(
            select(func.count())
            .select_from(CeleryTaskOutbox)
            .where(CeleryTaskOutbox.id.in_(old_ids))
        )
        assert remaining_old == 1
        assert db.get(CeleryTaskOutbox, fresh_id) is not None
        pending = db.get(CeleryTaskOutbox, pending_id)
        assert pending is not None
        assert pending.published_at is None
