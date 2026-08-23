"""Request and response contracts for Fase B.

``RelevamientoTramoCreate`` is the design's contract block, plus one field the
design's D4 prose requires and its Python snippet did not spell out:
``nivel_confirmado_sin_cambios``. Pre-fill provenance is set "by the API from an
explicit client flag PLUS a server-side comparison against the candidate row",
and with ``extra="forbid"`` the flag has to be a declared field or the request
carrying it is rejected. It is only half the answer — the service still compares
the submitted value against the candidate — because a flag the client sets freely
is a claim, not a fact.

Three named fields on the read side (``vigente`` / ``historial`` / ``candidata``)
rather than one merged record: no caller can then mistake the DEM guess for a
surveyed value, or an old version for the current one. ``vigente`` is echoed with
``es_vigente: true`` for the same reason.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

NivelRelativo = Literal["menor", "igual", "mayor"]
TieneCuneta = Literal["si", "no", "parcial"]
EstadoCuneta = Literal["limpia", "colmatada"]
ClasificacionCandidata = Literal["terraplen", "canal", "neutro"]


class RelevamientoTramoCreate(BaseModel):
    """One survey submission. Three answers, an optional note, nothing measured."""

    # A request carrying ``ancho_cuneta`` / ``profundidad`` / ``capacidad`` is
    # refused BY NAME — the mechanical form of RSS-R6.
    model_config = ConfigDict(extra="forbid")

    tramo_ref: str = Field(min_length=1)
    nivel_relativo: NivelRelativo
    tiene_cuneta: TieneCuneta
    estado_cuneta: Optional[EstadoCuneta] = None
    observaciones: Optional[str] = None
    #: The client's claim that the level control was left exactly as pre-filled.
    #: Corroborated server-side against the candidate row before it is stored.
    nivel_confirmado_sin_cambios: bool = False

    @field_validator("estado_cuneta")
    @classmethod
    def _estado_cuneta_matches_tiene_cuneta(
        cls, value: Optional[EstadoCuneta], info: ValidationInfo
    ) -> Optional[EstadoCuneta]:
        """``estado_cuneta`` is present **iff** there is a cuneta to describe.

        A FIELD validator, not a model one: a model-level failure reports
        ``loc: []`` and the operator is handed a sentence with no control
        attached to it, while this one names ``estado_cuneta`` in the 422 — which
        is the requirement, not a nicety. ``tiene_cuneta`` is declared before this
        field, so it is already in ``info.data``; when it failed its own
        validation it is absent, and there is nothing to cross-check yet.

        The same rule is a table-level CHECK. This one gives a named 422; that
        one holds when something bypasses the schema entirely.
        """
        tiene_cuneta = info.data.get("tiene_cuneta")
        if tiene_cuneta is None:
            return value
        if tiene_cuneta == "no" and value is not None:
            raise ValueError("debe ser nulo cuando tiene_cuneta es 'no'")
        if tiene_cuneta != "no" and value is None:
            raise ValueError("es obligatorio cuando el tramo tiene cuneta")
        return value


class RelevamientoTramoResponse(BaseModel):
    """A stored survey. Always carries its author and its moment."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tramo_ref: str
    nivel_relativo: NivelRelativo
    tiene_cuneta: TieneCuneta
    estado_cuneta: Optional[EstadoCuneta] = None
    observaciones: Optional[str] = None
    relevado_por: uuid.UUID
    relevado_en: datetime
    version: int
    nivel_desde_candidata: bool
    #: Echoed as ``true`` only on the current record, so an old version read out
    #: of context cannot be mistaken for the live one.
    es_vigente: bool = False


class CandidataResponse(BaseModel):
    """The DEM's guess. Labelled a candidate everywhere it appears."""

    model_config = ConfigDict(from_attributes=True)

    tramo_ref: str
    geo_job_id: uuid.UUID
    dem_layer_id: Optional[uuid.UUID] = None
    clasificacion_candidata: ClasificacionCandidata
    #: SIGNED median difference in metres. A magnitude, not a confidence score.
    confianza_m: float
    calculada_en: datetime


class TramoRelevamientoDetalle(BaseModel):
    """Three NAMED fields — never merged into one "the value of this segment"."""

    tramo_ref: str
    vigente: Optional[RelevamientoTramoResponse] = None
    historial: list[RelevamientoTramoResponse] = Field(default_factory=list)
    candidata: Optional[CandidataResponse] = None


class CoberturaResponse(BaseModel):
    """Three counters that are never summed into one "surveyed" figure (RSS-R4).

    All four are computed over ``red_vial`` rows with ``activo = true`` only: a
    retired segment keeps its survey history but is out of the working set, so
    counting it either way would misreport coverage of the network that exists.
    """

    area_id: Optional[str] = None
    relevados: int
    solo_candidato: int
    sin_datos: int
    total_activos: int


__all__ = [
    "CandidataResponse",
    "CoberturaResponse",
    "RelevamientoTramoCreate",
    "RelevamientoTramoResponse",
    "TramoRelevamientoDetalle",
]
