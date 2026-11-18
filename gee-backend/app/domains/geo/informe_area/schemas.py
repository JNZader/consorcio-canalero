"""Wire contract of the informe de área endpoints (PR 2, T1).

One flat create body (no discriminated union — the informe is zonas-only by
construction, ``preview``/``ficha`` already own the general selection
contract), one response shape for create/status/list. ``desglose`` mirrors
the T3 front's SegmentedControl "Solo total" | "Total y subcuencas".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings

INFORME_AREA_NOMBRE_MAX = 200


class InformeAreaCreate(BaseModel):
    """The Generar step: a nombre, the picked subcuencas, and the depth."""

    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=INFORME_AREA_NOMBRE_MAX)
    # Schema-level bound on the LOOKUP cost (S5). The service re-checks the
    # RESOLVED count against the same cap so config drift cannot open a gap
    # between what the schema admitted and what the resolver accepts.
    zona_ids: list[UUID] = Field(min_length=1, max_length=settings.informe_area_max_zonas)
    desglose: bool = Field(
        default=True,
        description="False → totals only; True → plus one row per subcuenca",
    )


class InformeAreaResponse(BaseModel):
    """What Mis informes and the polling hook consume."""

    id: UUID
    nombre: str
    estado: str
    progreso: int
    desde_cache: bool = Field(
        default=False,
        description="True when this create reused a completed informe (S4)",
    )
    area_ha: float | None = Field(default=None, description="Union hectares once resultado exists")
    cantidad_zonas: int = Field(default=0, description="Zonas in the selection")
    error: str | None = None
    vence_at: datetime
    created_at: datetime
    updated_at: datetime


class InformeAreaListResponse(BaseModel):
    """The Mis informes table: own rows for a user, all rows for an admin."""

    items: list[InformeAreaResponse]
    total: int


def respuesta_informe(
    row: Any,
    *,
    desde_cache: bool = False,
) -> InformeAreaResponse:
    """Serialize one row, pulling the completed figures out of ``resultado``.

    ``area_ha``/``cantidad_zonas`` live inside the JSONB ``resultado`` once the
    task completes; before that they stay ``None``/``0`` — never a fabricated
    partial number.
    """
    resultado = row.resultado or {}
    return InformeAreaResponse(
        id=row.id,
        nombre=row.nombre,
        estado=row.estado.value if hasattr(row.estado, "value") else str(row.estado),
        progreso=row.progreso,
        desde_cache=desde_cache,
        area_ha=resultado.get("area_ha"),
        cantidad_zonas=resultado.get("zonas", 0),
        error=row.error,
        vence_at=row.vence_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
