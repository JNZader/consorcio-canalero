"""ETL: IDECOR soils 1:50.000 → ``idecor_suelos_50mil`` (PR 4, S3).

Runs inside the backend container (house pattern, ``gem15_fase2_geoid`` /
``load_suelos_catastro``)::

    docker compose exec backend python -m app.domains.geo.etl.idecor_suelos_50mil

Pulls the WFS layer ``idecor:carta_suelo_50mil_2025`` (JSON outputFormat,
EPSG:4326 — endpoint verified live 2026-11-18, 1.555 features province
wide) restricted to the consorcio zona bbox, resolved from
``ST_Extent(zonas_operativas)`` + a 0.02° margin. The extent comes from
the database — not a hardcoded constant, not GEE — because the informe
can only ever select zonas that live there, so the ETL's coverage and the
report's selection domain are the same set by construction.

Idempotence = full refresh inside ONE transaction (the
``load_suelos_catastro`` contract): ``TRUNCATE`` → bulk insert →
assertions → ``COMMIT``. A re-run converges on the same row set with a
fresh ``fecha_de_bajada``; the natural primary key (the WFS feature id)
keeps the count stable regardless of paging order. Fail-closed on every
external answer: a truncated page, an unrepairable geometry or a count
mismatch aborts with a non-zero exit and leaves the table untouched.

The informe NEVER calls IDECOR live (S2) — everything it renders comes
from this table.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Sequence
from urllib.parse import urlencode

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

WFS_BASE = "https://idecor-ws.mapascordoba.gob.ar/geoserver/idecor/wfs"
WFS_LAYER = "idecor:carta_suelo_50mil_2025"
#: Page size below GeoServer's maxFeatures default; the loop walks
#: ``startIndex`` until the page comes back short.
PAGE_SIZE = 500
#: Margin around the zonas extent, degrees — heals boundary slivers where
#: a carta polygon straddles the bbox edge (WFS bbox clipping is not
#: guaranteed to be inclusive).
MARGEN_BBOX_DEG = 0.02

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_LOAD_FAILED = 3
EXIT_INFRA_FAILED = 5

FUENTE_IDECOR = "Carta de suelos 1:50.000 2025 — IDECOR/WFS idecor:carta_suelo_50mil_2025"

#: ``(column, source_property)`` — everything the migration stores, in the
#: order the INSERT lists them. VERBATIM WFS property names.
_COLUMNAS: tuple[tuple[str, str], ...] = (
    ("simbolo", "simbolo"),
    ("cu", "cu"),
    ("clase", "clase"),
    ("subclase", "subclase"),
    ("ip", "ip"),
    ("au_1m", "au_1m"),
    ("au_1_5m", "au_1_5m"),
    ("au_2m", "au_2m"),
    ("serie_1", "serie_1"),
    ("serie_2", "serie_2"),
    ("serie_3", "serie_3"),
    ("serie_4", "serie_4"),
    ("serie_5", "serie_5"),
    ("serie_6", "serie_6"),
    ("serie_7", "serie_7"),
    ("serie_8", "serie_8"),
    ("porc_1", "porc_1"),
    ("porc_2", "porc_2"),
    ("porc_3", "porc_3"),
    ("porc_4", "porc_4"),
    ("nombre", "nombre"),
    ("tipo_unida", "tipo_unida"),
    ("pdf_simbolo", "pdf_simbolo"),
    ("pdf_serie_1", "pdf_serie1"),
    ("pdf_serie_2", "pdf_serie2"),
    ("pdf_serie_3", "pdf_serie3"),
    ("pdf_serie_4", "pdf_serie4"),
    ("pdf_serie_5", "pdf_serie5"),
    ("pdf_serie_6", "pdf_serie6"),
    ("pdf_serie_7", "pdf_serie7"),
    ("pdf_serie_8", "pdf_serie8"),
)

_INSERT = text(
    "INSERT INTO idecor_suelos_50mil (id, "
    + ", ".join(col for col, _prop in _COLUMNAS)
    + ", geometria, fecha_de_bajada) VALUES ("
    + ", ".join([":id"] + [f":{col}" for col, _prop in _COLUMNAS])
    + ", ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromGeoJSON(:geojson)), 3)), :fecha)"
)


class EtlAssertionError(RuntimeError):
    """A load-time assertion failed. Always raised BEFORE commit."""


# ── zona bbox (shared resolution: zonas_operativas extent + margin) ──────────


def resolver_bbox_zonas(
    db: Session, margen_deg: float = MARGEN_BBOX_DEG
) -> tuple[float, float, float, float]:
    """(minx, miny, maxx, maxy) of every operational zone, plus a margin.

    Fail-closed on an empty ``zonas_operativas``: an ETL that guessed a
    bbox would download a province-wide 38 MB payload (or the wrong
    corner) and register it as if it were the zona. No zonas → no extent
    → no download.
    """
    fila = db.execute(
        text("SELECT ST_Extent(geometria)::text FROM zonas_operativas")
    ).scalar_one_or_none()
    if not fila:
        raise EtlAssertionError(
            "zonas_operativas está vacía — no se puede resolver el bbox de la zona; "
            "nada se descargó ni se escribió"
        )
    # BOX(minx miny, maxx maxy) — the canonical ST_Extent text form.
    interior = fila.removeprefix("BOX(").removesuffix(")")
    par_min, par_max = interior.split(",")
    minx, miny = (float(v) for v in par_min.split())
    maxx, maxy = (float(v) for v in par_max.split())
    return minx - margen_deg, miny - margen_deg, maxx + margen_deg, maxy + margen_deg


# ── WFS paging (injectable fetch for hermetic tests) ─────────────────────────


def url_pagina(bbox: tuple[float, float, float, float], start_index: int, count: int) -> str:
    """One GetFeature page URL: bbox-filtered, JSON, EPSG:4326."""
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": WFS_LAYER,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:4326",
        "startIndex": str(start_index),
        "count": str(count),
    }
    return f"{WFS_BASE}?{urlencode(params)}"


def _fetcher_real(requests_module: Any) -> Callable[[str], dict[str, Any]]:
    """URL → parsed JSON GeoJSON, with the HTTP status surfaced fail-closed."""

    def _get(url: str) -> dict[str, Any]:
        response = requests_module.get(url, timeout=120)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "features" not in payload:
            # GeoServer answers XML exception reports with HTTP 200 in some
            # misconfigurations; a dict without features is never valid here.
            raise EtlAssertionError(f"respuesta WFS inesperada (sin features): {url}")
        return payload

    return _get


def bajar_features(
    bbox: tuple[float, float, float, float],
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    page_size: int = PAGE_SIZE,
    max_features: int = 20_000,
) -> list[dict[str, Any]]:
    """Walk the WFS pages until one comes back short. Duplicates by id removed.

    ``max_features`` is the runaway bound: the zona bbox measured ~212
    features live (2026-11-19); an order of magnitude above that means
    the bbox resolution (or the layer) is not what we think, and the load
    refuses instead of sucking the province in.
    """
    features: dict[int, dict[str, Any]] = {}
    start = 0
    while True:
        pagina = fetch_json(url_pagina(bbox, start, page_size))
        lote = pagina.get("features") or []
        for feature in lote:
            fid = _feature_id(feature)
            if fid is None:
                raise EtlAssertionError(f"feature sin id numérico: {feature.get('id')!r}")
            features[fid] = feature
        if len(lote) < page_size:
            break
        start += page_size
        if len(features) > max_features:
            raise EtlAssertionError(
                f"la descarga superó {max_features} features — bbox o capa erróneos, no se carga"
            )
    return [features[k] for k in sorted(features)]


# ── load (one transaction, assertions before commit) ─────────────────────────


def _feature_id(feature: dict[str, Any]) -> int | None:
    """The WFS numeric feature id («carta_suelo_50mil_2025.17» → 17)."""
    fid: Any = feature.get("id")
    if isinstance(fid, str) and "." in fid:
        fid = fid.rsplit(".", 1)[1]
    try:
        return int(fid)
    except (TypeError, ValueError):
        props = feature.get("properties") or {}
        try:
            # str() first: props["id"] may be None, and int(None) is a
            # TypeError mypy refuses — 'None' stringifies into ValueError.
            return int(str(props.get("id")))
        except (TypeError, ValueError):
            return None


def _params(feature: dict[str, Any], fecha: datetime) -> dict[str, Any] | None:
    """INSERT params for one feature; ``None`` when it carries no geometry."""
    geom = feature.get("geometry")
    if not geom or not geom.get("coordinates"):
        return None
    fid = _feature_id(feature)
    if fid is None:
        raise EtlAssertionError(f"feature sin id numérico: {feature.get('id')!r}")
    props = feature.get("properties") or {}
    params: dict[str, Any] = {"id": fid, "geojson": json.dumps(geom), "fecha": fecha}
    for col, prop in _COLUMNAS:
        params[col] = props.get(prop)
    return params


def cargar_suelos(
    db: Session,
    features: list[dict[str, Any]],
    *,
    fecha: datetime | None = None,
) -> int:
    """TRUNCATE → insert → assert inside ONE transaction. Returns rows stored.

    Assertions (the ``load_suelos_catastro`` contract, adapted):

    1. stored row count == source feature count (features without
       geometry are refused, not silently dropped);
    2. every stored geometry is a valid MULTIPOLYGON in SRID 4326.
    """
    fecha = fecha or datetime.now(timezone.utc)
    db.execute(text("TRUNCATE idecor_suelos_50mil"))
    insertados = 0
    for feature in features:
        params = _params(feature, fecha)
        if params is None:
            raise EtlAssertionError(
                f"feature {feature.get('id')!r} sin geometría — se rehúsa la carga completa"
            )
        db.execute(_INSERT, params)
        insertados += 1

    almacenados = db.execute(text("SELECT count(*) FROM idecor_suelos_50mil")).scalar_one()
    if almacenados != len(features):
        raise EtlAssertionError(f"filas almacenadas {almacenados} != features {len(features)}")
    invalidos = db.execute(
        text(
            "SELECT count(*) FROM idecor_suelos_50mil "
            "WHERE NOT ST_IsValid(geometria) OR ST_SRID(geometria) <> 4326"
        )
    ).scalar_one()
    if invalidos:
        raise EtlAssertionError(f"{invalidos} geometrías inválidas o con SRID distinto de 4326")
    return int(almacenados)


def run_etl(
    db: Session,
    *,
    fetch_json: Callable[[str], dict[str, Any]],
    margen_deg: float = MARGEN_BBOX_DEG,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    """Resolve bbox → download → load. ``fecha_de_bajada`` = one stamp per run."""
    bbox = resolver_bbox_zonas(db, margen_deg)
    features = bajar_features(bbox, fetch_json=fetch_json, page_size=page_size)
    if not features:
        raise EtlAssertionError("el WFS no devolvió features para el bbox de la zona")
    fecha = datetime.now(timezone.utc)
    filas = cargar_suelos(db, features, fecha=fecha)
    db.commit()
    return {
        "bbox": bbox,
        "features": len(features),
        "filas": filas,
        "fecha_de_bajada": fecha.isoformat(),
    }


# ── CLI (module entry point — the container ships only ``app/``) ─────────────


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover — network/CLI
    parser = argparse.ArgumentParser(
        prog="python -m app.domains.geo.etl.idecor_suelos_50mil",
        description="Baja la carta de suelos 1:50.000 de IDECOR para el bbox de la zona "
        "y la carga en idecor_suelos_50mil (refresh completo idempotente).",
    )
    parser.parse_args(argv)

    import requests

    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db:
            resultado = run_etl(db, fetch_json=_fetcher_real(requests))
    except EtlAssertionError as exc:
        print(f"CARGA RECHAZADA: {exc}", file=sys.stderr)
        return EXIT_LOAD_FAILED
    except requests.RequestException as exc:
        print(f"WFS INALCANZABLE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_INFRA_FAILED
    except SQLAlchemyError as exc:
        print(f"ERROR DE BASE DE DATOS: {exc}", file=sys.stderr)
        return EXIT_INFRA_FAILED

    print(
        f"IDECOR suelos 1:50.000 cargado: {resultado['filas']} unidades "
        f"(bbox {resultado['bbox']}, bajada {resultado['fecha_de_bajada']})"
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
