"""Emitters for the three static assets the React frontend consumes.

- ``relevados.geojson`` / ``propuestas.geojson`` — GeoJSON FeatureCollections,
  one LineString feature per canal.  ``metadata.schema_version`` is pinned at
  ``"1.0"`` (frozen per the spec) and ``metadata.generated_at`` is an ISO-8601
  UTC timestamp.  Set ``ETL_GENERATED_AT`` in the env for reproducible
  byte-identical output during tests.
- ``index.json`` — the per-canal metadata registry consumed by the store to
  bootstrap toggle IDs without parsing the GeoJSONs upfront.

Both writers deliberately use compact JSON separators (no indent) on the
GeoJSON side to keep the on-disk payload minimal; ``index.json`` is indented
for human readability (it's smaller and read by hand during debugging).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

SCHEMA_VERSION: str = "1.0"


def _now_iso() -> str:
    """Return the current timestamp in ISO-8601 UTC with a trailing ``Z``.

    Honours the ``ETL_GENERATED_AT`` env var so tests can pin the value for
    golden-file comparisons.
    """
    override = os.environ.get("ETL_GENERATED_AT")
    if override:
        return override
    now = datetime.now(tz=timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CanalFeature:
    """In-memory representation of one canal feature, pre-serialisation.

    The fields here are the UNION of the properties the frontend will see
    PLUS the geometry coords.  ``write_geojson_canales`` splits them into
    the GeoJSON ``properties`` dict and ``geometry.coordinates`` array.
    """

    id: str
    codigo: str | None
    nombre: str
    descripcion: str | None
    estado: Literal["relevado", "propuesto"]
    longitud_m: float
    longitud_declarada_m: float | None
    prioridad: str | None
    featured: bool
    tramo_folder: str | None
    source_style: str | None
    coords: list[tuple[float, float]] = field(default_factory=list)


@dataclass(frozen=True)
class IndexMeta:
    """One row of the ``index.json`` per-canal metadata registry."""

    id: str
    nombre: str
    codigo: str | None
    prioridad: str | None
    longitud_m: float
    featured: bool
    estado: Literal["relevado", "propuesto"]


def _feature_to_geojson(feature: CanalFeature) -> dict[str, Any]:
    """Serialise a ``CanalFeature`` into a GeoJSON Feature dict."""
    return {
        "type": "Feature",
        "properties": {
            "id": feature.id,
            "codigo": feature.codigo,
            "nombre": feature.nombre,
            "descripcion": feature.descripcion,
            "estado": feature.estado,
            "longitud_m": round(feature.longitud_m, 1),
            "longitud_declarada_m": feature.longitud_declarada_m,
            "prioridad": feature.prioridad,
            "featured": feature.featured,
            "tramo_folder": feature.tramo_folder,
            "source_style": feature.source_style,
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon, lat] for lon, lat in feature.coords],
        },
    }


def write_geojson_canales(
    features: list[CanalFeature],
    out_path: Path,
    *,
    schema_version: str = SCHEMA_VERSION,
    generated_at: str | None = None,
) -> None:
    """Write a GeoJSON FeatureCollection with ``metadata.schema_version`` + ``metadata.generated_at``.

    The ``metadata`` sub-object is an extra top-level key alongside the RFC
    7946 ``type`` / ``features`` fields; strict GeoJSON consumers ignore
    unknown top-level keys, so this stays compatible.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = generated_at or _now_iso()

    payload: dict[str, Any] = {
        "type": "FeatureCollection",
        "metadata": {
            "schema_version": schema_version,
            "generated_at": stamp,
        },
        "features": [_feature_to_geojson(f) for f in features],
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "write_geojson_canales path=%s features=%d schema=%s",
        out_path,
        len(features),
        schema_version,
    )


def _index_meta_to_dict(meta: IndexMeta) -> dict[str, Any]:
    """Serialise IndexMeta; drop the ``prioridad`` key when it's None AND estado=relevado.

    The spec says `prioridad?` is optional and absent on relevados; we emit
    it as ``null`` for propuestos to keep the shape uniform across the list
    but drop it entirely for relevados so consumers can branch cleanly.
    """
    d = asdict(meta)
    if meta.estado == "relevado" and meta.prioridad is None:
        d.pop("prioridad", None)
    return d


def write_index_json(
    relevados_meta: list[IndexMeta],
    propuestas_meta: list[IndexMeta],
    out_path: Path,
    *,
    schema_version: str = SCHEMA_VERSION,
    generated_at: str | None = None,
) -> None:
    """Write ``index.json`` — the per-canal metadata registry."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = generated_at or _now_iso()

    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "generated_at": stamp,
        "counts": {
            "relevados": len(relevados_meta),
            "propuestas": len(propuestas_meta),
            "total": len(relevados_meta) + len(propuestas_meta),
        },
        "relevados": [_index_meta_to_dict(m) for m in relevados_meta],
        "propuestas": [_index_meta_to_dict(m) for m in propuestas_meta],
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "write_index_json path=%s relevados=%d propuestas=%d",
        out_path,
        len(relevados_meta),
        len(propuestas_meta),
    )
