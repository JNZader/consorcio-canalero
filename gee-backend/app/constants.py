"""
Constantes centralizadas del sistema.
Valores que deben ser consistentes en toda la aplicacion.
"""

from typing import Dict

# ===========================================
# CONSORCIO CONFIGURATION
# ===========================================

# Total area of the consorcio in hectares
CONSORCIO_AREA_HA: int = 88277

# Total kilometers of rural roads maintained
CONSORCIO_KM_CAMINOS: int = 753

# ===========================================
# CUENCAS (Watersheds)
# ===========================================

# Area per cuenca in hectares
CUENCA_AREAS_HA: Dict[str, int] = {
    "candil": 18800,
    "ml": 18900,
    "noroeste": 18500,
    "norte": 18300,
}

# Colors for visualization (hex codes)
CUENCA_COLORS: Dict[str, str] = {
    "candil": "#2196F3",    # Blue
    "ml": "#4CAF50",        # Green
    "noroeste": "#FF9800",  # Orange
    "norte": "#9C27B0",     # Purple
}

# Cuenca display names
CUENCA_NOMBRES: Dict[str, str] = {
    "candil": "Candil",
    "ml": "ML",
    "noroeste": "Noroeste",
    "norte": "Norte",
}

# Valid cuenca IDs
CUENCA_IDS: list[str] = list(CUENCA_AREAS_HA.keys())

# Total area of all cuencas
TOTAL_CUENCAS_HA: int = sum(CUENCA_AREAS_HA.values())

# ===========================================
# MAP CONFIGURATION
# ===========================================

# Default map center (centro de la zona del consorcio)
MAP_CENTER_LAT: float = -32.548
MAP_CENTER_LNG: float = -62.542

# Default zoom level
MAP_DEFAULT_ZOOM: int = 11

# Map bounds
MAP_BOUNDS = {
    "north": -32.3,
    "south": -33.0,
    "east": -62.3,
    "west": -63.1,
}

# ===========================================
# ANALYSIS DEFAULTS
# ===========================================

# Default max cloud coverage for Sentinel-2
DEFAULT_MAX_CLOUD: int = 20

# Default days to look back for analysis
DEFAULT_DAYS_BACK: int = 30

# ===========================================
# RATE LIMITS
# ===========================================

# Max suggestions per user per day
MAX_SUGERENCIAS_POR_DIA: int = 5

# Max reports per phone per day
MAX_DENUNCIAS_POR_TELEFONO_DIA: int = 3

# ===========================================
# PAGINATION
# ===========================================

DEFAULT_PAGE_SIZE: int = 10
MAX_PAGE_SIZE: int = 100
