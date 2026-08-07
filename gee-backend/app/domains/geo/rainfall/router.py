"""Authenticated snapshot-only Rainfall v2 API."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.rainfall.repository import RainfallRepository, ScopeConfigurationError
from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv
from app.domains.geo.rainfall.scope import (
    NoScopeMatch,
    ScopeRef,
    UnsupportedDirectScope,
    executable_scope,
)


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


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_fingerprint: str
    policy_revision: str
    data_revision: str


@router.post("/scopes:resolve")
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


@router.post("/analyses")
def read_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)):
    revision = RainfallRepository().get_snapshot(
        db, payload.request_fingerprint, payload.policy_revision, payload.data_revision
    )
    if revision is None:
        raise HTTPException(404, detail="rainfall analysis is unavailable")
    return revision.snapshot


@router.get("/analyses/{revision}.csv")
def export_analysis(revision: UUID, db: Session = Depends(get_db)) -> Response:
    snapshot = RainfallRepository().get_revision(db, revision)
    if snapshot is None:
        raise HTTPException(404, detail="rainfall analysis is unavailable")
    return Response(metric_rows_csv(metric_rows(snapshot.snapshot)), media_type="text/csv")
