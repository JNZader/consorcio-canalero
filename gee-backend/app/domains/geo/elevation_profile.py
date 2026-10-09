"""Longitudinal elevation profile over the real filled DEM.

Same 15 m densify + ``dem_filled.tif`` rule as the road-segment classifier.
This module returns the series (distance vs elevation) instead of a median
verdict. It does not size canals, cunetas or culverts: GLO-30 is a ~30 m
surface, not a project grade.

Never open a burned or hydro-filled raster. ``resolver_dem_filled`` is the gate.
"""

from __future__ import annotations

from math import hypot
from typing import Any, Optional, Sequence

from shapely.geometry.base import BaseGeometry

from app.domains.geo.relevamiento.clasificador import (
    NOMBRE_DEM_FILLED,
    PASO_DENSIFICADO_M,
    densificar,
)

DISCLAIMER = "Perfil sobre Copernicus GLO-30 (~30 m). No es cota de proyecto ni sección de canal."

# Abuse cap, not GLO-30 physics. Compute is bounded by MAX_POINTS via paso_muestreo.
MAX_LENGTH_M = 200_000.0
MAX_POINTS = 2_000


def paso_muestreo(largo_m: float) -> float:
    """Keep ≤ MAX_POINTS vertices: 15 m until the trace no longer fits."""
    if largo_m <= 0:
        return PASO_DENSIFICADO_M
    intervalos = max(1, MAX_POINTS - 1)
    return max(PASO_DENSIFICADO_M, largo_m / intervalos)


def distancias_sobre(linea: BaseGeometry, vertices: Sequence[tuple[float, float]]) -> list[float]:
    """True chainage along ``vertices`` in the line CRS (metres), not index-uniform."""
    if not vertices:
        return []
    if len(vertices) == 1 or float(linea.length) <= 0:
        return [0.0] * len(vertices)
    distancias = [0.0]
    for index in range(1, len(vertices)):
        x0, y0 = vertices[index - 1]
        x1, y1 = vertices[index]
        distancias.append(distancias[-1] + hypot(x1 - x0, y1 - y0))
    return distancias


def ensamblar_perfil(
    *,
    distancias_m: Sequence[float],
    cotas: Sequence[Optional[float]],
    dem_nombre: str,
    longitudes: Sequence[float] | None = None,
    latitudes: Sequence[float] | None = None,
    cell_m: float = PASO_DENSIFICADO_M,
) -> dict[str, Any]:
    """Wire payload. Extrema ignore nodata holes."""
    if len(distancias_m) != len(cotas):
        raise ValueError("distancias y cotas desalineadas")
    if longitudes is not None and len(longitudes) != len(distancias_m):
        raise ValueError("longitudes desalineadas")
    if latitudes is not None and len(latitudes) != len(distancias_m):
        raise ValueError("latitudes desalineadas")
    puntos = []
    for index, (d, z) in enumerate(zip(distancias_m, cotas)):
        punto: dict[str, Any] = {
            "distance_m": float(d),
            "elevation_m": None if z is None else float(z),
        }
        if longitudes is not None and latitudes is not None:
            punto["lon"] = float(longitudes[index])
            punto["lat"] = float(latitudes[index])
        puntos.append(punto)
    validas = [p["elevation_m"] for p in puntos if p["elevation_m"] is not None]
    length_m = float(distancias_m[-1]) if distancias_m else 0.0
    return {
        "puntos": puntos,
        "length_m": length_m,
        "min_elevation_m": min(validas) if validas else None,
        "max_elevation_m": max(validas) if validas else None,
        "source": dem_nombre,
        "cell_m": float(cell_m),
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
    paso = paso_muestreo(largo)
    vertices = densificar(linea, paso)
    if len(vertices) > MAX_POINTS:
        raise ValueError(f"el perfil superaría {MAX_POINTS} muestras")
    distancias = distancias_sobre(linea, vertices)
    cotas = muestrear_alineado(dem_path, vertices)
    payload = ensamblar_perfil(
        distancias_m=distancias,
        cotas=cotas,
        dem_nombre=NOMBRE_DEM_FILLED,
        cell_m=paso,
    )
    payload["_vertices_xy"] = vertices
    return payload
