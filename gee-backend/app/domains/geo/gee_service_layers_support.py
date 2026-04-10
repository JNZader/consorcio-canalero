"""Support helpers for GEE layer catalog and road-network queries."""

from __future__ import annotations

from typing import Any, Dict, List

AVAILABLE_LAYERS: List[Dict[str, str]] = [
    {
        "id": "zona",
        "nombre": "Zona Consorcio",
        "descripcion": "Limite del area del consorcio",
    },
    {
        "id": "candil",
        "nombre": "Cuenca Candil",
        "descripcion": "Cuenca hidrografica Candil",
    },
    {"id": "ml", "nombre": "Cuenca ML", "descripcion": "Cuenca hidrografica ML"},
    {
        "id": "noroeste",
        "nombre": "Cuenca Noroeste",
        "descripcion": "Cuenca hidrografica Noroeste",
    },
    {
        "id": "norte",
        "nombre": "Cuenca Norte",
        "descripcion": "Cuenca hidrografica Norte",
    },
    {
        "id": "caminos",
        "nombre": "Red Vial",
        "descripcion": "Red de caminos rurales",
    },
]

CONSORCIO_COLORS = [
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#46f0f0",
    "#f032e6",
    "#bcf60c",
    "#fabebe",
    "#008080",
    "#e6beff",
    "#9a6324",
    "#fffac8",
    "#800000",
    "#aaffc3",
    "#808000",
    "#ffd8b1",
    "#000075",
    "#808080",
    "#000000",
]


def get_layer_mapping(asset_path) -> dict[str, str]:
    return {
        "zona": asset_path("zona_cc_ampliada"),
        "candil": asset_path("candil"),
        "ml": asset_path("ml"),
        "noroeste": asset_path("noroeste"),
        "norte": asset_path("norte"),
        "caminos": asset_path("red_vial"),
    }


def fetch_layer_geojson(layer_name: str, *, ensure_initialized, asset_path, ee_module) -> Dict[str, Any]:
    ensure_initialized()
    layer_mapping = get_layer_mapping(asset_path)
    if layer_name not in layer_mapping:
        raise ValueError(
            f"Capa '{layer_name}' no encontrada. Disponibles: {list(layer_mapping.keys())}"
        )
    return ee_module.FeatureCollection(layer_mapping[layer_name]).getInfo()


def get_available_layers_payload() -> List[Dict[str, str]]:
    return [dict(layer) for layer in AVAILABLE_LAYERS]


def fetch_red_vial_features(*, ensure_initialized, asset_path, ee_module) -> list[dict[str, Any]]:
    ensure_initialized()
    caminos = ee_module.FeatureCollection(asset_path("red_vial"))
    return caminos.getInfo().get("features", [])


def ensure_consorcio_bucket(
    stats_map: Dict[str, Dict[str, Any]],
    *,
    nombre: str,
    codigo: str,
) -> Dict[str, Any]:
    if nombre not in stats_map:
        stats_map[nombre] = {
            "nombre": nombre,
            "codigo": codigo,
            "tramos": 0,
            "longitud_km": 0.0,
            "por_jerarquia": {},
            "por_superficie": {},
        }
    return stats_map[nombre]


def update_breakdown(
    breakdown: Dict[str, Dict[str, float | int]],
    key: str,
    length_km: float,
) -> None:
    if key not in breakdown:
        breakdown[key] = {"tramos": 0, "km": 0.0}
    breakdown[key]["tramos"] += 1
    breakdown[key]["km"] += length_km


def fetch_caminos_by_consorcio(
    consorcio_codigo: str,
    *,
    ensure_initialized,
    asset_path,
    ee_module,
) -> Dict[str, Any]:
    ensure_initialized()
    caminos = ee_module.FeatureCollection(asset_path("red_vial"))
    filtered = caminos.filter(ee_module.Filter.eq("ccc", consorcio_codigo))
    geojson = filtered.getInfo()
    if len(geojson.get("features", [])) == 0:
        geojson = caminos.filter(ee_module.Filter.eq("ccc", consorcio_codigo.upper())).getInfo()
    return geojson


def fetch_caminos_by_consorcio_nombre(
    consorcio_nombre: str,
    *,
    ensure_initialized,
    asset_path,
    ee_module,
) -> Dict[str, Any]:
    ensure_initialized()
    caminos = ee_module.FeatureCollection(asset_path("red_vial"))
    return caminos.filter(ee_module.Filter.eq("ccn", consorcio_nombre)).getInfo()
