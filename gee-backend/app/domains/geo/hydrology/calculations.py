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


# ── Manning Formula ────────────────────────────────────────────────────────


def manning_section(
    ancho_m: float,
    profundidad_m: float,
    talud: float = 0.0,
) -> tuple[float, float]:
    """Compute cross-sectional area and wetted perimeter for a trapezoidal section.

    Args:
        ancho_m:      Bottom width of the canal in meters.
        profundidad_m: Normal depth (water depth) in meters.
        talud:         Side slope ratio H:V (0 = rectangular, 1 = 1:1).

    Returns:
        (area_m2, perimeter_m) tuple.
    """
    import math

    y = profundidad_m
    b = ancho_m
    z = talud
    area = (b + z * y) * y
    perimeter = b + 2 * y * math.sqrt(1 + z**2)
    return area, perimeter


def manning_q(
    ancho_m: float,
    profundidad_m: float,
    slope: float,
    n: float,
    talud: float = 0.0,
) -> float:
    """Compute canal discharge via Manning's equation.

    Q = (1/n) × A × R^(2/3) × S^(1/2)

    Args:
        ancho_m:       Bottom width in meters.
        profundidad_m: Normal depth in meters.
        slope:         Longitudinal bed slope (dimensionless, rise/run).
        n:             Manning roughness coefficient.
        talud:         Side slope H:V (0 = rectangular).

    Returns:
        Discharge Q in m³/s. Returns 0.0 if inputs are non-positive.
    """
    import math

    if ancho_m <= 0 or profundidad_m <= 0 or slope <= 0 or n <= 0:
        return 0.0

    area, perimeter = manning_section(ancho_m, profundidad_m, talud)
    if perimeter == 0:
        return 0.0

    R = area / perimeter  # hydraulic radius
    return (1.0 / n) * area * (R ** (2.0 / 3.0)) * math.sqrt(slope)


# Default Manning n values by material
MANNING_N_DEFAULTS: dict[str, float] = {
    "hormigon": 0.014,
    "hormigon_prefabricado": 0.013,
    "mamposteria": 0.020,
    "tierra": 0.025,
    "tierra_limpia": 0.022,
    "tierra_vegetacion": 0.030,
    "tierra_maleza": 0.035,
    "riprap": 0.035,
    "default": 0.025,
}


def get_manning_n(material: str | None, coef_override: float | None = None) -> float:
    """Resolve Manning n from material string or explicit override.

    Priority: coef_override > material lookup > 0.025 (earth channel default).
    """
    if coef_override is not None and coef_override > 0:
        return coef_override
    if material:
        key = material.lower().replace(" ", "_").replace("-", "_")
        return MANNING_N_DEFAULTS.get(key, MANNING_N_DEFAULTS["default"])
    return MANNING_N_DEFAULTS["default"]


# ── Gumbel return periods ──────────────────────────────────────────────────


def gumbel_return_period(
    annual_maxima: list[float],
    return_periods: list[int] | None = None,
) -> dict[int, float]:
    """Fit a Gumbel EV-I distribution to annual maxima and compute quantiles.

    Gumbel parameters (method of moments):
        μ (location) = mean - 0.5772 × β
        β  (scale)   = std × √6 / π

    Quantile formula:
        xT = μ - β × ln(-ln(1 - 1/T))

    Args:
        annual_maxima:  List of annual maximum precipitation values (mm).
        return_periods: List of return period years to compute. Defaults to
                        [5, 10, 25, 50, 100].

    Returns:
        Dict mapping return_period → estimated precipitation (mm).
        Returns empty dict if fewer than 5 years of data.
    """
    import math
    import statistics

    if return_periods is None:
        return_periods = [5, 10, 25, 50, 100]

    data = [x for x in annual_maxima if x is not None and x > 0]
    if len(data) < 5:
        return {}

    mean = statistics.mean(data)
    std = statistics.stdev(data)

    if std == 0:
        return {t: mean for t in return_periods}

    beta = std * math.sqrt(6) / math.pi
    mu = mean - 0.5772156649 * beta

    result: dict[int, float] = {}
    for T in return_periods:
        y = -math.log(-math.log(1.0 - 1.0 / T))
        result[T] = round(mu + beta * y, 2)

    return result
