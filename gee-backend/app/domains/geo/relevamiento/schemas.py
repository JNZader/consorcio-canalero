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

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    computed_field,
    field_validator,
)

NivelRelativo = Literal["menor", "igual", "mayor"]
TieneCuneta = Literal["si", "no", "parcial"]
EstadoCuneta = Literal["limpia", "colmatada"]
ClasificacionCandidata = Literal["terraplen", "canal", "neutro"]

#: What each DEM classification means in the operator's vocabulary. The
#: classifier compares ``median(road) - median(flank)``, so a road that sits
#: ABOVE its flanks is an embankment and reads as ``mayor``; below is a channel
#: and reads as ``menor``.
#:
#: **THE table — there is no second one.** It lives here, next to the two
#: Literals it maps between, because three consumers need exactly this mapping
#: and any of them re-typing it would be a fork nobody would notice until the
#: two copies disagreed: the form pre-fills through it, ``CandidataResponse``
#: exposes it as ``nivel_sugerido`` so the client never has to own a copy, and
#: ``RelevamientoService`` compares the submitted value against it to decide
#: whether the operator really accepted what was displayed. It is total over
#: ``ClasificacionCandidata``, so the lookup below cannot raise.
CANDIDATA_A_NIVEL: dict[ClasificacionCandidata, NivelRelativo] = {
    "terraplen": "mayor",
    "canal": "menor",
    "neutro": "igual",
}


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def nivel_sugerido(self) -> NivelRelativo:
        """The candidate in the operator's vocabulary — a SUGGESTION, not a value.

        Computed from :data:`CANDIDATA_A_NIVEL` rather than stored or accepted
        from anywhere: the server already compares a submission against that
        table to decide ``nivel_desde_candidata``, so a client translating
        ``clasificacion_candidata`` on its own would be a second table, and the
        day the two disagreed the form would pre-fill a value the server then
        refused to call confirmed. Derived, so it cannot drift and cannot be set.

        It stays in ``candidata``, next to ``clasificacion_candidata`` and never
        merged into ``vigente``: naming what the DEM would suggest is not the
        same as recording what somebody surveyed.
        """
        return CANDIDATA_A_NIVEL[self.clasificacion_candidata]


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
    "CANDIDATA_A_NIVEL",
    "CandidataResponse",
    "CoberturaResponse",
    "RelevamientoTramoCreate",
    "RelevamientoTramoResponse",
    "TramoRelevamientoDetalle",
]
