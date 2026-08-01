"""Class-break definitions shared by tile rendering and zonal profiles.

Leaf module by design: it MUST NOT import the tile service (geo-worker code) so
the API process can read the same breaks without pulling in rendering
dependencies. ``tile_service_support`` re-exports ``RANGE_CONFIGS`` from here for
source compatibility.

The ficha percentages MUST match the legend the user reads on the map, so both
paths read these definitions -- two copies would drift.

Bin-edge convention: every bin is half-open ``[min, max)`` except the last one of
each list, which is closed ``[min, max]`` so the raster maximum is never dropped.
"""

from __future__ import annotations

RANGE_CONFIGS: dict[str, list[dict]] = {
    "flood_risk": [
        {"label": "Bajo", "min": 0, "max": 30, "color": "#1a9850"},
        {"label": "Medio", "min": 30, "max": 55, "color": "#fee08b"},
        {"label": "Alto", "min": 55, "max": 75, "color": "#fc8d59"},
        {"label": "Crítico", "min": 75, "max": 100, "color": "#d73027"},
    ],
    "drainage_need": [
        {"label": "Bajo", "min": 0, "max": 30, "color": "#fff7ec"},
        {"label": "Medio", "min": 30, "max": 50, "color": "#fdd49e"},
        {"label": "Alto", "min": 50, "max": 70, "color": "#e34a33"},
        {"label": "Crítico", "min": 70, "max": 100, "color": "#b30000"},
    ],
    "twi": [
        {"label": "Seco", "min": 6, "max": 9, "color": "#f7fbff"},
        {"label": "Normal", "min": 9, "max": 12, "color": "#6baed6"},
        {"label": "Húmedo", "min": 12, "max": 16, "color": "#2171b5"},
        {"label": "Muy Húmedo", "min": 16, "max": 19, "color": "#08306b"},
    ],
    "hand": [
        {"label": "Muy Bajo (<0.5m)", "min": 0, "max": 0.5, "color": "#bd0026"},
        {"label": "Bajo (0.5-1m)", "min": 0.5, "max": 1.0, "color": "#f03b20"},
        {"label": "Medio (1-2m)", "min": 1.0, "max": 2.0, "color": "#fd8d3c"},
        {"label": "Alto (>2m)", "min": 2.0, "max": 4.0, "color": "#ffffb2"},
    ],
    "slope": [
        {
            "label": "Muy baja zona I (<0.5 m/1000m)",
            "min": 0,
            "max": 0.0265,
            "color": "#0b7d3b",
        },
        {
            "label": "Muy baja zona II (0.5-2.1 m/1000m)",
            "min": 0.0265,
            "max": 0.1227,
            "color": "#1a9850",
        },
        {
            "label": "Baja zona (2.1-4.2 m/1000m)",
            "min": 0.1227,
            "max": 0.2420,
            "color": "#91cf60",
        },
        {
            "label": "Suave zona (4.2-6.9 m/1000m)",
            "min": 0.2420,
            "max": 0.3964,
            "color": "#d9ef8b",
        },
        {
            "label": "Moderada zona (6.9-15.3 m/1000m)",
            "min": 0.3964,
            "max": 0.8754,
            "color": "#fc8d59",
        },
        {
            "label": "Alta puntual (>15.3 m/1000m)",
            "min": 0.8754,
            "max": 90.0,
            "color": "#d73027",
        },
    ],
    "dem_raw": [
        {"label": "100-105m", "min": 100, "max": 105, "color": "#08306b"},
        {"label": "105-110m", "min": 105, "max": 110, "color": "#2171b5"},
        {"label": "110-115m", "min": 110, "max": 115, "color": "#6baed6"},
        {"label": "115-120m", "min": 115, "max": 120, "color": "#a1d99b"},
        {"label": "120-125m", "min": 120, "max": 125, "color": "#ffffbf"},
        {"label": "125-130m", "min": 125, "max": 130, "color": "#fdae61"},
        {"label": "130-135m", "min": 130, "max": 135, "color": "#f46d43"},
        {"label": "135-145m", "min": 135, "max": 145, "color": "#a50026"},
    ],
    "flow_acc": [
        {"label": "Mínimo (1 celda)", "min": 1, "max": 1.5, "color": "#ffffcc"},
        {"label": "Muy bajo (2-6)", "min": 1.5, "max": 6, "color": "#d9f0a3"},
        {"label": "Bajo (6-53)", "min": 6, "max": 53, "color": "#addd8e"},
        {"label": "Moderado (53-210)", "min": 53, "max": 210, "color": "#78c679"},
        {"label": "Alto (210-6.525)", "min": 210, "max": 6525.22, "color": "#41b6c4"},
        {
            "label": "Muy alto (>6.525)",
            "min": 6525.22,
            "max": 487848,
            "color": "#0c2c84",
        },
    ],
    "profile_curvature": [
        {"label": "Cóncavo", "min": -0.001, "max": -0.0002, "color": "#b2182b"},
        {"label": "Plano", "min": -0.0002, "max": 0.0002, "color": "#f7f7f7"},
        {"label": "Convexo", "min": 0.0002, "max": 0.001, "color": "#2166ac"},
    ],
    "tpi": [
        {"label": "Valle", "min": -1.5, "max": -0.5, "color": "#b2182b"},
        {"label": "Llano", "min": -0.5, "max": 0.5, "color": "#f7f7f7"},
        {"label": "Cresta", "min": 0.5, "max": 1.5, "color": "#2166ac"},
    ],
}
