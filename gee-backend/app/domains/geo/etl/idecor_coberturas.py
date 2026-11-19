"""ETL: IDECOR land-cover rasters → ``idecor_cobertura_raster`` (PR 4, S4).

Runs inside the backend container::

    docker compose exec backend python -m app.domains.geo.etl.idecor_coberturas

Downloads, for the zona bbox (``ST_Extent(zonas_operativas)`` + 2 km
margin, reprojected to the covers' native EPSG:22174):

* ``cobertura_uso_2024_2025`` — 21 land-cover classes, 10 m, uint8 (255 =
  nodata);
* ``coberturas_estivales_2223`` / ``_2324`` / ``_2425`` — summer-crop
  classes per campaign, 10 m, float32 (NaN = no summer crop).

Verified live 2026-11-19 (all on the IDECOR GeoServer):

* they are WCS **raster** coverages — the WFS answers "unknown Feature
  type" for every one of them, and the WCS 2.0.1 GetCapabilities lists
  ``idecor__cobertura_uso_2024_2025`` and the three estivales;
* WCS 2.0.1 ``subset=`` GetCoverage kept answering "Empty intersection"
  for in-range intervals (both axis orders), so the ETL uses WCS **1.0.0**
  KVP (``bbox`` + ``width``/``height``), which works and lets us pin the
  10 m grid explicitly — the four downloads share ONE grid, which is what
  makes the pixel-aligned three-campaign recurrence computable later;
* the class legends come from WMS ``GetLegendGraphic`` with
  ``format=application/json`` and are STORED per layer, because the
  campaign codings differ (2223: 1=Soja…; 2324/2425: 1=Maíz temprano…).

All-or-nothing: every file downloads and validates BEFORE the database
touches anything; then one transaction replaces all four rows. A re-run
converges on the same rows (UNIQUE ``capa``) with a fresh
``fecha_de_bajada``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlencode

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

WCS_BASE = "https://idecor-ws.mapascordoba.gob.ar/geoserver/idecor/wcs"
WMS_BASE = "https://idecor-ws.mapascordoba.gob.ar/geoserver/idecor/wms"
#: Native CRS of every cover (DescribeCoverage, verified 2026-11-19).
SRID_COBERTURA = 22174
#: Native pixel size in metres (10 m — verified via offsetVector).
PASO_M = 10.0
#: Margin around the zonas extent, metres.
MARGEN_BBOX_M = 2_000.0
DEFAULT_DATA_ROOT = "/data/geo/zona_principal/idecor"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_LOAD_FAILED = 3
EXIT_INFRA_FAILED = 5

FUENTE_IDECOR = "IDECOR · Mapas Córdoba (WCS/WMS) · licencia CC BY 4.0"

#: capa → (coverageId, WMS layer, tipo, campaña).
CAPAS: dict[str, dict[str, str]] = {
    "uso_2024_2025": {
        "coverage_id": "idecor__cobertura_uso_2024_2025",
        "wms_layer": "cobertura_uso_2024_2025",
        "tipo": "cobertura_uso",
        "campania": "2024/2025",
    },
    "estival_2223": {
        "coverage_id": "idecor__coberturas_estivales_2223",
        "wms_layer": "coberturas_estivales_2223",
        "tipo": "cobertura_estival",
        "campania": "2022/2023",
    },
    "estival_2324": {
        "coverage_id": "idecor__coberturas_estivales_2324",
        "wms_layer": "coberturas_estivales_2324",
        "tipo": "cobertura_estival",
        "campania": "2023/2024",
    },
    "estival_2425": {
        "coverage_id": "idecor__coberturas_estivales_2425",
        "wms_layer": "coberturas_estivales_2425",
        "tipo": "cobertura_estival",
        "campania": "2024/2025",
    },
}


class EtlAssertionError(RuntimeError):
    """A download or validation failed. Raised before ANY database write."""


# ── zona bbox in the covers' CRS ─────────────────────────────────────────────


def resolver_bbox_22174(
    db: Session, margen_m: float = MARGEN_BBOX_M
) -> tuple[float, float, float, float]:
    """Zonas extent + margin, in EPSG:22174 (minx, miny, maxx, maxy).

    Same fail-closed rule as the suelos ETL: no zonas → no extent → no
    download. The 4326→22174 hop happens here so the WCS request and the
    stored ``bbox_22174`` always agree.
    """
    from pyproj import Transformer

    fila = db.execute(
        text("SELECT ST_Extent(geometria)::text FROM zonas_operativas")
    ).scalar_one_or_none()
    if not fila:
        raise EtlAssertionError(
            "zonas_operativas está vacía — no se puede resolver el bbox de la zona; "
            "nada se descargó ni se escribió"
        )
    interior = fila.removeprefix("BOX(").removesuffix(")")
    par_min, par_max = interior.split(",")
    minx, miny = (float(v) for v in par_min.split())
    maxx, maxy = (float(v) for v in par_max.split())
    oeste, sur, este, norte = Transformer.from_crs(
        "EPSG:4326", "EPSG:22174", always_xy=True
    ).transform_bounds(minx, miny, maxx, maxy)
    return oeste - margen_m, sur - margen_m, este + margen_m, norte + margen_m


# ── URLs (pure; the fetchers are injected for hermetic tests) ────────────────


def url_get_coverage(coverage_id: str, bbox: tuple[float, float, float, float]) -> str:
    """WCS 1.0.0 KVP: bbox + the exact 10 m grid (width/height pinned)."""
    minx, miny, maxx, maxy = bbox
    ancho = max(1, round((maxx - minx) / PASO_M))
    alto = max(1, round((maxy - miny) / PASO_M))
    params = {
        "service": "WCS",
        "version": "1.0.0",
        "request": "GetCoverage",
        "coverage": coverage_id.split("idecor__", 1)[1],
        "crs": f"EPSG:{SRID_COBERTURA}",
        "bbox": f"{minx:.1f},{miny:.1f},{maxx:.1f},{maxy:.1f}",
        "width": str(ancho),
        "height": str(alto),
        "format": "GeoTIFF",
    }
    return f"{WCS_BASE}?{urlencode(params)}"


def url_leyenda(wms_layer: str) -> str:
    params = {
        "service": "WMS",
        "version": "1.1.1",
        "request": "GetLegendGraphic",
        "layer": wms_layer,
        "format": "application/json",
    }
    return f"{WMS_BASE}?{urlencode(params)}"


def normalizar_leyenda(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """GeoServer legend JSON → ``[{codigo, etiqueta, color}]`` (sorted by code)."""
    entradas: list[dict[str, Any]] = []
    for regla in payload.get("Legend") or []:
        for simbolizador in regla.get("rules") or []:
            for raster in simbolizador.get("symbolizers") or []:
                for entrada in ((raster.get("Raster") or {}).get("colormap") or {}).get(
                    "entries"
                ) or []:
                    try:
                        codigo = int(entrada["quantity"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise EtlAssertionError(
                            f"leyenda con quantity no numérico: {entrada!r}"
                        ) from exc
                    entradas.append(
                        {
                            "codigo": codigo,
                            "etiqueta": str(entrada.get("label") or codigo).strip(),
                            "color": str(entrada.get("color") or "#000000"),
                        }
                    )
    if not entradas:
        raise EtlAssertionError("leyenda vacía — no se registra la capa sin clases")
    return sorted(entradas, key=lambda e: e["codigo"])


# ── download + validate (all-or-nothing BEFORE any DB write) ─────────────────


def _validar_geotiff(path: Path, ancho: int, alto: int) -> dict[str, Any]:
    import rasterio

    with rasterio.open(path) as src:
        if src.count < 1:
            raise EtlAssertionError(f"{path.name}: raster sin bandas")
        if src.width < 2 or src.height < 2:
            raise EtlAssertionError(f"{path.name}: ventana vacía ({src.width}x{src.height})")
        if src.crs is None or src.crs.to_epsg() != SRID_COBERTURA:
            raise EtlAssertionError(f"{path.name}: CRS {src.crs} != EPSG:{SRID_COBERTURA}")
        return {
            "ancho_px": src.width,
            "alto_px": src.height,
            "esperado": (ancho, alto),
        }


def bajar_coberturas(
    db: Session,
    *,
    data_root: str | Path,
    fetch_bytes: Callable[[str], bytes],
    fetch_json: Callable[[str], dict[str, Any]],
    margen_m: float = MARGEN_BBOX_M,
) -> dict[str, Any]:
    """Download the four covers + legends to ``data_root``; nothing DB-bound.

    Returns the registration payload per capa. The files land as
    ``<capa>.tif`` under ``data_root``; an existing file is replaced only
    after its replacement validated (write to ``.tmp`` then rename — the
    gem15 fail-closed pattern).
    """
    bbox = resolver_bbox_22174(db, margen_m)
    destino = Path(data_root)
    destino.mkdir(parents=True, exist_ok=True)
    ancho = max(1, round((bbox[2] - bbox[0]) / PASO_M))
    alto = max(1, round((bbox[3] - bbox[1]) / PASO_M))

    registros: list[dict[str, Any]] = []
    for capa, spec in CAPAS.items():
        tif_bytes = fetch_bytes(url_get_coverage(spec["coverage_id"], bbox))
        if not tif_bytes[:2] == b"II" and not tif_bytes[:2] == b"MM":
            # GeoTIFF is big/little endian TIFF; XML means an exception report.
            raise EtlAssertionError(f"{capa}: la respuesta no es un GeoTIFF — {tif_bytes[:120]!r}")
        tmp = destino / f"{capa}.tmp.tif"
        final = destino / f"{capa}.tif"
        tmp.write_bytes(tif_bytes)
        dims = _validar_geotiff(tmp, ancho, alto)
        if (dims["ancho_px"], dims["alto_px"]) != dims["esperado"]:
            raise EtlAssertionError(
                f"{capa}: grilla {dims['ancho_px']}x{dims['alto_px']} != "
                f"pedida {dims['esperado']} — las capas dejarían de estar alineadas"
            )
        tmp.replace(final)
        leyenda = normalizar_leyenda(fetch_json(url_leyenda(spec["wms_layer"])))
        registros.append(
            {
                "capa": capa,
                "tipo": spec["tipo"],
                "campania": spec["campania"],
                "archivo_path": str(final),
                "leyenda": leyenda,
                "bbox_22174": list(bbox),
                "ancho_px": dims["ancho_px"],
                "alto_px": dims["alto_px"],
            }
        )
    return {"bbox": bbox, "registros": registros}


def registrar(db: Session, registros: list[dict[str, Any]]) -> int:
    """Replace every ``capa`` row in ONE transaction (idempotent re-run)."""
    fecha = datetime.now(timezone.utc)
    db.execute(text("DELETE FROM idecor_cobertura_raster"))
    insertados = 0
    for registro in registros:
        db.execute(
            text(
                "INSERT INTO idecor_cobertura_raster "
                "(id, capa, tipo, campania, archivo_path, srid, leyenda, bbox_22174, "
                " ancho_px, alto_px, fecha_de_bajada) "
                "VALUES (gen_random_uuid(), :capa, :tipo, :campania, :archivo_path, :srid, "
                "        CAST(:leyenda AS jsonb), :bbox, :ancho_px, :alto_px, :fecha)"
            ),
            {
                "capa": registro["capa"],
                "tipo": registro["tipo"],
                "campania": registro["campania"],
                "archivo_path": registro["archivo_path"],
                "srid": SRID_COBERTURA,
                "leyenda": json.dumps(registro["leyenda"]),
                "bbox": registro["bbox_22174"],
                "ancho_px": registro["ancho_px"],
                "alto_px": registro["alto_px"],
                "fecha": fecha,
            },
        )
        insertados += 1
    almacenados = db.execute(text("SELECT count(*) FROM idecor_cobertura_raster")).scalar_one()
    if almacenados != len(CAPAS):
        raise EtlAssertionError(
            f"filas registradas {almacenados} != capas {len(CAPAS)} — no se commitea"
        )
    db.commit()
    return int(almacenados)


def run_etl(
    db: Session,
    *,
    data_root: str | Path,
    fetch_bytes: Callable[[str], bytes],
    fetch_json: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Download → validate → register. One ``fecha_de_bajada`` for the batch."""
    resultado = bajar_coberturas(
        db, data_root=data_root, fetch_bytes=fetch_bytes, fetch_json=fetch_json
    )
    filas = registrar(db, resultado["registros"])
    return {"bbox": resultado["bbox"], "filas": filas}


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover — network/CLI
    parser = argparse.ArgumentParser(
        prog="python -m app.domains.geo.etl.idecor_coberturas",
        description="Baja los rasters de cobertura IDECOR (uso 2024/2025 + 3 estivales) "
        "para el bbox de la zona y los registra en idecor_cobertura_raster.",
    )
    parser.add_argument(
        "--data-root",
        default=DEFAULT_DATA_ROOT,
        help=f"Directorio de descarga (por defecto {DEFAULT_DATA_ROOT}).",
    )
    args = parser.parse_args(argv)

    import requests

    from app.db.session import SessionLocal

    def _get_bytes(url: str) -> bytes:
        respuesta = requests.get(url, timeout=600)
        respuesta.raise_for_status()
        return respuesta.content

    def _get_json(url: str) -> dict[str, Any]:
        respuesta = requests.get(url, timeout=60)
        respuesta.raise_for_status()
        return respuesta.json()

    try:
        with SessionLocal() as db:
            resultado = run_etl(
                db, data_root=args.data_root, fetch_bytes=_get_bytes, fetch_json=_get_json
            )
    except EtlAssertionError as exc:
        print(f"CARGA RECHAZADA: {exc}", file=sys.stderr)
        return EXIT_LOAD_FAILED
    except requests.RequestException as exc:
        print(f"IDECOR INALCANZABLE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_INFRA_FAILED
    except SQLAlchemyError as exc:
        print(f"ERROR DE BASE DE DATOS: {exc}", file=sys.stderr)
        return EXIT_INFRA_FAILED

    print(
        f"IDECOR coberturas registradas: {resultado['filas']} capas "
        f"(bbox 22174 {tuple(round(v, 1) for v in resultado['bbox'])}, "
        f"directorio {args.data_root})"
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
