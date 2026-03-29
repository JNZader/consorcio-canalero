"""
Pure calculation functions for operational intelligence.

No database access — only numpy, rasterio, shapely, geopandas, whiteboxtools.
These are the computational building blocks for the intelligence pipeline.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np
from shapely.geometry import LineString, mapping

_wbt = None


def _get_wbt():
    """Lazily initialise a WhiteboxTools instance (verbose off)."""
    global _wbt  # noqa: PLW0603
    if _wbt is None:
        from whitebox import WhiteboxTools

        _wbt = WhiteboxTools()
        _wbt.set_verbose_mode(False)
    return _wbt


# ---------------------------------------------------------------------------
# Default HCI weights
# ---------------------------------------------------------------------------

DEFAULT_HCI_WEIGHTS = {
    "pendiente": 0.15,
    "acumulacion": 0.30,
    "twi": 0.25,
    "dist_canal": 0.15,
    "hist_inundacion": 0.15,
}


# ---------------------------------------------------------------------------
# a) Hydric Criticality Index
# ---------------------------------------------------------------------------


def calcular_indice_criticidad_hidrica(
    pendiente: float,
    acumulacion: float,
    twi: float,
    dist_canal: float,
    hist_inundacion: float,
    pesos: Optional[dict[str, float]] = None,
) -> float:
    """Calculate the Hydric Criticality Index (HCI) for a zone.

    All inputs must be pre-normalized to [0, 1].
    The result is a weighted sum scaled to [0, 100].

    Args:
        pendiente: Normalized mean slope (0-1).
        acumulacion: Normalized mean flow accumulation (0-1).
        twi: Normalized mean TWI (0-1).
        dist_canal: Normalized distance to nearest canal (0-1).
            Closer to canal → higher value (inverted before calling).
        hist_inundacion: Flood history factor (0-1).
        pesos: Custom weight dict. Keys must match DEFAULT_HCI_WEIGHTS.

    Returns:
        HCI score in [0, 100].
    """
    w = pesos if pesos is not None else DEFAULT_HCI_WEIGHTS

    score = (
        w["pendiente"] * pendiente
        + w["acumulacion"] * acumulacion
        + w["twi"] * twi
        + w["dist_canal"] * dist_canal
        + w["hist_inundacion"] * hist_inundacion
    )

    return round(min(max(score * 100.0, 0.0), 100.0), 2)


def clasificar_nivel_riesgo(indice: float) -> str:
    """Classify an HCI score into a risk level.

    Args:
        indice: HCI score 0-100.

    Returns:
        One of: bajo, medio, alto, critico.
    """
    if indice >= 75:
        return "critico"
    if indice >= 50:
        return "alto"
    if indice >= 25:
        return "medio"
    return "bajo"


# ---------------------------------------------------------------------------
# b) Conflict point detection
# ---------------------------------------------------------------------------


def detectar_puntos_conflicto(
    canales_gdf: "gpd.GeoDataFrame",
    caminos_gdf: "gpd.GeoDataFrame",
    drenajes_gdf: "gpd.GeoDataFrame",
    flow_acc_path: str,
    slope_path: str,
    buffer_m: float = 50.0,
    flow_acc_threshold: float = 500.0,
    slope_threshold: float = 5.0,
) -> "gpd.GeoDataFrame":
    """Detect infrastructure conflict points where canals, roads, and drainage cross.

    Uses buffer + intersection to find crossings, then filters by
    flow accumulation > threshold AND slope < threshold at each point.

    Args:
        canales_gdf: Canal linestrings.
        caminos_gdf: Road linestrings.
        drenajes_gdf: Drainage linestrings.
        flow_acc_path: Path to flow accumulation raster.
        slope_path: Path to slope raster.
        buffer_m: Buffer distance in meters for intersection detection.
        flow_acc_threshold: Minimum flow accumulation to flag as conflict.
        slope_threshold: Maximum slope (degrees) to flag as conflict.

    Returns:
        GeoDataFrame with conflict points and attributes.
    """
    import geopandas as gpd
    import rasterio
    from rasterio.transform import rowcol

    conflicts: list[dict[str, Any]] = []

    pairs = [
        ("canal_camino", canales_gdf, caminos_gdf),
        ("canal_drenaje", canales_gdf, drenajes_gdf),
        ("camino_drenaje", caminos_gdf, drenajes_gdf),
    ]

    with rasterio.open(flow_acc_path) as fa_src, rasterio.open(slope_path) as sl_src:
        fa_data = fa_src.read(1)
        sl_data = sl_src.read(1)
        fa_transform = fa_src.transform
        sl_transform = sl_src.transform

        for tipo, gdf_a, gdf_b in pairs:
            if gdf_a.empty or gdf_b.empty:
                continue

            # Buffer the first set and intersect with the second
            buffered = gdf_a.copy()
            buffered["geometry"] = buffered.geometry.buffer(buffer_m)

            intersections = gpd.overlay(
                buffered, gdf_b, how="intersection", keep_geom_type=False
            )

            for _, row in intersections.iterrows():
                centroid = row.geometry.centroid

                # Sample raster values at intersection point
                try:
                    fa_row, fa_col = rowcol(fa_transform, centroid.x, centroid.y)
                    sl_row, sl_col = rowcol(sl_transform, centroid.x, centroid.y)

                    if (
                        0 <= fa_row < fa_data.shape[0]
                        and 0 <= fa_col < fa_data.shape[1]
                    ):
                        fa_val = float(fa_data[fa_row, fa_col])
                    else:
                        fa_val = 0.0

                    if (
                        0 <= sl_row < sl_data.shape[0]
                        and 0 <= sl_col < sl_data.shape[1]
                    ):
                        sl_val = float(sl_data[sl_row, sl_col])
                    else:
                        sl_val = 0.0
                except Exception:
                    fa_val = 0.0
                    sl_val = 0.0

                # Filter: high accumulation AND low slope = problem zone
                if fa_val > flow_acc_threshold and sl_val < slope_threshold:
                    severidad = _clasificar_severidad_conflicto(fa_val, sl_val)
                    conflicts.append(
                        {
                            "tipo": tipo,
                            "geometry": centroid,
                            "descripcion": (
                                f"Cruce {tipo.replace('_', '/')} — "
                                f"acum={fa_val:.0f}, pend={sl_val:.1f}°"
                            ),
                            "severidad": severidad,
                            "acumulacion_valor": fa_val,
                            "pendiente_valor": sl_val,
                        }
                    )

    if not conflicts:
        return gpd.GeoDataFrame(
            columns=[
                "tipo",
                "geometry",
                "descripcion",
                "severidad",
                "acumulacion_valor",
                "pendiente_valor",
            ],
            geometry="geometry",
        )

    return gpd.GeoDataFrame(conflicts, geometry="geometry", crs="EPSG:4326")


def _clasificar_severidad_conflicto(
    acumulacion: float, pendiente: float
) -> str:
    """Classify conflict severity based on accumulation and slope."""
    if acumulacion > 5000 or pendiente < 0.5:
        return "alta"
    if acumulacion > 2000 or pendiente < 2.0:
        return "media"
    return "baja"


# ---------------------------------------------------------------------------
# c) Runoff simulation
# ---------------------------------------------------------------------------


def simular_escorrentia(
    flow_dir_path: str,
    flow_acc_path: str,
    punto_inicio: tuple[float, float],
    lluvia_mm: float,
    max_steps: int = 5000,
) -> dict[str, Any]:
    """Trace downstream from a point following D8 flow direction.

    Args:
        flow_dir_path: Path to D8 flow direction raster.
        flow_acc_path: Path to flow accumulation raster.
        punto_inicio: (lon, lat) starting point.
        lluvia_mm: Rainfall amount in mm (used as multiplier on accumulation).
        max_steps: Safety limit on trace length.

    Returns:
        GeoJSON FeatureCollection with the traced flow path and stats.
    """
    import rasterio
    from rasterio.transform import rowcol

    # D8 direction encoding (WhiteboxTools convention):
    # 1=E, 2=NE, 4=N, 8=NW, 16=W, 32=SW, 64=S, 128=SE
    d8_offsets = {
        1: (0, 1),     # East
        2: (-1, 1),    # NE
        4: (-1, 0),    # North
        8: (-1, -1),   # NW
        16: (0, -1),   # West
        32: (1, -1),   # SW
        64: (1, 0),    # South
        128: (1, 1),   # SE
    }

    with rasterio.open(flow_dir_path) as fd_src:
        fd_data = fd_src.read(1)
        fd_transform = fd_src.transform
        fd_nodata = fd_src.nodata

    with rasterio.open(flow_acc_path) as fa_src:
        fa_data = fa_src.read(1)

    # Start from the given point
    lon, lat = punto_inicio
    try:
        row, col = rowcol(fd_transform, lon, lat)
    except Exception:
        return _empty_runoff_geojson(punto_inicio, lluvia_mm, "Punto fuera del raster")

    coords: list[tuple[float, float]] = [(lon, lat)]
    accumulations: list[float] = []
    visited: set[tuple[int, int]] = set()

    for _ in range(max_steps):
        if (row, col) in visited:
            break
        visited.add((row, col))

        if row < 0 or row >= fd_data.shape[0] or col < 0 or col >= fd_data.shape[1]:
            break

        direction = int(fd_data[row, col])
        if fd_nodata is not None and direction == int(fd_nodata):
            break

        fa_val = float(fa_data[row, col]) if (
            0 <= row < fa_data.shape[0] and 0 <= col < fa_data.shape[1]
        ) else 0.0
        accumulations.append(fa_val * lluvia_mm)

        offset = d8_offsets.get(direction)
        if offset is None:
            break

        row += offset[0]
        col += offset[1]

        # Convert back to geographic coordinates
        x = fd_transform.c + col * fd_transform.a + row * fd_transform.b
        y = fd_transform.f + col * fd_transform.d + row * fd_transform.e
        coords.append((x, y))

    if len(coords) < 2:
        return _empty_runoff_geojson(punto_inicio, lluvia_mm, "No se pudo trazar flujo")

    line = LineString(coords)

    feature = {
        "type": "Feature",
        "geometry": mapping(line),
        "properties": {
            "punto_inicio": list(punto_inicio),
            "lluvia_mm": lluvia_mm,
            "longitud_m": len(coords),
            "acumulacion_max": max(accumulations) if accumulations else 0.0,
            "acumulacion_media": (
                sum(accumulations) / len(accumulations) if accumulations else 0.0
            ),
            "pasos": len(coords),
        },
    }

    return {
        "type": "FeatureCollection",
        "features": [feature],
    }


def _empty_runoff_geojson(
    punto: tuple[float, float], lluvia_mm: float, error: str
) -> dict[str, Any]:
    """Return an empty runoff result with an error message."""
    return {
        "type": "FeatureCollection",
        "features": [],
        "properties": {
            "punto_inicio": list(punto),
            "lluvia_mm": lluvia_mm,
            "error": error,
        },
    }


# ---------------------------------------------------------------------------
# d) Zonification (watershed delineation)
# ---------------------------------------------------------------------------


def generar_zonificacion(
    dem_path: str,
    flow_acc_path: str,
    threshold: int = 2000,
) -> "gpd.GeoDataFrame":
    """Generate operational zones using WhiteboxTools watershed delineation.

    Args:
        dem_path: Path to the DEM (filled, ideally).
        flow_acc_path: Path to flow accumulation raster.
        threshold: Flow accumulation threshold for pour points.

    Returns:
        GeoDataFrame with sub-basin polygons.
    """
    import geopandas as gpd
    import rasterio

    wbt = _get_wbt()

    with tempfile.TemporaryDirectory() as tmpdir:
        pour_points = str(Path(tmpdir) / "pour_points.tif")
        basins = str(Path(tmpdir) / "basins.tif")

        # Extract pour points from flow accumulation
        with rasterio.open(flow_acc_path) as src:
            fa = src.read(1)
            meta = src.meta.copy()
            nodata = src.nodata

        pp = np.where(fa >= threshold, 1, 0).astype(np.int16)
        if nodata is not None:
            pp[fa == nodata] = 0

        meta.update({"dtype": "int16", "count": 1, "nodata": 0})
        with rasterio.open(pour_points, "w", **meta) as dst:
            dst.write(pp, 1)

        # Run watershed delineation
        wbt.watershed(dem_path, pour_points, basins)

        # Vectorize basins
        with rasterio.open(basins) as src:
            basin_data = src.read(1)
            basin_transform = src.transform
            basin_crs = src.crs

        from rasterio.features import shapes as rasterio_shapes

        geometries = []
        basin_ids = []
        for geom, value in rasterio_shapes(
            basin_data, mask=basin_data > 0, transform=basin_transform
        ):
            if value > 0:
                from shapely.geometry import shape

                geometries.append(shape(geom))
                basin_ids.append(int(value))

    if not geometries:
        return gpd.GeoDataFrame(
            columns=["basin_id", "geometry"],
            geometry="geometry",
        )

    gdf = gpd.GeoDataFrame(
        {"basin_id": basin_ids, "geometry": geometries},
        geometry="geometry",
        crs=str(basin_crs) if basin_crs else "EPSG:4326",
    )

    # Compute area in hectares (approximate with geodesic)
    try:
        gdf_projected = gdf.to_crs("EPSG:32720")  # UTM zone 20S (Córdoba)
        gdf["superficie_ha"] = gdf_projected.geometry.area / 10_000
    except Exception:
        gdf["superficie_ha"] = 0.0

    return gdf


# ---------------------------------------------------------------------------
# e) Canal priority score
# ---------------------------------------------------------------------------


def calcular_prioridad_canal(
    canal_geom: Any,
    flow_acc_path: str,
    slope_path: str,
    zonas_criticas_gdf: Optional["gpd.GeoDataFrame"] = None,
) -> float:
    """Score a canal based on upstream accumulation, slope, and proximity to critical zones.

    Args:
        canal_geom: Shapely LineString geometry of the canal.
        flow_acc_path: Path to flow accumulation raster.
        slope_path: Path to slope raster.
        zonas_criticas_gdf: Optional GeoDataFrame of critical zones.

    Returns:
        Priority score 0-100 (higher = more critical).
    """
    # Sample raster values along the canal
    fa_values = _sample_raster_along_line(canal_geom, flow_acc_path)
    sl_values = _sample_raster_along_line(canal_geom, slope_path)

    if not fa_values or not sl_values:
        return 0.0

    # Normalize components
    fa_max = max(fa_values)
    fa_norm = min(fa_max / 10_000.0, 1.0)  # Normalize against 10k threshold

    sl_mean = sum(sl_values) / len(sl_values)
    sl_norm = min(sl_mean / 10.0, 1.0)  # Normalize against 10° threshold

    # Proximity to critical zones
    zona_factor = 0.0
    if zonas_criticas_gdf is not None and not zonas_criticas_gdf.empty:
        min_dist = zonas_criticas_gdf.geometry.distance(canal_geom).min()
        zona_factor = max(1.0 - (min_dist / 1000.0), 0.0)  # Within 1km

    score = (0.40 * fa_norm + 0.30 * sl_norm + 0.30 * zona_factor) * 100.0
    return round(min(max(score, 0.0), 100.0), 2)


# ---------------------------------------------------------------------------
# f) Road risk score
# ---------------------------------------------------------------------------


def calcular_riesgo_camino(
    camino_geom: Any,
    flow_acc_path: str,
    slope_path: str,
    twi_path: str,
    drainage_gdf: Optional["gpd.GeoDataFrame"] = None,
) -> float:
    """Calculate road flooding risk score.

    Risk is higher where: low slope + high accumulation + high TWI + near drainage.

    Args:
        camino_geom: Shapely LineString geometry of the road.
        flow_acc_path: Path to flow accumulation raster.
        slope_path: Path to slope raster.
        twi_path: Path to TWI raster.
        drainage_gdf: Optional drainage network GeoDataFrame.

    Returns:
        Risk score 0-100 (higher = more at risk).
    """
    fa_values = _sample_raster_along_line(camino_geom, flow_acc_path)
    sl_values = _sample_raster_along_line(camino_geom, slope_path)
    twi_values = _sample_raster_along_line(camino_geom, twi_path)

    if not fa_values or not sl_values or not twi_values:
        return 0.0

    # High accumulation = bad
    fa_norm = min(max(fa_values) / 10_000.0, 1.0)

    # LOW slope = bad (water pools)
    sl_mean = sum(sl_values) / len(sl_values)
    sl_norm = max(1.0 - (sl_mean / 5.0), 0.0)  # Invert: flat = high risk

    # High TWI = bad
    twi_mean = sum(twi_values) / len(twi_values)
    twi_norm = min(max(twi_mean / 15.0, 0.0), 1.0)

    # Proximity to drainage
    drain_factor = 0.0
    if drainage_gdf is not None and not drainage_gdf.empty:
        min_dist = drainage_gdf.geometry.distance(camino_geom).min()
        drain_factor = max(1.0 - (min_dist / 500.0), 0.0)  # Within 500m

    score = (
        0.30 * fa_norm + 0.25 * sl_norm + 0.25 * twi_norm + 0.20 * drain_factor
    ) * 100.0
    return round(min(max(score, 0.0), 100.0), 2)


# ---------------------------------------------------------------------------
# g) Dynamic terrain classification
# ---------------------------------------------------------------------------


def clasificar_terreno_dinamico(
    sar_data: np.ndarray | None,
    sentinel2_data: np.ndarray | None,
    dem_data: np.ndarray | None,
) -> dict[str, Any]:
    """Combine SAR (water detection) + optical (vegetation) + DEM for classification.

    Args:
        sar_data: 2D array of SAR backscatter values (dB). None if unavailable.
        sentinel2_data: 2D array of NDVI values. None if unavailable.
        dem_data: 2D array of DEM elevation values. None if unavailable.

    Returns:
        dict with classified arrays and statistics.
    """
    result: dict[str, Any] = {
        "clases": {},
        "estadisticas": {},
    }

    # Determine shape from first available data
    shape = None
    for data in [sar_data, sentinel2_data, dem_data]:
        if data is not None:
            shape = data.shape
            break

    if shape is None:
        return result

    classified = np.zeros(shape, dtype=np.uint8)
    # Classes: 0=unknown, 1=agua, 2=vegetacion_densa, 3=suelo_desnudo,
    #          4=vegetacion_rala, 5=urbano

    # SAR-based water detection (backscatter < -15 dB = water)
    if sar_data is not None:
        water_mask = sar_data < -15.0
        classified[water_mask] = 1

    # NDVI-based vegetation classification
    if sentinel2_data is not None:
        dense_veg = (sentinel2_data > 0.5) & (classified == 0)
        sparse_veg = (sentinel2_data > 0.2) & (sentinel2_data <= 0.5) & (classified == 0)
        bare_soil = (sentinel2_data <= 0.2) & (sentinel2_data > -0.1) & (classified == 0)

        classified[dense_veg] = 2
        classified[sparse_veg] = 4
        classified[bare_soil] = 3

    total_pixels = classified.size
    class_names = {
        0: "sin_clasificar",
        1: "agua",
        2: "vegetacion_densa",
        3: "suelo_desnudo",
        4: "vegetacion_rala",
        5: "urbano",
    }

    stats = {}
    for code, name in class_names.items():
        count = int(np.sum(classified == code))
        stats[name] = {
            "pixeles": count,
            "porcentaje": round((count / total_pixels) * 100.0, 2) if total_pixels > 0 else 0.0,
        }

    result["clasificacion"] = classified
    result["clases"] = class_names
    result["estadisticas"] = stats

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_raster_along_line(
    line_geom: Any,
    raster_path: str,
    num_points: int = 20,
) -> list[float]:
    """Sample raster values at evenly spaced points along a line geometry.

    Args:
        line_geom: Shapely LineString.
        raster_path: Path to the raster file.
        num_points: Number of sample points.

    Returns:
        List of sampled values (excluding nodata).
    """
    if line_geom is None or line_geom.is_empty:
        return []

    try:
        fractions = np.linspace(0, 1, num_points)
        points = [line_geom.interpolate(f, normalized=True) for f in fractions]
    except Exception:
        return []

    import rasterio
    from rasterio.transform import rowcol

    values: list[float] = []
    try:
        with rasterio.open(raster_path) as src:
            data = src.read(1)
            nodata = src.nodata
            transform = src.transform

            for pt in points:
                try:
                    r, c = rowcol(transform, pt.x, pt.y)
                    if 0 <= r < data.shape[0] and 0 <= c < data.shape[1]:
                        val = float(data[r, c])
                        if nodata is None or val != nodata:
                            values.append(val)
                except Exception:
                    continue
    except Exception:
        pass

    return values
