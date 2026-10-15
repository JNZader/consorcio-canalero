"""Longitudinal elevation profile over the real filled DEM.

Same 15 m densify + ``dem_filled.tif`` rule as the road-segment classifier.
This module returns the series (distance vs elevation) instead of a median
verdict. It does not size canals, cunetas or culverts: GLO-30 is a ~30 m
surface, not a project grade.

Never open a burned or hydro-filled raster. ``resolver_dem_filled`` is the gate.
"""

from __future__ import annotations

from math import hypot
from pathlib import Path
from typing import Any, Optional, Sequence

from shapely.geometry.base import BaseGeometry

from app.domains.geo.relevamiento.clasificador import (
    NOMBRE_DEM_FILLED,
    PASO_DENSIFICADO_M,
    densificar,
)

DISCLAIMER = "Perfil sobre Copernicus GLO-30 (~30 m). No es cota de proyecto ni sección de canal."
MDE_AR_NOMBRE = "mde_ar.tif"
MDE_AR_DISCLAIMER = "MDE-Ar (IGN, SRVN16). No comparar el delta con GLO-30 como cota verdadera."
MDE_AR_NODATA = frozenset({-999999.0, -9999.0})

# Abuse cap, not GLO-30 physics. Compute is bounded by MAX_POINTS via paso_muestreo.
MAX_LENGTH_M = 200_000.0
MAX_POINTS = 2_000


RETRACE_COSINE = -0.85
RETRACE_SNAP_M = 2.0


def desplegar_retrazado(
    coords: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Keep the outbound vertices; skip samples that reverse along the last edge."""
    if len(coords) < 3:
        return [(float(x), float(y)) for x, y in coords]
    out: list[tuple[float, float]] = [
        (float(coords[0][0]), float(coords[0][1])),
        (float(coords[1][0]), float(coords[1][1])),
    ]
    for raw in coords[2:]:
        point = (float(raw[0]), float(raw[1]))
        previous = out[-2]
        tip = out[-1]
        v1 = (tip[0] - previous[0], tip[1] - previous[1])
        v2 = (point[0] - tip[0], point[1] - tip[1])
        n1 = hypot(v1[0], v1[1])
        n2 = hypot(v2[0], v2[1])
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        cosine = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        back = hypot(point[0] - previous[0], point[1] - previous[1])
        if cosine <= RETRACE_COSINE and back <= n1 + RETRACE_SNAP_M:
            continue
        out.append(point)
    return out if len(out) >= 2 else [(float(x), float(y)) for x, y in coords]


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
    dem_path: str,
    puntos: Sequence[tuple[float, float]],
    extra_nodata: frozenset[float] | None = None,
) -> list[Optional[float]]:
    """One value per vertex. Nodata / NaN / out-of-footprint stay ``None``."""
    import rasterio

    if not puntos:
        return []

    extra = extra_nodata or frozenset()
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
        if numero in extra:
            alineados.append(None)
            continue
        alineados.append(numero)
    return alineados


def aplicar_mde_ar(payload: dict[str, Any], dem_filled_path: str) -> dict[str, Any]:
    """Sample sibling ``mde_ar.tif`` in EPSG:4326. Missing file is a no-op."""
    mde_path = Path(dem_filled_path).with_name(MDE_AR_NOMBRE)
    if not mde_path.is_file():
        return payload
    puntos = payload.get("puntos")
    if not isinstance(puntos, list) or not puntos:
        return payload
    lonlats: list[tuple[float, float]] = []
    for punto in puntos:
        lon = punto.get("lon")
        lat = punto.get("lat")
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            return payload
        lonlats.append((float(lon), float(lat)))
    cotas = muestrear_alineado(str(mde_path), lonlats, extra_nodata=MDE_AR_NODATA)
    for punto, cota in zip(puntos, cotas):
        punto["elevation_mde_ar"] = cota
    payload["mde_ar_disclaimer"] = MDE_AR_DISCLAIMER
    return payload


def perfil_desde_linea_metrica(
    linea: BaseGeometry,
    dem_path: str,
    *,
    paso_m: float | None = None,
) -> dict[str, Any]:
    """Sample ``linea`` (metric CRS matching the raster) against ``dem_path``.

    ``paso_m`` lets a multi-part trace share one step across its parts so the
    total stays inside MAX_POINTS instead of each part spending the whole budget.
    """
    if linea is None or linea.is_empty or len(getattr(linea, "coords", [])) < 2:
        raise ValueError("hace falta un LineString con al menos dos vértices")
    from shapely.geometry import LineString as ShapelyLine

    unfolded = desplegar_retrazado(list(linea.coords))
    if len(unfolded) < 2:
        raise ValueError("hace falta un LineString con al menos dos vértices")
    linea = ShapelyLine(unfolded)
    largo = float(linea.length)
    if largo > MAX_LENGTH_M:
        raise ValueError(f"la traza supera {int(MAX_LENGTH_M)} m")
    paso = paso_muestreo(largo) if paso_m is None else max(PASO_DENSIFICADO_M, float(paso_m))
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


def unir_perfiles(parciales: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Concatenate per-part payloads into one multi-part profile.

    Chainage accumulates across parts so the X axis stays monotonic, and every
    point carries its ``parte`` so the chart can break the line where the trace
    jumps instead of drawing a segment across the gap. The gap is a real break in
    the road, never a straight line sampled across it.
    """
    if not parciales:
        raise ValueError("hace falta al menos una parte")
    puntos: list[dict[str, Any]] = []
    offset = 0.0
    for parte, parcial in enumerate(parciales):
        for punto in parcial.get("puntos") or []:
            puntos.append(
                {**punto, "distance_m": float(punto["distance_m"]) + offset, "parte": parte}
            )
        offset += float(parcial.get("length_m") or 0.0)
    validas = [p["elevation_m"] for p in puntos if p.get("elevation_m") is not None]
    primero = parciales[0]
    return {
        "puntos": puntos,
        "length_m": offset,
        "min_elevation_m": min(validas) if validas else None,
        "max_elevation_m": max(validas) if validas else None,
        "source": primero.get("source"),
        "cell_m": primero.get("cell_m"),
        "disclaimer": primero.get("disclaimer", DISCLAIMER),
        "partes": len(parciales),
    }
