from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.shared.celery_outbox import (
    MAX_CLEANUP_BATCH_SIZE,
    MAX_PUBLISH_BATCH_SIZE,
    CeleryTaskKey,
    ClaimedCeleryTask,
    InvalidCeleryTaskRegistryError,
    UnknownCeleryTaskKeyError,
    _claim_due_celery_task,
    _cleanup_published,
    _finalize_published,
    _process_claimed,
    _publish_claimed,
    _safe_publication_error,
    celery_outbox_backoff,
    enqueue_celery_task,
    get_celery_task_registry,
    publish_due_celery_tasks,
    try_publish_celery_task,
)


NOW = datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)


def _claim(
    task_key: str = CeleryTaskKey.COMPUTE_SLOPE.value,
    *,
    attempts: int = 1,
) -> ClaimedCeleryTask:
    return ClaimedCeleryTask(
        outbox_id=uuid.uuid4(),
        celery_task_id=str(uuid.uuid4()),
        task_key=task_key,
        task_args=["dem.tif", "slope.tif"],
        task_kwargs={"job_id": str(uuid.uuid4())},
        attempts=attempts,
        lease_id=uuid.uuid4(),
    )


def _task(name: str = CeleryTaskKey.COMPUTE_SLOPE.value) -> MagicMock:
    task = MagicMock()
    task.name = name
    return task


def test_task_key_allowlist_is_exact() -> None:
    assert {task_key.value for task_key in CeleryTaskKey} == {
        "geo.process_dem_pipeline",
        "geo.compute_slope",
        "geo.compute_aspect",
        "geo.compute_flow_direction",
        "geo.compute_flow_accumulation",
        "geo.compute_twi",
        "geo.compute_hand",
        "geo.extract_drainage_network",
        "geo.classify_terrain",
        "gee.analyze_flood",
        "gee.supervised_classification",
        "geo.run_full_dem_pipeline",
        "geo.delineate_basins",
        "geo.composite_analysis",
        "gee.sar_temporal",
        "geo.intelligence.compute_road_flow_crossings",
        "geo.relevamiento.classify_road_segments",
    }


def test_registry_contains_concrete_tasks_with_matching_names() -> None:
    registry = get_celery_task_registry()

    assert set(registry) == set(CeleryTaskKey)
    assert all(task.name == task_key.value for task_key, task in registry.items())
    assert all(callable(task.apply_async) for task in registry.values())


def test_enqueue_uses_fixed_uuid_and_copies_json_payload() -> None:
    db = MagicMock()
    celery_task_id = uuid.uuid4()
    args = ["dem.tif"]
    kwargs = {"nested": {"value": 1}}

    row = enqueue_celery_task(
        db,
        celery_task_id=celery_task_id,
        task_key=CeleryTaskKey.PROCESS_DEM_PIPELINE,
        task_args=args,
        task_kwargs=kwargs,
    )
    args.append("mutated")
    kwargs["nested"]["value"] = 2

    assert row.celery_task_id == str(celery_task_id)
    assert row.task_key == CeleryTaskKey.PROCESS_DEM_PIPELINE.value
    assert row.task_args == ["dem.tif"]
    assert row.task_kwargs == {"nested": {"value": 1}}
    assert isinstance(row.id, uuid.UUID)
    db.add.assert_called_once_with(row)


def test_enqueue_rejects_raw_task_names_and_non_json_payloads() -> None:
    with pytest.raises(TypeError, match="CeleryTaskKey"):
        enqueue_celery_task(
            MagicMock(),
            celery_task_id=uuid.uuid4(),
            task_key="geo.compute_slope",  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="JSON serializable"):
        enqueue_celery_task(
            MagicMock(),
            celery_task_id=uuid.uuid4(),
            task_key=CeleryTaskKey.COMPUTE_SLOPE,
            task_kwargs={"not_json": object()},
        )


def test_publish_calls_concrete_task_with_fixed_id_and_broker_retry_disabled() -> None:
    claim = _claim()
    task = _task()
    registry = {CeleryTaskKey.COMPUTE_SLOPE: task}

    _publish_claimed(claim, task_registry=registry)
    _publish_claimed(claim, task_registry=registry)

    assert task.apply_async.call_count == 2
    task.apply_async.assert_called_with(
        args=claim.task_args,
        kwargs=claim.task_kwargs,
        task_id=claim.celery_task_id,
        retry=False,
    )


def test_unknown_or_mismatched_task_key_never_executes() -> None:
    with pytest.raises(UnknownCeleryTaskKeyError):
        _publish_claimed(_claim("system.shell"), task_registry={})

    mismatched = _task("geo.compute_aspect")
    with pytest.raises(InvalidCeleryTaskRegistryError):
        _publish_claimed(
            _claim(),
            task_registry={CeleryTaskKey.COMPUTE_SLOPE: mismatched},
        )
    mismatched.apply_async.assert_not_called()


def test_claim_statement_uses_skip_locked_and_optional_exact_id() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    outbox_id = uuid.uuid4()

    assert (
        _claim_due_celery_task(
            db,
            now=NOW,
            lease_for=timedelta(minutes=5),
            outbox_id=outbox_id,
        )
        is None
    )

    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "celery_task_outbox.id" in sql
    assert "celery_task_outbox.published_at IS NULL" in sql
    assert "celery_task_outbox.next_attempt_at <=" in sql


def test_finalize_statement_is_fenced_by_row_and_lease_token() -> None:
    db = MagicMock()
    db.execute.return_value.rowcount = 1
    claim = _claim()

    assert _finalize_published(db, claim=claim, now=NOW) is True

    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "celery_task_outbox.id =" in sql
    assert "celery_task_outbox.lease_id =" in sql
    assert "celery_task_outbox.published_at IS NULL" in sql


def test_retention_statement_is_bounded_and_skip_locked() -> None:
    db = MagicMock()
    db.execute.return_value.rowcount = 2

    deleted = _cleanup_published(
        db,
        cutoff=NOW - timedelta(days=30),
        batch_size=2,
    )

    assert deleted == 2
    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "DELETE FROM celery_task_outbox" in sql
    assert "LIMIT" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql


@pytest.mark.parametrize(
    ("attempts", "seconds"),
    [(1, 5), (2, 10), (3, 20), (8, 640), (9, 900), (1_000_000, 900)],
)
def test_backoff_is_exponential_and_capped(attempts: int, seconds: int) -> None:
    assert celery_outbox_backoff(attempts) == timedelta(seconds=seconds)


def test_failure_diagnostic_is_sanitized_and_bounded() -> None:
    diagnostic = _safe_publication_error(
        ConnectionError("redis://user:secret@broker/home/private token=" + "x" * 500)
    )

    assert diagnostic == "ConnectionError: Celery publication failed"
    assert len(diagnostic) <= 255
    assert "secret" not in diagnostic.lower()
    assert "/home/" not in diagnostic


def test_poison_row_records_backoff_without_arbitrary_publication(caplog) -> None:
    claim = _claim("system.shell", attempts=4)
    db = MagicMock()
    db.execute.return_value.rowcount = 1

    with caplog.at_level(logging.WARNING):
        outcome = _process_claimed(
            claim,
            session_factory=lambda: db,
            now=NOW,
            task_registry={},
        )

    assert outcome == "failed"
    db.commit.assert_called_once()
    statement = db.execute.call_args.args[0]
    params = statement.compile(dialect=postgresql.dialect()).params
    assert params["next_attempt_at"] == NOW + timedelta(seconds=40)
    assert params["last_error"].startswith("UnknownCeleryTaskKeyError:")
    assert "system.shell" not in caplog.text


def test_finalize_storage_failure_after_publish_is_contained(caplog) -> None:
    claim = _claim()
    task = _task()
    db = MagicMock()
    db.execute.side_effect = RuntimeError("password=do-not-log")

    with caplog.at_level(logging.ERROR):
        outcome = _process_claimed(
            claim,
            session_factory=lambda: db,
            now=NOW,
            task_registry={CeleryTaskKey.COMPUTE_SLOPE: task},
        )

    assert outcome == "finalize_lost"
    task.apply_async.assert_called_once()
    db.rollback.assert_called_once()
    assert "do-not-log" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_batch_isolates_poison_row_and_continues_to_valid_row() -> None:
    poison = _claim("system.shell")
    valid = _claim()

    with (
        patch(
            "app.shared.celery_outbox._claim_committed",
            side_effect=[poison, valid, None],
        ),
        patch(
            "app.shared.celery_outbox._process_claimed",
            side_effect=["failed", "published"],
        ) as process,
        patch("app.shared.celery_outbox._cleanup_committed", return_value=3),
    ):
        stats = publish_due_celery_tasks(
            session_factory=MagicMock(),
            now=NOW,
            task_registry={},
        )

    assert process.call_count == 2
    assert stats == {
        "claimed": 2,
        "published": 1,
        "failed": 1,
        "finalize_lost": 0,
        "claim_errors": 0,
        "cleaned": 3,
    }


def test_batch_and_retention_work_are_hard_capped() -> None:
    claim = _claim()
    with (
        patch("app.shared.celery_outbox._claim_committed", return_value=claim) as claim_one,
        patch("app.shared.celery_outbox._process_claimed", return_value="published"),
        patch("app.shared.celery_outbox._cleanup_committed", return_value=0) as cleanup,
    ):
        stats = publish_due_celery_tasks(
            batch_size=1_000_000,
            cleanup_batch_size=1_000_000,
            session_factory=MagicMock(),
            now=NOW,
            task_registry={CeleryTaskKey.COMPUTE_SLOPE: _task()},
        )

    assert claim_one.call_count == MAX_PUBLISH_BATCH_SIZE
    assert stats["published"] == MAX_PUBLISH_BATCH_SIZE
    assert cleanup.call_args.kwargs["batch_size"] == MAX_CLEANUP_BATCH_SIZE


def test_immediate_publish_contains_claim_storage_failure(caplog) -> None:
    db = MagicMock()
    db.execute.side_effect = RuntimeError("token=do-not-log")

    with caplog.at_level(logging.ERROR):
        published = try_publish_celery_task(
            uuid.uuid4(),
            session_factory=lambda: db,
            now=NOW,
            task_registry={},
        )

    assert published is False
    db.rollback.assert_called_once()
    assert "do-not-log" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_batch_continues_after_unexpected_process_error(caplog) -> None:
    first = _claim()
    second = _claim()
    with (
        patch(
            "app.shared.celery_outbox._claim_committed",
            side_effect=[first, second, None],
        ),
        patch(
            "app.shared.celery_outbox._process_claimed",
            side_effect=[RuntimeError("password=do-not-log"), "published"],
        ),
        patch("app.shared.celery_outbox._cleanup_committed", return_value=0),
        caplog.at_level(logging.ERROR),
    ):
        stats = publish_due_celery_tasks(
            session_factory=MagicMock(),
            now=NOW,
            task_registry={},
        )

    assert stats["claimed"] == 2
    assert stats["published"] == 1
    assert stats["finalize_lost"] == 1
    assert "do-not-log" not in caplog.text


def test_immediate_publish_contains_unexpected_process_error(caplog) -> None:
    claim = _claim()
    with (
        patch("app.shared.celery_outbox._claim_committed", return_value=claim),
        patch(
            "app.shared.celery_outbox._process_claimed",
            side_effect=RuntimeError("token=do-not-log"),
        ),
        caplog.at_level(logging.ERROR),
    ):
        published = try_publish_celery_task(
            claim.outbox_id,
            session_factory=MagicMock(),
            now=NOW,
            task_registry={},
        )

    assert published is False
    assert "do-not-log" not in caplog.text
