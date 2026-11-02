"""IDECOR WFS layers verified against GetCapabilities on 2026-11-02.

Host: https://gn-idecor.mapascordoba.gob.ar/geoserver/idecor/ows
The names below are the `<Name>` values returned for these layers. Nearby
aliases (`lc_cursos_de_agua_aprhi`, `lg_…`, `nono_…`) are other products and
are not the layers the owner asked for.
"""

from __future__ import annotations

from typing import Final

IDECOR_ATTRIBUTION: Final[str] = (
    "Fuente: IDECOR — Infraestructura de Datos Espaciales de la Provincia de Córdoba"
)

# Official consortium boundary, APRHI watercourses, hydrographic basins, irrigation canals.
IDECOR_LAYER_NAMES: Final[dict[str, str]] = {
    "consorcios": "idecor:consorcios_canaleros",
    "cursos": "idecor:cursos_de_agua_aprhi",
    "cuencas": "idecor:cuencas_hidrograficas",
    "canales_riego": "idecor:canales_riego",
}

# Parcel layer used by the padrón work. Verified in the same capabilities document.
IDECOR_PARCELAS_BV: Final[str] = "idecor:parcelas_bv"

# Properties copied into the GeoJSON. Everything else is dropped so a future
# schema change cannot leak a name or a tax id into the tile.
PUBLIC_PROPERTIES: Final[frozenset[str]] = frozenset(
    {"nombre", "name", "nom", "codigo", "descripcion", "tipo"}
)


def public_feature(feature: dict) -> dict:
    """Keep geometry and the public name fields. Drop everything else."""
    props = feature.get("properties") or {}
    kept = {key: props.get(key) for key in PUBLIC_PROPERTIES if props.get(key) not in (None, "")}
    return {
        "type": "Feature",
        "geometry": feature.get("geometry"),
        "properties": kept,
    }
