"""Informe de área — static map rendering (T2, S7).

Zero new dependencies (S7): rasterio window-reads and DECIMATES the
registered class raster over the selection (never the full grid — S10's
worker-memory rule), numpy classifies the window against
``class_breaks.RANGE_CONFIGS`` and Pillow paints the RGB image plus every
map-furniture element: subcuenca outlines, selection contour, graphic scale
bar, north arrow and the legend strip (label · color · ha · %).

Background is plain WHITE on purpose. The map-stack policy (AGENTS.md) bans
Esri imagery in derived products — a report PDF is exactly that. The dated
Sentinel-2/Landsat miniatures the S6 section embeds DO comply with the
policy: they are our own GEE scene exports (dated provenance, selected by
the imagery shortlist), never a tiled basemap service.

Two renderers:

* :func:`render_mapa_clasificado` — flood_risk / drainage_need over the
  selection: the class raster + vectors + furniture.
* :func:`render_mapa_ubicacion` — the Resumen's location map: vectors +
  furniture on white (no raster), with zona labels when they fit.

Both return PNG bytes sized ≤ 1400 px wide (brief: ≤ 1500), a budget that
keeps the final PDF comfortably under S9's 5 MB.
"""

from __future__ import annotations

import io
import math
from typing import Any

import numpy as np
import rasterio
import structlog
from PIL import Image, ImageDraw, ImageFont
from pyproj import CRS, Geod, Transformer
from shapely.geometry import shape
from shapely.ops import transform as shapely_transform

from app.domains.geo.class_breaks import RANGE_CONFIGS
from app.shared.pdf.format_es import fmt_num

logger = structlog.get_logger(__name__)

# Output budget (S7 brief caps width at 1500 px; 1400 leaves frame room).
ANCHO_MAX_PX = 1400
ALTO_MAX_PX = 1400
# Floor so a small selection still gets a legible map instead of a thumbnail.
ANCHO_MIN_PX = 900
# Padding around the selection bounds, as a fraction of the span, so the
# contour never touches the frame.
MARGEN_FRACC = 0.08

_BLANCO = (255, 255, 255)
_FUERA_DE_CLASE = (238, 238, 238)  # valid pixel that belongs to no break
_CONTORNO = (17, 17, 17)
_SUBCUENCA = (120, 120, 120)
_TEXTO = (33, 33, 33)
_GRIS_SUAVE = (170, 170, 170)

# Geodesic scale-bar math (degrees ≠ metres anywhere useful).
_GEOD = Geod(ellps="WGS84")


def _hex_a_rgb(hex_color: str) -> tuple[int, int, int]:
    valor = hex_color.lstrip("#")
    return int(valor[0:2], 16), int(valor[2:4], 16), int(valor[4:6], 16)


def _fuente(tamano: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Scalable default font with a bitmap fallback for older Pillow installs."""
    try:
        return ImageFont.load_default(size=tamano)
    except TypeError:  # Pillow < 10.1: load_default takes no size
        return ImageFont.load_default()


def _ancho_texto(draw: ImageDraw.ImageDraw, texto: str, font: Any) -> float:
    caja = draw.textbbox((0, 0), texto, font=font)
    return caja[2] - caja[0]


def _a_crs_raster(geom: Any, src_crs: CRS, dst_crs: CRS) -> Any:
    """Reproject a shapely geometry to the raster CRS (identity when equal)."""
    if src_crs == dst_crs:
        return geom
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return shapely_transform(transformer.transform, geom)


def _bounds_con_margen(geoms: list[Any]) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = geoms[0].bounds
    for g in geoms[1:]:
        bx0, by0, bx1, by1 = g.bounds
        minx, miny = min(minx, bx0), min(miny, by0)
        maxx, maxy = max(maxx, bx1), max(maxy, by1)
    dx = max((maxx - minx) * MARGEN_FRACC, 1e-9)
    dy = max((maxy - miny) * MARGEN_FRACC, 1e-9)
    return minx - dx, miny - dy, maxx + dx, maxy + dy


def _metros_por_px(
    bounds: tuple[float, float, float, float], ancho_px: int, es_geografico: bool
) -> float:
    """Horizontal ground metres per pixel at the map's centre latitude.

    Projected CRS → the map units ARE metres. Geographic CRS → geodesic
    length of the centre row (``Geod.inv``), which is what the scale bar
    actually claims to measure; a cos(lat) shortcut would drift at these
    latitudes for no savings.
    """
    minx, miny, maxx, maxy = bounds
    if not es_geografico:
        return (maxx - minx) / ancho_px
    lat_centro = (miny + maxy) / 2.0
    _, _, metros = _GEOD.inv(minx, lat_centro, maxx, lat_centro)
    return metros / ancho_px


def _longitud_escala_nice(metros_objetivo: float) -> float:
    """Round bar length from the 1/2/5 ladder closest to ``metros_objetivo``."""
    if metros_objetivo <= 0:
        return 1.0
    exponente = math.floor(math.log10(metros_objetivo))
    candidatos = [base * 10**exponente for base in (1.0, 2.0, 5.0)] + [10.0 * 10**exponente]
    return min(candidatos, key=lambda c: abs(math.log(c / metros_objetivo)))


def _dibujar_escala(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    metros_por_px: float,
    ancho_canvas: int,
    font: Any,
) -> None:
    """Graphic scale bar at (x0, y0): two-tone bar, end ticks, es-AR label."""
    ancho_disponible = ancho_canvas - x0 - 20
    if ancho_disponible <= 60:
        return
    metros = _longitud_escala_nice(0.22 * ancho_disponible * metros_por_px)
    px = max(2, round(metros / metros_por_px))
    alto = 7
    # Bar: black first half, white-outlined second half (cartographic convention).
    draw.rectangle([x0, y0, x0 + px // 2, y0 + alto], fill=_CONTORNO)
    draw.rectangle([x0 + px // 2, y0, x0 + px, y0 + alto], fill=_BLANCO, outline=_CONTORNO, width=1)
    draw.rectangle([x0, y0, x0 + px, y0 + alto], outline=_CONTORNO, width=1)
    for tick in (x0, x0 + px):
        draw.line([(tick, y0 - 4), (tick, y0 + alto + 4)], fill=_CONTORNO, width=2)
    etiqueta = f"{fmt_num(metros / 1000.0, 0)} km" if metros >= 1000 else f"{fmt_num(metros, 0)} m"
    draw.text((x0 + px + 10, y0 - 3), etiqueta, fill=_TEXTO, font=font)


def _dibujar_norte(draw: ImageDraw.ImageDraw, x: int, y: int, largo: int, font: Any) -> None:
    """North arrow: shaft + filled head + 'N', pointing up (map/grid north)."""
    draw.line([(x, y), (x, y - largo)], fill=_CONTORNO, width=3)
    draw.polygon(
        [(x, y - largo - 12), (x - 7, y - largo + 4), (x + 7, y - largo + 4)],
        fill=_CONTORNO,
    )
    draw.text((x - 5, y + 6), "N", fill=_TEXTO, font=font)


def _anillos(geom: Any) -> list[tuple[list[float], list[float]]]:
    """Exterior + interior rings of a (multi)polygon as (xs, ys) pairs."""
    polys = list(getattr(geom, "geoms", [geom]))
    anillos: list[tuple[list[float], list[float]]] = []
    for poly in polys:
        anillos.append(poly.exterior.coords.xy)
        for interior in poly.interiors:
            anillos.append(interior.coords.xy)
    return anillos


def _dibujar_geometria(
    draw: ImageDraw.ImageDraw,
    geom: Any,
    a_pantalla: Any,
    color: tuple[int, int, int],
    ancho: int,
) -> None:
    """Draw every ring of a (multi)polygon through the (x, y) → px projector."""
    for xs, ys in _anillos(geom):
        puntos = [a_pantalla(x, y) for x, y in zip(xs, ys)]
        if len(puntos) >= 2:
            draw.line(puntos, fill=color, width=ancho, joint="curve")


class _Proyector:
    """Map-unit → pixel projector for a known bounds/size pair."""

    def __init__(self, bounds: tuple[float, float, float, float], ancho: int, alto: int) -> None:
        minx, miny, maxx, maxy = bounds
        self.escala_x = ancho / max(maxx - minx, 1e-12)
        self.escala_y = alto / max(maxy - miny, 1e-12)
        self.minx = minx
        self.maxy = maxy

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        return ((x - self.minx) * self.escala_x, (self.maxy - y) * self.escala_y)


def _leyenda_clases(
    img: Image.Image,
    breaks: list[dict],
    ha_por_clase: dict[str, float],
    pct_por_clase: dict[str, float],
    con_datos: bool,
) -> Image.Image:
    """Legend strip appended below the map: swatch · label · ha · % (es-AR).

    Greedy row wrap keeps one row for the usual 4-class rasters and two for
    longer legends; every number goes through ``format_es`` (S12).
    """
    font = _fuente(19)
    swatch, gap, alto_item = 22, 14, 34
    provisional = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(provisional)
    items: list[tuple[str, str]] = []
    for cfg in breaks:
        etiqueta = str(cfg["label"])
        if con_datos:
            detalle = f"{fmt_num(ha_por_clase.get(etiqueta, 0.0))} ha · {fmt_num(pct_por_clase.get(etiqueta, 0.0), 1)} %"
        else:
            detalle = "sin cobertura"
        items.append((etiqueta, detalle))
    anchos = [swatch + 8 + _ancho_texto(d, f"{e} · {det}", font) for e, det in items]

    ancho_total = img.width
    filas: list[list[int]] = [[]]
    used = 0.0
    for i, ancho_item in enumerate(anchos):
        if used and used + gap + ancho_item > ancho_total - 24:
            filas.append([])
            used = 0.0
        filas[-1].append(i)
        used += ancho_item + (gap if len(filas[-1]) > 1 else 0)

    alto_banda = len(filas) * alto_item + 16
    lienzo = Image.new("RGB", (ancho_total, img.height + alto_banda), _BLANCO)
    lienzo.paste(img, (0, 0))
    draw = ImageDraw.Draw(lienzo)
    draw.line([(0, img.height), (ancho_total, img.height)], fill=_GRIS_SUAVE, width=1)
    y = img.height + 8
    for fila in filas:
        x = 16.0
        for i in fila:
            etiqueta, detalle = items[i]
            draw.rectangle(
                [x, y + 6, x + swatch, y + 6 + swatch - 10], fill=_hex_a_rgb(breaks[i]["color"])
            )
            draw.text((x + swatch + 8, y), f"{etiqueta} · {detalle}", fill=_TEXTO, font=font)
            x += anchos[i] + gap
        y += alto_item
    return lienzo


def render_mapa_clasificado(
    tipo: str,
    raster_path: str,
    union_geojson: dict[str, Any],
    zonas: list[dict[str, Any]],
    clases: list[dict[str, Any]],
) -> bytes | None:
    """Class raster over the selection, painted with the ``class_breaks`` palette.

    ``clases`` are the dataset's own ``{clase, ha, pct}`` rows (what the PDF
    table shows) so the legend and the table can never disagree. ``None`` is
    returned when the window cannot be built (raster gone / disjoint) — the
    caller degrades, it does not fail the report.
    """
    breaks = RANGE_CONFIGS.get(tipo)
    if not breaks:
        return None
    try:
        return _render_clasificado(tipo, raster_path, union_geojson, zonas, clases, breaks)
    except Exception:  # noqa: BLE001 — a map is decoration; the report must live
        logger.warning("informe_area.mapa_fallo", tipo=tipo, exc_info=True)
        return None


def _render_clasificado(
    tipo: str,
    raster_path: str,
    union_geojson: dict[str, Any],
    zonas: list[dict[str, Any]],
    clases: list[dict[str, Any]],
    breaks: list[dict],
) -> bytes | None:
    union = shape(union_geojson)
    geoms_zonas = [shape(z["geojson"]) for z in zonas if z.get("geojson")]

    with rasterio.open(raster_path) as src:
        if src.crs is None:
            return None
        crs_raster = CRS.from_user_input(src.crs)
        crs_geom = CRS.from_user_input("EPSG:4326")
        union_r = _a_crs_raster(union, crs_geom, crs_raster)
        zonas_r = [_a_crs_raster(g, crs_geom, crs_raster) for g in geoms_zonas]

        from rasterio.windows import Window, from_bounds

        bounds = _bounds_con_margen([union_r, *zonas_r])
        try:
            ventana = from_bounds(*bounds, transform=src.transform).round_lengths().round_offsets()
            ventana = ventana.intersection(Window(0, 0, src.width, src.height))
        except Exception:  # noqa: BLE001 — selection off the raster entirely
            return None
        if ventana.width < 2 or ventana.height < 2:
            return None

        # Upscale tiny windows to a readable width (nearest resampling keeps
        # the class raster honest — the vector overlay is drawn at output
        # resolution regardless), never past the pixel budget.
        ancho_deseado = min(max(ventana.width, ANCHO_MIN_PX), ANCHO_MAX_PX)
        escala = ancho_deseado / ventana.width
        if ventana.height * escala > ALTO_MAX_PX:
            escala = ALTO_MAX_PX / ventana.height
        ancho_out = max(1, round(ventana.width * escala))
        alto_out = max(1, round(ventana.height * escala))

        data = src.read(1, window=ventana, out_shape=(alto_out, ancho_out), masked=True)

        # Vectors project over the WINDOW's own map bounds — the window is
        # CLIPPED to the raster extent, so it can be narrower than the padded
        # selection bounds; projecting over the latter would skew the overlay
        # whenever the selection touches the raster edge.
        from rasterio.windows import bounds as bounds_de_ventana

        bounds_ventana = bounds_de_ventana(ventana, src.transform)
        proj = _Proyector(bounds_ventana, ancho_out, alto_out)

        def a_pantalla(x: float, y: float) -> tuple[float, float]:
            return proj(x, y)

        es_geografico = crs_raster.is_geographic
        metros_px = _metros_por_px(bounds_ventana, ancho_out, es_geografico)

    # ── classify (numpy) ────────────────────────────────────────────────
    arr = data.filled(np.nan)
    valido = ~np.isnan(arr)
    rgb = np.full((alto_out, ancho_out, 3), _FUERA_DE_CLASE, dtype=np.uint8)
    ultimo = len(breaks) - 1
    for i, cfg in enumerate(breaks):
        lo, hi = float(cfg["min"]), float(cfg["max"])
        miembro = valido & (arr >= lo) & ((arr <= hi) if i == ultimo else (arr < hi))
        rgb[miembro] = _hex_a_rgb(cfg["color"])
    rgb[~valido] = _BLANCO

    img = Image.fromarray(rgb, "RGB")
    draw = ImageDraw.Draw(img)
    for g in zonas_r:
        _dibujar_geometria(draw, g, a_pantalla, _SUBCUENCA, 2)
    _dibujar_geometria(draw, union_r, a_pantalla, _CONTORNO, 4)

    font = _fuente(19)
    _dibujar_escala(draw, 18, alto_out - 26, metros_px, ancho_out, font)
    _dibujar_norte(draw, ancho_out - 26, 44, 30, font)
    draw.rectangle([0, 0, ancho_out - 1, alto_out - 1], outline=_GRIS_SUAVE, width=1)

    ha_por_clase = {c["clase"]: float(c.get("ha") or 0.0) for c in clases}
    pct_por_clase = {c["clase"]: float(c.get("pct") or 0.0) for c in clases}
    img = _leyenda_clases(img, breaks, ha_por_clase, pct_por_clase, con_datos=bool(clases))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_mapa_ubicacion(
    union_geojson: dict[str, Any],
    zonas: list[dict[str, Any]],
) -> bytes | None:
    """Location map for the Resumen: vectors + furniture on a white field.

    Zona name labels are drawn only when there are ≤ 8 zonas — beyond that
    the labels become noise, and the per-section tables carry the names.
    """
    try:
        union = shape(union_geojson)
        geoms_zonas = [shape(z["geojson"]) for z in zonas if z.get("geojson")]
        bounds = _bounds_con_margen([union, *geoms_zonas])
        minx, miny, maxx, maxy = bounds

        lat_media = (miny + maxy) / 2.0
        cos_lat = max(math.cos(math.radians(lat_media)), 0.1)
        aspecto = (maxy - miny) / max((maxx - minx) * cos_lat, 1e-12)
        ancho = ANCHO_MAX_PX
        alto = round(ancho * aspecto)
        if alto > ALTO_MAX_PX:
            alto = ALTO_MAX_PX
            ancho = round(alto / max(aspecto, 1e-12))
        ancho, alto = max(ancho, 200), max(alto, 200)

        proj = _Proyector(bounds, ancho, alto)
        img = Image.new("RGB", (ancho, alto), _BLANCO)
        draw = ImageDraw.Draw(img)

        font = _fuente(19)
        etiquetas = len(geoms_zonas) <= 8
        for zona, g in zip(zonas, geoms_zonas):
            _dibujar_geometria(draw, g, proj, _SUBCUENCA, 2)
            if etiquetas and zona.get("nombre"):
                cx, cy = g.representative_point().x, g.representative_point().y
                px, py = proj(cx, cy)
                draw.text((px + 4, py - 10), str(zona["nombre"]), fill=_TEXTO, font=font)
        _dibujar_geometria(draw, union, proj, _CONTORNO, 4)

        _dibujar_escala(draw, 18, alto - 26, _metros_por_px(bounds, ancho, True), ancho, font)
        _dibujar_norte(draw, ancho - 26, 44, 30, font)
        draw.rectangle([0, 0, ancho - 1, alto - 1], outline=_GRIS_SUAVE, width=1)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 — decoration degrades, never fails
        logger.warning("informe_area.mapa_ubicacion_fallo", exc_info=True)
        return None
