"""Wire contract of ``POST /api/v2/geo/analisis-zona`` (design §2, spec
``geo-analysis-endpoint``).

Request: ONE Pydantic v2 discriminated union on ``tipo`` so the UI has a single
code path and an unknown ``tipo`` dies before any geometry or raster work.

Response: ONE shape for the four variants — the spec requires a ficha for a
precomputed catchment to be byte-compatible with a ficha for a parcel.

Two things this module deliberately does NOT do:

* it does NOT echo the input geometry back, and it carries no ``nro_cuenta``,
  no consorcista id and no name: the ficha publishes aggregates only, and the
  BPA/forestación membership is joined client-side against the already-public
  tile property (design [R1]);
* it does NOT own the caps. The ``poligono`` validators below are the CHEAP
  pre-checks over a caller-supplied polygon; three of the four ``tipo`` values
  resolve a geometry the caller never sends, so ``ficha_service.assert_within_caps``
  is the authority (design §2.1, JD-A-002).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings
from app.domains.geo import ficha_errors

TipoFicha = Literal["parcela", "poligono", "canal_buffer", "canal_cuenca"]
Cobertura = Literal["total", "parcial", "sin_cobertura"]
VarianteCuenca = Literal["natural", "relevado"]

_GEOMETRIAS_ACEPTADAS = ("Polygon", "MultiPolygon")


def _contar_vertices(coordinates: Any, geometry_type: str) -> int:
    """Vertex count + ring sanity for a GeoJSON Polygon / MultiPolygon.

    Raises the §2.6 errors directly (pydantic v2 propagates non-``ValueError``
    exceptions out of a validator) so the caller gets ``geometria_invalida`` /
    ``cap_excedido`` instead of FastAPI's generic validation envelope.
    """
    poligonos = coordinates if geometry_type == "MultiPolygon" else [coordinates]
    if not isinstance(poligonos, list) or not poligonos:
        raise ficha_errors.geometria_invalida("coordinates vacio")

    total = 0
    for poligono in poligonos:
        if not isinstance(poligono, list) or not poligono:
            raise ficha_errors.geometria_invalida("poligono sin anillos")
        for anillo in poligono:
            if not isinstance(anillo, list) or len(anillo) < 4:
                raise ficha_errors.geometria_invalida("anillo con menos de 4 posiciones")
            if anillo[0] != anillo[-1]:
                raise ficha_errors.geometria_invalida("anillo no cerrado")
            for posicion in anillo:
                if not isinstance(posicion, (list, tuple)) or len(posicion) < 2:
                    raise ficha_errors.geometria_invalida("posicion mal formada")
                lon, lat = posicion[0], posicion[1]
                if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
                    raise ficha_errors.geometria_invalida("coordenada no numerica")
                if not (-180.0 <= lon <= 180.0) or not (-90.0 <= lat <= 90.0):
                    raise ficha_errors.geometria_invalida("coordenada fuera de rango WGS84")
            total += len(anillo)
    return total


class _FichaRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FichaParcelaRequest(_FichaRequestBase):
    """Geometry resolved server-side from ``parcelas_catastro``."""

    tipo: Literal["parcela"]
    nomenclatura: str = Field(min_length=1, max_length=64)


class FichaPoligonoRequest(_FichaRequestBase):
    """Caller-supplied GeoJSON geometry, EPSG:4326."""

    tipo: Literal["poligono"]
    geometry: dict[str, Any]

    @field_validator("geometry")
    @classmethod
    def _validar_geometria(cls, value: dict[str, Any]) -> dict[str, Any]:
        geometry_type = value.get("type")
        if geometry_type not in _GEOMETRIAS_ACEPTADAS:
            raise ficha_errors.geometria_invalida(
                f"se esperaba {' o '.join(_GEOMETRIAS_ACEPTADAS)}, llego {geometry_type!r}"
            )
        vertices = _contar_vertices(value.get("coordinates"), geometry_type)
        if vertices > settings.ficha_max_vertices:
            raise ficha_errors.cap_excedido(
                "vertices", float(settings.ficha_max_vertices), float(vertices)
            )
        return value


class FichaCanalBufferRequest(_FichaRequestBase):
    """Influence strip around a curated consorcio canal; buffered in EPSG:32720.

    ``canal_ref`` is the ``canal_consorcio`` string id (e.g.
    ``canal-ne-sin-intervencion``) — the ficha operates on the 60 curated canals,
    not the pgRouting ``canal_network`` graph.
    """

    tipo: Literal["canal_buffer"]
    canal_ref: str = Field(min_length=1, max_length=128)
    buffer_m: float = Field(gt=0)

    @field_validator("buffer_m")
    @classmethod
    def _validar_buffer(cls, value: float) -> float:
        # The schema cap is the cheap one; ``assert_within_caps`` re-checks the
        # resolved geometry because the buffered AREA is what actually costs
        # (JDB-006). Raised as ``cap_excedido`` so the wire code is stable.
        if value > settings.ficha_max_buffer_m:
            raise ficha_errors.cap_excedido("buffer_m", settings.ficha_max_buffer_m, value)
        return value


class FichaCanalCuencaRequest(_FichaRequestBase):
    """Precomputed upstream catchment of a curated consorcio canal (A7).

    ``canal_ref`` is the ``canal_consorcio`` string id. ``variante`` defaults to
    ``relevado``: v1 precomputes every catchment against the base/relevado
    ``flow_dir`` raster, so ``relevado`` is the only variante with a stored
    catchment (``natural`` is reserved for a later slice).
    """

    tipo: Literal["canal_cuenca"]
    canal_ref: str = Field(min_length=1, max_length=128)
    variante: VarianteCuenca = "relevado"


FichaRequest = Annotated[
    Union[
        FichaParcelaRequest,
        FichaPoligonoRequest,
        FichaCanalBufferRequest,
        FichaCanalCuencaRequest,
    ],
    Field(discriminator="tipo"),
]


class ClaseFicha(BaseModel):
    """One row of a dataset breakdown. ``pct`` comes from the server, always."""

    clase: str
    ha: float
    pct: float
    # Full subclass string when classes are grouped by roman prefix (IVws → IV).
    detalle: str | None = None


class DatasetFicha(BaseModel):
    cobertura: Cobertura
    clases: list[ClaseFicha] = Field(default_factory=list)
    # RAW sampling diagnostic (edge pixels included) — deliberately NOT
    # proportional to ``ha``, which is fractional-weight.
    pixel_count: int = 0
    low_confidence: bool = False
    # Fraction of the requested geometry the raster actually covered, 0..1.
    # This is what ``cobertura`` is derived from, and the spec scenarios assert
    # the NUMBER, not just the label: "parcial" alone cannot tell 99 % apart
    # from 5 %. A2's zonal primitive already returns it (R3-008).
    cobertura_ratio: float = Field(default=0.0, ge=0.0, le=1.0)


class PrecipMes(BaseModel):
    mes: int = Field(ge=1, le=12)
    mm: float


class PrecipitacionFicha(BaseModel):
    """Typed exception to ``{clase, ha, pct}``.

    Monthly normals are mean millimetres, not a class partition of the area:
    there is no ``ha`` per class and ``pct`` cannot sum to 100 (spec delta,
    JDB-011).
    """

    cobertura: Cobertura = "sin_cobertura"
    low_confidence: bool = False
    pixel_count: int = 0
    cobertura_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    unidad: Literal["mm"] = "mm"
    serie: list[PrecipMes] = Field(default_factory=list)
    anual_mm: float | None = None


class FichaResponse(BaseModel):
    """Uniform across the four ``tipo`` values."""

    tipo: TipoFicha
    area_ha: float
    suelos: DatasetFicha
    flood_risk: DatasetFicha
    drainage_need: DatasetFicha
    # NOT optional (R3-007). The four datasets are symmetric: a missing raster
    # is reported as ``cobertura="sin_cobertura"``, never by omitting the key.
    # ``None`` would have forced every consumer to branch on absence for this
    # one dataset and would have made "we have no precipitation product" look
    # identical to "the server forgot to include it".
    precipitacion_mensual: PrecipitacionFicha = Field(default_factory=PrecipitacionFicha)
    # ── canal_cuenca-only additive fields (A7) ──────────────────────────────
    # ``variante`` echoes which precomputed catchment variante answered, and
    # ``geometria_cuenca`` carries the catchment outline (GeoJSON, EPSG:4326) so
    # the frontend can draw it on the map. Both are ``None`` for the other three
    # tipos — additive, so the datasets above stay byte-compatible across tipos.
    variante: VarianteCuenca | None = None
    geometria_cuenca: dict[str, Any] | None = None


# ── on-map overlay (A(b) slice 1: soils only) ───────────────────────────────
# The opt-in ``/analisis-zona/overlay`` endpoint returns the analysis geometry
# CLIPPED to the analyzed zone as GeoJSON so the map can paint it. Slice 1 is
# soils only — the cheap, exact PostGIS vector path; flood_risk/drainage raster
# vectorization is slice 2. ``dataset`` is validated to ``"suelos"`` for now.
DatasetOverlay = Literal["suelos", "flood_risk", "drainage_need"]


class FichaOverlayFeature(BaseModel):
    """One GeoJSON Feature of the clipped overlay.

    ``properties.clase`` is the SAME normalized capability label the ficha soils
    panel groups by (``IVws`` → ``IV``), so the frontend colors each feature with
    the panel palette. The feature carries NO color — the client maps class →
    color — and NO area: the ha/pct breakdown is the ficha panel's job.
    """

    type: Literal["Feature"] = "Feature"
    properties: dict[str, Any]
    geometry: dict[str, Any]


class FichaOverlayResponse(BaseModel):
    """A GeoJSON FeatureCollection of the analysis clipped to the zone.

    Zero coverage (no soil polygons intersect the geometry) is an EMPTY
    ``features`` list with a 200 — never an error and never fabricated geometry.
    """

    dataset: DatasetOverlay
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[FichaOverlayFeature] = Field(default_factory=list)
