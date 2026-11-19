"""Hermetic WCS/WMS doubles for the IDECOR cobertura ETL tests.

The ETL validates every download with rasterio (CRS, grid size, band
count), so a fake ``bytes`` payload is not enough — these doubles build
REAL in-memory GeoTIFFs on the exact grid the ETL requested, with class
codes driven by a per-capa paint function. The legends mirror the live
GetLegendGraphic answers (verified 2026-11-19), including the fact that
the 22/23 campaign uses a DIFFERENT coding than 23/24 and 24/25.
"""

from __future__ import annotations

import io
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import numpy as np
import rasterio
from rasterio.transform import from_origin

# Legends copied from the live GetLegendGraphic (format=application/json).
LEYENDA_USO: list[dict[str, Any]] = [
    {"codigo": n, "etiqueta": etiqueta, "color": "#000000"}
    for n, etiqueta in enumerate(
        [
            "1 - Monte",
            "2 - Matorral",
            "3 - Pastizal natural",
            "4 - Matorral halófilo",
            "5 - Roca",
            "6 - Suelo desnudo",
            "7 - Salina",
            "8 - Cuerpo de agua",
            "9 - Cuerpo de agua estacional",
            "10 - Curso de agua",
            "11 - Urbano compacidad alta",
            "12 - Urbano compacidad media",
            "13 - Urbano compacidad baja",
            "14 - Urbano compacidad muy baja o edificación dispersa",
            "15 - Infraestructura vial y ferroviaria",
            "16 - Cultivo extensivo anual",
            "17 - Cultivos anual irrigado",
            "18 - Pastura implantada",
            "19 - Pastura manejada",
            "20 - Cultivo hortícola multiespecífico",
            "21 - Plantación leñosa comercial",
        ],
        start=1,
    )
]

#: The campaign codings DIFFER on purpose (the ETL stores legends because
#: of exactly this): 22/23 is 1=Soja/2=Maíz/3=Otros; the later campaigns
#: split maize into early/late and add maní.
LEYENDA_ESTIVAL_2223: list[dict[str, Any]] = [
    {"codigo": 1, "etiqueta": "Soja", "color": "#16A90B"},
    {"codigo": 2, "etiqueta": "Maíz", "color": "#EFD10A"},
    {"codigo": 3, "etiqueta": "Otros cultivos", "color": "#E87305"},
]
LEYENDA_ESTIVAL_TARDIA: list[dict[str, Any]] = [
    {"codigo": 1, "etiqueta": "Maíz temprano", "color": "#F9F929"},
    {"codigo": 2, "etiqueta": "Maíz tardío", "color": "#F5B02F"},
    {"codigo": 3, "etiqueta": "Soja", "color": "#17BF17"},
    {"codigo": 4, "etiqueta": "Maní", "color": "#A35531"},
    {"codigo": 5, "etiqueta": "Otros", "color": "#6A6B68"},
]


def leyenda_wms(leyenda: list[dict[str, Any]]) -> dict[str, Any]:
    """The GetLegendGraphic JSON shape for one legend list."""
    return {
        "Legend": [
            {
                "layerName": "doble",
                "title": "doble",
                "rules": [
                    {
                        "symbolizers": [
                            {
                                "Raster": {
                                    "colormap": {
                                        "type": "values",
                                        "entries": [
                                            {
                                                "label": str(e["etiqueta"]),
                                                "quantity": str(e["codigo"]),
                                                "color": e["color"],
                                            }
                                            for e in leyenda
                                        ],
                                    }
                                }
                            }
                        ]
                    }
                ],
            }
        ]
    }


def _grid_de_url(url: str) -> tuple[float, float, float, float, int, int]:
    qs = parse_qs(urlparse(url).query)
    minx, miny, maxx, maxy = (float(v) for v in qs["bbox"][0].split(","))
    return minx, miny, maxx, maxy, int(qs["width"][0]), int(qs["height"][0])


def geotiff_de_pintura(
    pintura: Callable[[np.ndarray, np.ndarray], np.ndarray],
    url: str,
    *,
    dtype: str = "uint8",
    nodata: float | None = None,
) -> bytes:
    """A real GeoTIFF on the ETL's requested grid; ``pintura`` fills it.

    ``pintura(xs, ys)`` receives the pixel-center coordinates in EPSG:22174
    (meshgrid) and returns the class grid — so tests can place classes by
    geography, not by fragile pixel indices.
    """
    minx, miny, maxx, maxy, ancho, alto = _grid_de_url(url)
    transform = from_origin(minx, maxy, (maxx - minx) / ancho, (maxy - miny) / alto)
    xs = minx + (np.arange(ancho) + 0.5) * (maxx - minx) / ancho
    ys = maxy - (np.arange(alto) + 0.5) * (maxy - miny) / alto
    datos = pintura(*np.meshgrid(xs, ys)).astype(dtype)
    buffer = io.BytesIO()
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        height=alto,
        width=ancho,
        count=1,
        dtype=dtype,
        crs="EPSG:22174",
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(datos, 1)
    return buffer.getvalue()
