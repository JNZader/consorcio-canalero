"""Official APRHI SR PA inventory (static GeoJSON) + staff publication ids."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SR_PA_ID_PREFIX = "srpa:"


def sr_pa_canal_id(properties: dict[str, Any] | None) -> str:
    props = properties or {}
    identificador = str(props.get("Identificador") or "").strip()
    if identificador:
        return f"{SR_PA_ID_PREFIX}{identificador}"
    object_id = props.get("OBJECTID")
    if object_id is None:
        object_id = props.get("id")
    return f"{SR_PA_ID_PREFIX}{object_id if object_id is not None else 'sin-id'}"


def sr_pa_geojson_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "consorcio-web" / "public" / "capas" / "aprhi_sr_pa.geojson"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("aprhi_sr_pa.geojson")


@lru_cache(maxsize=1)
def load_sr_pa_collection() -> dict[str, Any]:
    with sr_pa_geojson_path().open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("SR PA catalog is not a FeatureCollection")
    return payload


def iter_sr_pa_features() -> list[dict[str, Any]]:
    features = load_sr_pa_collection().get("features") or []
    return [feature for feature in features if isinstance(feature, dict)]


def append_published_sr_pa(
    relevados: list[dict[str, Any]],
    sr_pa_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Append staff-published SR PA works into public relevados.

    Unpublished stays off the citizen map. KMZ features are copied, never rewritten.
    """
    merged = list(relevados)
    for feature in sr_pa_features:
        props = feature.get("properties") or {}
        if not props.get("publicado"):
            continue
        canal_id = feature.get("id") or props.get("id") or sr_pa_canal_id(props)
        nombre = props.get("nombre_publico") or props.get("Nombre_Obra") or canal_id
        merged.append(
            {
                "type": "Feature",
                "id": canal_id,
                "geometry": feature.get("geometry"),
                "properties": {
                    "id": canal_id,
                    "nombre": nombre,
                    "estado": "relevado",
                    "source_style": "aprhi_sr_pa",
                    "origen": "sr_pa",
                    "Identificador": props.get("Identificador"),
                    "Estado_Registro": props.get("Estado_Registro"),
                },
            }
        )
    return merged
