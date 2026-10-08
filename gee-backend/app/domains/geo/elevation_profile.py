"""Longitudinal elevation profile over the real filled DEM.

Same 15 m densify + ``dem_filled.tif`` rule as the road-segment classifier.
This module returns the series (distance vs elevation) instead of a median
verdict. It does not size canals, cunetas or culverts: GLO-30 is a ~30 m
surface, not a project grade.

Never open a burned or hydro-filled raster. ``resolver_dem_filled`` is the gate.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from shapely.geometry.base import BaseGeometry

from app.domains.geo.relevamiento.clasificador import (
    NOMBRE_DEM_FILLED,
    PASO_DENSIFICADO_M,
    densificar,
)

DISCLAIMER = "Perfil sobre Copernicus GLO-30 (~30 m). No es cota de proyecto ni sección de canal."

MAX_LENGTH_M = 25_000.0
MAX_POINTS = 2_000


def distancias_sobre(linea: BaseGeometry, vertices: Sequence[tuple[float, float]]) -> list[float]:
    """Chainage of ``vertices`` along ``linea``, metres in the line's CRS."""
    if not vertices:
        return []
    largo = float(linea.length)
    if largo <= 0 or len(vertices) == 1:
        return [0.0] * len(vertices)
    ultimo = len(vertices) - 1
    return [i * largo / ultimo for i in range(len(vertices))]


def ensamblar_perfil(
    *,
    distancias_m: Sequence[float],
    cotas: Sequence[Optional[float]],
    dem_nombre: str,
) -> dict[str, Any]:
    """Wire payload. Extrema ignore nodata holes."""
    if len(distancias_m) != len(cotas):
        raise ValueError("distancias y cotas desalineadas")
    puntos = [
        {"distance_m": float(d), "elevation_m": None if z is None else float(z)}
        for d, z in zip(distancias_m, cotas)
    ]
    validas = [p["elevation_m"] for p in puntos if p["elevation_m"] is not None]
    length_m = float(distancias_m[-1]) if distancias_m else 0.0
    return {
        "puntos": puntos,
        "length_m": length_m,
        "min_elevation_m": min(validas) if validas else None,
        "max_elevation_m": max(validas) if validas else None,
        "source": dem_nombre,
        "cell_m": PASO_DENSIFICADO_M,
        "disclaimer": DISCLAIMER,
    }


def muestrear_alineado(
    dem_path: str, puntos: Sequence[tuple[float, float]]
) -> list[Optional[float]]:
    """One value per vertex. Nodata / NaN / out-of-footprint stay ``None``."""
    import rasterio

    if not puntos:
        return []

    with rasterio.open(dem_path) as src:
        nodata = src.nodata
        crudos = [v[0] for v in src.sample(puntos)]

    alineados: list[Optional[float]] = []
    for valor in crudos:
        numero = float(valor)
        if numero != numero:
            alineados.append(None)
            continue
        if nodata is not None and numero == float(nodata):
            alineados.append(None)
            continue
        alineados.append(numero)
    return alineados


def perfil_desde_linea_metrica(linea: BaseGeometry, dem_path: str) -> dict[str, Any]:
    """Sample ``linea`` (metric CRS matching the raster) against ``dem_path``."""
    if linea is None or linea.is_empty or len(getattr(linea, "coords", [])) < 2:
        raise ValueError("hace falta un LineString con al menos dos vértices")
    largo = float(linea.length)
    if largo > MAX_LENGTH_M:
        raise ValueError(f"la traza supera {int(MAX_LENGTH_M)} m")
    vertices = densificar(linea, PASO_DENSIFICADO_M)
    if len(vertices) > MAX_POINTS:
        raise ValueError(f"el perfil superaría {MAX_POINTS} muestras")
    distancias = distancias_sobre(linea, vertices)
    cotas = muestrear_alineado(dem_path, vertices)
    return ensamblar_perfil(
        distancias_m=distancias,
        cotas=cotas,
        dem_nombre=NOMBRE_DEM_FILLED,
    )
