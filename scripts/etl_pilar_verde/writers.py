"""Output writers + simplifiers.

Every file written by this ETL goes through ``write_geojson`` or ``write_json``
— both stamp ``schema_version`` and ``generated_at`` so downstream consumers
(React hook, AI analysis sessions) can validate contracts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape

from scripts.etl_pilar_verde.constants import (
    AGRO_ZONAS_SIMPLIFY_TOLERANCE,
    FORESTACION_KEEP_PROPS,
    SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def simplify_features(
    features: list[dict[str, Any]], tolerance: float = AGRO_ZONAS_SIMPLIFY_TOLERANCE
) -> list[dict[str, Any]]:
    """Run ``shapely.simplify(tolerance, preserve_topology=True)`` on each feature."""
    out: list[dict[str, Any]] = []
    for feature in features:
        geom = feature.get("geometry")
        if geom is None:
            out.append(feature)
            continue
        shapely_geom = shape(geom)
        simplified = shapely_geom.simplify(tolerance, preserve_topology=True)
        out.append(
            {
                "type": "Feature",
                "properties": feature.get("properties") or {},
                "geometry": mapping(simplified),
            }
        )
    return out


def thin_properties(
    features: list[dict[str, Any]], keep: frozenset[str] = FORESTACION_KEEP_PROPS
) -> list[dict[str, Any]]:
    """Keep only a whitelist of properties per feature."""
    out: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        thinned = {k: v for k, v in props.items() if k in keep}
        out.append(
            {
                "type": "Feature",
                "properties": thinned,
                "geometry": feature.get("geometry"),
            }
        )
    return out


def write_geojson(
    path: Path,
    features: list[dict[str, Any]],
    *,
    schema_version: str = SCHEMA_VERSION,
    generated_at: str | None = None,
    source: str | None = None,
) -> None:
    """Write a GeoJSON FeatureCollection with metadata stamped in.

    The GeoJSON spec doesn't forbid extra top-level members, so we tuck
    ``metadata.schema_version`` + ``metadata.generated_at`` alongside the
    standard ``type`` / ``features`` fields. Consumers that validate strictly
    against the GeoJSON RFC will still read ``features`` correctly.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {
        "schema_version": schema_version,
        "generated_at": generated_at or _now_iso(),
    }
    if source is not None:
        metadata["source"] = source
    payload = {
        "type": "FeatureCollection",
        "metadata": metadata,
        "features": features,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    logger.info("write_geojson path=%s features=%d", path, len(features))


def write_json(
    path: Path,
    payload: dict[str, Any],
    *,
    schema_version: str = SCHEMA_VERSION,
    generated_at: str | None = None,
) -> None:
    """Write a plain JSON dict with ``schema_version`` + ``generated_at`` merged in."""
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {
        "schema_version": schema_version,
        "generated_at": generated_at or _now_iso(),
        **payload,
    }
    path.write_text(
        json.dumps(merged, ensure_ascii=False, separators=(",", ":"), indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("write_json path=%s keys=%s", path, sorted(merged.keys()))


def build_bpa_historico_features(
    enriched_parcels: list[dict[str, Any]],
    catastro_features: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the ``bpa_historico.geojson`` FeatureCollection.

    One feature per parcel with ``años_bpa >= 1``:
    - Geometry is pulled from the matching catastro feature (by ``Nro_Cuenta``
      normalised through :func:`normalize_cuenta`). Parcels without a catastro
      match are silently dropped — the map wouldn't have anywhere to draw them.
    - Properties carry the commitment depth (``años_bpa``), the sorted year
      list (``años_lista``), the most recent ``n_explotacion``, and the
      ``bpa_activa_2025`` flag.

    ``n_explotacion_ultima`` resolves to the 2025 name when the parcel is
    still active; otherwise to the name from the most recent historical
    year. Returns ``""`` when no name can be resolved (defensive default so
    the frontend never renders ``undefined``).
    """
    from scripts.etl_pilar_verde.join import normalize_cuenta

    # Index catastro by normalised cuenta so lookup is O(1).
    cuenta_to_geom: dict[str, Any] = {}
    for feature in catastro_features:
        props = feature.get("properties") or {}
        cuenta = normalize_cuenta(props.get("Nro_Cuenta"))
        if cuenta is None:
            continue
        if feature.get("geometry") is None:
            continue
        cuenta_to_geom[cuenta] = feature["geometry"]

    features: list[dict[str, Any]] = []
    for parcel in enriched_parcels:
        anios = int(parcel.get("años_bpa") or 0)
        if anios < 1:
            continue
        cuenta = parcel.get("nro_cuenta")
        if cuenta is None or cuenta not in cuenta_to_geom:
            continue

        bpa_2025 = parcel.get("bpa_2025") or None
        historico = parcel.get("bpa_historico") or {}
        lista: list[str] = list(parcel.get("años_lista") or [])

        if bpa_2025 is not None:
            n_explotacion = str(bpa_2025.get("n_explotacion") or "")
        elif historico:
            # Most recent historical year — sort keys ASC and pick the last.
            last_year = sorted(historico.keys())[-1]
            n_explotacion = str(historico[last_year])
        else:
            n_explotacion = ""

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "nro_cuenta": cuenta,
                    "años_bpa": anios,
                    "años_lista": lista,
                    "n_explotacion_ultima": n_explotacion,
                    "bpa_activa_2025": bpa_2025 is not None,
                },
                "geometry": cuenta_to_geom[cuenta],
            }
        )

    return {"type": "FeatureCollection", "features": features}


def geojson_bbox(feature_or_collection: dict[str, Any]) -> tuple[float, float, float, float]:
    """Compute ``(minx, miny, maxx, maxy)`` in the source CRS."""
    if feature_or_collection.get("type") == "FeatureCollection":
        features = feature_or_collection.get("features") or []
        if not features:
            raise ValueError("empty FeatureCollection")
        geom = shape(features[0]["geometry"])
        for feat in features[1:]:
            geom = geom.union(shape(feat["geometry"]))
    elif feature_or_collection.get("type") == "Feature":
        geom = shape(feature_or_collection["geometry"])
    else:
        geom = shape(feature_or_collection)
    return geom.bounds
