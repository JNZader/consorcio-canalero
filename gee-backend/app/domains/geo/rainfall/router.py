"""Authenticated snapshot-only Rainfall v2 API."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.router_common import parse_bounded_json_object
from app.domains.geo.rainfall.repository import RainfallRepository, ScopeConfigurationError
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


@router.post("/analyses", openapi_extra=_request_body(AnalysisRequest))
def read_analysis(
    payload: AnalysisRequest = Depends(parse_analysis_request), db: Session = Depends(get_db)
):
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
    revision = RainfallRepository().get_snapshot(db, analysis_request_fingerprint(request))
    if revision is None:
        queued = queue_missing_analysis(
            db,
            scope=scope,
            year=payload.year,
            labels=("analysis_missing",),
        )
        return JSONResponse(queued, status_code=202)
    try:
        return normalize_snapshot(
            revision.snapshot, expected_policy_revision=revision.policy_revision
        )
    except SnapshotContractError as exc:
        raise HTTPException(503, detail="rainfall analysis snapshot is invalid") from exc


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
    return Response(metric_rows_csv(metric_rows(normalized)), media_type="text/csv")
