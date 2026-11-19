"""Informe de área PDF builder — the S6 seven sections (PR 2, T2).

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
4. Suelos (catastro ``suelos_cu`` vigente; PR 4 lo reemplaza)
5. Lluvia (normales mensuales en barras — ReportLab primitives, no chart lib)
6. Consideraciones (cobertura por capa, límites, descargo)
7. Fuentes (capa · fecha · resolución · origen)

Per-subcuenca tables (S6): inline and complete when there are ≤ 8 subcuencas;
beyond that each section shows a resumen line and the complete table at the
END of the section. ``% Alto+Crítico`` figures carry the ``legacy70`` note
wherever they appear (S12, until #738 recalibrates the stored threshold);
per-class producer phrases are PR 5's, not this builder's.
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
    "Capacidad de uso de los suelos según el catastro INTA vigente "
    "(suelos_cu), agrupada por clase romana (I a VIII)."
)
_FRASE_LLUVIA = "Normales mensuales de precipitación (mm) promediadas sobre la selección."

_NOTA_LEGACY70 = (
    "El porcentaje Alto+Crítico usa el umbral histórico de 70 puntos "
    "(umbral_alto_critico: legacy70) hasta su recalibración; los cortes de "
    "clase del mapa y de las tablas no dependen de ese umbral."
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
    if datos.get("umbral_alto_critico") == "legacy70":
        flowables.append(Spacer(1, 1.5 * mm))
        flowables.append(Paragraph(_NOTA_LEGACY70, estilos["small"]))
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
                    "el detalle completo está al final de las secciones 2, 4 y 5.",
                    estilos["small"],
                )
            )
    else:
        flowables.append(
            Paragraph("Informe generado sin desglose por subcuenca.", estilos["small"])
        )
    flowables.append(PageBreak())
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
) -> list[Flowable]:
    """Sections 2 and 3 share this shape (S6: 'igual estructura')."""
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
    flowables.append(PageBreak())
    return flowables


def _seccion_suelos(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("4. Suelos", estilos["subtitle"])]
    flowables.append(Paragraph(_FRASE_SUELOS, estilos["body"]))
    flowables.append(Spacer(1, 2 * mm))

    dataset = datos.get("suelos")
    clases = (dataset or {}).get("clases") or []
    # The dataset's own order (I..VIII, then sin clasificar/sin dato) is the
    # canonical one — no invented zero rows for absent classes.
    orden_suelos = [{"label": c["clase"]} for c in clases]
    flowables.extend(
        _tabla_clases(
            dataset,
            orden_suelos,
            branding,
            titulo_total="Total con catastro",
        )
    )
    flowables.append(Spacer(1, 2 * mm))
    flowables.append(
        Paragraph(
            "Agrupado por prefijo romano (IVws → IV). «Sin dato» es la "
            "superficie que el catastro no cubre; «sin clasificar» es "
            "superficie catastrada sin clase de capacidad.",
            estilos["small"],
        )
    )
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
            ("Clase dominante", "clase_suelo_dominante", str),
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


def _seccion_lluvia(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("5. Lluvia", estilos["subtitle"])]
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


def _seccion_consideraciones(
    datos: dict[str, Any],
    branding: BrandingInfo,
    estilos: dict[str, Any],
) -> list[Flowable]:
    flowables: list[Flowable] = [Paragraph("6. Consideraciones", estilos["subtitle"])]

    cobertura_labels = [
        ("Riesgo hídrico", datos.get("riesgo")),
        ("Necesidad de drenaje", datos.get("drenaje")),
        ("Suelos", datos.get("suelos")),
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
    if datos.get("umbral_alto_critico") == "legacy70":
        limites.insert(0, _NOTA_LEGACY70)
    limites.append(
        "El desglose por subcuenca se lee de datos ya calculados por el "
        "pipeline (composite_zonal_stats) y hereda su fecha de cálculo (ver "
        "Fuentes)."
    )
    limites.append(
        "Suelos: catastro vectorial vigente sin fecha de versión registrada en el sistema."
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
    flowables: list[Flowable] = [Paragraph("7. Fuentes", estilos["subtitle"])]
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
    story.extend(_seccion_lluvia(datos, branding, estilos))
    story.extend(_seccion_consideraciones(datos, branding, estilos))
    story.extend(_seccion_fuentes(datos, branding, estilos))

    return pdf.build(story, title=f"Informe de área — {datos.get('nombre', '')}")


def _notas_metodo_clase(
    tipo: str, dataset: dict[str, Any] | None, datos: dict[str, Any]
) -> list[str]:
    """Method notes for sections 2/3: break edges, coverage base, legacy70."""
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
    if tipo == "flood_risk" and datos.get("umbral_alto_critico") == "legacy70":
        notas.append(_NOTA_LEGACY70)
    if tipo == "drainage_need":
        notas.append(
            "El desglose por subcuenca de esta capa usa el mismo umbral "
            "histórico de 70 puntos (legacy70) hasta su recalibración."
        )
    return notas


def _recorte(valor: float) -> str:
    """Break edge without trailing zeros: 55.0 → '55'."""
    return fmt_num(valor, 0)
