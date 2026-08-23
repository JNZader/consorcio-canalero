"""The DEM candidate classifier (design D5). Pure geometry and statistics.

What it does, per segment: densify the trace every **15 m** (half a GLO-30 cell),
sample the DEM at each vertex for the road profile, sample two flanking points at
**±``flanco_offset_m``** along the local perpendicular for the terrain, and
compare **medians**:

    median(road) − median(flank) ≥  T  → ``terraplen``
    median(road) − median(flank) ≤ −T  → ``canal``
    otherwise                          → ``neutro``

``confianza_m`` stores the **signed** difference — the direction of the
disagreement is half the information, and an absolute value would make the two
non-neutral verdicts indistinguishable in the column.

**Medians, not means.** A culvert or a spoil pile is a metre-scale outlier on a
profile of tens of samples; under a mean, one cell decides the segment.

**Stated plainly so nobody reads the output as a measurement**: GLO-30's vertical
error is of the same order as ``T``. That is exactly why the value lives in its
own table, why the UI labels it a candidate, and why the UI carries the 30 m
resolution disclosure.

**Law 2 — the source is the fill of the REAL DEM.** ``dem_filled.tif``, resolved
by name from the newest DEM run's own record. Never ``dem_filled_hydro.tif`` or
``dem_burned.tif``: those carry a −10 m fictional trench, and the pipeline already
keeps the lineages apart. A newest run that offers only a burned surface **raises**
— it does not fall back to an older run, which would classify today's road against
yesterday's terrain.
"""

from __future__ import annotations

import math
import os
from statistics import median
from typing import Any, Iterable, Optional, Sequence

#: Half a GLO-30 cell. NOT a tuning knob: it is a property of the sampling grid,
#: and task 3.1's decision covers the two parameters below, not this one.
PASO_DENSIFICADO_M: float = 15.0

UMBRAL_FALLBACK_M: float = 1.0
FLANCO_OFFSET_FALLBACK_M: float = 60.0

#: ONE home for both parameters — ``system_settings``, category ``analisis``,
#: exactly where Fase A's five went (task 3.1). "Changeable without a code change"
#: is only true if the value is a row; a task-dispatch default is still code, and
#: two callers passing different literals would make "the parameters that produced
#: this candidate" depend on who launched the run.
PARAMETER_KEYS: dict[str, str] = {
    "umbral_m": "analisis/tramo_clasif_umbral_m",
    "flanco_offset_m": "analisis/tramo_clasif_flanco_offset_m",
}

#: Used only if a deployment has never been seeded. Identical to the seeds in
#: ``SettingsService._SEED_DEFAULTS`` — the row is the home, this is the "the row
#: is missing" answer, not a second home.
PARAMETER_FALLBACKS: dict[str, float] = {
    "umbral_m": UMBRAL_FALLBACK_M,
    "flanco_offset_m": FLANCO_OFFSET_FALLBACK_M,
}

NOMBRE_DEM_FILLED = "dem_filled.tif"

#: Names that must never be opened by this classifier. Listed by name so the rule
#: is greppable and so a new burned/simulated product added later fails closed
#: rather than being read because nobody remembered to exclude it.
NOMBRES_PROHIBIDOS: tuple[str, ...] = (
    "dem_filled_hydro.tif",
    "dem_burned.tif",
    "dem_filled_escenario.tif",
    "dem_burned_escenario.tif",
)


class DemFilledNoDisponible(RuntimeError):
    """The real filled DEM cannot be resolved for this area — a named refusal."""

    def __init__(self, detalle: str) -> None:
        self.detalle = detalle
        super().__init__(f"dem_filled_no_disponible: {detalle}")


def leer_parametros(db) -> dict[str, float]:
    """Read ``T`` and the flank offset from ``system_settings``, once per run."""
    from app.domains.settings.service import SettingsService

    settings_service = SettingsService()
    return {
        nombre: float(settings_service.get_setting(db, clave, PARAMETER_FALLBACKS[nombre]))
        for nombre, clave in PARAMETER_KEYS.items()
    }


def resolver_dem_filled(resultados: Sequence[dict[str, Any]]) -> str:
    """The newest DEM run's ``filled_dem``, or a refusal. Never a fallback.

    ``resultados`` is newest-first, exactly as ``dem_resultados_por_area``
    returns it. Only the first is considered: an older run's raster describes
    terrain this area may no longer have, and silently classifying against it is
    the kind of degradation nobody can see from the candidate row.
    """
    if not resultados:
        raise DemFilledNoDisponible(
            "no hay corridas DEM registradas para el área; sin superficie real no hay candidata"
        )

    ruta = (resultados[0] or {}).get("filled_dem")
    if not ruta:
        raise DemFilledNoDisponible(
            "la última corrida DEM no registró filled_dem; no se sustituye por otra superficie"
        )

    nombre = os.path.basename(str(ruta))
    if nombre in NOMBRES_PROHIBIDOS or nombre != NOMBRE_DEM_FILLED:
        raise DemFilledNoDisponible(
            f"la última corrida DEM ofrece {nombre!r}, que no es {NOMBRE_DEM_FILLED!r}; "
            "una superficie quemada o simulada nunca alimenta una clasificación"
        )
    return str(ruta)


def densificar(linea, paso_m: float = PASO_DENSIFICADO_M) -> list[tuple[float, float]]:
    """Vertices every ``paso_m`` along ``linea``, endpoints included.

    ``linea`` is in a METRIC CRS: the step is metres, so a degree-based geometry
    would produce a grid roughly 10^5 times too coarse.
    """
    largo = float(linea.length)
    if largo <= 0:
        punto = linea.coords[0]
        return [(float(punto[0]), float(punto[1]))]

    # ``ceil``, not ``floor``: rounding down would stretch the real spacing past
    # ``paso_m`` (a 100 m line over 6 intervals samples every 16.7 m), and the
    # step is half a DEM cell precisely so no cell is skipped.
    pasos = max(1, math.ceil(largo / paso_m))
    distancias = [i * largo / pasos for i in range(pasos + 1)]
    vertices = [linea.interpolate(d) for d in distancias]
    return [(float(p.x), float(p.y)) for p in vertices]


def puntos_flanco(
    vertices: Sequence[tuple[float, float]], *, offset_m: float
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Two points per vertex, at ±``offset_m`` along the LOCAL perpendicular.

    The local direction is taken from the neighbouring vertices (forward at the
    first, backward at the last), so a curve's flanks follow the curve instead of
    being projected off one global bearing.
    """
    if len(vertices) < 2:
        return []

    flancos: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for indice, (x, y) in enumerate(vertices):
        anterior = vertices[max(indice - 1, 0)]
        siguiente = vertices[min(indice + 1, len(vertices) - 1)]
        dx = siguiente[0] - anterior[0]
        dy = siguiente[1] - anterior[1]
        norma = (dx * dx + dy * dy) ** 0.5
        if norma == 0:
            continue
        # Perpendicular in the plane: (-dy, dx) normalized.
        px, py = -dy / norma, dx / norma
        flancos.append(
            (
                (x + px * offset_m, y + py * offset_m),
                (x - px * offset_m, y - py * offset_m),
            )
        )
    return flancos


def clasificar_perfiles(
    perfil_camino: Iterable[float],
    perfil_flanco: Iterable[float],
    *,
    umbral_m: float,
) -> tuple[str, float]:
    """``(clasificacion, confianza_m)`` from the two profiles. Medians only.

    Raises ``ValueError`` when either profile is empty: an unmeasured segment is
    not ``neutro``. ``neutro`` says "the DEM sees no difference"; no samples say
    nothing at all, and storing the first as the second would invent a reading.
    """
    camino = [float(v) for v in perfil_camino]
    flanco = [float(v) for v in perfil_flanco]
    if not camino or not flanco:
        raise ValueError(
            "un tramo sin muestras utilizables no se clasifica: 'neutro' afirmaría "
            "que el DEM no ve diferencia, y acá no se midió nada"
        )

    diferencia = median(camino) - median(flanco)
    if diferencia >= umbral_m:
        return "terraplen", diferencia
    if diferencia <= -umbral_m:
        return "canal", diferencia
    return "neutro", diferencia


def muestrear(dem_path: str, puntos: Sequence[tuple[float, float]]) -> list[float]:
    """DEM values at ``puntos``, nodata and out-of-footprint dropped.

    Dropped rather than zero-filled: a nodata cell read as 0 m would drag a
    median toward sea level and invent a canal.
    """
    import rasterio

    if not puntos:
        return []

    with rasterio.open(dem_path) as src:
        nodata = src.nodata
        valores = [v[0] for v in src.sample(puntos)]

    limpios: list[float] = []
    for valor in valores:
        numero = float(valor)
        if numero != numero:  # NaN
            continue
        if nodata is not None and numero == float(nodata):
            continue
        limpios.append(numero)
    return limpios


def clasificar_tramo(
    linea_utm,
    dem_path: str,
    *,
    umbral_m: float,
    flanco_offset_m: float,
) -> Optional[dict[str, Any]]:
    """One segment's candidate, or ``None`` when it cannot be measured.

    ``None`` is a segment the DEM does not cover — no candidate row is written
    for it, which is not the same as writing ``neutro``.
    """
    vertices = densificar(linea_utm)
    flancos = puntos_flanco(vertices, offset_m=flanco_offset_m)
    if not flancos:
        return None

    perfil_camino = muestrear(dem_path, vertices)
    perfil_flanco = muestrear(dem_path, [punto for par in flancos for punto in par])
    if not perfil_camino or not perfil_flanco:
        return None

    clasificacion, confianza = clasificar_perfiles(perfil_camino, perfil_flanco, umbral_m=umbral_m)
    return {
        "clasificacion_candidata": clasificacion,
        "confianza_m": confianza,
        "muestras_camino": len(perfil_camino),
        "muestras_flanco": len(perfil_flanco),
    }


__all__ = [
    "FLANCO_OFFSET_FALLBACK_M",
    "NOMBRES_PROHIBIDOS",
    "NOMBRE_DEM_FILLED",
    "PARAMETER_FALLBACKS",
    "PARAMETER_KEYS",
    "PASO_DENSIFICADO_M",
    "UMBRAL_FALLBACK_M",
    "DemFilledNoDisponible",
    "clasificar_perfiles",
    "clasificar_tramo",
    "densificar",
    "leer_parametros",
    "muestrear",
    "puntos_flanco",
    "resolver_dem_filled",
]
