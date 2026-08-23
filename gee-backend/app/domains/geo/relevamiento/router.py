"""HTTP layer for Fase B. Operator-and-admin only, and append-only.

**``POST`` always inserts. There is no ``PUT`` and no ``DELETE``** — not "they
are not implemented yet", but the shape of the capability: a correction is a new
version, the record it corrects stays retrievable, and the author of a stored
record is therefore unrewritable because nothing can rewrite it (RSS-R1).

The read returns **three named fields** — ``vigente``, ``historial``,
``candidata`` — rather than one merged record. Merging them is precisely how a
DEM guess becomes an authoritative value and how an old version gets read as the
current one.

Nothing here is published: these routes are the only way to this data, and the
dependency rejects before the service runs, so a denial has no payload to leak.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.relevamiento.schemas import (
    CoberturaResponse,
    RelevamientoTramoCreate,
    RelevamientoTramoResponse,
    TramoRelevamientoDetalle,
)
from app.domains.geo.relevamiento.service import RelevamientoService

logger = get_logger(__name__)

router = APIRouter(prefix="/relevamiento", tags=["Relevamiento"])


def _require_operator():
    # Lazy import, the geo domain's standing pattern for auth dependencies:
    # importing them at module scope closes a circular import.
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _get_service() -> RelevamientoService:
    return RelevamientoService()


@router.post("/tramos", response_model=RelevamientoTramoResponse)
def registrar_relevamiento(
    payload: RelevamientoTramoCreate,
    db: Session = Depends(get_db),
    servicio: RelevamientoService = Depends(_get_service),
    usuario=Depends(_require_operator()),
) -> RelevamientoTramoResponse:
    """Record one survey of one segment.

    The author is the **authenticated user**, never a field of the request: a
    client-supplied author is not an author, and ``extra="forbid"`` refuses the
    attempt by name rather than quietly ignoring it.
    """
    fila = servicio.registrar(db, payload=payload, relevado_por=usuario.id)
    db.commit()
    logger.info(
        "relevamiento.registrado",
        tramo_ref=payload.tramo_ref,
        version=fila["version"],
        desde_candidata=fila["nivel_desde_candidata"],
    )
    return RelevamientoTramoResponse(**fila, es_vigente=True)


@router.get("/tramos/{tramo_ref}", response_model=TramoRelevamientoDetalle)
def leer_tramo(
    tramo_ref: str,
    db: Session = Depends(get_db),
    servicio: RelevamientoService = Depends(_get_service),
    _usuario=Depends(_require_operator()),
) -> TramoRelevamientoDetalle:
    """``{vigente, historial[], candidata}`` — three fields that stay apart.

    Each survey entry carries its author and its moment, and ``vigente`` is
    echoed with ``es_vigente: true``. A retired segment still answers here: it
    left the working set, not the record.
    """
    return servicio.get_detalle(db, tramo_ref)


@router.get("/cobertura", response_model=CoberturaResponse)
def leer_cobertura(
    area_id: Optional[str] = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    servicio: RelevamientoService = Depends(_get_service),
    _usuario=Depends(_require_operator()),
) -> CoberturaResponse:
    """Three counters and their denominator, over ACTIVE segments only.

    They are three fields on purpose: a candidate is not a survey, and a single
    "surveyed" figure that quietly included candidate-only segments would report
    fieldwork nobody did (RSS-R4).

    With ``area_id`` the scope is that area's **DEM footprint**; without it, the
    whole network. An area with no registered DEM footprint is a 404 naming the
    area, never the network's numbers wearing the area's label.
    """
    return servicio.get_cobertura(db, area_id)
