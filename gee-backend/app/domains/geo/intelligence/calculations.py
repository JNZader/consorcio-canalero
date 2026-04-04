"""Pure calculation functions for operational intelligence.

All functions in this module are stateless and DB-free — they receive
numeric inputs and return computed results.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

# ── Default HCI Weights ─────────────────────────────────────────────

DEFAULT_HCI_WEIGHTS: dict[str, float] = {
    "pendiente": 0.15,
    "acumulacion": 0.30,
    "twi": 0.25,
    "dist_canal": 0.15,
    "hist_inundacion": 0.15,
}


# ── HCI Calculation ─────────────────────────────────────────────────


def calcular_indice_criticidad_hidrica(
    pendiente: float,
    acumulacion: float,
    twi: float,
    dist_canal: float,
    hist_inundacion: float,
    pesos: dict[str, float] | None = None,
) -> float:
    """Compute the Hydric Criticality Index (HCI).

    Each input should be normalised to [0, 1].  The result is a
    weighted sum scaled to [0, 100], clamped at 100.

    Args:
        pendiente: Normalised slope value.
        acumulacion: Normalised flow accumulation value.
        twi: Normalised Topographic Wetness Index.
        dist_canal: Normalised distance to nearest canal.
        hist_inundacion: Normalised historical flood indicator.
        pesos: Optional weight overrides (must contain same keys as
               DEFAULT_HCI_WEIGHTS).

    Returns:
        HCI value in [0, 100].
    """
    w = pesos if pesos is not None else DEFAULT_HCI_WEIGHTS
    raw = (
        w["pendiente"] * pendiente
        + w["acumulacion"] * acumulacion
        + w["twi"] * twi
        + w["dist_canal"] * dist_canal
        + w["hist_inundacion"] * hist_inundacion
    )
    return min(round(raw * 100, 10), 100.0)


# ── Risk Classification ─────────────────────────────────────────────


def clasificar_nivel_riesgo(indice: float) -> str:
    """Classify an HCI value into a risk level.

    Thresholds:
        [0, 25)   → bajo
        [25, 50)  → medio
        [50, 75)  → alto
        [75, 100] → critico
    """
    if indice < 25.0:
        return "bajo"
    if indice < 50.0:
        return "medio"
    if indice < 75.0:
        return "alto"
    return "critico"


# ── Conflict Severity ───────────────────────────────────────────────


def _clasificar_severidad_conflicto(
    acumulacion: float,
    pendiente: float,
) -> str:
    """Classify conflict severity based on accumulation and slope.

    Rules:
        alta  — accumulation >= 5000 OR slope < 0.5
        media — accumulation >= 2000 OR slope < 2.0
        baja  — otherwise
    """
    if acumulacion >= 5000 or pendiente < 0.5:
        return "alta"
    if acumulacion >= 2000 or pendiente < 2.0:
        return "media"
    return "baja"


# ── Dynamic Terrain Classification ──────────────────────────────────

_CLASS_LABELS: dict[int, str] = {
    0: "sin_clasificar",
    1: "agua",
    2: "vegetacion_densa",
    3: "suelo_desnudo",
    4: "vegetacion_dispersa",
}


def clasificar_terreno_dinamico(
    sar: Any | None,
    ndvi: Any | None,
    dem: Any | None,
) -> dict[str, Any]:
    """Multi-sensor terrain classification.

    Priority: SAR water detection > NDVI vegetation > unclassified.

    Args:
        sar: 2-D numpy array of SAR backscatter values (dB), or None.
        ndvi: 2-D numpy array of NDVI values [-1, 1], or None.
        dem: 2-D numpy array of elevation values (m), or None.

    Returns:
        Dict with keys ``clasificacion``, ``clases``, ``estadisticas``.
    """
    # Determine reference shape
    shape = None
    for arr in (sar, ndvi, dem):
        if arr is not None:
            shape = np.asarray(arr).shape
            break

    if shape is None:
        return {"clasificacion": None, "clases": {}, "estadisticas": {}}

    classified = np.zeros(shape, dtype=int)

    # NDVI classification (lower priority — applied first, overridden by SAR)
    if ndvi is not None:
        ndvi_arr = np.asarray(ndvi, dtype=float)
        classified[ndvi_arr > 0.5] = 2   # dense vegetation
        classified[(ndvi_arr > 0.2) & (ndvi_arr <= 0.5)] = 4  # sparse vegetation
        classified[(ndvi_arr > -0.1) & (ndvi_arr <= 0.2)] = 3  # bare soil

    # SAR water detection (highest priority — overwrites previous)
    if sar is not None:
        sar_arr = np.asarray(sar, dtype=float)
        classified[sar_arr < -15.0] = 1  # water

    # Build statistics
    total_pixels = int(np.prod(shape))
    stats: dict[str, dict[str, Any]] = {}
    for class_id, label in _CLASS_LABELS.items():
        count = int(np.sum(classified == class_id))
        if count > 0:
            stats[label] = {
                "pixeles": count,
                "porcentaje": round(count / total_pixels * 100, 1),
            }

    return {
        "clasificacion": classified,
        "clases": _CLASS_LABELS,
        "estadisticas": stats,
    }


# ── Canal Network Analysis (used by suggestions.py) ────────────────


def rank_canal_hotspots(
    canal_geometries: list[dict],
    flow_acc_path: str,
    num_points: int = 20,
) -> list[dict]:
    """Rank canal segments by flow accumulation hotspot score.

    Placeholder — actual implementation requires raster sampling.
    """
    raise NotImplementedError("rank_canal_hotspots requires raster I/O")


def detect_coverage_gaps(
    zones: list[dict],
    hci_scores: dict[str, float],
    canal_geometries: list[dict],
    threshold_km: float = 2.0,
) -> list[dict]:
    """Detect zones with poor canal coverage relative to HCI risk.

    Placeholder — actual implementation requires spatial analysis.
    """
    raise NotImplementedError("detect_coverage_gaps requires spatial analysis")


def suggest_canal_routes(
    gap_results: list[dict],
    canal_geometries: list[dict],
    slope_path: str,
) -> list[dict]:
    """Suggest new canal routes to address coverage gaps.

    Placeholder — actual implementation requires least-cost path analysis.
    """
    raise NotImplementedError("suggest_canal_routes requires raster I/O")


def compute_maintenance_priority(
    centrality_scores: dict[int, float] | None = None,
    flow_acc_scores: dict[int, float] | None = None,
    hci_scores: dict[str, float] | None = None,
    conflict_counts: dict[int, int] | None = None,
) -> list[dict]:
    """Compute composite maintenance priority for canal nodes.

    Placeholder — actual implementation combines multiple factors.
    """
    raise NotImplementedError("compute_maintenance_priority not yet implemented")


# ── Service-layer stubs (used by service.py) ────────────────────────


def calcular_prioridad_canal(*args: Any, **kwargs: Any) -> Any:
    """Calculate canal maintenance priority."""
    raise NotImplementedError


def calcular_riesgo_camino(*args: Any, **kwargs: Any) -> Any:
    """Calculate road risk score."""
    raise NotImplementedError


def detectar_puntos_conflicto(*args: Any, **kwargs: Any) -> Any:
    """Detect canal/road conflict points."""
    raise NotImplementedError


def generar_zonificacion(*args: Any, **kwargs: Any) -> Any:
    """Generate operational zoning."""
    raise NotImplementedError


def simular_escorrentia(*args: Any, **kwargs: Any) -> Any:
    """Simulate surface runoff."""
    raise NotImplementedError
