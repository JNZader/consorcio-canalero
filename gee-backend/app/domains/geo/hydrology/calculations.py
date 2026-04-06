"""Pure hydrological calculation functions — no I/O, no external dependencies.

All functions implement established hydraulic engineering formulas adapted for
the flat Pampa terrain of the Consorcio Canalero 10 de Mayo operational zones.
"""

from typing import Optional


def kirpich_tc(L_m: float, S: float) -> float:
    """Estimate concentration time via the Kirpich (1940) formula.

    Tc = 0.0195 * L^0.77 * S^-0.385   (result in minutes)

    Args:
        L_m: Channel / overland flow length in meters.
        S:   Channel slope (dimensionless, rise/run). A floor of 0.001 is
             applied to handle the near-flat Pampa terrain and avoid
             division-by-zero / unrealistically large Tc values.

    Returns:
        Concentration time in minutes (float).
    """
    S_safe = max(S, 0.001)
    return 0.0195 * (L_m**0.77) * (S_safe**-0.385)


def ndvi_to_c(ndvi: float) -> float:
    """Convert mean NDVI to a runoff coefficient C for the Rational Method.

    NDVI is clamped to [0.0, 1.0] before applying the lookup table.

    Lookup table:
        NDVI < 0.15          → C = 0.80  (bare soil / urban / roads)
        0.15 ≤ NDVI < 0.30   → C = 0.65  (sparse vegetation)
        0.30 ≤ NDVI < 0.50   → C = 0.45  (moderate vegetation / row crops)
        NDVI ≥ 0.50          → C = 0.25  (dense vegetation / forest)

    Args:
        ndvi: Mean NDVI value for the zone (any float; clamped internally).

    Returns:
        Runoff coefficient C (dimensionless, 0–1).
    """
    ndvi_clamped = max(0.0, min(1.0, ndvi))

    if ndvi_clamped < 0.15:
        return 0.80
    elif ndvi_clamped < 0.30:
        return 0.65
    elif ndvi_clamped < 0.50:
        return 0.45
    else:
        return 0.25


def rational_method_q(C: float, I_mm_h: float, A_km2: float) -> float:
    """Estimate peak discharge via the Rational Method (Método Racional).

    Q = (C * I * A) / 3.6   (result in m³/s)

    The constant 3.6 converts the result from mm·km²/h to m³/s:
        1 mm/h × 1 km² = 1000 m³/h / 3600 s = 1/3.6 m³/s

    Args:
        C:      Runoff coefficient (dimensionless, 0–1).
        I_mm_h: Design rainfall intensity in mm/h.
        A_km2:  Drainage area in km².

    Returns:
        Peak discharge Q in m³/s.
    """
    return (C * I_mm_h * A_km2) / 3.6


def classify_hydraulic_risk(
    Q: float,
    capacity_m3s: Optional[float],
) -> tuple[str, Optional[float]]:
    """Classify hydraulic risk based on Q vs. canal capacity.

    Args:
        Q:            Estimated peak discharge in m³/s.
        capacity_m3s: Canal design capacity in m³/s. Pass None when unknown.

    Returns:
        A tuple (nivel_riesgo, porcentaje_capacidad) where:
            - nivel_riesgo is one of: "bajo" | "moderado" | "alto" | "critico" | "sin_capacidad"
            - porcentaje_capacidad is Q / capacity * 100, or None when capacity is unknown.

    Risk thresholds:
        percentage < 50   → "bajo"
        50 ≤ p < 75       → "moderado"
        75 ≤ p ≤ 100      → "alto"
        p > 100           → "critico"
    """
    if capacity_m3s is None:
        return ("sin_capacidad", None)

    percentage = (Q / capacity_m3s) * 100.0

    if percentage < 50:
        nivel = "bajo"
    elif percentage < 75:
        nivel = "moderado"
    elif percentage <= 100:
        nivel = "alto"
    else:
        nivel = "critico"

    return (nivel, percentage)
