"""Informe de área PDF builder — the informe de área PDF sections (PR 2 T2 + PR 4 IDECOR layers).

Mandatory reuse (S12): ``BrandedPDF``/``NumberedCanvas`` from
``app.shared/pdf/base.py`` (the "Página n de N" folio is stamped there) and
every number goes through ``format_es`` (``fmt_num``/``fmt_ha``/``fmt_pct``)
so the report reads es-AR — comma decimals, dot thousands — never the Python
default that PR 0 audited out of the zoning builders.

Section order is FIXED (S6) and the tests assert it in extracted text:

1. Resumen (nombre, fecha, ha, subcuencas/cuencas, mapa de ubicación, 4
   KPIs, ranking de subcuencas)
2. Riesgo hídrico (frase, mapa + leyenda + escala + norte, tabla clase·ha·%,
   nota de método, desglose por subcuenca)
3. Necesidad de drenaje (igual estructura que 2)
4. Suelos (carta IDECOR 1:50.000 — PR 4: unidades, series, IP, agua útil)
5. Cobertura y cultivos (IDECOR uso 2024/2025 + estivales — PR 4, S4)
6. Lluvia (normales mensuales en barras — ReportLab primitives, no chart lib)
7. Canales (km relevados/propuestos clip por el área, cruces, conflictos — PR 4, S5)
8. Imágenes de eventos ancla (miniaturas GEE falso color NIR-SWIR1-R — PR 4, S6)
9. Consideraciones (cobertura por capa, límites, descargo)
10. Fuentes (capa · fecha · resolución · origen)

Per-subcuenca tables (S6): inline and complete when there are ≤ 8 subcuencas;
beyond that each section shows a resumen line and the complete table at the
END of the section. ``% Alto+Crítico`` figures carry the threshold tag
wherever they appear (S12): ``leyenda-55`` since #738 — the count starts at
the legend's Alto edge, with the Alto/Crítico split stored since PR 5;
per-class producer phrases remain gated on the S7 monotonicity verdict
(PR 5 T2), so this builder ships none.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape as _esc

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
)

from app.shared.pdf.base import (
    BrandingInfo,
    BrandedPDF,
    build_data_table,
    build_info_table,
    get_pdf_styles,
)
from app.shared.pdf.format_es import fmt_ha, fmt_num, fmt_pct

# A4 (210 mm) minus BrandedPDF's 1.5 cm side margins — the width every table
# and map scales to (same constant discipline as builders_zoning).
ANCHO_CONTENIDO_MM = (A4[0] - 2 * 1.5 * cm) / mm

# S6: inline per-subcuenca tables up to this many zonas; beyond it, resumen +
# complete table at the end of each section.
ZONAS_INLINE_MAX = 8

_MESES = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]

# One-sentence "qué mide" per S6 — honest descriptions of the stored
# composites (TWI/HAND/curvature/TPI for flood; flow accumulation/HAND/
# drainage proximity for drainage need), not marketing.
_FRASE_RIESGO = (
    "Índice de 0 a 100 que combina humedad topográfica (TWI), altura sobre la "
    "red de drenaje (HAND), curvatura y posición en la ladera (TPI) para "
    "estimar la propensión del terreno a acumular agua en exceso."
)
_FRASE_DRENAJE = (
    "Índice de 0 a 100 que combina acumulación de flujo, altura sobre el "
    "drenaje y proximidad a la red de drenaje para estimar la necesidad de "
    "obras de drenaje en cada superficie."
)
_FRASE_SUELOS = (
    "Carta de suelos 1:50.000 (IDECOR 2025): unidades cartográficas con sus "
    "series constituyentes, clase de capacidad de uso, índice de "
    "productividad (IP) y agua útil a 1 y 2 m de profundidad."
)
_FRASE_SUELOS_SIN_DATOS = (
    "La carta de suelos 1:50.000 de IDECOR no está cargada en este "
    "despliegue: ejecutá el ETL app.domains.geo.etl.idecor_suelos_50mil "
    "para habilitar la sección."
)
_FRASE_COBERTURA = (
    "Cobertura y uso del suelo (IDECOR 2024/2025, 10 m, 21 clases) y "
    "cultivos estivales de las campañas 22/23 a 24/25 (IDECOR/INTA)."
)
_FRASE_COBERTURA_SIN_DATOS = (
    "Los rasters de cobertura IDECOR no están registrados en este "
    "despliegue: ejecutá el ETL app.domains.geo.etl.idecor_coberturas "
    "para habilitar la sección."
)
_FUENTE_COBERTURA = (
    "Fuente: IDECOR · Mapas Córdoba — cobertura_uso_2024_2025 y "
    "coberturas_estivales 2223/2324/2425 (WCS/WMS) · licencia CC BY 4.0."
)
_FRASE_LLUVIA = "Normales mensuales de precipitación (mm) promediadas sobre la selección."

_NOTA_LEGACY70 = (
    "El porcentaje Alto+Crítico usa el umbral histórico de 70 puntos "
    "(umbral_alto_critico: legacy70) hasta su recalibración; los cortes de "
    "clase del mapa y de las tablas no dependen de ese umbral."
)
_NOTA_LEYENDA55 = (
    "El porcentaje Alto+Crítico se cuenta desde el inicio de la clase Alto "
    "de la leyenda (55 puntos; umbral_alto_critico: leyenda-55): Alto "
    "55–75 y Crítico 75 o más, la misma leyenda del mapa y de las tablas."
)
_NOTA_VALIDACION = (
    "El índice de riesgo es puramente topográfico: no incorpora lluvia ni "
    "historial de inundación. La tabla de validación lo contrasta contra "
    "agua observada (MNDWI ≥ 0,1 sobre la escena ancla; Sentinel-1 marcado "
    "aparte cuando no hubo óptica) a escala de toda la zona del consorcio, "
    "con la lluvia CHIRPS de los 30 días previos al evento. Nubes, escenas "
    "tardías y lagunas o arrozales permanentes pueden inflar o recortar el "
    "agua observada; el desglose por clase no es un perímetro de inundación."
)
_AVISO_PIXEL = (
    "Los valores de lluvia provienen de un raster de píxeles de ~5 km: son "
    "normales climáticas regionales, no mediciones locales."
)
_DESCARGO = (
    "Este informe es una herramienta de apoyo a la decisión. No reemplaza el "
    "relevamiento de campo ni el criterio técnico profesional. Las "
    "superficies son estimaciones derivadas de los productos con la "
    "resolución listada en Fuentes y heredan su fecha de cálculo."
)


# ── KPIs (shared by the builder and the task's ``resultado``) ────────────────


def _pct_clases(dataset: dict[str, Any] | None, etiquetas: tuple[str, ...]) -> float | None:
    """Sum of ``pct`` over the clases whose label is in ``etiquetas``.

    ``None`` when the dataset has no coverage at all — never 0, which would
    read as "medido y despreciable" when the truth is "no medido".
    """
    if not dataset or dataset.get("cobertura") == "sin_cobertura":
        return None
    clases = dataset.get("clases") or []
    if not clases:
        return None
    return round(sum(float(c.get("pct") or 0.0) for c in clases if c.get("clase") in etiquetas), 2)


def calcular_kpis(datos: dict[str, Any]) -> dict[str, float | None]:
    """The four Resumen KPIs — pure over ``datos`` so task and PDF agree."""
    return {
        "pct_riesgo_alto_critico": _pct_clases(datos.get("riesgo"), ("Alto", "Crítico")),
        "pct_drenaje_alto_critico": _pct_clases(datos.get("drenaje"), ("Alto", "Crítico")),
        "pct_suelos_i_iii": _pct_clases(datos.get("suelos"), ("I", "II", "III")),
        "lluvia_anual_mm": (datos.get("lluvia") or {}).get("anual_mm"),
    }


# ── helpers ──────────────────────────────────────────────────────────────────


def _fecha_es_ar(iso: str | None) -> str:
    """``generado_el`` ISO → "18/11/2026 14:05" in consorcio local time."""
    if not iso:
        return "—"
    try:
        momento = datetime.fromisoformat(iso)
    except ValueError:
        return str(iso)
    try:
        from zoneinfo import ZoneInfo

        momento = momento.astimezone(ZoneInfo("America/Argentina/Cordoba"))
    except Exception:  # noqa: BLE001 — zoneinfo data missing: show UTC as-is
        pass
    return momento.strftime("%d/%m/%Y %H:%M")


def _imagen_mapa(png: bytes, *, alto_max_mm: float = 92.0) -> Image | None:
    """PNG bytes → content-width Image flowable, aspect preserved."""
    if not png:
        return None
    try:
        ancho_px, alto_px = ImageReader(io.BytesIO(png)).getSize()
    except Exception:  # noqa: BLE001 — a broken map degrades, never fails
        return None
    if ancho_px <= 0 or alto_px <= 0:
        return None
    ancho_mm = ANCHO_CONTENIDO_MM
    alto_mm = ancho_mm * alto_px / ancho_px
    if alto_mm > alto_max_mm:
        alto_mm = alto_max_mm
        ancho_mm = alto_mm * ancho_px / alto_px
    return Image(io.BytesIO(png), width=ancho_mm * mm, height=alto_mm * mm)


def _tabla_clases(
    dataset: dict[str, Any] | None,
    orden: list[dict],
    branding: BrandingInfo,
    *,
    titulo_total: str = "Total cubierto por la capa",
) -> list[Flowable]:
    """clase · ha · % table in ``orden`` (class_breaks order), plus totals.

    A "sin cobertura" row closes the gap to the selection's own area, so the
    table's grand total IS ``area_ha`` — the reader can reconcile the two.
    """
    flowables: list[Flowable] = []
    clases = (dataset or {}).get("clases") or []
    if (dataset or {}).get("cobertura") == "sin_cobertura" or not clases:
        flowables.append(
            Paragraph(
                "La capa no tiene cobertura sobre la selección.", get_pdf_styles(branding)["small"]
            )
        )
        return flowables

    # clases non-empty ⇒ dataset is a real dict here; narrow once for mypy.
    assert dataset is not None

    por_clase = {c["clase"]: c for c in clases}
    filas: list[list[str]] = []
    cubierto = 0.0
    for cfg in orden:
        fila = por_clase.get(str(cfg["label"]))
        if fila is None:
            filas.append([str(cfg["label"]), fmt_ha(0.0), fmt_pct(0.0)])
            continue
        cubierto += float(fila.get("ha") or 0.0)
        filas.append([str(cfg["label"]), fmt_ha(fila.get("ha")), fmt_pct(fila.get("pct"))])

    area_ha = (
        float(dataset["area_ha"]) if dataset.get("area_ha") is not None else 0.0
    )  # injected by the task
    sin_cobertura = max(0.0, area_ha - cubierto)
    filas.append(
        [titulo_total, fmt_ha(cubierto), fmt_pct(cubierto / area_ha * 100.0 if area_ha else 0.0)]
    )
    if sin_cobertura > 0.05:
        filas.append(
            [
                "Sin cobertura de la capa",
                fmt_ha(sin_cobertura),
                fmt_pct(sin_cobertura / area_ha * 100.0 if area_ha else 0.0),
            ]
        )
    filas.append(["Total de la selección", fmt_ha(area_ha), fmt_pct(100.0)])

    flowables.append(
        build_data_table(
            ["Clase", "Superficie (ha)", "% de la selección"],
            filas,
            branding,
        )
    )
    return flowables


def _tabla_desglose(
    desglose: list[dict[str, Any]],
    columnas: list[tuple[str, str, Any]],
    branding: BrandingInfo,
    *,
    encabezados: list[str] | None = None,
) -> Table:
    """Per-subcuenca table with column specs ``(clave, tipo, formateador)``."""
    encabezados = encabezados or [c[0] for c in columnas]
    filas: list[list[str]] = []
    for fila in desglose:
        celdas = []
        for _encabezado, clave, formateador in columnas:
            valor = fila.get(clave)
            celdas.append("—" if valor is None else str(formateador(valor)))
        filas.append(celdas)
    return build_data_table(encabezados, filas, branding)


def _nota_resumen_zonas(
    desglose: list[dict[str, Any]] | None, estilos: dict[str, Any]
) -> Paragraph | None:
    """S6's >8 rule note: resumen inline, complete tables at section end."""
    if not desglose or len(desglose) <= ZONAS_INLINE_MAX:
        return None
    return Paragraph(
        f"{len(desglose)} subcuencas en la selección: las tablas de cada "
        f"sección listan primero las {ZONAS_INLINE_MAX} mayores y el detalle "
        "completo va al final de la sección.",
        estilos["small"],
    )


def _top_zonas(desglose: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(desglose) <= ZONAS_INLINE_MAX:
        return desglose
    return sorted(desglose, key=lambda z: float(z.get("ha") or 0.0), reverse=True)[
        :ZONAS_INLINE_MAX
    ]


# ── monthly bar chart (ReportLab primitives only — S7: no chart lib) ─────────


def _techo_nice(valor_max: float) -> float:
    """Axis ceiling from the 1/2/5 ladder; 1.0 minimum so empty ≠ crash."""
    if valor_max <= 0:
        return 1.0
    exponente = 0
    while valor_max > 10.0:
        valor_max /= 10.0
        exponente += 1
    while valor_max <= 1.0:
        valor_max *= 10.0
        exponente -= 1
    base = next(b for b in (1.0, 2.0, 5.0, 10.0) if valor_max <= b)
    return base * 10**exponente


class GraficoBarrasMeses(Flowable):
    """Twelve monthly normals as bars, drawn with raw canvas primitives."""

    def __init__(
        self, serie: list[dict[str, Any]], branding: BrandingInfo, ancho_mm: float
    ) -> None:
        super().__init__()
        self.serie = sorted(serie, key=lambda m: int(m.get("mes") or 0))
        self.color = colors.HexColor(branding.color_primario)
        self.ancho = ancho_mm * mm
        self.alto = 62 * mm

    def wrap(self, ancho_disponible: float, _alto: float | None = None) -> tuple[float, float]:
        return self.ancho, self.alto

    def draw(self) -> None:
        from app.shared.pdf.base import _register_fonts

        c = self.canv
        fuente = _register_fonts()
        izq, abajo, alto_eje = 15 * mm, 9 * mm, 6 * mm
        plot_ancho = self.ancho - izq - 3 * mm
        plot_alto = self.alto - abajo - alto_eje

        valores = [float(m.get("mm") or 0.0) for m in self.serie]
        techo = _techo_nice(max(valores) if valores else 0.0)
        paso = plot_ancho / max(len(valores), 1)
        ancho_barra = paso * 0.62

        c.saveState()
        # Gridlines + y labels (es-AR through fmt_num — S12).
        for i in range(5):
            y = abajo + plot_alto * i / 4
            c.setStrokeColor(colors.Color(0.85, 0.85, 0.85))
            c.setLineWidth(0.4)
            c.line(izq, y, izq + plot_ancho, y)
            c.setFont(fuente, 7)
            c.setFillColor(colors.grey)
            c.drawRightString(izq - 2 * mm, y - 2, fmt_num(techo * i / 4, 0))
        # Axes.
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.8)
        c.line(izq, abajo, izq, abajo + plot_alto)
        c.line(izq, abajo, izq + plot_ancho, abajo)
        c.setFillColor(colors.grey)
        c.setFont(fuente, 7)
        c.drawString(izq, abajo + plot_alto + 2 * mm, "mm")

        for i, mes in enumerate(self.serie):
            valor = float(mes.get("mm") or 0.0)
            x = izq + paso * i + (paso - ancho_barra) / 2
            alto_barra = plot_alto * valor / techo
            c.setFillColor(self.color)
            c.rect(x, abajo, ancho_barra, alto_barra, fill=1, stroke=0)
            c.setFillColor(colors.black)
            c.setFont(fuente, 6.5)
            c.drawCentredString(
                x + ancho_barra / 2, abajo + alto_barra + 1.5 * mm, fmt_num(valor, 0)
            )
            c.setFillColor(colors.grey)
            c.drawCentredString(
                x + ancho_barra / 2, abajo - 4.5 * mm, _MESES[int(mes.get("mes") or 1) - 1]
            )
        c.restoreState()


# ── sections ─────────────────────────────────────────────────────────────────


def _nota_umbral(datos: dict[str, Any]) -> str | None:
    """Threshold note for the % Alto+Crítico figures, by stored tag.

    ``legacy70`` only appears on rows generated before #738 — kept so an old
    cached PDF re-render still explains itself instead of printing a tag it
    no longer understands.
    """
    etiqueta = str(datos.get("umbral_alto_critico") or "")
    if etiqueta == "leyenda-55":
        return _NOTA_LEYENDA55
    if etiqueta == "legacy70":
        return _NOTA_LEGACY70
    return None


def _seccion_resumen(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
    mapas: dict[str, bytes],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("1. Resumen", estilos["subtitle"])]
    kpis = calcular_kpis(datos)

    flowables.append(
        build_info_table(
            [
                ("Nombre del informe", _esc(str(datos.get("nombre") or "—"))),
                ("Fecha de generación", _fecha_es_ar(datos.get("generado_el"))),
                ("Superficie total", f"{fmt_ha(datos.get('area_ha'))} ha"),
                ("Subcuencas", str(datos.get("cantidad_zonas") or 0)),
                ("Cuencas", ", ".join(datos.get("cuencas") or []) or "—"),
            ],
            branding,
        )
    )
    flowables.append(Spacer(1, 3 * mm))

    mapa = _imagen_mapa(mapas.get("ubicacion") or b"")
    if mapa is not None:
        flowables.append(KeepTogether([mapa, Spacer(1, 1 * mm)]))
        flowables.append(
            Paragraph(
                "Ubicación de la selección: contorno negro (selección), gris "
                "(límite de cada subcuenca).",
                estilos["small"],
            )
        )
        flowables.append(Spacer(1, 3 * mm))
    else:
        flowables.append(Paragraph("Mapa de ubicación no disponible.", estilos["small"]))
        flowables.append(Spacer(1, 3 * mm))

    filas_kpi = [
        (
            "Riesgo hídrico Alto+Crítico",
            fmt_pct(kpis["pct_riesgo_alto_critico"])
            if kpis["pct_riesgo_alto_critico"] is not None
            else "— (sin cobertura)",
        ),
        (
            "Necesidad de drenaje Alto+Crítico",
            fmt_pct(kpis["pct_drenaje_alto_critico"])
            if kpis["pct_drenaje_alto_critico"] is not None
            else "— (sin cobertura)",
        ),
        (
            "Suelos clases I–III",
            fmt_pct(kpis["pct_suelos_i_iii"])
            if kpis["pct_suelos_i_iii"] is not None
            else "— (sin cobertura)",
        ),
        (
            "Lluvia anual media",
            f"{fmt_num(kpis['lluvia_anual_mm'])} mm"
            if kpis["lluvia_anual_mm"] is not None
            else "— (sin cobertura)",
        ),
    ]
    tabla_kpi = build_info_table(filas_kpi, branding, col_widths=(8.5 * cm, 8.5 * cm))
    flowables.append(tabla_kpi)
    nota_umbral = _nota_umbral(datos)
    if nota_umbral is not None:
        flowables.append(Spacer(1, 1.5 * mm))
        flowables.append(Paragraph(nota_umbral, estilos["small"]))
    flowables.append(Spacer(1, 3 * mm))

    desglose = datos.get("desglose")
    if desglose:
        flowables.append(Paragraph("Ranking de subcuencas por superficie", estilos["body"]))
        nota = _nota_resumen_zonas(desglose, estilos)
        if nota is not None:
            flowables.append(nota)
        ranking = sorted(desglose, key=lambda z: float(z.get("ha") or 0.0), reverse=True)[
            :ZONAS_INLINE_MAX
        ]
        flowables.append(
            _tabla_desglose(
                ranking,
                [
                    ("Subcuenca", "nombre", str),
                    ("Cuenca", "cuenca", str),
                    ("Superficie (ha)", "ha", fmt_ha),
                    ("% Alto+Crítico riesgo", "pct_alto_critico", lambda v: fmt_pct(v)),
                ],
                branding,
            )
        )
        if len(desglose) > ZONAS_INLINE_MAX:
            flowables.append(
                Paragraph(
                    f"Se muestran las {ZONAS_INLINE_MAX} mayores de {len(desglose)}; "
                    "el detalle completo está al final de las secciones 2, 3, 4 y 6.",
                    estilos["small"],
                )
            )
    else:
        flowables.append(
            Paragraph("Informe generado sin desglose por subcuenca.", estilos["small"])
        )
    flowables.append(PageBreak())
    return flowables


def _tabla_validacion_riesgo(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    """PR 5 (S1/S4): observed water per flood_risk class, per anchor event.

    One row per event, one % con agua column per legend class, plus the
    event's 30-day CHIRPS total. The figures are ZONE-scale (the whole
    consorcio zone — the validation is of the index), which the título says
    out loud; a per-selection clip is not derivable from these rows and is
    never invented.
    """
    from app.domains.geo.class_breaks import RANGE_CONFIGS

    dataset = datos.get("riesgo_validacion") or {}
    eventos = dataset.get("eventos") or []
    if not eventos:
        return []

    clases_leyenda = [str(cfg["label"]) for cfg in RANGE_CONFIGS["flood_risk"]]
    flowables: list[Flowable] = [
        Paragraph("Validación contra agua observada (eventos ancla)", estilos["body"]),
        Spacer(1, 1 * mm),
    ]
    filas: list[list[str]] = []
    for evento in eventos:
        por_clase = evento.get("clases") or {}
        celdas = [
            f"{evento.get('evento_key')} ({evento.get('fecha')})",
            str(evento.get("sensor") or "—"),
        ]
        for clase in clases_leyenda:
            fila_clase = por_clase.get(clase)
            celdas.append(fmt_pct(fila_clase["pct_con_agua"]) if fila_clase else "—")
        lluvia = evento.get("lluvia_30d_mm")
        celdas.append(f"{fmt_num(lluvia)} mm" if lluvia is not None else "—")
        filas.append(celdas)

    flowables.append(
        build_data_table(
            [
                "Evento (fecha)",
                "Sensor",
                "% agua Bajo",
                "% agua Medio",
                "% agua Alto",
                "% agua Crítico",
                "Lluvia 30 d",
            ],
            filas,
            branding,
        )
    )
    flowables.append(Spacer(1, 1 * mm))
    flowables.append(Paragraph(_NOTA_VALIDACION, estilos["small"]))
    flowables.append(Spacer(1, 3 * mm))
    return flowables


def _seccion_clase(
    numero_titulo: str,
    frase: str,
    dataset: dict[str, Any] | None,
    orden: list[dict],
    mapa: bytes | None,
    mapa_caption: str,
    notas_metodo: list[str],
    desglose: list[dict[str, Any]] | None,
    desglose_columnas: list[tuple[str, str, Any]] | None,
    branding: BrandingInfo,
    estilos: dict[str, Any],
    extra: list[Flowable] | None = None,
) -> list[Flowable]:
    """Sections 2 and 3 share this shape (S6: 'igual estructura').

    ``extra`` is section-2-only content (PR 5): the anchor-event validation
    table, appended after the desglose so the class table and the desglose
    keep their fixed order.
    """
    flowables: list[Flowable] = [Paragraph(numero_titulo, estilos["subtitle"])]
    flowables.append(Paragraph(frase, estilos["body"]))
    flowables.append(Spacer(1, 2 * mm))

    imagen = _imagen_mapa(mapa or b"")
    if imagen is not None:
        flowables.append(KeepTogether([imagen, Spacer(1, 1 * mm)]))
        flowables.append(Paragraph(mapa_caption, estilos["small"]))
    else:
        flowables.append(Paragraph("Mapa no disponible para esta capa.", estilos["small"]))
    flowables.append(Spacer(1, 3 * mm))

    flowables.extend(_tabla_clases(dataset, orden, branding))
    flowables.append(Spacer(1, 2 * mm))

    for nota in notas_metodo:
        flowables.append(Paragraph(nota, estilos["small"]))
    flowables.append(Spacer(1, 3 * mm))

    if desglose and desglose_columnas:
        nota_zonas = _nota_resumen_zonas(desglose, estilos)
        if nota_zonas is not None:
            flowables.append(nota_zonas)
            flowables.append(Spacer(1, 1 * mm))
        flowables.append(Paragraph("Desglose por subcuenca", estilos["body"]))
        flowables.append(Spacer(1, 1 * mm))
        flowables.append(_tabla_desglose(_top_zonas(desglose), desglose_columnas, branding))
        if len(desglose) > ZONAS_INLINE_MAX:
            flowables.append(Spacer(1, 2 * mm))
            flowables.append(
                Paragraph(f"Detalle completo ({len(desglose)} subcuencas):", estilos["body"])
            )
            flowables.append(Spacer(1, 1 * mm))
            flowables.append(_tabla_desglose(desglose, desglose_columnas, branding))
    if extra:
        flowables.append(Spacer(1, 2 * mm))
        flowables.extend(extra)
    flowables.append(PageBreak())
    return flowables


def _seccion_suelos(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("4. Suelos", estilos["subtitle"])]

    dataset = datos.get("suelos")
    if not dataset or not dataset.get("unidades"):
        # S7: a deployment without the IDECOR ETL still gets its informe —
        # the section says so and moves on.
        flowables.append(Paragraph(_FRASE_SUELOS_SIN_DATOS, estilos["body"]))
        flowables.append(Spacer(1, 3 * mm))
        desglose = datos.get("desglose")
        if desglose:
            flowables.append(
                _tabla_desglose(
                    desglose,
                    [
                        ("Subcuenca", "nombre", str),
                        ("Cuenca", "cuenca", str),
                        ("Superficie (ha)", "ha", fmt_ha),
                    ],
                    branding,
                )
            )
        flowables.append(PageBreak())
        return flowables

    flowables.append(Paragraph(_FRASE_SUELOS, estilos["body"]))
    flowables.append(Spacer(1, 2 * mm))

    # Main table: one row per cartographic unit (S3: símbolo · series ·
    # clase · IP · agua útil · ha · %). Wide units list → the 12 largest
    # plus a count note, so the section stays inside its page budget.
    unidades = dataset["unidades"]
    mostradas = unidades[:12]
    filas_unidades: list[list[str]] = []
    for unidad in mostradas:
        filas_unidades.append(
            [
                _esc(str(unidad.get("simbolo") or "—")),
                _esc(str(unidad.get("series") or "—")),
                _esc(str(unidad.get("clase") or "—")),
                str(unidad.get("ip") if unidad.get("ip") is not None else "—"),
                str(unidad.get("au_1m") if unidad.get("au_1m") is not None else "—"),
                str(unidad.get("au_2m") if unidad.get("au_2m") is not None else "—"),
                fmt_ha(unidad.get("ha")),
                fmt_pct(unidad.get("pct")),
            ]
        )
    cubierto = sum(float(u.get("ha") or 0.0) for u in unidades)
    area_ha = float(dataset.get("area_ha") or 0.0)
    filas_unidades.append(
        [
            "Total con carta 1:50.000",
            "",
            "",
            "",
            "",
            "",
            fmt_ha(cubierto),
            fmt_pct(cubierto / area_ha * 100.0 if area_ha else 0.0),
        ]
    )
    sin_cobertura = max(0.0, area_ha - cubierto)
    if sin_cobertura > 0.05:
        filas_unidades.append(
            [
                "Sin carta 1:50.000",
                "",
                "",
                "",
                "",
                "",
                fmt_ha(sin_cobertura),
                fmt_pct(sin_cobertura / area_ha * 100.0 if area_ha else 0.0),
            ]
        )
    filas_unidades.append(
        ["Total de la selección", "", "", "", "", "", fmt_ha(area_ha), fmt_pct(100.0)]
    )

    flowables.append(
        build_data_table(
            [
                "Unidad",
                "Series (%)",
                "Clase",
                "IP",
                "AU 1 m (mm)",
                "AU 2 m (mm)",
                "Superficie (ha)",
                "% de la selección",
            ],
            filas_unidades,
            branding,
        )
    )
    if len(unidades) > len(mostradas):
        flowables.append(Spacer(1, 1 * mm))
        flowables.append(
            Paragraph(
                f"Se listan las {len(mostradas)} mayores de {len(unidades)} "
                "unidades cartográficas.",
                estilos["small"],
            )
        )
    flowables.append(Spacer(1, 2 * mm))

    ip = dataset.get("ip_ponderado")
    partes_resumen: list[str] = []
    if ip is not None:
        clases_i_iii = _pct_clases(dataset, ("I", "II", "III"))
        partes_resumen.append(f"IP ponderado por superficie: {fmt_num(ip, 1)}.")
        if clases_i_iii is not None:
            partes_resumen.append(f"Clases I–III: {fmt_pct(clases_i_iii)} de la selección.")
    flowables.append(Paragraph(" ".join(partes_resumen), estilos["body"]))
    flowables.append(
        Paragraph(
            "AU = agua útil estimada por el INTA a la profundidad indicada. "
            "Fuente: IDECOR · carta de suelos 1:50.000 (2025), WFS "
            "idecor:carta_suelo_50mil_2025 · licencia CC BY 4.0.",
            estilos["small"],
        )
    )
    flowables.append(Spacer(1, 3 * mm))

    # Per-subcuenca breakdown: dominant class + weighted IP + coverage of
    # the carta inside each zone (S10).
    por_zona = dataset.get("por_zona") or {}
    desglose = datos.get("desglose")
    if desglose:
        nota = _nota_resumen_zonas(desglose, estilos)
        if nota is not None:
            flowables.append(nota)
            flowables.append(Spacer(1, 1 * mm))
        flowables.append(Paragraph("Desglose por subcuenca", estilos["body"]))
        flowables.append(Spacer(1, 1 * mm))
        top = _top_zonas(desglose)

        def _fila_suelos_zona(fila: dict[str, Any]) -> list[str]:
            extra = por_zona.get(str(fila.get("zona_id")) or "") or {}
            return [
                str(fila.get("nombre") or "—"),
                str(fila.get("cuenca") or "—"),
                fmt_ha(fila.get("ha")),
                str(extra.get("clase_dominante") or "—"),
                fmt_num(extra["ip_ponderado"], 1) if extra.get("ip_ponderado") is not None else "—",
                fmt_pct(extra["cobertura_pct"]) if extra.get("cobertura_pct") is not None else "—",
            ]

        encabezados = [
            "Subcuenca",
            "Cuenca",
            "Superficie (ha)",
            "Clase dominante",
            "IP ponderado",
            "% con carta",
        ]
        filas_zonas = [_fila_suelos_zona(f) for f in top]
        flowables.append(build_data_table(encabezados, filas_zonas, branding))
        if len(desglose) > ZONAS_INLINE_MAX:
            flowables.append(Spacer(1, 2 * mm))
            flowables.append(
                Paragraph(f"Detalle completo ({len(desglose)} subcuencas):", estilos["body"])
            )
            flowables.append(Spacer(1, 1 * mm))
            flowables.append(
                build_data_table(encabezados, [_fila_suelos_zona(f) for f in desglose], branding)
            )
    flowables.append(PageBreak())
    return flowables


def _seccion_cobertura(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("5. Cobertura y cultivos", estilos["subtitle"])]

    dataset = datos.get("cobertura")
    if not dataset or not dataset.get("clases"):
        flowables.append(Paragraph(_FRASE_COBERTURA_SIN_DATOS, estilos["body"]))
        flowables.append(PageBreak())
        return flowables

    flowables.append(Paragraph(_FRASE_COBERTURA, estilos["body"]))
    flowables.append(Spacer(1, 2 * mm))

    # Uso 2024/2025: clase · ha · % (S4). The dataset's own ha order.
    orden = [{"label": c["clase"]} for c in dataset["clases"]]
    flowables.extend(_tabla_clases(dataset, orden, branding, titulo_total="Total con cobertura"))
    flowables.append(Spacer(1, 2 * mm))

    pct_agua = dataset.get("pct_agua_estacional")
    etiqueta_agua = dataset.get("etiqueta_agua_estacional") or "Cuerpo de agua estacional"
    if pct_agua is not None:
        flowables.append(
            Paragraph(
                f"{_esc(etiqueta_agua)} (clase 9): {fmt_pct(pct_agua)} de la selección.",
                estilos["body"],
            )
        )
    flowables.append(Spacer(1, 3 * mm))

    # Campañas estivales: one class table per campaign, plus the
    # cultivated summary line (S4 "recurrencia" follows below).
    flowables.append(Paragraph("Cultivos estivales por campaña", estilos["body"]))
    for campania in dataset.get("campanias") or []:
        clases = campania.get("clases") or []
        if not clases:
            continue
        filas = [[str(c["clase"]), fmt_ha(c.get("ha")), fmt_pct(c.get("pct"))] for c in clases]
        filas.append(
            [
                "Total cultivado",
                fmt_ha(campania.get("ha_cultivo")),
                fmt_pct(campania.get("pct_cultivo")),
            ]
        )
        flowables.append(Spacer(1, 1 * mm))
        flowables.append(Paragraph(f"Campaña {campania['campania']}", estilos["body"]))
        flowables.append(
            build_data_table(["Clase", "Superficie (ha)", "% de la selección"], filas, branding)
        )
    flowables.append(Spacer(1, 3 * mm))

    # Recurrencia del cultivo de verano across the three campaigns (S4).
    recurrencia = dataset.get("recurrencia")
    if recurrencia:
        etiquetas_rec = {
            "3_campanias_ha": "Con cultivo en las 3 campañas",
            "2_campanias_ha": "Con cultivo en 2 campañas",
            "1_campanias_ha": "Con cultivo en 1 campaña",
            "0_campanias_ha": "Sin cultivo estival en ninguna",
        }
        filas_rec = [
            [etiqueta, fmt_ha(recurrencia.get(clave))] for clave, etiqueta in etiquetas_rec.items()
        ]
        flowables.append(Paragraph("Recurrencia del cultivo de verano", estilos["body"]))
        flowables.append(Spacer(1, 1 * mm))
        flowables.append(build_data_table(["Situación", "Superficie (ha)"], filas_rec, branding))
        flowables.append(
            Paragraph(
                "Píxeles de 10 m clasificados por campaña; un píxel cuenta para "
                "una campaña cuando esa campaña lo mapeó como cultivado.",
                estilos["small"],
            )
        )
    flowables.append(Spacer(1, 3 * mm))

    # Desglose por subcuenca (S10): % cultivo + % soja última campaña.
    por_zona = dataset.get("por_zona") or {}
    desglose = datos.get("desglose")
    if desglose and por_zona:
        nota = _nota_resumen_zonas(desglose, estilos)
        if nota is not None:
            flowables.append(nota)
            flowables.append(Spacer(1, 1 * mm))
        flowables.append(Paragraph("Desglose por subcuenca", estilos["body"]))
        flowables.append(Spacer(1, 1 * mm))
        columnas: list[tuple[str, str, Any]] = [
            ("Subcuenca", "nombre", str),
            ("Cuenca", "cuenca", str),
            ("Superficie (ha)", "ha", fmt_ha),
        ]
        filas_zonas: list[list[str]] = []
        for fila in _top_zonas(desglose):
            extra = por_zona.get(str(fila.get("zona_id")) or "") or {}
            celdas = [
                "—" if fila.get(clave) is None else str(fmt(fila.get(clave)))
                for _enc, clave, fmt in columnas
            ]
            celdas.append(
                fmt_pct(extra["pct_cultivo"]) if extra.get("pct_cultivo") is not None else "—"
            )
            celdas.append(fmt_pct(extra["pct_soja"]) if extra.get("pct_soja") is not None else "—")
            filas_zonas.append(celdas)
        flowables.append(
            build_data_table(
                [
                    "Subcuenca",
                    "Cuenca",
                    "Superficie (ha)",
                    "% cultivo (uso)",
                    "% soja (última campaña)",
                ],
                filas_zonas,
                branding,
            )
        )
    flowables.append(Spacer(1, 2 * mm))
    flowables.append(Paragraph(_FUENTE_COBERTURA, estilos["small"]))
    flowables.append(PageBreak())
    return flowables


def _seccion_lluvia(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("6. Lluvia", estilos["subtitle"])]
    flowables.append(Paragraph(_FRASE_LLUVIA, estilos["body"]))
    flowables.append(Spacer(1, 2 * mm))

    lluvia = datos.get("lluvia") or {}
    serie = lluvia.get("serie") or []
    anual = lluvia.get("anual_mm")
    if serie and len(serie) >= 12:
        flowables.append(GraficoBarrasMeses(serie, branding, ANCHO_CONTENIDO_MM))
        flowables.append(Spacer(1, 2 * mm))
        partes = [f"Total anual medio: {fmt_num(anual)} mm."] if anual is not None else []
        partes += [
            f"Fuente: {_esc(str(lluvia.get('fuente') or '—'))}.",
            f"Período de las normales: {_esc(str(lluvia.get('periodo') or '—'))}.",
        ]
        flowables.append(Paragraph(" ".join(partes), estilos["body"]))
    else:
        flowables.append(
            Paragraph(
                "Sin cobertura del producto de normales de precipitación sobre la selección.",
                estilos["body"],
            )
        )
    flowables.append(Spacer(1, 2 * mm))
    flowables.append(Paragraph(_AVISO_PIXEL, estilos["small"]))
    flowables.append(Spacer(1, 3 * mm))

    desglose = datos.get("desglose")
    if desglose:
        nota = _nota_resumen_zonas(desglose, estilos)
        if nota is not None:
            flowables.append(nota)
            flowables.append(Spacer(1, 1 * mm))
        flowables.append(Paragraph("Desglose por subcuenca", estilos["body"]))
        flowables.append(Spacer(1, 1 * mm))
        columnas = [
            ("Subcuenca", "nombre", str),
            ("Cuenca", "cuenca", str),
            ("Superficie (ha)", "ha", fmt_ha),
            ("Lluvia anual media (mm)", "lluvia_anual_mm", fmt_num),
        ]
        flowables.append(_tabla_desglose(_top_zonas(desglose), columnas, branding))
        if len(desglose) > ZONAS_INLINE_MAX:
            flowables.append(Spacer(1, 2 * mm))
            flowables.append(
                Paragraph(f"Detalle completo ({len(desglose)} subcuencas):", estilos["body"])
            )
            flowables.append(Spacer(1, 1 * mm))
            flowables.append(_tabla_desglose(desglose, columnas, branding))
    flowables.append(PageBreak())
    return flowables


def _seccion_canales(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("7. Canales", estilos["subtitle"])]

    dataset = datos.get("canales")
    if not dataset:
        flowables.append(
            Paragraph(
                "Los datos de canales no están disponibles en este despliegue.",
                estilos["body"],
            )
        )
        flowables.append(PageBreak())
        return flowables

    km_mil = dataset.get("km_por_mil_ha")
    filas_kpi = [
        ("Canales relevados en el área", f"{fmt_num(dataset.get('km_relevados'), 2)} km"),
        ("Canales propuestos en el área", f"{fmt_num(dataset.get('km_propuestos'), 2)} km"),
        ("Total de canales", f"{fmt_num(dataset.get('km_total'), 2)} km"),
        (
            "Densidad de canales",
            f"{fmt_num(km_mil, 2)} km cada 1.000 ha" if km_mil is not None else "—",
        ),
    ]
    flowables.append(build_info_table(filas_kpi, branding, col_widths=(8.5 * cm, 8.5 * cm)))
    flowables.append(Spacer(1, 3 * mm))

    cruces = dataset.get("cruces_camino") or {}
    conflictos = dataset.get("puntos_conflicto") or {}
    if cruces or conflictos:
        flowables.append(Paragraph("Cruces y conflictos en el área", estilos["body"]))
        flowables.append(Spacer(1, 1 * mm))
        filas_cruces = [
            ("Cruces canal / camino", str(cruces.get("canal", 0))),
            ("Cruces drenaje natural / camino", str(cruces.get("flujo_natural", 0))),
            ("Puntos de conflicto (severidad alta)", str(conflictos.get("alta", 0))),
            ("Puntos de conflicto (severidad media)", str(conflictos.get("media", 0))),
            ("Puntos de conflicto (severidad baja)", str(conflictos.get("baja", 0))),
        ]
        flowables.append(build_info_table(filas_cruces, branding, col_widths=(11 * cm, 6 * cm)))
    else:
        flowables.append(
            Paragraph(
                "Sin cruces con caminos ni puntos de conflicto registrados dentro del área.",
                estilos["body"],
            )
        )
    flowables.append(Spacer(1, 3 * mm))

    if dataset.get("sin_datos"):
        flowables.append(
            Paragraph(
                "El área no intersecta canales relevados ni propuestos del "
                "consorcio; las cifras anteriores son ceros reales, no falta de datos.",
                estilos["small"],
            )
        )
        flowables.append(Spacer(1, 2 * mm))
    flowables.append(
        Paragraph(
            "Longitudes medidas sobre el trazado clip por el área (EPSG:32720). "
            "Fuente: relevamiento del consorcio (canal_consorcio) y cruce_camino / "
            "puntos_conflicto del pipeline.",
            estilos["small"],
        )
    )
    flowables.append(Spacer(1, 3 * mm))

    por_zona = dataset.get("por_zona") or {}
    desglose = datos.get("desglose")
    if desglose and por_zona:
        nota = _nota_resumen_zonas(desglose, estilos)
        if nota is not None:
            flowables.append(nota)
            flowables.append(Spacer(1, 1 * mm))
        flowables.append(Paragraph("Desglose por subcuenca", estilos["body"]))
        flowables.append(Spacer(1, 1 * mm))
        filas_zonas: list[list[str]] = []
        for fila in _top_zonas(desglose):
            extra = por_zona.get(str(fila.get("zona_id")) or "")
            if not extra:
                continue
            filas_zonas.append(
                [
                    str(fila.get("nombre") or "—"),
                    fmt_num(extra.get("km_relevados"), 2),
                    fmt_num(extra.get("km_propuestos"), 2),
                    fmt_num(extra.get("km_total"), 2),
                    fmt_num(extra.get("km_por_mil_ha"), 2)
                    if extra.get("km_por_mil_ha") is not None
                    else "—",
                ]
            )
        flowables.append(
            build_data_table(
                [
                    "Subcuenca",
                    "Relevados (km)",
                    "Propuestos (km)",
                    "Total (km)",
                    "km cada 1.000 ha",
                ],
                filas_zonas,
                branding,
            )
        )
    flowables.append(PageBreak())
    return flowables


def _seccion_imagenes(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("8. Imágenes de eventos ancla", estilos["subtitle"])]
    flowables.append(
        Paragraph(
            "Miniaturas en falso color (NIR-SWIR1-rojo: el agua absorbe el "
            "SWIR, los anegamientos leen oscuro) de los eventos de "
            "inundación ancla del catálogo, recortadas al área de la "
            "selección.",
            estilos["body"],
        )
    )
    flowables.append(Spacer(1, 2 * mm))

    imagenes = datos.get("imagenes") or []
    if not imagenes:
        flowables.append(
            Paragraph(
                "El catálogo de eventos extremos no está disponible en este "
                "despliegue: no hay eventos ancla que mostrar.",
                estilos["body"],
            )
        )
        flowables.append(PageBreak())
        return flowables

    for imagen in imagenes:
        fecha_es = str(imagen.get("fecha") or "—")
        nubes = imagen.get("nubes_pct")
        partes = [
            f"{_esc(str(imagen.get('nombre') or imagen.get('event_key')))} · {fecha_es}",
            f"sensor {_esc(str(imagen.get('sensor') or '—'))}",
        ]
        if nubes is not None:
            partes.append(f"nubes {fmt_pct(float(nubes))}")
        escena = str(imagen.get("escena") or "")
        flowables.append(Paragraph(" · ".join(partes), estilos["body"]))
        png = imagen.get("png")
        miniatura = _imagen_mapa(png or b"", alto_max_mm=70.0) if png else None
        if miniatura is not None:
            flowables.append(KeepTogether([miniatura, Spacer(1, 1 * mm)]))
        else:
            flowables.append(
                Paragraph(
                    "Sin miniatura para este evento (sin candidata o GEE no respondió).",
                    estilos["small"],
                )
            )
        if escena:
            flowables.append(Paragraph(f"Escena: {_esc(escena)}", estilos["small"]))
        flowables.append(Spacer(1, 2 * mm))

    flowables.append(
        Paragraph(
            "Fuente: escenas Sentinel-2 / Landsat vía Google Earth Engine, "
            "seleccionadas por el shortlist de candidatos del catálogo de "
            "lluvias extremas (rainfall_event_imagery_candidate).",
            estilos["small"],
        )
    )
    flowables.append(PageBreak())
    return flowables


def _seccion_consideraciones(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("9. Consideraciones", estilos["subtitle"])]

    cobertura_labels = [
        ("Riesgo hídrico", datos.get("riesgo")),
        ("Necesidad de drenaje", datos.get("drenaje")),
        ("Suelos", datos.get("suelos")),
        ("Cobertura y cultivos", datos.get("cobertura")),
    ]
    filas: list[list[str]] = []
    for nombre, dataset in cobertura_labels:
        ds = dataset or {}
        cobertura = str(ds.get("cobertura") or "sin_cobertura")
        ratio = float(ds.get("cobertura_ratio") or 0.0)
        filas.append([nombre, cobertura.replace("_", " "), fmt_pct(ratio * 100.0)])
    lluvia = datos.get("lluvia") or {}
    filas.append(
        [
            "Lluvia",
            str(lluvia.get("cobertura") or "sin_cobertura").replace("_", " "),
            fmt_pct(float(lluvia.get("cobertura_ratio") or 0.0) * 100.0),
        ]
    )
    flowables.append(Paragraph("Cobertura por capa", estilos["body"]))
    flowables.append(Spacer(1, 1 * mm))
    flowables.append(build_data_table(["Capa", "Cobertura", "% cubierto"], filas, branding))
    flowables.append(Spacer(1, 3 * mm))

    flowables.append(Paragraph("Límites", estilos["body"]))
    limites = [_DESCARGO, _AVISO_PIXEL]
    nota_umbral = _nota_umbral(datos)
    if nota_umbral is not None:
        limites.insert(0, nota_umbral)
    limites.append(
        "El desglose por subcuenca se lee de datos ya calculados por el "
        "pipeline (composite_zonal_stats) y hereda su fecha de cálculo (ver "
        "Fuentes)."
    )
    limites.append(
        "Suelos: carta IDECOR 1:50.000 bajada por ETL; la fecha de bajada "
        "queda en Fuentes. Una sección sin datos significa que el ETL no "
        "corrió en este despliegue."
    )
    limites.append(
        "Mapas: render simbólico sobre fondo blanco, sin imagen satelital en esta versión."
    )
    for limite in limites:
        flowables.append(Paragraph(f"• {_esc(limite)}", estilos["small"]))
    flowables.append(Spacer(1, 2 * mm))

    degradado = datos.get("degradado") or []
    if degradado:
        flowables.append(Paragraph("Incidencias durante la generación", estilos["body"]))
        for item in degradado:
            flowables.append(Paragraph(f"• {_esc(str(item))}", estilos["small"]))
    flowables.append(PageBreak())
    return flowables


def _seccion_fuentes(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("10. Fuentes", estilos["subtitle"])]
    fuentes = datos.get("fuentes") or []
    if not fuentes:
        flowables.append(Paragraph("Sin capas registradas para este informe.", estilos["body"]))
        return flowables
    filas = [
        [
            _esc(str(f.get("capa") or "—")),
            _esc(str(f.get("fecha") or "—")),
            _esc(str(f.get("resolucion") or "—")),
            _esc(str(f.get("origen") or "—")),
        ]
        for f in fuentes
    ]
    flowables.append(build_data_table(["Capa", "Fecha", "Resolución", "Origen"], filas, branding))
    return flowables


# ── entry point ──────────────────────────────────────────────────────────────


def _qr_campo(url: str, estilos: dict[str, Any]) -> list[Flowable]:
    """The cover's campo-map QR (S7): QR drawing + caption + plain URL.

    ``reportlab.graphics.barcode.qr`` ships with ReportLab — zero new
    dependencies, same rule as the KMZ. The caption is real text (not part
    of the image) so pypdf can assert it; the plain URL below the QR is the
    copy-paste fallback for a phone that cannot scan.
    """
    from reportlab.graphics.barcode import qr as rl_qr
    from reportlab.graphics.shapes import Drawing

    lado_mm = 24.0
    widget = rl_qr.QrCodeWidget(url, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    dibujo = Drawing(
        lado_mm,
        lado_mm,
        transform=[
            lado_mm / (x1 - x0),
            0,
            0,
            lado_mm / (y1 - y0),
            0,
            0,
        ],
    )
    dibujo.add(widget)

    return [
        Table(
            [[dibujo]],
            colWidths=[lado_mm * mm],
            style=[("ALIGN", (0, 0), (-1, -1), "CENTER")],
            hAlign="RIGHT",
        ),
        Spacer(1, 1.5 * mm),
        Paragraph("Mapa de campo — escaneá para abrirlo en el celular", estilos["body"]),
        Paragraph(f"(también funciona sin señal: {url})", estilos["small"]),
        Spacer(1, 3 * mm),
    ]


def build_informe_area_pdf(
    datos: dict[str, Any],
    branding: BrandingInfo,
    *,
    mapas: dict[str, bytes],
) -> io.BytesIO:
    """Render the 7-section informe de área (S6) with the house branding."""
    pdf = BrandedPDF(branding)
    estilos = get_pdf_styles(branding)

    story: list[Flowable] = [
        Paragraph("Informe de área", estilos["title"]),
        Spacer(1, 2 * mm),
        Paragraph(
            "Documento generado en segundo plano a partir de los productos "
            "registrados del consorcio; todas las superficies en hectáreas.",
            estilos["body"],
        ),
        Spacer(1, 4 * mm),
    ]

    # PR 6 (S7): the campo-map QR on the cover — right-aligned, with the
    # plain URL as the copy-paste fallback. Optional: a pre-PR6 caller (or a
    # test isolating the cover) builds the same PDF without it.
    campo_url = str(datos.get("campo_url") or "").strip()
    if campo_url:
        story.extend(_qr_campo(campo_url, estilos))

    story.extend(_seccion_resumen(datos, branding, estilos, mapas))

    from app.domains.geo.class_breaks import RANGE_CONFIGS

    story.extend(
        _seccion_clase(
            "2. Riesgo hídrico",
            _FRASE_RIESGO,
            datos.get("riesgo"),
            RANGE_CONFIGS["flood_risk"],
            mapas.get("flood_risk"),
            "Mapa de riesgo hídrico: clases del índice, contorno negro "
            "(selección), gris (subcuencas), escala gráfica y norte.",
            _notas_metodo_clase("flood_risk", datos.get("riesgo"), datos),
            datos.get("desglose"),
            [
                ("Subcuenca", "nombre", str),
                ("Cuenca", "cuenca", str),
                ("Superficie (ha)", "ha", fmt_ha),
                ("% Alto+Crítico", "pct_alto_critico", fmt_pct),
            ],
            branding,
            estilos,
            extra=_tabla_validacion_riesgo(datos, branding, estilos),
        )
    )
    story.extend(
        _seccion_clase(
            "3. Necesidad de drenaje",
            _FRASE_DRENAJE,
            datos.get("drenaje"),
            RANGE_CONFIGS["drainage_need"],
            mapas.get("drainage_need"),
            "Mapa de necesidad de drenaje: clases del índice, contorno negro "
            "(selección), gris (subcuencas), escala gráfica y norte.",
            _notas_metodo_clase("drainage_need", datos.get("drenaje"), datos),
            datos.get("desglose"),
            [
                ("Subcuenca", "nombre", str),
                ("Cuenca", "cuenca", str),
                ("Superficie (ha)", "ha", fmt_ha),
                ("% Alto+Crítico", "pct_drenaje_alto_critico", fmt_pct),
            ],
            branding,
            estilos,
        )
    )
    story.extend(_seccion_suelos(datos, branding, estilos))
    story.extend(_seccion_cobertura(datos, branding, estilos))
    story.extend(_seccion_lluvia(datos, branding, estilos))
    story.extend(_seccion_canales(datos, branding, estilos))
    story.extend(_seccion_imagenes(datos, branding, estilos))
    story.extend(_seccion_consideraciones(datos, branding, estilos))
    story.extend(_seccion_fuentes(datos, branding, estilos))

    return pdf.build(story, title=f"Informe de área — {datos.get('nombre', '')}")


def _notas_metodo_clase(
    tipo: str, dataset: dict[str, Any] | None, datos: dict[str, Any]
) -> list[str]:
    """Method notes for sections 2/3: break edges, coverage base, threshold tag."""
    from app.domains.geo.class_breaks import RANGE_CONFIGS

    cortes = ", ".join(
        f"{cfg['label']} {_recorte(cfg['min'])}–{_recorte(cfg['max'])}"
        for cfg in RANGE_CONFIGS[tipo]
    )
    notas = [f"Clases según los cortes del mapa: {cortes}."]
    cobertura = str((dataset or {}).get("cobertura") or "sin_cobertura")
    if cobertura != "sin_cobertura":
        ratio = float((dataset or {}).get("cobertura_ratio") or 0.0)
        notas.append(
            f"Cobertura de la capa sobre la selección: {cobertura.replace('_', ' ')} "
            f"({fmt_pct(ratio * 100.0)}); los porcentajes se calculan sobre la "
            "superficie total de la selección."
        )
    nota_umbral = _nota_umbral(datos)
    if tipo == "flood_risk" and nota_umbral is not None:
        notas.append(nota_umbral)
    if tipo == "drainage_need":
        nota_drenaje = (
            _NOTA_LEYENDA55
            if str(datos.get("umbral_alto_critico") or "") == "leyenda-55"
            else _NOTA_LEGACY70
        )
        notas.append(
            "El desglose por subcuenca de esta capa usa el mismo criterio "
            "(desde el inicio de Alto): " + nota_drenaje
        )
    return notas


def _recorte(valor: float) -> str:
    """Break edge without trailing zeros: 55.0 → '55'."""
    return fmt_num(valor, 0)
