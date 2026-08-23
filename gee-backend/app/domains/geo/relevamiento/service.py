"""Business rules for Fase B: provenance, the three-field read, and coverage.

Three decisions live here and nowhere else:

1. **``nivel_desde_candidata`` is corroborated, not accepted.** The client's flag
   says the level control was left as pre-filled; the service compares the
   submitted value against the newest candidate row before believing it. A flag
   the client sets freely is a claim, and a survey that says "confirmed" while
   submitting something the DEM never suggested confirmed nothing.
2. **The candidate is never written to.** A survey that disagrees with it leaves
   it exactly where it is: it is a record of what the DEM once suggested, not a
   draft of the operator's answer.
3. **Coverage counts the ACTIVE network, inside the area's DEM footprint.** A
   retired segment keeps its history and leaves the denominator (design D4), and
   the area is the ground its terrain analysis covers — not the union of every
   layer that ever named the area (owner ratification A, 2026-08-23).
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.relevamiento.repository import RelevamientoRepository
from app.domains.geo.relevamiento.schemas import (
    CANDIDATA_A_NIVEL,
    CandidataResponse,
    CoberturaResponse,
    RelevamientoTramoCreate,
    RelevamientoTramoResponse,
    TramoRelevamientoDetalle,
)

# ``CANDIDATA_A_NIVEL`` is IMPORTED, never redefined here. It moved to
# ``schemas`` because ``CandidataResponse.nivel_sugerido`` is computed from it
# and a schema module cannot import this one without a cycle;
# ``service.CANDIDATA_A_NIVEL`` still resolves, to the SAME object. That
# identity is the point: "the response suggests it, the form pre-fills it, the
# server compares against it" holds by construction instead of by two copies
# agreeing.

SQL_TRAMO_EXISTE = text("SELECT activo FROM red_vial WHERE id = :tramo_ref")


class RelevamientoService:
    """Stateless. The caller owns the session and the transaction boundary."""

    def __init__(self, repo: Optional[RelevamientoRepository] = None) -> None:
        self._repo = repo or RelevamientoRepository()

    # ── Write ───────────────────────────────────────────────────────────
    def registrar(
        self,
        db: Session,
        *,
        payload: RelevamientoTramoCreate,
        relevado_por: uuid.UUID,
    ) -> dict[str, Any]:
        """Insert one survey. Always an INSERT — there is no edit path.

        A correction is a new version of the same segment, and the record it
        corrects stays retrievable with its own author and moment.
        """
        if db.execute(SQL_TRAMO_EXISTE, {"tramo_ref": payload.tramo_ref}).first() is None:
            raise HTTPException(
                status_code=404,
                detail=f"El tramo {payload.tramo_ref} no existe en la red vial",
            )

        candidata = self._repo.get_candidata(db, payload.tramo_ref)
        return self._repo.insertar(
            db,
            tramo_ref=payload.tramo_ref,
            nivel_relativo=payload.nivel_relativo,
            tiene_cuneta=payload.tiene_cuneta,
            estado_cuneta=payload.estado_cuneta,
            observaciones=payload.observaciones,
            relevado_por=relevado_por,
            nivel_desde_candidata=self._nivel_proviene_de_la_candidata(payload, candidata),
        )

    @staticmethod
    def _nivel_proviene_de_la_candidata(
        payload: RelevamientoTramoCreate, candidata: Optional[dict[str, Any]]
    ) -> bool:
        """True only when the operator accepted exactly what was displayed.

        Both halves are required, and neither is sufficient:

        * the client flag — the control was not touched;
        * the server-side comparison — what arrived is what the newest candidate
          actually suggested.

        With no candidate there was nothing to accept, so the answer is False
        however confident the flag is.
        """
        if not payload.nivel_confirmado_sin_cambios or candidata is None:
            return False
        equivalente = CANDIDATA_A_NIVEL.get(candidata["clasificacion_candidata"])
        return equivalente == payload.nivel_relativo

    # ── Read ────────────────────────────────────────────────────────────
    def get_detalle(self, db: Session, tramo_ref: str) -> TramoRelevamientoDetalle:
        """``{vigente, historial, candidata}`` — three NAMED fields.

        ``vigente`` is echoed with ``es_vigente: true`` and the candidate keeps
        its own field, so no caller can mistake the DEM guess for a surveyed
        value or an old version for the current one.
        """
        vigente = self._repo.get_vigente(db, tramo_ref)
        historial = self._repo.get_historial(db, tramo_ref)
        candidata = self._repo.get_candidata(db, tramo_ref)

        vigente_version = vigente["version"] if vigente else None
        return TramoRelevamientoDetalle(
            tramo_ref=tramo_ref,
            vigente=(RelevamientoTramoResponse(**vigente, es_vigente=True) if vigente else None),
            historial=[
                RelevamientoTramoResponse(**entry, es_vigente=entry["version"] == vigente_version)
                for entry in historial
            ],
            candidata=CandidataResponse(**candidata) if candidata else None,
        )

    def get_cobertura(self, db: Session, area_id: Optional[str] = None) -> CoberturaResponse:
        """Three counters plus their denominator, over ACTIVE segments only.

        The area filter is the **DEM footprint** and only that (owner
        ratification A, 2026-08-23): the area is the ground its terrain analysis
        covers, so a segment outside the DEM is one this area never looked at.
        A union over every registered layer would make the denominator depend on
        what else happened to be registered against the area.

        ``area_id`` stays optional — omitting it counts the whole network on
        purpose, which is a different question and is asked differently. An
        ``area_id`` with no registered DEM footprint is a **named refusal**, not
        a silent count of the whole network: answering a question about one area
        with a number about every area is the kind of degradation nobody spots
        from the number alone.
        """
        bbox = None
        if area_id is not None:
            bbox = self._repo.get_area_bbox(db, area_id)
            if bbox is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"El área {area_id} no tiene un DEM con extensión registrada; "
                        "no hay sobre qué contar cobertura"
                    ),
                )
        return CoberturaResponse(area_id=area_id, **self._repo.contar_cobertura(db, bbox=bbox))


__all__ = ["CANDIDATA_A_NIVEL", "RelevamientoService"]
