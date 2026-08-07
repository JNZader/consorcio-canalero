"""Authenticated snapshot-only Rainfall v2 API."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.rainfall.repository import RainfallRepository, ScopeConfigurationError
from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv, normalize_snapshot
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


async def enforce_rainfall_request_contract(request: Request) -> None:
    """Bound JSON snapshots before parsing and never expose a partial request."""
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(415, detail="rainfall requests require application/json")
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            if int(declared_length) > MAX_RAINFALL_REQUEST_BYTES:
                raise HTTPException(413, detail="rainfall request body exceeds limit")
        except ValueError as exc:
            raise HTTPException(400, detail="invalid content-length") from exc
    if len(await request.body()) > MAX_RAINFALL_REQUEST_BYTES:
        raise HTTPException(413, detail="rainfall request body exceeds limit")


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


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_fingerprint: str = Field(min_length=1, max_length=128)
    policy_revision: str = Field(min_length=1, max_length=64)
    data_revision: str = Field(min_length=1, max_length=128)


@router.post("/scopes:resolve", dependencies=[Depends(enforce_rainfall_request_contract)])
def resolve_scope(payload: ScopeRequest, db: Session = Depends(get_db)):
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


@router.post("/analyses", dependencies=[Depends(enforce_rainfall_request_contract)])
def read_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)):
    revision = RainfallRepository().get_snapshot(
        db, payload.request_fingerprint, payload.policy_revision, payload.data_revision
    )
    if revision is None:
        raise HTTPException(404, detail="rainfall analysis is unavailable")
    return normalize_snapshot(revision.snapshot, expected_policy_revision=payload.policy_revision)


@router.get("/analyses/{revision}.csv")
def export_analysis(revision: UUID, db: Session = Depends(get_db)) -> Response:
    snapshot = RainfallRepository().get_revision(db, revision)
    if snapshot is None:
        raise HTTPException(404, detail="rainfall analysis is unavailable")
    normalized = normalize_snapshot(
        snapshot.snapshot, expected_policy_revision=snapshot.policy_revision
    )
    return Response(metric_rows_csv(metric_rows(normalized)), media_type="text/csv")
