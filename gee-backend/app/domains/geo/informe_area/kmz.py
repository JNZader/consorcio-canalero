"""Informe de área — KMZ export for Google Earth (PR 6, S3).

``zipfile`` + hand-written KML XML, ZERO new dependencies (the plan's own
constraint, same discipline as ``mapas.py``). The KMZ reuses the SAME data
the PDF renders: the union boundary + subcuencas, the class rasters
vectorized with ``vectorize_zonal_classes`` (crisper than a PNG overlay at
Google Earth's zooms, and lighter than a raster), the IDECOR soils units,
and the anchor-event imagery PNGs the task already fetched from GEE — our
own dated Sentinel-2/Landsat exports, NEVER Esri (map-stack policy: derived
products).

One theme visible at a time (S3): every theme Folder lives inside a wrapper
``Temas`` Folder carrying a ``radioFolder`` ListStyle, so Google Earth treats
the siblings as a radio group — switching Riesgo on switches Drenaje off.
``Límite y subcuencas`` stays OUTSIDE the group: the boundary is reference
geometry the operator wants beside whichever theme is on.

The builder is PURE (dicts + bytes in → kmz bytes out): the Celery task
assembles the pieces it already computed for the PDF, and the pytest suite
exercises the XML without a database, a raster, or GEE.
"""

from __future__ import annotations

import io
import math
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape

#: KML 2.2 namespace — Google Earth rejects bare un-namespaced documents.
KML_NS = "http://www.opengis.net/kml/2.2"

#: Polygon fill alpha (~72 %): classes stay readable with imagery beneath.
_ALPHA_RELLENO = "b4"

#: Qualitative palette for the soils theme (IDECOR classes are roman
#: numerals I..VIII-ish; there is no house RANGE_CONFIGS entry for them).
#: Earth tones, ordered light→heavy so the visual ladder matches drainage
#: limitation the way the PDF's soils section ranks them.
PALETA_SUELOS: dict[str, str] = {
    "I": "#f2f0e4",
    "II": "#e4d9b0",
    "III": "#d3b878",
    "IV": "#bd9757",
    "V": "#a3763f",
    "VI": "#855931",
    "VII": "#66412a",
    "VIII": "#472b1f",
}
_PALETA_SUELOS_EXTRA = ["#9aae7a", "#c98d6b", "#7d8fa3", "#b5a5c9", "#8fbc8f", "#c7b577"]


def color_suelo(clase: str, indice: int) -> str:
    """Palette lookup with a cycle fallback for unknown/extra class labels."""
    if clase in PALETA_SUELOS:
        return PALETA_SUELOS[clase]
    return _PALETA_SUELOS_EXTRA[indice % len(_PALETA_SUELOS_EXTRA)]


@dataclass(frozen=True)
class ClaseKmz:
    """One class of one theme: dissolved geometry + palette color."""

    clase: str
    color: str  # "#rrggbb"
    geometrias: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class TemaKmz:
    """One theme folder: riesgo / drenaje / suelos (vector classes)."""

    titulo: str
    clases: list[ClaseKmz] = field(default_factory=list)


@dataclass(frozen=True)
class ImagenKmz:
    """One georeferenced PNG overlay (anchor-event imagery)."""

    titulo: str
    png: bytes
    #: (west, south, east, north) in EPSG:4326 — the bounds the thumbnail
    #: was fitted to (getThumbURL maps the region bbox linearly onto the
    #: PNG), which is exactly what a KML LatLonBox declares.
    bounds: tuple[float, float, float, float]


def _kml_color(hex_color: str, alpha: str = "ff") -> str:
    """``#rrggbb`` → KML ``aabbggrr`` (KML is byte-reversed RGBA)."""
    valor = hex_color.lstrip("#")
    if len(valor) != 6:
        valor = "808080"
    return f"{alpha}{valor[4:6]}{valor[2:4]}{valor[0:2]}"


def _coord(lon: float, lat: float) -> str:
    return f"{lon:.7f},{lat:.7f}"


def _anillos(geometry: dict[str, Any]) -> list[list[list[float]]]:
    """Exterior + interior rings of a Polygon/MultiPolygon as coord lists."""
    tipo = geometry.get("type")
    polys: list[Any] = []
    if tipo == "Polygon":
        polys = [geometry.get("coordinates")]
    elif tipo == "MultiPolygon":
        polys = geometry.get("coordinates") or []
    anillos: list[list[list[float]]] = []
    for poly in polys:
        if not poly:
            continue
        anillos.extend(list(anillo) for anillo in poly)
    return anillos


def _placemark_poligono(nombre: str, style_id: str, geometrias: list[dict[str, Any]]) -> str:
    """One Placemark per class: MultiGeometry of tessellated polygons."""
    poligonos: list[str] = []
    for geometria in geometrias:
        piezas: list[str] = []
        for anillo in _anillos(geometria):
            coords = " ".join(_coord(c[0], c[1]) for c in anillo if len(c) >= 2)
            if len(coords) < 2:
                continue
            piezas.append(f"<LinearRing><coordinates>{coords}</coordinates></LinearRing>")
        if not piezas:
            continue
        # First ring = outerBoundaryIs, the rest inner (GeoJSON ring order:
        # exterior then holes — KML needs them split by container).
        exterior, *interiores = piezas
        inner = "".join(f"<innerBoundaryIs>{p}</innerBoundaryIs>" for p in interiores)
        poligonos.append(
            "<Polygon><tessellate>1</tessellate>"
            f"<outerBoundaryIs>{exterior}</outerBoundaryIs>{inner}</Polygon>"
        )
    if not poligonos:
        return ""
    cuerpo = "".join(poligonos) if len(poligonos) > 1 else poligonos[0]
    if len(poligonos) > 1:
        cuerpo = f"<MultiGeometry>{cuerpo}</MultiGeometry>"
    return (
        f"<Placemark><name>{escape(nombre)}</name>"
        f"<styleUrl>#{style_id}</styleUrl>{cuerpo}</Placemark>"
    )


def _placemark_linea(nombre: str, style_id: str, geometrias: list[dict[str, Any]]) -> str:
    """Boundary/subcuenca outlines as LineStrings (never filled)."""
    lineas: list[str] = []
    for geometria in geometrias:
        for anillo in _anillos(geometria):
            coords = " ".join(_coord(c[0], c[1]) for c in anillo if len(c) >= 2)
            if len(coords) < 2:
                continue
            lineas.append(
                f"<LineString><tessellate>1</tessellate>"
                f"<coordinates>{coords}</coordinates></LineString>"
            )
    if not lineas:
        return ""
    cuerpo = "".join(lineas)
    if len(lineas) > 1:
        cuerpo = f"<MultiGeometry>{cuerpo}</MultiGeometry>"
    return (
        f"<Placemark><name>{escape(nombre)}</name>"
        f"<styleUrl>#{style_id}</styleUrl>{cuerpo}</Placemark>"
    )


def _estilo_linea(style_id: str, color: str, ancho: float) -> str:
    return (
        f'<Style id="{style_id}"><LineStyle><color>{_kml_color(color)}</color>'
        f"<width>{ancho}</width></LineStyle></Style>"
    )


def _estilo_poligono(style_id: str, color: str) -> str:
    relleno = _kml_color(color, _ALPHA_RELLENO)
    borde = _kml_color(color, "ff")
    return (
        f'<Style id="{style_id}">'
        f"<LineStyle><color>{borde}</color><width>0.8</width></LineStyle>"
        f"<PolyStyle><color>{relleno}</color></PolyStyle>"
        f"</Style>"
    )


def _look_at(bounds: tuple[float, float, float, float]) -> str:
    """Document camera centred on the selection, range ≈ its diagonal."""
    west, south, east, north = bounds
    lat_c = (south + north) / 2.0
    lon_c = (west + east) / 2.0
    # Local equirectangular diagonal is honest enough for a camera range.
    metros_lon = (east - west) * 111_320.0 * math.cos(math.radians(lat_c))
    metros_lat = (north - south) * 110_540.0
    alcance = max(2_000.0, 1.4 * math.hypot(metros_lon, metros_lat))
    return (
        f"<LookAt><longitude>{lon_c:.7f}</longitude><latitude>{lat_c:.7f}</latitude>"
        f"<altitude>0</altitude><range>{alcance:.0f}</range>"
        "<tilt>0</tilt><heading>0</heading></LookAt>"
    )


def _bounds_geojson(geometrias: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    minx = miny = 180.0
    maxx = maxy = -180.0
    for geometria in geometrias:
        for anillo in _anillos(geometria):
            for c in anillo:
                minx, maxx = min(minx, c[0]), max(maxx, c[0])
                miny, maxy = min(miny, c[1]), max(maxy, c[1])
    return minx, miny, maxx, maxy


def construir_kmz_informe(
    *,
    nombre: str,
    seleccion_geojson: dict[str, Any],
    subcuencas: list[dict[str, Any]],
    temas: list[TemaKmz],
    imagenes: list[ImagenKmz] | None = None,
) -> bytes:
    """Build the informe KMZ (pure; S3).

    Layout::

        doc.kml                       ← Document + styles + folders
        files/imagen-{clave}.png      ← GroundOverlay rasters

    The first zip entry is ``doc.kml`` (KMZ contract: readers open the
    initial entry; Google Earth also accepts a rooted path but first-entry
    is the portable form). PNG entries are STORED — a PNG is already
    deflate-compressed, re-deflating buys ~1 % and costs CPU on the worker.
    """
    estilos: list[str] = [
        '<Style id="temas-radio"><ListStyle><listItemType>radioFolder'
        "</listItemType></ListStyle></Style>",
        _estilo_linea("linea-seleccion", "#111111", 3.2),
        _estilo_linea("linea-subcuenca", "#8a8a8a", 1.6),
    ]
    carpetas: list[str] = []

    # ── Límite y subcuencas (outside the radio group: always available) ──
    linea_seleccion = _placemark_linea("Selección", "linea-seleccion", [seleccion_geojson])
    lineas_zonas = [
        _placemark_linea(
            str(z.get("nombre") or f"Subcuenca {i + 1}"),
            "linea-subcuenca",
            [z["geojson"]] if z.get("geojson") else [],
        )
        for i, z in enumerate(subcuencas)
    ]
    cuerpo_limite = linea_seleccion + "".join(filter(None, lineas_zonas))
    if cuerpo_limite:
        carpetas.append(
            f"<Folder><name>Límite y subcuencas</name><open>1</open>"
            f"<visibility>1</visibility>{cuerpo_limite}</Folder>"
        )

    # ── Temas (inside ONE radioFolder wrapper → one visible at a time) ──
    temas_xml: list[str] = []
    primer_tema_emitido = False
    for indice_tema, tema in enumerate(temas):
        placemarks: list[str] = []
        for indice_clase, clase in enumerate(tema.clases):
            if not clase.geometrias:
                continue
            style_id = f"clase-{indice_tema}-{indice_clase}"
            estilos.append(_estilo_poligono(style_id, clase.color))
            placemarks.append(_placemark_poligono(clase.clase, style_id, clase.geometrias))
        if not placemarks:
            continue
        # First theme on, the rest off: Google Earth opens with exactly one
        # theme of the radio group checked.
        visible = "0" if primer_tema_emitido else "1"
        primer_tema_emitido = True
        temas_xml.append(
            f"<Folder><name>{escape(tema.titulo)}</name>"
            f"<visibility>{visible}</visibility>"
            f"{''.join(placemarks)}</Folder>"
        )

    for indice, imagen in enumerate(imagenes or []):
        west, south, east, north = imagen.bounds
        href = f"files/imagen-{_clave_imagen(imagen.titulo, indice)}.png"
        temas_xml.append(
            f"<Folder><name>{escape(imagen.titulo)}</name><visibility>0</visibility>"
            "<GroundOverlay>"
            f"<name>{escape(imagen.titulo)}</name>"
            "<color>ffffffff</color>"
            f"<Icon><href>{escape(href)}</href></Icon>"
            "<LatLonBox>"
            f"<north>{north:.7f}</north><south>{south:.7f}</south>"
            f"<east>{east:.7f}</east><west>{west:.7f}</west>"
            "<rotation>0</rotation>"
            "</LatLonBox>"
            "</GroundOverlay></Folder>"
        )

    if temas_xml:
        carpetas.append(
            f"<Folder><name>Temas del informe</name><open>1</open><visibility>1</visibility>"
            "<styleUrl>#temas-radio</styleUrl>"
            f"{''.join(temas_xml)}</Folder>"
        )

    bounds = _bounds_geojson([seleccion_geojson])
    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<kml xmlns="{KML_NS}"><Document><name>{escape(nombre)}</name>'
        f"{_look_at(bounds)}"
        f"{''.join(estilos)}"
        f"{''.join(carpetas)}"
        "</Document></kml>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        info = zipfile.ZipInfo("doc.kml")
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, kml)
        for indice, imagen in enumerate(imagenes or []):
            info_png = zipfile.ZipInfo(f"files/imagen-{_clave_imagen(imagen.titulo, indice)}.png")
            info_png.compress_type = zipfile.ZIP_STORED
            zf.writestr(info_png, imagen.png)
    return buffer.getvalue()


def _clave_imagen(titulo: str, indice: int) -> str:
    """ASCII-safe, unique-per-archive file stem for one overlay PNG.

    Deterministic on ``(titulo, indice)``: the XML href and the zip entry
    name both come from this function, so they cannot drift apart.
    """
    plano = "".join(c if c.isalnum() else "-" for c in titulo.lower())
    clave = re.sub(r"-{2,}", "-", plano).strip("-")[:40]
    return f"{clave or 'imagen'}-{indice}"
