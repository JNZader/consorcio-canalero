"""Join primitives — normalize_cuenta + catastro/bpa/agro join.

Pre-joining at ETL time (Approach 6a in the exploration) is the core of this
ETL: it means the frontend never has to re-resolve ``Nro_Cuenta`` at runtime.
Everything goes through :func:`normalize_cuenta` before the join indexes are
built — no exceptions, not even "obviously clean" strings.
"""

from __future__ import annotations

import logging
from typing import Any

from scripts.etl_pilar_verde.constants import BPA_EJES, BPA_PRACTICAS

logger = logging.getLogger(__name__)


#: IDECor's catastro rural publishes ``Superficie_Tierra_Rural`` in SQUARE METRES
#: despite the naming suggesting hectares.  This factor converts m² → ha so
#: downstream consumers (aggregates, enriched JSON, widget, AI sessions) see
#: realistic values.  See Phase 0 addendum (anomaly #1) for the discovery trail.
M2_TO_HA: float = 1.0 / 10_000.0


#: Historical BPA year window — 2019..2025 inclusive.  Used by the commitment-
#: depth helpers (``compute_anios_bpa`` / ``compute_anios_lista``) so a stray
#: year outside this range (bad IDECor row) never inflates the count.
BPA_HISTORICAL_YEARS: tuple[str, ...] = (
    "2019",
    "2020",
    "2021",
    "2022",
    "2023",
    "2024",
    "2025",
)


def compute_anios_bpa(historico: dict[str, str], has_2025: bool) -> int:
    """Count the years (2019..2025) in which a parcel participated in BPA.

    ``historico`` is the parcel's ``bpa_historico`` map (year → n_explotacion).
    ``has_2025`` flips in the 2025 participation tick — which lives in
    ``bpa_2025`` on the enriched parcel, NOT in ``bpa_historico``.
    """
    years: set[str] = {y for y in (historico or {}) if y in BPA_HISTORICAL_YEARS}
    if has_2025:
        years.add("2025")
    return len(years)


def compute_anios_lista(historico: dict[str, str], has_2025: bool) -> list[str]:
    """Return the sorted ascending list of year strings (2019..2025).

    Used by the BPA info card to render the literal "Hizo BPA: 2019, 2020,
    2025" line without client-side sorting / dedupe.
    """
    years: set[str] = {y for y in (historico or {}) if y in BPA_HISTORICAL_YEARS}
    if has_2025:
        years.add("2025")
    return sorted(years)


def _m2_to_ha(raw: Any) -> float | None:
    """Convert raw IDECor m² to hectares.  Returns ``None`` when input is null.

    Keeps ``None`` as ``None`` (never 0.0) so downstream aggregators can
    distinguish "missing superficie" from "zero superficie" — the
    ``_safe_float`` helper in ``aggregates.py`` treats ``None`` as 0 anyway,
    but join-level consumers may care.
    """
    if raw is None:
        return None
    try:
        return round(float(raw) * M2_TO_HA, 1)
    except (TypeError, ValueError):
        return None


def normalize_cuenta(raw: Any) -> str | None:
    """Canonicalise a cuenta value so join keys match across IDECor layers.

    Rules (documented in tests):
    - ``None`` / empty / whitespace-only / the literal string ``"None"`` → ``None``.
    - Integers are cast via ``str()``.
    - All whitespace (spaces, tabs, newlines) is stripped.
    - Dots used as thousands separators are stripped (``"1501.1573.6126"`` → ``"150115736126"``).
    - The function is idempotent: ``f(f(x)) == f(x)``.
    """
    if raw is None:
        return None

    text = str(raw)
    # Remove all whitespace — not just leading/trailing — because IDECor
    # occasionally returns segmented values like "1501 157 36126".
    text = "".join(text.split())
    # Strip dot thousands separators only AFTER whitespace removal.
    text = text.replace(".", "")
    if not text or text == "None":
        return None
    return text


def _index_by_cuenta(features: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """Build ``normalized_cuenta -> feature`` index, warning on collisions."""
    index: dict[str, dict[str, Any]] = {}
    for feature in features:
        props = feature.get("properties") or {}
        raw = props.get(key)
        cuenta = normalize_cuenta(raw)
        if cuenta is None:
            continue
        if cuenta in index:
            logger.warning(
                "join: duplicate cuenta=%s on key=%s — last wins", cuenta, key
            )
        index[cuenta] = feature
    return index


def _extract_bpa_block(feature: dict[str, Any]) -> dict[str, Any]:
    """Pull the bpa_2025 sub-object that lives on each enriched parcel."""
    props = feature.get("properties") or {}
    return {
        "n_explotacion": props.get("n_explotacion"),
        "superficie_bpa": props.get("superficie_bpa"),
        "bpa_total": props.get("bpa_total"),
        "id_explotacion": str(props.get("id_explotacion"))
        if props.get("id_explotacion") is not None
        else None,
        "activa": bool(props.get("activa", False)),
        "ejes": {eje: props.get(f"eje_{eje}") for eje in BPA_EJES},
        "practicas": {practica: props.get(practica) for practica in BPA_PRACTICAS},
    }


def join_bpa(
    catastro: list[dict[str, Any]],
    bpa_2025: list[dict[str, Any]],
    aceptada: list[dict[str, Any]],
    presentada: list[dict[str, Any]],
    history_by_year: dict[int, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Join catastro rural against BPA + agro layers by normalised cuenta.

    Returns a flat list of enriched parcel dicts following the frozen
    ``bpa_enriched.json`` schema v1.0.  Parcels without a BPA match are still
    emitted, with ``bpa_2025 = None`` (EXACTLY ``None`` — not ``{}``).  When a
    parcel appears in BOTH aceptada and presentada, aceptada wins.
    """
    bpa_index = _index_by_cuenta(bpa_2025, key="cuenta")
    aceptada_set = set(_index_by_cuenta(aceptada, key="lista_cuenta").keys())
    presentada_set = set(_index_by_cuenta(presentada, key="lista_cuenta").keys())
    history_by_year = history_by_year or {}

    # Per-cuenta map: year -> n_explotacion
    historico_index: dict[str, dict[str, str]] = {}
    for year, features in history_by_year.items():
        for feature in features:
            props = feature.get("properties") or {}
            cuenta = normalize_cuenta(props.get("cuenta"))
            if cuenta is None:
                continue
            name = props.get("n_explotacion")
            if name is None:
                continue
            historico_index.setdefault(cuenta, {})[str(year)] = str(name)

    parcels: list[dict[str, Any]] = []
    for feature in catastro:
        props = feature.get("properties") or {}
        cuenta = normalize_cuenta(props.get("Nro_Cuenta"))
        if cuenta is None:
            continue

        if cuenta in aceptada_set:
            ley_forestal = "aceptada"
        elif cuenta in presentada_set:
            ley_forestal = "presentada"
        else:
            ley_forestal = "no_inscripta"

        bpa_block = _extract_bpa_block(bpa_index[cuenta]) if cuenta in bpa_index else None
        historico = historico_index.get(cuenta, {})
        has_2025 = bpa_block is not None

        parcels.append(
            {
                "nro_cuenta": cuenta,
                "nomenclatura": props.get("Nomenclatura"),
                "departamento": props.get("departamento"),
                "pedania": props.get("pedania"),
                # IDECor publishes this field in m² despite the name — convert.
                "superficie_ha": _m2_to_ha(props.get("Superficie_Tierra_Rural")),
                "valuacion": props.get("Valuacion_Tierra_Rural"),
                "ley_forestal": ley_forestal,
                "bpa_2025": bpa_block,
                "bpa_historico": historico,
                # Phase 7 — commitment-depth fields for the unified historical
                # map layer + simplified BpaCard.
                "años_bpa": compute_anios_bpa(historico, has_2025),
                "años_lista": compute_anios_lista(historico, has_2025),
            }
        )

    return parcels


def build_bpa_history(
    all_bpa_by_year: dict[int, list[dict[str, Any]]],
) -> dict[str, dict[str, str]]:
    """Flatten per-year BPA fetches to ``{cuenta: {year: n_explotacion}}``.

    Only keys where at least one year has a record appear.  2025 is excluded —
    it belongs to ``bpa_enriched.json`` (spec §bpa_history.json).
    """
    history: dict[str, dict[str, str]] = {}
    for year, features in all_bpa_by_year.items():
        if year == 2025:
            continue
        for feature in features:
            props = feature.get("properties") or {}
            cuenta = normalize_cuenta(props.get("cuenta"))
            if cuenta is None:
                continue
            name = props.get("n_explotacion")
            if name is None:
                continue
            history.setdefault(cuenta, {})[str(year)] = str(name)
    return history
