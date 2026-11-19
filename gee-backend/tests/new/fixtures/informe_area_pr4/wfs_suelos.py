"""Synthetic IDECOR payloads for the PR 4 informe de área tests.

Hermetic only — nothing in this package may touch
``idecor-ws.mapascordoba.gob.ar`` (the ONE exception is the opt-in live
test, gated on ``IDECOR_LIVE=1``, which reads the real WFS with a bounded
count).

The shapes mirror what was verified live on 2026-11-18/19:

* WFS ``carta_suelo_50mil_2025`` — GeoJSON FeatureCollection in EPSG:4326
  with the properties the ETL maps (``cu``, ``clase``, ``ip``, ``au_1m``,
  ``serie_N``/``porc_N``, ``pdf_serieN``...);
* WCS cobertura rasters are built in-test with rasterio (class codes 1..21
  for ``cobertura_uso``, campaign-specific codes for the estivales).
"""

from __future__ import annotations

import json


def feature_suelo(
    fid: int,
    bbox: tuple[float, float, float, float],
    *,
    simbolo: str = "MB",
    clase: str = "II",
    cu: str = "IIc",
    ip: int | None = 90,
    au_1m: int | None = 158,
    au_1_5m: int | None = 225,
    au_2m: int | None = 292,
    serie: str | None = "MONTE BUEY",
    porc: int | None = 100,
) -> dict:
    """One carta-unit polygon over ``bbox`` with realistic properties."""
    minx, miny, maxx, maxy = bbox
    return {
        "id": f"carta_suelo_50mil_2025.{fid}",
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [minx, miny],
                    [maxx, miny],
                    [maxx, maxy],
                    [minx, maxy],
                    [minx, miny],
                ]
            ],
        },
        "properties": {
            "id": fid,
            "simbolo": simbolo,
            "pdf_simbolo": simbolo,
            "cu": cu,
            "clase": clase,
            "subclase": None,
            "ip": ip,
            "au_1m": au_1m,
            "au_1_5m": au_1_5m,
            "au_2m": au_2m,
            "nombre": f"Consociación {serie}" if serie else "Unidad sin serie",
            "tipo_unida": "Consociación" if serie else "Misceláneo",
            "serie_1": serie,
            "fase_1": None,
            "pdf_serie1": serie.replace(" ", "_") if serie else None,
            "porc_1": porc,
            "serie_2": None,
            "fase_2": None,
            "pdf_serie2": None,
            "porc_2": None,
            "serie_3": None,
            "pdf_serie3": None,
            "porc_3": None,
            "serie_4": None,
            "pdf_serie4": None,
            "porc_4": None,
            "serie_5": None,
            "pdf_serie5": None,
            "serie_6": None,
            "pdf_serie6": None,
            "serie_7": None,
            "pdf_serie7": None,
            "serie_8": None,
            "pdf_serie8": None,
        },
    }


def pagina_wfs(features: list[dict], number_matched: int | None = None) -> dict:
    """A WFS 2.0 JSON page shape (``numberMatched`` + ``features``)."""
    return {
        "type": "FeatureCollection",
        "totalFeatures": number_matched if number_matched is not None else len(features),
        "numberMatched": number_matched if number_matched is not None else len(features),
        "features": features,
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
    }


def dump_pagina(features: list[dict], number_matched: int | None = None) -> str:
    return json.dumps(pagina_wfs(features, number_matched))
