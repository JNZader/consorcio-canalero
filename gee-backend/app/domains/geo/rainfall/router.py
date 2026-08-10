"""Authenticated snapshot-only Rainfall v2 API."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.router_common import parse_bounded_json_object
from app.domains.geo.rainfall.repository import RainfallRepository, ScopeConfigurationError
from app.domains.geo.rainfall.metrics import record_event
from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
from app.domains.geo.rainfall.series import build_series
from app.domains.geo.rainfall.service import (
    SnapshotContractError,
    analysis_request_fingerprint,
    metric_rows,
    metric_rows_csv,
    normalize_snapshot,
    queue_missing_analysis,
)
from app.domains.geo.rainfall.scope import (
    NoScopeMatch,
    ScopeRef,
    UnsupportedDirectScope,
    executable_scope,
)

MAX_RAINFALL_REQUEST_BYTES = 16_384


def _require_operator():
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


router = APIRouter(
    prefix="/rainfall", tags=["Rainfall v2"], dependencies=[Depends(_require_operator())]
)


class ScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    id: str | None = None
    version: str | None = None
    nomenclature: str | None = None
    geometry: dict | None = None


class EventWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_window(self) -> "EventWindow":
        if self.start.utcoffset() is None or self.end.utcoffset() is None or self.end <= self.start:
            raise ValueError("event window must be aware and half-open")
        return self


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: ScopeRequest
    year: int = Field(ge=1991, le=9999)
    event_window: EventWindow | None = None


async def _parse_request(request: Request, model: type[BaseModel]):
    payload = await parse_bounded_json_object(
        request, maximum=MAX_RAINFALL_REQUEST_BYTES, detail_prefix="rainfall request"
    )
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="rainfall request body is invalid") from exc


async def parse_scope_request(request: Request) -> ScopeRequest:
    return await _parse_request(request, ScopeRequest)


async def parse_analysis_request(request: Request) -> AnalysisRequest:
    return await _parse_request(request, AnalysisRequest)


def _request_body(model: type[BaseModel]) -> dict:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": model.model_json_schema()}},
        }
    }


@router.post("/scopes:resolve", openapi_extra=_request_body(ScopeRequest))
def resolve_scope(
    payload: ScopeRequest = Depends(parse_scope_request), db: Session = Depends(get_db)
):
    try:
        if payload.kind == "parcel":
            if not payload.nomenclature:
                raise NoScopeMatch("parcel nomenclature is required")
            choices = RainfallRepository().resolve_parcel_scopes(db, payload.nomenclature)
            return {"choices": choices, "regional_estimate": True}
        scope = executable_scope(ScopeRef(**payload.model_dump()))
    except (UnsupportedDirectScope, NoScopeMatch, ScopeConfigurationError, ValueError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return {"scope": scope, "regional_estimate": scope.regional_estimate}


def _requeue_stale_revision(db: Session, *, payload, scope, fingerprint: str) -> None:
    """Enqueue the stale-policy refresh WITHOUT letting it break the read
    (LI2B-002).

    The snapshot is already in memory by the time this runs, so a failing
    enqueue must never turn a serveable 200 into a 500. A bare ``try/except``
    is not enough: a statement that fails mid-transaction leaves the session
    ABORTED (SQLSTATE 25P02) and poisons everything that touches it
    afterwards, so the enqueue gets its own SAVEPOINT to roll back to.

    The savepoint is driven MANUALLY rather than through
    ``with db.begin_nested():`` on purpose, and the reason is empirical:
    ``queue_missing_analysis`` owns its own transaction boundary -- it
    ``commit()``s on success and ``rollback()``s to recover the
    ``IntegrityError`` race (decision 8, a spec-covered scenario). Inside the
    context-manager form, that inner ``rollback()`` closes the block's
    transaction and the very next statement -- the race recovery's own
    re-read -- raises ``InvalidRequestError: Can't operate on closed
    transaction inside context manager``. The manual form has no such guard,
    so both of the callee's paths keep working; ``is_active`` then tells us
    whether the savepoint is still ours to roll back or the callee already
    resolved it.

    ``record_event`` writes to the logger, never the session, but it is still
    emitted AFTER the rollback so the ordering never depends on that.
    """
    savepoint = db.begin_nested()
    try:
        queue_missing_analysis(
            db,
            scope=scope,
            year=payload.year,
            labels=("policy_revision_stale",),
            event_window=(
                payload.event_window.model_dump(mode="json") if payload.event_window else None
            ),
            request_fingerprint=fingerprint,
        )
    except (SQLAlchemyError, RuntimeError) as exc:
        if savepoint.is_active:
            savepoint.rollback()
        else:
            # The callee already committed or rolled back this savepoint and
            # then failed. Nothing else in this read path holds uncommitted
            # work, so a session-level rollback is the equally safe fallback
            # that still clears an aborted transaction.
            db.rollback()
        record_event(
            "rainfall.analysis.requeue_failed",
            scope_kind=scope.kind,
            scope_id=scope.id,
            scope_version=scope.version,
            year=payload.year,
            error_type=type(exc).__name__,
            error_message=str(exc)[:200],
        )
    else:
        if savepoint.is_active:
            savepoint.commit()


@router.post("/analyses", openapi_extra=_request_body(AnalysisRequest))
def read_analysis(
    payload: AnalysisRequest = Depends(parse_analysis_request), db: Session = Depends(get_db)
):
    started = datetime.now()
    try:
        scope = executable_scope(ScopeRef(**payload.scope.model_dump()))
    except (UnsupportedDirectScope, NoScopeMatch, ValueError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    request = {
        "scope": {"kind": scope.kind, "id": scope.id, "version": scope.version},
        "year": payload.year,
    }
    if payload.event_window is not None:
        request["event_window"] = payload.event_window.model_dump(mode="json")
    fingerprint = analysis_request_fingerprint(request)
    revision = RainfallRepository().get_snapshot(db, fingerprint)
    if revision is None:
        queued = queue_missing_analysis(
            db,
            scope=scope,
            year=payload.year,
            labels=("analysis_missing",),
            event_window=(
                payload.event_window.model_dump(mode="json") if payload.event_window else None
            ),
            request_fingerprint=fingerprint,
        )
        return JSONResponse(queued, status_code=202)
    # Read the row's fields BEFORE any enqueue below: queue_missing_analysis
    # commits, which expires the ORM instance and would make every later
    # attribute access a fresh SELECT.
    stored_snapshot = revision.snapshot
    stored_policy_revision = revision.policy_revision
    stored_data_revision = revision.data_revision
    revision_id = str(revision.id)

    if stored_policy_revision != RAINFALL_METRIC_POLICY_REVISION:
        # Task 2b.8 (design.md D3): the stored row was written under a
        # SUPERSEDED policy revision. It is still served -- normalized with
        # its OWN policy_revision below, so it stays self-consistent -- and a
        # refresh is enqueued so the enriched envelope eventually lands.
        # Neither sweep revisits a past-year key that is already `done`, so
        # the request path is the only place this is noticed. Enqueued BEFORE
        # normalization so a stale row that also fails its contract still
        # gets its healing refresh instead of only a 503.
        #
        # Bounded cost, corrected (LI2B-001 -- the earlier text here named
        # only the `done` cooldown and the pending pre-check, and was
        # therefore FALSE for the third state a key can be in). Every
        # terminal state a key's own history can reach now has a window, all
        # of them applied by service._requeue_cooldown:
        #   - newest row `done` (productive)  -> 10 min  (decision 6)
        #   - newest row `done` but its build REFUSED to write
        #     ("latched"/"gate_refused")      -> 24 h    (LI2B-003)
        #   - newest row terminal `failed`    -> 6 h     (LI2B-001)
        #   - a `pending` row already exists  -> reused, never duplicated
        # so a poll loop costs at most one refresh per key per window, never
        # one per poll, in EVERY state -- which is what the spec delta's
        # "Stale Policy Revision Refresh on Poll" MODIFIED requirement
        # promises.
        record_event(
            "rainfall.analysis.policy_revision_stale",
            revision_id=revision_id,
            scope_kind=scope.kind,
            scope_id=scope.id,
            scope_version=scope.version,
            year=payload.year,
            served_policy_revision=stored_policy_revision,
            current_policy_revision=RAINFALL_METRIC_POLICY_REVISION,
        )
        _requeue_stale_revision(db, payload=payload, scope=scope, fingerprint=fingerprint)

    try:
        normalized = normalize_snapshot(
            stored_snapshot, expected_policy_revision=stored_policy_revision
        )
        # JDB-301 (review-ledger.md "Judgment Day -- APPLY-PHASE completion"):
        # build_snapshot never sets this field (it does not know its own
        # persisted revision id yet), so it must be injected here, once the
        # served revision row is known. Already allow-listed in
        # SNAPSHOT_ROOT_KEYS (service.py:143); normalize_snapshot copies the
        # envelope via `dict(snapshot)` and never strips extra/missing root
        # keys, so setting it post-normalize is safe and does not need to
        # touch normalize_snapshot itself.
        normalized["analysis_revision_id"] = revision_id
        # design.md D3 (slice 3a): same mechanism, same reason -- the row's
        # `data_revision` column is computed after `build_snapshot` returns
        # (`tasks._persist_analysis_revision`), so disclosure time is the only
        # place it can be truthfully injected. It closes the client half of the
        # series consistency loop: the /series response echoes this digest, so
        # a tab holding an older snapshot can detect the drift itself. The
        # server-side pin stays authoritative; this is the cheap cross-check.
        normalized["data_revision"] = stored_data_revision
        record_event(
            "rainfall.analysis.served",
            revision_id=revision_id,
            scope_kind=scope.kind,
            scope_id=scope.id,
            scope_version=scope.version,
            year=payload.year,
            latency_ms=round((datetime.now() - started).total_seconds() * 1000),
        )
        return normalized
    except SnapshotContractError as exc:
        raise HTTPException(503, detail="rainfall analysis snapshot is invalid") from exc


@router.get("/analyses/{revision}/series")
def read_analysis_series(revision: UUID, db: Session = Depends(get_db)) -> dict:
    """The daily series for one stored revision, pinned to it (design.md D3).

    Resolved FROM the revision id, like the CSV export beside it, so it
    inherits that route's 404 semantics and the router-level
    `require_admin_or_operator` dependency without restating either. Strictly
    read-only: unlike `read_analysis`, it enqueues nothing, so no amount of
    polling can turn a chart into GEE work.
    """
    stored = RainfallRepository().get_revision(db, revision)
    if stored is None:
        raise HTTPException(404, detail="rainfall analysis is unavailable")
    started = datetime.now()
    try:
        series = build_series(db, stored)
    except SnapshotContractError as exc:
        raise HTTPException(503, detail="rainfall analysis snapshot is invalid") from exc
    record_event(
        "rainfall.series.served",
        revision_id=str(revision),
        data_revision=series["data_revision"],
        consistent_with_snapshot=series["consistent_with_snapshot"],
        consistency_reason=series["consistency_reason"],
        points=len(series["points"]),
        latency_ms=round((datetime.now() - started).total_seconds() * 1000),
    )
    return series


@router.get("/analyses/{revision}.csv")
def export_analysis(revision: UUID, db: Session = Depends(get_db)) -> Response:
    snapshot = RainfallRepository().get_revision(db, revision)
    if snapshot is None:
        raise HTTPException(404, detail="rainfall analysis is unavailable")
    try:
        normalized = normalize_snapshot(
            snapshot.snapshot, expected_policy_revision=snapshot.policy_revision
        )
    except SnapshotContractError as exc:
        raise HTTPException(503, detail="rainfall analysis snapshot is invalid") from exc
    started = datetime.now()
    csv_body = metric_rows_csv(metric_rows(normalized))
    record_event(
        "rainfall.csv.served",
        revision_id=str(revision),
        latency_ms=round((datetime.now() - started).total_seconds() * 1000),
    )
    return Response(csv_body, media_type="text/csv")
