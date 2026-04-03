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
# h) Canal hotspot ranking
# ---------------------------------------------------------------------------


def rank_canal_hotspots(
    canal_geometries: list[dict],
    flow_acc_raster_path: str,
    num_points: int = 20,
) -> list[dict]:
    """Rank canal segments by flow accumulation concentration.

    Samples the flow_acc raster along each canal segment geometry and
    ranks by maximum flow accumulation. Classifies risk using percentile
    thresholds within the dataset.

    Args:
        canal_geometries: List of dicts with at minimum 'geometry' (Shapely
            LineString or GeoJSON-like) and optionally 'id', 'nombre'.
        flow_acc_raster_path: Path to the flow accumulation raster.
        num_points: Number of sample points per segment.

    Returns:
        List of dicts sorted descending by flow_acc_max, each containing:
        geometry, score (flow_acc_max), flow_acc_mean, risk_level, segment_index.

    Raises:
        FileNotFoundError: If the flow_acc raster does not exist.
    """
    from shapely.geometry import shape as shapely_shape

    if not Path(flow_acc_raster_path).exists():
        raise FileNotFoundError(
            f"Flow accumulation raster not found: {flow_acc_raster_path}"
        )

    raw_results: list[dict] = []

    for idx, canal in enumerate(canal_geometries):
        geom = canal.get("geometry")
        if geom is None:
            continue

        # Accept both Shapely objects and GeoJSON-like dicts
        if isinstance(geom, dict):
            geom = shapely_shape(geom)

        values = _sample_raster_along_line(geom, flow_acc_raster_path, num_points)
        if not values:
            continue

        fa_max = max(values)
        fa_mean = sum(values) / len(values)

        raw_results.append({
            "geometry": mapping(geom),
            "segment_index": idx,
            "id": canal.get("id"),
            "nombre": canal.get("nombre"),
            "flow_acc_max": round(fa_max, 2),
            "flow_acc_mean": round(fa_mean, 2),
            "score": round(fa_max, 2),
        })

    if not raw_results:
        return []

    # Classify risk using percentile thresholds within this dataset
    all_maxes = [r["flow_acc_max"] for r in raw_results]
    p75 = float(np.percentile(all_maxes, 75))
    p25 = float(np.percentile(all_maxes, 25))

    for r in raw_results:
        if r["flow_acc_max"] >= p75:
            r["risk_level"] = "critico"
        elif r["flow_acc_max"] >= np.percentile(all_maxes, 50):
            r["risk_level"] = "alto"
        elif r["flow_acc_max"] >= p25:
            r["risk_level"] = "medio"
        else:
            r["risk_level"] = "bajo"

    # Sort descending by flow_acc_max
    raw_results.sort(key=lambda r: r["flow_acc_max"], reverse=True)
    return raw_results


# ---------------------------------------------------------------------------
# i) Coverage gap detection
# ---------------------------------------------------------------------------


def detect_coverage_gaps(
    zones: list[dict],
    hci_scores: dict[str, float],
    canal_geometries: list[dict],
    threshold_km: float = 2.0,
    hci_threshold: float = 50.0,
) -> list[dict]:
    """Detect areas with high HCI but no nearby canal infrastructure.

    For each zone, computes the distance to the nearest canal segment.
    Gaps are zones where distance > threshold_km AND HCI > hci_threshold.

    Args:
        zones: List of dicts with 'id' and 'geometry' (Shapely Polygon or
            GeoJSON-like dict). Zone id must match keys in hci_scores.
        hci_scores: Mapping of zone_id (str) to HCI score (0-100).
        canal_geometries: List of dicts with 'geometry' (Shapely LineString
            or GeoJSON-like dict).
        threshold_km: Minimum distance in km to qualify as a gap.
        hci_threshold: Minimum HCI score to qualify as a gap.

    Returns:
        List of gap dicts sorted descending by severity, each containing:
        geometry (centroid), gap_km, hci_score, zone_id, severity.
    """
    from shapely.geometry import shape as shapely_shape
    from shapely.ops import nearest_points, unary_union

    # Build a unified canal geometry for distance computation
    canal_shapes = []
    for c in canal_geometries:
        g = c.get("geometry")
        if g is None:
            continue
        if isinstance(g, dict):
            g = shapely_shape(g)
        canal_shapes.append(g)

    if not canal_shapes:
        return []

    canal_union = unary_union(canal_shapes)

    gaps: list[dict] = []

    for zone in zones:
        zone_id = str(zone.get("id", ""))
        hci = hci_scores.get(zone_id, 0.0)
        if hci < hci_threshold:
            continue

        geom = zone.get("geometry")
        if geom is None:
            continue
        if isinstance(geom, dict):
            geom = shapely_shape(geom)

        centroid = geom.centroid

        # Approximate distance in km using degree-based heuristic
        # For more accuracy, the caller should provide projected geometries
        _, nearest_pt = nearest_points(centroid, canal_union)
        # Rough conversion: 1 degree ~ 111 km at equator; good enough for
        # mid-latitudes when combined with a threshold
        dist_deg = centroid.distance(nearest_pt)
        dist_km = dist_deg * 111.0  # approximate

        if dist_km < threshold_km:
            continue

        # Classify severity per spec
        if hci > 80.0 and dist_km > 5.0:
            severity = "critico"
        elif hci > 60.0 and dist_km > 3.0:
            severity = "alto"
        else:
            severity = "moderado"

        gaps.append({
            "geometry": mapping(centroid),
            "gap_km": round(dist_km, 2),
            "hci_score": round(hci, 2),
            "zone_id": zone_id,
            "severity": severity,
        })

    # Sort: critico > alto > moderado, then by hci descending
    severity_order = {"critico": 0, "alto": 1, "moderado": 2}
    gaps.sort(key=lambda g: (severity_order.get(g["severity"], 3), -g["hci_score"]))

    return gaps


# ---------------------------------------------------------------------------
# j) Maintenance priority composite score
# ---------------------------------------------------------------------------


def compute_maintenance_priority(
    centrality_scores: dict[int, float],
    flow_acc_scores: dict[int, float],
    hci_scores: dict[str, float],
    conflict_counts: dict[int, int],
) -> list[dict]:
    """Compute composite maintenance priority for canal segments.

    Weights: 0.30 centrality + 0.25 flow_acc + 0.25 upstream_hci + 0.20 conflicts.
    Missing factors are handled via weight redistribution among available factors.

    Args:
        centrality_scores: Mapping node_id -> betweenness centrality value.
        flow_acc_scores: Mapping node_id -> flow accumulation value.
        hci_scores: Mapping zone/node_id (str) -> HCI score (0-100).
        conflict_counts: Mapping node_id -> number of conflict points.

    Returns:
        List of dicts sorted descending by composite_score, each containing:
        node_id, composite_score (0-1), components dict with raw and normalized
        values for each factor.
    """
    # Collect all node IDs across all factor dicts
    all_ids: set[int] = set()
    all_ids.update(centrality_scores.keys())
    all_ids.update(flow_acc_scores.keys())
    all_ids.update(int(k) for k in hci_scores.keys() if k.isdigit())
    all_ids.update(conflict_counts.keys())

    if not all_ids:
        return []

    # Compute normalization ranges (min-max)
    def _min_max(values: list[float]) -> tuple[float, float]:
        if not values:
            return 0.0, 1.0
        mn, mx = min(values), max(values)
        if mn == mx:
            return mn, mn + 1.0  # avoid division by zero
        return mn, mx

    cent_vals = list(centrality_scores.values())
    fa_vals = list(flow_acc_scores.values())
    hci_vals = list(hci_scores.values())
    conf_vals = list(conflict_counts.values())

    cent_min, cent_max = _min_max(cent_vals)
    fa_min, fa_max = _min_max(fa_vals)
    hci_min, hci_max = _min_max(hci_vals)
    conf_min, conf_max = _min_max([float(v) for v in conf_vals])

    base_weights = {
        "centrality": 0.30,
        "flow_acc": 0.25,
        "upstream_hci": 0.25,
        "conflict_count": 0.20,
    }

    results: list[dict] = []

    for node_id in all_ids:
        components: dict[str, dict] = {}
        available_weight = 0.0
        missing_factors: list[str] = []

        # Centrality
        if node_id in centrality_scores:
            raw = centrality_scores[node_id]
            norm = (raw - cent_min) / (cent_max - cent_min)
            components["centrality"] = {"raw": round(raw, 6), "normalized": round(norm, 4)}
            available_weight += base_weights["centrality"]
        else:
            missing_factors.append("centrality")

        # Flow accumulation
        if node_id in flow_acc_scores:
            raw = flow_acc_scores[node_id]
            norm = (raw - fa_min) / (fa_max - fa_min)
            components["flow_acc"] = {"raw": round(raw, 2), "normalized": round(norm, 4)}
            available_weight += base_weights["flow_acc"]
        else:
            missing_factors.append("flow_acc")

        # Upstream HCI
        hci_key = str(node_id)
        if hci_key in hci_scores:
            raw = hci_scores[hci_key]
            norm = (raw - hci_min) / (hci_max - hci_min)
            components["upstream_hci"] = {"raw": round(raw, 2), "normalized": round(norm, 4)}
            available_weight += base_weights["upstream_hci"]
        else:
            missing_factors.append("upstream_hci")

        # Conflict count
        if node_id in conflict_counts:
            raw = float(conflict_counts[node_id])
            norm = (raw - conf_min) / (conf_max - conf_min)
            components["conflict_count"] = {"raw": int(raw), "normalized": round(norm, 4)}
            available_weight += base_weights["conflict_count"]
        else:
            missing_factors.append("conflict_count")

        # Compute weighted sum with redistribution for missing factors
        if available_weight == 0.0:
            continue

        redistribution_factor = 1.0 / available_weight
        composite = 0.0
        for factor, weight in base_weights.items():
            if factor in components:
                adjusted_weight = weight * redistribution_factor
                composite += adjusted_weight * components[factor]["normalized"]

        results.append({
            "node_id": node_id,
            "composite_score": round(composite, 4),
            "components": components,
            "missing_factors": missing_factors if missing_factors else None,
        })

    results.sort(key=lambda r: r["composite_score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# k) Cost surface generation from slope raster
# ---------------------------------------------------------------------------


def generate_cost_surface(
    slope_raster_path: str,
    output_path: str,
) -> str:
    """Generate a cost surface from a slope raster.

    Cost formula: cost = 1 + (slope / max_slope) * 10
    Flat terrain has cost ~1 (cheapest), steepest terrain has cost ~11.

    Args:
        slope_raster_path: Path to the slope raster (degrees).
        output_path: Where to write the cost surface GeoTIFF.

    Returns:
        output_path on success.

    Raises:
        FileNotFoundError: If the slope raster does not exist.
        ValueError: If the slope raster contains only nodata.
    """
    import rasterio

    if not Path(slope_raster_path).exists():
        raise FileNotFoundError(
            f"Slope raster not found: {slope_raster_path}"
        )

    with rasterio.open(slope_raster_path) as src:
        slope = src.read(1).astype(np.float64)
        nodata = src.nodata
        meta = src.meta.copy()

    # Build valid-data mask
    valid_mask = np.ones(slope.shape, dtype=bool)
    if nodata is not None:
        valid_mask &= slope != nodata
    valid_mask &= np.isfinite(slope)

    if not np.any(valid_mask):
        raise ValueError(
            "Slope raster contains only nodata — cannot generate cost surface"
        )

    # Normalize slope to [0, 1] using max of valid pixels
    max_slope = float(np.max(slope[valid_mask]))
    if max_slope <= 0:
        max_slope = 1.0  # avoid division by zero on perfectly flat terrain

    cost = np.ones(slope.shape, dtype=np.float32)
    cost[valid_mask] = (
        1.0 + (slope[valid_mask] / max_slope) * 10.0
    ).astype(np.float32)

    # Mark nodata pixels with a high sentinel so WBT treats them as barriers
    out_nodata = np.float32(-9999.0)
    cost[~valid_mask] = out_nodata

    meta.update({
        "dtype": "float32",
        "count": 1,
        "driver": "GTiff",
        "nodata": float(out_nodata),
    })
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(cost, 1)

    return output_path


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
