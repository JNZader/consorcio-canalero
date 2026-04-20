"""Constants for the Pilar Verde ETL.

This module centralises every piece of metadata that tends to drift across
IDECor vintages (BPA layer naming quirks, output paths, the 22 BPA practicas,
the 4 ejes, simplification tolerances and exit codes).  Keeping them here — and
importing from here everywhere — is what makes this ETL resilient to IDECor's
naming inconsistencies.

Why the quirks: the IDECor WFS publishes the same conceptual layer under three
different naming shapes across years.  The ETL MUST not hardcode the year into
the layer name; the dict below is the single source of truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# IDECor WFS endpoint + layer catalogue
# ---------------------------------------------------------------------------

# IDECor publishes the same WFS layers on TWO hostnames.  ``gn-idecor`` is the
# primary — exploration validated it as faster and more stable.  ``idecor-ws``
# is the historical default and stays as a fallback (it can 504 during peak
# hours; the fetch helper iterates hosts in order inside every retry attempt).
WFS_HOSTS: Final[tuple[str, ...]] = (
    "gn-idecor.mapascordoba.gob.ar",
    "idecor-ws.mapascordoba.gob.ar",
)


def build_wfs_url(host: str) -> str:
    """Return the full IDECor WFS endpoint for a given hostname."""
    return f"https://{host}/geoserver/idecor/ows"


# Kept for backwards compatibility with tests / downstream imports that expect
# a single URL.  Points at the PRIMARY host — new code should iterate
# ``WFS_HOSTS`` via ``build_wfs_url`` instead.
IDECOR_WFS_URL: Final[str] = build_wfs_url(WFS_HOSTS[0])

# BPA layer naming drift across vintages — DO NOT collapse into f-strings.
# 2023-2025 use `bpa_YYYY`, 2021-2022 use `bpa_YYYY_v`, 2019-2020 `bpaYYYY`.
BPA_LAYERS: Final[dict[int, str]] = {
    2025: "idecor:bpa_2025",
    2024: "idecor:bpa_2024",
    2023: "idecor:bpa_2023",
    2022: "idecor:bpa_2022_v",
    2021: "idecor:bpa_2021_v",
    2020: "idecor:bpa2020",
    2019: "idecor:bpa2019",
}

AGRO_ACEPTADA: Final[str] = "idecor:agricultura_v_agro_aceptada_cuentas"
AGRO_PRESENTADA: Final[str] = "idecor:agricultura_v_agro_presentada_cuentas"
AGRO_ZONAS: Final[str] = "idecor:agricultura_agro_zonas"
AGRO_GRILLA: Final[str] = "idecor:agro_grilla_dist5"
FORESTACION: Final[str] = "idecor:agricultura_agro_porcentaje_forestacion"

REQUIRED_LAYERS: Final[tuple[str, ...]] = (
    BPA_LAYERS[2025],
    AGRO_ACEPTADA,
    AGRO_PRESENTADA,
)

# ---------------------------------------------------------------------------
# BPA schema — 22 practicas + 4 ejes (verbatim from IDECor bpa_2025 GetFeature)
# ---------------------------------------------------------------------------

BPA_PRACTICAS: Final[tuple[str, ...]] = (
    "capacitacion",
    "tranqueras_abiertas",
    "polinizacion",
    "integ_comunidad",
    "nutricion_suelo",
    "rotacion_gramineas",
    "pasturas_implantadas",
    "sistema_terraza",
    "bioinsumos",
    "manejo_de_cultivo_int",
    "trazabilidad",
    "tecn_pecuaria",
    "agricultura_de_precision",
    "economia_circular",
    "participacion_grup_asociativo",
    "indiacagro",
    "caminos_rurales",
    "ag_tech",
    "bpa_tutor",
    "corredores_bio",
    "riego_precision",
)

BPA_EJES: Final[tuple[str, ...]] = ("persona", "planeta", "prosperidad", "alianza")

# ---------------------------------------------------------------------------
# Retry / backoff
# ---------------------------------------------------------------------------

RETRY_ATTEMPTS: Final[int] = 3
RETRY_WAIT_MIN_SECONDS: Final[int] = 2
RETRY_WAIT_MAX_SECONDS: Final[int] = 8

# ---------------------------------------------------------------------------
# Simplification thresholds (design §3)
# ---------------------------------------------------------------------------

AGRO_ZONAS_SIMPLIFY_TOLERANCE: Final[float] = 0.0001  # ~11 m at zona latitude
FORESTACION_KEEP_PROPS: Final[frozenset[str]] = frozenset(
    {"nro_cuenta", "forest_obligatoria"}
)

# ---------------------------------------------------------------------------
# Schema version / metadata
# ---------------------------------------------------------------------------

# Generic (per-file default) schema version — GeoJSON outputs, bpa_enriched,
# bpa_history still live at 1.0 (no field changes).
SCHEMA_VERSION: Final[str] = "1.0"

# aggregates.json bumped to 1.1 for the Phase 0 addendum (additive, backward-
# compatible): 6 new historical-coverage KPIs + evolucion_anual under ``bpa``.
AGGREGATES_SCHEMA_VERSION: Final[str] = "1.1"

# ---------------------------------------------------------------------------
# Coordinate reference systems
# ---------------------------------------------------------------------------

CRS_LATLON: Final[str] = "EPSG:4326"
CRS_IDECOR: Final[str] = "EPSG:22174"  # Argentina POSGAR — IDECor native CRS
CRS_METRIC_FOR_AREA: Final[str] = "EPSG:22174"

# ---------------------------------------------------------------------------
# Filesystem layout (absolute paths resolved at runtime from REPO_ROOT)
# ---------------------------------------------------------------------------

# Scripts live at <repo>/scripts/etl_pilar_verde/<this file>.
# Parents: constants.py -> etl_pilar_verde/ -> scripts/ -> <repo>.
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

KML_SOURCE: Final[Path] = (
    REPO_ROOT / "gee" / "zona_cc_ampliada" / "CC 10 de mayo ampliado2.kml"
)

CATASTRO_SOURCE: Final[Path] = (
    REPO_ROOT / "consorcio-web" / "public" / "data" / "catastro_rural_cu.geojson"
)

OUT_CAPAS_DIR: Final[Path] = (
    REPO_ROOT / "consorcio-web" / "public" / "capas" / "pilar-verde"
)
OUT_DATA_DIR: Final[Path] = (
    REPO_ROOT / "consorcio-web" / "public" / "data" / "pilar-verde"
)

OUTPUT_FILES: Final[dict[str, Path]] = {
    "zona_ampliada": OUT_CAPAS_DIR / "zona_ampliada.geojson",
    "bpa_2025": OUT_CAPAS_DIR / "bpa_2025.geojson",
    "agro_aceptada": OUT_CAPAS_DIR / "agro_aceptada.geojson",
    "agro_presentada": OUT_CAPAS_DIR / "agro_presentada.geojson",
    "agro_zonas": OUT_CAPAS_DIR / "agro_zonas.geojson",
    "porcentaje_forestacion": OUT_CAPAS_DIR / "porcentaje_forestacion.geojson",
    "bpa_enriched": OUT_DATA_DIR / "bpa_enriched.json",
    "bpa_history": OUT_DATA_DIR / "bpa_history.json",
    "aggregates": OUT_DATA_DIR / "aggregates.json",
}

# ---------------------------------------------------------------------------
# Exit codes (design §3)
# ---------------------------------------------------------------------------

EXIT_OK: Final[int] = 0
EXIT_REQUIRED_LAYER_EMPTY: Final[int] = 1
EXIT_IDECOR_UNREACHABLE: Final[int] = 2
EXIT_KML_PARSE_FAILURE: Final[int] = 3
EXIT_ZONA_MISSING: Final[int] = 4
