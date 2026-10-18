"""Longitudinal elevation profile over the real filled DEM.

Same 15 m densify + ``dem_filled.tif`` rule as the road-segment classifier.
This module returns the series (distance vs elevation) instead of a median
verdict. It does not size canals, cunetas or culverts: GLO-30 is a ~30 m
surface, not a project grade.

Never open a burned or hydro-filled raster. ``resolver_dem_filled`` is the gate.
"""

from __future__ import annotations

from math import cos, hypot, radians
from pathlib import Path
from typing import Any, Optional, Sequence

from shapely.geometry import LineString, MultiLineString
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

# Holes that reach the profile as if they were heights. The filled DEM carries
# them as 0.0 and does not always declare `nodata` in its GeoTIFF, so the value
# has to be named here: a 0 m sample in this basin is a hole, not sea level.
# Unmasked, ONE of these stretches the chart's Y axis to 0 and squashes the whole
# profile into a sliver at the top — that is the live defect on S384 (2 points)
# and T269-08 (29 points), where the sibling MDE-Ar has real data on the very
# same vertices.
NODATA_HOLES = frozenset({-999999.0, -9999.0, 0.0})

# Abuse cap, not GLO-30 physics. Compute is bounded by MAX_POINTS via paso_muestreo.
MAX_LENGTH_M = 200_000.0
MAX_POINTS = 2_000


RETRACE_COSINE = -0.85
RETRACE_SNAP_M = 2.0

#: Two endpoints closer than this are the same vertex. This is NOT the weld
#: tolerance: closing a digitizing gap is migration 0030. Here a scrambled
#: part array is only reordered, so the sampler cannot teleport.
_VERTICE_COMPARTIDO_GRADOS = 1e-8

#: A reverse is an entrance only when the chosen end meets the cursor.
#: Wider than this, the piece keeps the direction it was drawn. Same 8 m
#: as the weld, but in metres: ``8/111320`` degrees is shorter east-west.
_ENTRADA_MAX_M = 8.0
_METROS_POR_GRADO = 111_320.0


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


def _xy(coord: Sequence[float]) -> tuple[float, float]:
    return (float(coord[0]), float(coord[1]))


def _distancia_grados(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def _distancia_metros(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Equirectangular metres. A raw degree length overstates longitude here."""
    medio = radians((a[1] + b[1]) / 2.0)
    return hypot(
        (a[0] - b[0]) * _METROS_POR_GRADO * cos(medio),
        (a[1] - b[1]) * _METROS_POR_GRADO,
    )


def _copia_linea(linea: LineString) -> LineString:
    return LineString([(float(x), float(y)) for x, y in linea.coords])


def _reversa_linea(linea: LineString) -> LineString:
    return LineString([(float(x), float(y)) for x, y in list(linea.coords)[::-1]])


def _ordenar_partes(partes: Sequence[LineString]) -> list[LineString]:
    """Same walk as ``caminos_soldar_ruta`` after migration 0032.

    Free end first. The nearer end wins the next part, and a reverse
    happens only when that end is within 8 m of the cursor.
    """
    piezas = [_copia_linea(parte) for parte in partes if len(parte.coords) >= 2]
    cantidad = len(piezas)
    if cantidad <= 1:
        return piezas
    extremos = [(_xy(pieza.coords[0]), _xy(pieza.coords[-1])) for pieza in piezas]

    def grado(punto: tuple[float, float]) -> int:
        cuenta = 0
        for inicio, fin in extremos:
            if _distancia_grados(punto, inicio) <= _VERTICE_COMPARTIDO_GRADOS:
                cuenta += 1
            if _distancia_grados(punto, fin) <= _VERTICE_COMPARTIDO_GRADOS:
                cuenta += 1
        return cuenta

    semilla: tuple[float, float, int, bool] | None = None
    for solo_libres in (True, False):
        if semilla is not None:
            break
        for indice, (inicio, fin) in enumerate(extremos):
            for al_final, punto in ((False, inicio), (True, fin)):
                if solo_libres and grado(punto) > 1:
                    continue
                clave = (punto[0], punto[1], indice)
                if semilla is None or clave < semilla[:3]:
                    semilla = (clave[0], clave[1], clave[2], al_final)
    if semilla is None:
        return piezas

    indice = semilla[2]
    primera = _reversa_linea(piezas[indice]) if semilla[3] else piezas[indice]
    orden = [primera]
    usadas = {indice}
    cursor = _xy(primera.coords[-1])
    while len(usadas) < cantidad:
        mejor: tuple[float, float, float, int, bool] | None = None
        for j, (inicio, fin) in enumerate(extremos):
            if j in usadas:
                continue
            d0 = _distancia_grados(cursor, inicio)
            d1 = _distancia_grados(cursor, fin)
            if d0 <= d1:
                elegido, voltear, distancia = inicio, False, d0
            else:
                elegido, voltear, distancia = fin, True, d1
            if _distancia_metros(cursor, elegido) > _ENTRADA_MAX_M:
                voltear = False
            clave = (distancia, elegido[0], elegido[1], j, voltear)
            if mejor is None or clave[:4] < mejor[:4]:
                mejor = clave
        if mejor is None:
            break
        _distancia, _x, _y, elegido_j, voltear = mejor
        pieza = _reversa_linea(piezas[elegido_j]) if voltear else piezas[elegido_j]
        orden.append(pieza)
        usadas.add(elegido_j)
        cursor = _xy(pieza.coords[-1])
    return orden


def geometria_ordenada(geom: BaseGeometry) -> BaseGeometry:
    """Walk a MultiLineString from its westernmost free end.

    A free end meets no other part endpoint. The next part is the unused one
    whose nearer end is closest to the cursor. That part is reversed only
    when the far end is the nearer one and that end is within 8 m of the
    cursor. A separated piece keeps the direction it was drawn. A gap is
    not filled. A single LineString keeps the orientation it arrived with,
    so a drawn measurement does not flip.

    Migration ``0030_weld_order_caminos`` welds endpoints within 8 m.
    Migration ``0031_drop_covered_caminos`` drops a covered copy before that
    snap, then drops what the merge still leaves inside the buffer.
    Migration ``0032_keep_gap_direction`` is this 8 m entrance gate.
    """
    if geom.geom_type == "LineString":
        return geom
    if geom.geom_type != "MultiLineString":
        return geom
    partes = [parte for parte in geom.geoms if not parte.is_empty]
    if len(partes) <= 1:
        return partes[0] if partes else geom
    ordenadas = _ordenar_partes(partes)
    if len(ordenadas) == 1:
        return ordenadas[0]
    return MultiLineString(ordenadas)


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

    extra = (extra_nodata or frozenset()) | NODATA_HOLES
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
