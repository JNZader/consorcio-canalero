"""Pydantic v2 schemas for the operational intelligence sub-module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _wkb_to_geojson(v: Any) -> Optional[dict[str, Any]]:
    """Convert WKBElement / WKT / dict to a plain GeoJSON dict."""
    if v is None or isinstance(v, dict):
        return v
    try:
        from geoalchemy2.shape import to_shape

        shape = to_shape(v)
        import json
        from shapely.geometry import mapping

        return json.loads(json.dumps(mapping(shape)))
    except Exception:
        try:
            # Fallback: try shapely WKB/WKT
            from shapely import wkb, wkt
            from shapely.geometry import mapping
            import json

            shape = wkb.loads(bytes(v.data)) if hasattr(v, "data") else wkt.loads(str(v))
            return json.loads(json.dumps(mapping(shape)))
        except Exception:
            return None


# ──────────────────────────────────────────────
# ZONA OPERATIVA
# ──────────────────────────────────────────────


class ZonaOperativaResponse(BaseModel):
    """Full operational zone detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    cuenca: str
    superficie_ha: float
    geometria: Optional[dict[str, Any]] = Field(
        default=None,
        description="Zone boundary as GeoJSON geometry object (Polygon)",
    )
    created_at: datetime
    updated_at: datetime

    @field_validator("geometria", mode="before")
    @classmethod
    def parse_geometria(cls, v: Any) -> Optional[dict[str, Any]]:
        return _wkb_to_geojson(v)


class ZonaOperativaListResponse(BaseModel):
    """Lightweight zone for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    cuenca: str
    superficie_ha: float


# ──────────────────────────────────────────────
# INDICE HIDRICO
# ──────────────────────────────────────────────


class IndiceHidricoResponse(BaseModel):
    """Full HCI calculation result."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    zona_id: uuid.UUID
    fecha_calculo: date
    pendiente_media: float
    acumulacion_media: float
    twi_medio: float
    proximidad_canal_m: float
    historial_inundacion: float
    indice_final: float
    nivel_riesgo: str
    created_at: datetime
    updated_at: datetime


class CriticidadRequest(BaseModel):
    """Request to calculate HCI for a zone."""

    zona_id: uuid.UUID = Field(..., description="Zone to calculate HCI for")
    pendiente_media: float = Field(..., ge=0, le=1, description="Normalized mean slope")
    acumulacion_media: float = Field(
        ..., ge=0, le=1, description="Normalized mean flow accumulation"
    )
    twi_medio: float = Field(..., ge=0, le=1, description="Normalized mean TWI")
    proximidad_canal_m: float = Field(
        ..., ge=0, description="Average distance to nearest canal (m)"
    )
    historial_inundacion: float = Field(..., ge=0, le=1, description="Flood history factor")
    pesos: Optional[dict[str, float]] = Field(default=None, description="Custom weight dict")


class CriticidadResponse(BaseModel):
    """HCI calculation result."""

    zona_id: uuid.UUID
    indice_final: float
    nivel_riesgo: str
    componentes: dict[str, float]


# ──────────────────────────────────────────────
# PUNTO DE CONFLICTO
# ──────────────────────────────────────────────


class PuntoConflictoResponse(BaseModel):
    """Full conflict point detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    descripcion: str
    severidad: str
    infraestructura_ids: Optional[list[str]] = None
    acumulacion_valor: float
    pendiente_valor: float
    created_at: datetime
    updated_at: datetime


class ConflictoDetectarRequest(BaseModel):
    """Request to run conflict detection."""

    buffer_m: float = Field(default=50.0, ge=10, le=500, description="Buffer in meters")
    flow_acc_threshold: float = Field(default=500.0, ge=0, description="Min flow accumulation")
    slope_threshold: float = Field(default=5.0, ge=0, description="Max slope in degrees")


# ──────────────────────────────────────────────
# ESCORRENTIA
# ──────────────────────────────────────────────


class EscorrentiaRequest(BaseModel):
    """Request to run runoff simulation."""

    punto_inicio: list[float] = Field(..., min_length=2, max_length=2, description="[lon, lat]")
    lluvia_mm: float = Field(..., gt=0, le=500, description="Rainfall in mm")


class EscorrentiaResponse(BaseModel):
    """Runoff simulation result (GeoJSON FeatureCollection)."""

    type: str = "FeatureCollection"
    features: list[dict[str, Any]]
    properties: Optional[dict[str, Any]] = None


# ──────────────────────────────────────────────
# ZONIFICACION
# ──────────────────────────────────────────────


class ZonificacionRequest(BaseModel):
    """Request to generate operational zones."""

    dem_layer_id: uuid.UUID = Field(..., description="GeoLayer ID of the DEM")
    threshold: int = Field(default=2000, ge=100, description="Pour point threshold")


class ZonificacionResponse(BaseModel):
    """Zonification generation result."""

    zonas_creadas: int
    zonas: list[ZonaOperativaListResponse]


# ──────────────────────────────────────────────
# ALERTAS
# ──────────────────────────────────────────────


class AlertaResponse(BaseModel):
    """Full alert detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    mensaje: str
    nivel: str
    datos: Optional[dict[str, Any]] = None
    activa: bool
    zona_id: Optional[uuid.UUID] = None
    created_at: datetime


# ──────────────────────────────────────────────
# PRIORIDAD / RIESGO
# ──────────────────────────────────────────────


class CanalPrioridadResponse(BaseModel):
    """Canal with its priority score."""

    canal_id: str
    nombre: str
    prioridad: float
    detalles: Optional[dict[str, Any]] = None


class CaminoRiesgoResponse(BaseModel):
    """Road segment with its risk score."""

    camino_id: str
    nombre: str
    riesgo: float
    detalles: Optional[dict[str, Any]] = None


# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────


class DashboardInteligente(BaseModel):
    """Aggregated intelligence dashboard."""

    porcentaje_area_riesgo: float = Field(
        ..., description="Percentage of total area at risk (medio+)"
    )
    canales_criticos: int = Field(..., description="Number of canals with priority > 70")
    caminos_vulnerables: int = Field(..., description="Number of roads with risk > 70")
    conflictos_activos: int = Field(..., description="Number of detected conflict points")
    alertas_activas: int = Field(..., description="Number of active alerts")
    zonas_por_nivel: dict[str, int] = Field(
        default_factory=dict,
        description="Count of zones per risk level",
    )
    evolucion_temporal: list[dict[str, Any]] = Field(
        default_factory=list,
        description="HCI evolution over time",
    )


# ──────────────────────────────────────────────
# COMPOSITE ANALYSIS
# ──────────────────────────────────────────────


class CompositeAnalysisRequest(BaseModel):
    """Request to trigger composite analysis (flood risk + drainage need)."""

    area_id: str = Field(..., description="Processing area identifier")
    weights_flood: Optional[dict[str, float]] = Field(
        default=None,
        description="Custom flood risk weights (keys: twi, hand, flow_acc, slope). Must sum to 1.0",
    )
    weights_drainage: Optional[dict[str, float]] = Field(
        default=None,
        description="Custom drainage need weights (keys: flow_acc, twi, hand, dist_drainage). Must sum to 1.0",
    )


class CompositeZonalStatsResponse(BaseModel):
    """Zonal statistics for a composite raster (flood risk or drainage need)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    zona_id: uuid.UUID
    zona_nombre: Optional[str] = Field(
        default=None, description="Zone name (joined from ZonaOperativa)"
    )
    cuenca: Optional[str] = Field(default=None, description="Parent watershed / basin family")
    superficie_ha: Optional[float] = Field(default=None, description="Zone area in hectares")
    tipo: str = Field(..., description="flood_risk | drainage_need")
    mean_score: float
    max_score: float
    p90_score: float
    area_high_risk_ha: float
    weights_used: Optional[dict[str, float]] = None
    fecha_calculo: date


class BasinRiskRankingResponse(BaseModel):
    """List of basins ranked by composite risk score."""

    items: list[CompositeZonalStatsResponse]
    total: int


class CompositeComparisonItemResponse(BaseModel):
    """Before/after comparison for a zone under a given composite analysis."""

    zona_id: uuid.UUID
    zona_nombre: Optional[str] = None
    cuenca: Optional[str] = None
    superficie_ha: Optional[float] = None
    tipo: str
    current_mean_score: float
    baseline_mean_score: float
    delta_mean_score: float
    current_area_high_risk_ha: float
    baseline_area_high_risk_ha: float
    delta_area_high_risk_ha: float


class CompositeComparisonResponse(BaseModel):
    """Comparison response between current and baseline composite stats."""

    area_id: str
    tipo: str
    items: list[CompositeComparisonItemResponse]
    total: int


# ──────────────────────────────────────────────
# CANAL SUGGESTIONS
# ──────────────────────────────────────────────


class CanalSuggestionResponse(BaseModel):
    """Single canal suggestion from network analysis."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str = Field(..., description="hotspot | gap | route | maintenance | bottleneck")
    score: float = Field(..., description="Relevance / priority score 0-100")
    metadata_: Optional[dict[str, Any]] = Field(
        default=None,
        alias="metadata",
        description="Analysis-specific payload",
    )
    batch_id: uuid.UUID
    created_at: datetime


class AnalysisRequest(BaseModel):
    """Request to trigger canal network analysis."""

    area_id: str = Field(..., description="Processing area identifier (cuenca name or zone)")
    tipos: Optional[list[str]] = Field(
        default=None,
        description=(
            "Analysis types to run. Options: hotspot, gap, route, "
            "maintenance, bottleneck. Defaults to all."
        ),
    )
    parameters: Optional[dict[str, Any]] = Field(
        default=None,
        description="Override default analysis parameters",
    )


class AnalysisSummaryResponse(BaseModel):
    """Summary of a completed analysis batch."""

    batch_id: uuid.UUID
    total_suggestions: int
    by_tipo: dict[str, int] = Field(
        default_factory=dict,
        description="Count of suggestions per tipo",
    )
    avg_score: float = Field(..., description="Average score across all suggestions")
    created_at: datetime


# ──────────────────────────────────────────────────────────────────────
# F5-B batch 3 — typed responses for intelligence endpoints that were
# returning ``response_model=dict`` (and therefore typed as
# ``Record<string, unknown>`` on the frontend).
# ──────────────────────────────────────────────────────────────────────


class RefreshViewsResponse(BaseModel):
    """Result of ``POST /intelligence/refresh-views`` — one entry per
    materialized view, value is either ``"ok"``, ``"ok (non-concurrent)"``
    or ``"error: <message>"`` per the repo implementation."""

    status: str = Field(..., description="Always ``refreshed`` on this endpoint.")
    views: dict[str, str] = Field(..., description="Per-view refresh status keyed by view name.")


class AsyncTaskResponse(BaseModel):
    """Standard celery dispatch result. Returned by every ``POST`` that
    enqueues background work (``/conflictos/detectar``, ``/zonas/generar``,
    ``/hci/batch``, ``/composite/analyze``)."""

    task_id: str = Field(..., description="Celery task UUID.")
    status: str = Field(
        default="submitted",
        description="Always ``submitted`` immediately after dispatch.",
    )


class AlertasActivasResponse(BaseModel):
    """Non-paginated wrapper for ``GET /intelligence/alertas`` — the
    list is short (active alerts only) so pagination isn't worth the
    envelope overhead. ``total`` is redundant with ``len(items)`` but
    surfaced explicitly to match the historical ``response_model=dict``
    contract the frontend already consumes."""

    items: list["AlertaResponse"]
    total: int


class AlertEvaluationResponse(BaseModel):
    """Outcome of ``POST /intelligence/alertas/evaluar`` — how many new
    alerts the run created and the resulting total."""

    alertas_creadas: int
    alertas_activas_total: int


class IntelligencePlaceholderResponse(BaseModel):
    """Used by the two stub GET endpoints (``/canales/prioridad`` and
    ``/caminos/riesgo``) that don't compute results synchronously yet —
    they tell the caller to POST to the matching ``/calcular`` instead.
    Keeping a real schema (vs ``response_model=dict``) so the OpenAPI
    surface still documents the response shape."""

    items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Always empty on these placeholder endpoints.",
    )
    message: str = Field(..., description="Operator-facing hint pointing at the real endpoint.")


# ──────────────────────────────────────────────
# CRUCES CAMINO x FLUJO (flujo-caminos Fase A)
# ──────────────────────────────────────────────


class CrucesCaminoRecalcularRequest(BaseModel):
    """Request to recompute an area's crossings.

    The five thresholds are deliberately NOT accepted here. They live in
    ``system_settings`` (category ``analisis``) so that what a run records cannot
    depend on who dispatched it; letting a caller override them per request would
    reintroduce exactly the ambiguity the single home was chosen to remove.
    """

    model_config = ConfigDict(extra="forbid")

    area_id: str = Field(..., min_length=1, max_length=100)


class CrucesCaminoResponse(BaseModel):
    """One response feeding BOTH the ranked list and the map.

    Deliberately one payload: the list and the map read the *same* response and
    therefore cannot disagree about direction, contributing area, segment or rank
    (RFA's "A crossing point is selected on the map" scenario).

    **No volume, flow rate, depth, cuneta size or return period appears here, and
    none is implied by a placeholder figure.** This capability derives a
    direction, an upslope contributing area and a relative ordering; it derives
    no hydraulics, and the UI says so beside the results.

    ``total_flujo_natural`` is the rank denominator. The UI reads ``N.º de M``
    with M = that count and never the total row count: canal crossings are a
    separate, unranked set, and a denominator that moved with DEM coverage rather
    than with the road network would mean nothing.
    """

    model_config = ConfigDict(from_attributes=True)

    area_id: str
    calculada_en: Optional[datetime] = Field(
        default=None,
        description=(
            "Generation timestamp of the run that produced this set. Always shown "
            "with the list, so no rank is ever read without knowing how old it is."
        ),
    )
    desactualizado: bool = Field(
        default=False,
        description=(
            "True when the terrain data or the road network changed after "
            "``calculada_en``. A false positive costs a dismissible notice; the "
            "comparison is deliberately biased that way, because a false negative "
            "would cost a silently wrong ranking presented as current."
        ),
    )
    total_flujo_natural: int = Field(
        default=0, description="Rank denominator — the ranked set's size."
    )
    total_canal: int = Field(
        default=0, description="Culvert/bridge candidates. Unranked, counted separately."
    )
    features: dict[str, Any] = Field(
        default_factory=lambda: {"type": "FeatureCollection", "features": []},
        description="GeoJSON in EPSG:4326 — reprojected, never merely stamped.",
    )
    excluidos: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "The run's own account of what it decided not to keep, with motivo in "
            "{sin_direccion, flujo_paralelo, suprimido_por_separacion, "
            "maximo_en_extremo}. A suppressed double crossing stays visible here."
        ),
    )
    parametros: dict[str, Any] = Field(
        default_factory=dict,
        description="The five recorded thresholds this run actually used.",
    )
    variante: Optional[str] = Field(
        default=None,
        description=(
            "Which drainage result was read: ``natural``, or "
            "``relevado_equivale_natural`` when the operational pair stood in "
            "under a verified no-burn condition."
        ),
    )
    segmentos_parcialmente_cubiertos: int = Field(
        default=0,
        description=(
            "Segments only partly inside the raster footprint. A crossing near "
            "the edge can be missed when its ridge lies just outside it."
        ),
    )
