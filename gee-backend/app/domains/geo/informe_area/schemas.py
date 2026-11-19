"""Wire contract of the informe de área endpoints (PR 2, T1 + PR 3 geometrías).

One flat create body (no discriminated union — the informe is zonas-only by
construction, ``preview``/``ficha`` already own the general selection
contract), one response shape for create/status/list. ``desglose`` mirrors
the T3 front's SegmentedControl "Solo total" | "Total y subcuencas".

PR 3 (S3/S4): the selection is now MIXED — ``zona_ids`` (subcuencas) and
``geometrias`` (caller-supplied GeoJSON Polygon/MultiPolygon, drawn on the
map or imported from a KML/KMZ) enter together; either side may be empty but
not both. The geometries reuse the ficha's own GeoJSON validation verbatim
(``schemas_ficha._contar_vertices``) so both surfaces reject the same shapes
with the same §2.6 codes; the repair itself (``ST_MakeValid``) is
server-side, in ``service.resolver_seleccion``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings
from app.domains.geo import ficha_errors
from app.domains.geo.schemas_ficha import _contar_vertices  # noqa: SLF001 — PR 3 reuse

INFORME_AREA_NOMBRE_MAX = 200

#: The only geometries the informe accepts (S3): GeoJSON polygonal, EPSG:4326.
GEOMETRIAS_ACEPTADAS = frozenset({"Polygon", "MultiPolygon"})


def _validar_geometria(value: dict[str, Any]) -> dict[str, Any]:
    """Validate ONE caller-supplied geometry with the ficha's own rules.

    Ring closure and the 4-position minimum are REQUIRED on the wire (the
    frontend closes KML rings; mapbox-gl-draw emits closed rings) — what
    ``ST_MakeValid`` repairs server-side is TOPOLOGY (self-intersections),
    not missing vertices. The per-geometry vertex bound is the informe's own
    (``informe_area_max_vertices``, the same figure the frontend caps a whole
    file at, S4), not the ficha's tighter one: the informe's authority is the
    POST-SIMPLIFY union cap the resolver enforces.
    """
    if not isinstance(value, dict):
        raise ficha_errors.geometria_invalida("se esperaba una geometria GeoJSON")
    geometry_type = value.get("type")
    if geometry_type not in GEOMETRIAS_ACEPTADAS:
        raise ficha_errors.geometria_invalida(
            f"se esperaba Polygon o MultiPolygon, llego {geometry_type!r}"
        )
    vertices = _contar_vertices(value.get("coordinates"), geometry_type)
    if vertices > settings.informe_area_max_vertices:
        raise ficha_errors.cap_excedido(
            "vertices", float(settings.informe_area_max_vertices), float(vertices)
        )
    return value


def _validar_geometrias(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate the geometrias list (each entry, then the count)."""
    if len(value) > settings.informe_area_max_zonas:
        raise ficha_errors.cap_excedido(
            "subcuencas", float(settings.informe_area_max_zonas), float(len(value))
        )
    return [_validar_geometria(geometria) for geometria in value]


class _SeleccionMixtaBase(BaseModel):
    """The shared mixed-selection half of create and preview bodies."""

    model_config = ConfigDict(extra="forbid")

    zona_ids: list[UUID] = Field(
        default_factory=list,
        max_length=settings.informe_area_max_zonas,
        description="Picked subcuencas (may be empty when geometrias carry the selection)",
    )
    geometrias: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Caller-supplied GeoJSON Polygon/MultiPolygon (drawn or KML/KMZ)",
    )

    @field_validator("geometrias")
    @classmethod
    def _validar_geos(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _validar_geometrias(value)

    @model_validator(mode="after")
    def _al_menos_un_lado(self) -> "_SeleccionMixtaBase":
        if not self.zona_ids and not self.geometrias:
            raise ficha_errors.geometria_invalida(
                "la seleccion esta vacia: manda zona_ids o geometrias"
            )
        if len(self.zona_ids) + len(self.geometrias) > settings.informe_area_max_zonas:
            raise ficha_errors.cap_excedido(
                "subcuencas",
                float(settings.informe_area_max_zonas),
                float(len(self.zona_ids) + len(self.geometrias)),
            )
        return self


class InformeAreaCreate(_SeleccionMixtaBase):
    """The Generar step: a nombre, the mixed selection, and the depth."""

    nombre: str = Field(min_length=1, max_length=INFORME_AREA_NOMBRE_MAX)
    desglose: bool = Field(
        default=True,
        description="False → totals only; True → plus one row per subcuenca",
    )


class InformeAreaPreviewRequest(_SeleccionMixtaBase):
    """The Revisar step's mixed selection (mirror of the create body)."""


class InformeAreaPreviewSubcuenca(BaseModel):
    """One zonas-side row of the preview (geometrias carry no names)."""

    id: UUID
    nombre: str
    cuenca: str
    ha: float


class InformeAreaPreviewResponse(BaseModel):
    """What the Revisar step shows over a MIXED selection (S2/S4).

    ``fuera_zona_ha`` is the portion of the union outside the consorcio's
    zone and ``poligonos_separados`` flags a disjoint selection — the two
    avisos S2 puts on the preview.
    """

    area_total_ha: float
    area_total_ha_geodesica: float
    subcuencas: list[InformeAreaPreviewSubcuenca]
    cantidad_geometrias: int = 0
    fuera_zona_ha: float = 0.0
    poligonos_separados: bool = False
    aviso_cap: bool = Field(default=False, description="True past the 35 000 ha online cap")


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
    cantidad_geometrias: int = Field(
        default=0, description="Caller-supplied geometries in the selection (PR 3)"
    )
    fuera_zona_ha: float | None = Field(
        default=None,
        description="Hectares of the union outside the consorcio zone, once resultado exists",
    )
    error: str | None = None
    vence_at: datetime
    created_at: datetime
    updated_at: datetime
    token_publico: str = Field(
        default="",
        description="Opaque token of the public campo map (PR 6, S5); empty pre-PR6 rows",
    )


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

    ``area_ha``/``cantidad_zonas`` (and the PR 3 ``cantidad_geometrias`` /
    ``fuera_zona_ha``) live inside the JSONB ``resultado`` once the task
    completes; before that they stay ``None``/``0`` — never a fabricated
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
        cantidad_geometrias=resultado.get("geometrias", 0),
        fuera_zona_ha=resultado.get("fuera_zona_ha"),
        error=row.error,
        vence_at=row.vence_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        token_publico=str(getattr(row, "token_publico", "") or ""),
    )
