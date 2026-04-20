"""Pre-computed aggregates for the Pilar Verde dashboard widget + AI sessions.

Everything here is pure-functional and deterministic — given the same inputs,
the output of these functions is byte-identical.  That's what lets us freeze
``aggregates.json`` as a stable contract (schema_version "1.0").

All rounding is 1 decimal place, matching the spec §aggregates.json rules.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from shapely.geometry import shape
from shapely.ops import transform
import pyproj

from scripts.etl_pilar_verde.constants import (
    BPA_EJES,
    BPA_PRACTICAS,
    CRS_LATLON,
    CRS_METRIC_FOR_AREA,
)

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float:
    """Coerce to float, treating None/null as zero (spec: null superficie → 0)."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round1(value: float) -> float:
    return round(value, 1)


def compute_ley_forestal(parcels: list[dict[str, Any]]) -> dict[str, Any]:
    """Two-track ley forestal counts + superficie with zero-division guards.

    Returns the shape required by ``aggregates.json``:
    ``aceptada_count``, ``presentada_count``, ``no_inscripta_count``,
    ``aceptada_superficie_ha``, ``presentada_superficie_ha``,
    ``cumplimiento_pct_parcelas``, ``cumplimiento_pct_superficie``.
    """
    aceptada = [p for p in parcels if p.get("ley_forestal") == "aceptada"]
    presentada = [p for p in parcels if p.get("ley_forestal") == "presentada"]
    no_inscripta = [p for p in parcels if p.get("ley_forestal") == "no_inscripta"]

    aceptada_ha = _round1(sum(_safe_float(p.get("superficie_ha")) for p in aceptada))
    presentada_ha = _round1(sum(_safe_float(p.get("superficie_ha")) for p in presentada))

    total_count = len(aceptada) + len(presentada)
    total_ha = aceptada_ha + presentada_ha

    if total_count == 0:
        logger.warning(
            "compute_ley_forestal: zero-denominator on parcelas "
            "(no aceptada+presentada rows) — emitting 0"
        )
        cumplimiento_pct_parcelas = 0
    else:
        cumplimiento_pct_parcelas = _round1(len(aceptada) / total_count * 100)

    if total_ha == 0:
        logger.warning(
            "compute_ley_forestal: zero-denominator on superficie "
            "(no aceptada+presentada ha) — emitting 0"
        )
        cumplimiento_pct_superficie = 0
    else:
        cumplimiento_pct_superficie = _round1(aceptada_ha / total_ha * 100)

    return {
        "aceptada_count": len(aceptada),
        "presentada_count": len(presentada),
        "no_inscripta_count": len(no_inscripta),
        "aceptada_superficie_ha": aceptada_ha,
        "presentada_superficie_ha": presentada_ha,
        "cumplimiento_pct_parcelas": cumplimiento_pct_parcelas,
        "cumplimiento_pct_superficie": cumplimiento_pct_superficie,
    }


def _active_bpa_records(parcels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        p["bpa_2025"]
        for p in parcels
        if p.get("bpa_2025") is not None and p["bpa_2025"].get("activa")
    ]


def compute_practicas_ranking(parcels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return 21 entries sorted desc by adoption %.  All practicas ALWAYS appear."""
    records = _active_bpa_records(parcels)
    total = len(records)
    ranking: list[dict[str, Any]] = []
    for practica in BPA_PRACTICAS:
        if total == 0:
            pct = 0
        else:
            adopted = sum(
                1 for r in records if r.get("practicas", {}).get(practica) == "Si"
            )
            pct = _round1(adopted / total * 100)
        ranking.append({"nombre": practica, "adopcion_pct": pct})
    # Stable sort: desc by adopcion_pct, then alphabetical by name as tiebreaker.
    ranking.sort(key=lambda row: (-row["adopcion_pct"], row["nombre"]))
    return ranking


def compute_ejes_distribucion(parcels: list[dict[str, Any]]) -> dict[str, float]:
    """``{eje: pct of active BPA records where ejes[eje] == "Si"}`` for the 4 ejes."""
    records = _active_bpa_records(parcels)
    total = len(records)
    distribution: dict[str, float] = {}
    for eje in BPA_EJES:
        if total == 0:
            distribution[eje] = 0
            continue
        hits = sum(1 for r in records if r.get("ejes", {}).get(eje) == "Si")
        distribution[eje] = _round1(hits / total * 100)
    return distribution


def compute_bpa_kpis(
    parcels: list[dict[str, Any]], zona_superficie_ha: float
) -> dict[str, Any]:
    """Return the ``bpa`` block of aggregates.json.

    ``superficie_total_ha`` uses ``superficie_bpa`` when present and positive,
    else falls back to parcel ``superficie_ha`` (spec rule).
    """
    active = [p for p in parcels if p.get("bpa_2025") is not None and p["bpa_2025"].get("activa")]

    superficie_total = 0.0
    for parcel in active:
        bpa_block = parcel["bpa_2025"] or {}
        sup_bpa = _safe_float(bpa_block.get("superficie_bpa"))
        sup_catastro = _safe_float(parcel.get("superficie_ha"))
        if sup_bpa > 0:
            superficie_total += sup_bpa
        else:
            superficie_total += sup_catastro
    superficie_total = _round1(superficie_total)

    if zona_superficie_ha > 0:
        cobertura_pct = _round1(superficie_total / zona_superficie_ha * 100)
    else:
        cobertura_pct = 0

    # Phase 7 refinement (schema 1.2) — ``practica_top_adoptada``,
    # ``practica_top_no_adoptada`` and ``practicas_ranking`` dropped per user
    # feedback (not actionable for the widget). ``compute_practicas_ranking``
    # stays exported for downstream consumers / future rehydration.
    block: dict[str, Any] = {
        "explotaciones_activas": len(active),
        "superficie_total_ha": superficie_total,
        "cobertura_pct_zona": cobertura_pct,
        "ejes_distribucion": compute_ejes_distribucion(parcels),
    }
    # Phase 0 addendum — schema v1.1 (additive): historical-coverage KPIs.
    block.update(compute_cobertura_historica(parcels))
    block["evolucion_anual"] = compute_evolucion_anual(parcels)
    return block


def _metric_transformer() -> pyproj.Transformer:
    return pyproj.Transformer.from_crs(CRS_LATLON, CRS_METRIC_FOR_AREA, always_xy=True)


def compute_zonas_agroforestales_intersect(
    zonas_features: list[dict[str, Any]],
    zona_polygon_feature: dict[str, Any],
) -> list[dict[str, Any]]:
    """Intersect each Zona Agroforestal with the zona CC ampliada; area in ha."""
    from scripts.etl_pilar_verde.clip import _as_polygon

    zona_geom = _as_polygon(zona_polygon_feature)
    transformer = _metric_transformer()

    def to_metric(geom):
        return transform(transformer.transform, geom)

    out: list[dict[str, Any]] = []
    for feature in zonas_features:
        props = feature.get("properties") or {}
        leyenda = props.get("leyenda") or props.get("nombre") or ""
        geom = feature.get("geometry")
        if geom is None:
            continue
        feature_geom = shape(geom)
        if not feature_geom.intersects(zona_geom):
            continue
        intersection = feature_geom.intersection(zona_geom)
        if intersection.is_empty:
            continue
        area_m2 = to_metric(intersection).area
        out.append(
            {
                "leyenda": leyenda,
                "superficie_ha_en_zona": _round1(area_m2 / 10000.0),
            }
        )
    return out


#: Years covered by the BPA historical-coverage KPIs.  Keep this tuple
#: explicit — consumers (frontend charts, AI sessions) want a stable year
#: axis even when a year has zero participants.
HISTORICAL_YEARS: tuple[str, ...] = ("2019", "2020", "2021", "2022", "2023", "2024", "2025")


def _was_in_bpa(parcel: dict[str, Any]) -> bool:
    """True iff the parcel was in BPA at any point (history OR 2025)."""
    if parcel.get("bpa_2025") is not None:
        return True
    historico = parcel.get("bpa_historico") or {}
    return bool(historico)


def compute_cobertura_historica(parcels: list[dict[str, Any]]) -> dict[str, Any]:
    """Historical coverage KPIs — exposed under ``aggregates.bpa``.

    Emits 6 fields that slice the parcel population three ways:
    - ``cobertura_historica_*``: was in BPA at any point (2019-2025).
    - ``abandonaron_*``: was in before but NOT in 2025 (dropped out).
    - ``nunca_*``: never in BPA.

    All percentages are over the total parcel count and rounded 1dp.
    """
    total = len(parcels)
    if total == 0:
        return {
            "cobertura_historica_count": 0,
            "cobertura_historica_pct": 0,
            "abandonaron_count": 0,
            "abandonaron_pct": 0,
            "nunca_count": 0,
            "nunca_pct": 0,
        }

    cobertura = 0
    abandonaron = 0
    for parcel in parcels:
        historico = parcel.get("bpa_historico") or {}
        has_history = bool(historico)
        has_2025 = parcel.get("bpa_2025") is not None
        if has_history or has_2025:
            cobertura += 1
        if has_history and not has_2025:
            abandonaron += 1
    nunca = total - cobertura

    return {
        "cobertura_historica_count": cobertura,
        "cobertura_historica_pct": _round1(cobertura / total * 100),
        "abandonaron_count": abandonaron,
        "abandonaron_pct": _round1(abandonaron / total * 100),
        "nunca_count": nunca,
        "nunca_pct": _round1(nunca / total * 100),
    }


def compute_evolucion_anual(parcels: list[dict[str, Any]]) -> dict[str, int]:
    """Per-year participant count across the full historical series.

    Every year in :data:`HISTORICAL_YEARS` MUST appear — even at 0 — so
    downstream chart consumers don't have to defensive-default missing keys.
    """
    counts: dict[str, int] = {year: 0 for year in HISTORICAL_YEARS}
    for parcel in parcels:
        historico = parcel.get("bpa_historico") or {}
        for year in historico:
            year_key = str(year)
            if year_key in counts:
                counts[year_key] += 1
        if parcel.get("bpa_2025") is not None:
            counts["2025"] += 1
    return counts


def compute_grilla_aggregates(
    grilla_features: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Summary stats for ``agro_grilla_dist5`` — we ship aggregates, not geometry."""
    features = grilla_features or []
    props_list = [f.get("properties") or {} for f in features]

    def _mean(key: str) -> float:
        values = [_safe_float(p.get(key)) for p in props_list if p.get(key) is not None]
        return _round1(sum(values) / len(values)) if values else 0

    def _distribution(key: str) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for p in props_list:
            value = p.get(key)
            if value is None:
                continue
            counter[str(value)] += 1
        return dict(counter)

    return {
        "altura_med_mean": _mean("altura_med"),
        "pend_media_mean": _mean("pend_media"),
        "forest_mean_pct": _mean("forest_mean"),
        "categoria_distribution": _distribution("categoria"),
        "drenaje_distribution": _distribution("drenaje"),
    }
