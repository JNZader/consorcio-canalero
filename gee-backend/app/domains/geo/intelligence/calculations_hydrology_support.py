from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np
from shapely.geometry import LineString, mapping


def calcular_indice_criticidad_hidrica_impl(
    pendiente: float,
    acumulacion: float,
    twi: float,
    dist_canal: float,
    hist_inundacion: float,
    *,
    pesos: Optional[dict[str, float]],
    default_weights: dict[str, float],
    round_score,
) -> float:
    w = pesos if pesos is not None else default_weights
    return round_score(
        (
            w["pendiente"] * pendiente
            + w["acumulacion"] * acumulacion
            + w["twi"] * twi
            + w["dist_canal"] * dist_canal
            + w["hist_inundacion"] * hist_inundacion
        )
        * 100.0
    )


def clasificar_nivel_riesgo_impl(indice: float) -> str:
    return (
        "critico"
        if indice >= 75
        else "alto"
        if indice >= 50
        else "medio"
        if indice >= 25
        else "bajo"
    )


def clasificar_severidad_conflicto_impl(acumulacion: float, pendiente: float) -> str:
    return (
        "alta"
        if acumulacion > 5000 or pendiente < 0.5
        else "media"
        if acumulacion > 2000 or pendiente < 2.0
        else "baja"
    )


def detectar_puntos_conflicto_impl(
    canales_gdf,
    caminos_gdf,
    drenajes_gdf,
    flow_acc_path: str,
    slope_path: str,
    *,
    buffer_m: float,
    flow_acc_threshold: float,
    slope_threshold: float,
    classify_severity,
    build_empty_geojson,
):
    import geopandas as gpd
    import rasterio
    from rasterio.transform import rowcol

    conflicts: list[dict[str, Any]] = []
    for tipo, gdf_a, gdf_b in [
        ("canal_camino", canales_gdf, caminos_gdf),
        ("canal_drenaje", canales_gdf, drenajes_gdf),
        ("camino_drenaje", caminos_gdf, drenajes_gdf),
    ]:
        if gdf_a.empty or gdf_b.empty:
            continue
        with (
            rasterio.open(flow_acc_path) as fa_src,
            rasterio.open(slope_path) as sl_src,
        ):
            fa_data, sl_data = fa_src.read(1), sl_src.read(1)
            fa_transform, sl_transform = fa_src.transform, sl_src.transform
            buffered = gdf_a.copy()
            buffered["geometry"] = buffered.geometry.buffer(buffer_m)
            for _, row in gpd.overlay(
                buffered, gdf_b, how="intersection", keep_geom_type=False
            ).iterrows():
                centroid = row.geometry.centroid
                try:
                    fa_row, fa_col = rowcol(fa_transform, centroid.x, centroid.y)
                    sl_row, sl_col = rowcol(sl_transform, centroid.x, centroid.y)
                    fa_val = (
                        float(fa_data[fa_row, fa_col])
                        if 0 <= fa_row < fa_data.shape[0]
                        and 0 <= fa_col < fa_data.shape[1]
                        else 0.0
                    )
                    sl_val = (
                        float(sl_data[sl_row, sl_col])
                        if 0 <= sl_row < sl_data.shape[0]
                        and 0 <= sl_col < sl_data.shape[1]
                        else 0.0
                    )
                except Exception:
                    fa_val = sl_val = 0.0
                if fa_val > flow_acc_threshold and sl_val < slope_threshold:
                    conflicts.append(
                        {
                            "tipo": tipo,
                            "geometry": centroid,
                            "descripcion": f"Cruce {tipo.replace('_', '/')} — acum={fa_val:.0f}, pend={sl_val:.1f}°",
                            "severidad": classify_severity(fa_val, sl_val),
                            "acumulacion_valor": fa_val,
                            "pendiente_valor": sl_val,
                        }
                    )
    return (
        gpd.GeoDataFrame(conflicts, geometry="geometry", crs="EPSG:4326")
        if conflicts
        else build_empty_geojson(
            [
                "tipo",
                "geometry",
                "descripcion",
                "severidad",
                "acumulacion_valor",
                "pendiente_valor",
            ]
        )
    )


def empty_runoff_geojson_impl(
    punto: tuple[float, float], lluvia_mm: float, error: str
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [],
        "properties": {
            "punto_inicio": list(punto),
            "lluvia_mm": lluvia_mm,
            "error": error,
        },
    }


def simular_escorrentia_impl(
    flow_dir_path: str,
    flow_acc_path: str,
    punto_inicio: tuple[float, float],
    lluvia_mm: float,
    *,
    max_steps: int,
    rasterio_module,
    empty_geojson,
) -> dict[str, Any]:
    from rasterio.transform import rowcol

    d8_offsets = {
        1: (0, 1),
        2: (-1, 1),
        4: (-1, 0),
        8: (-1, -1),
        16: (0, -1),
        32: (1, -1),
        64: (1, 0),
        128: (1, 1),
    }
    with rasterio_module.open(flow_dir_path) as fd_src:
        fd_data, fd_transform, fd_nodata = (
            fd_src.read(1),
            fd_src.transform,
            fd_src.nodata,
        )
    with rasterio_module.open(flow_acc_path) as fa_src:
        fa_data = fa_src.read(1)
    try:
        row, col = rowcol(fd_transform, *punto_inicio)
    except Exception:
        return empty_geojson(punto_inicio, lluvia_mm, "Punto fuera del raster")
    coords, accumulations, visited = [punto_inicio], [], set()
    for _ in range(max_steps):
        if (row, col) in visited or not (
            0 <= row < fd_data.shape[0] and 0 <= col < fd_data.shape[1]
        ):
            break
        visited.add((row, col))
        direction = int(fd_data[row, col])
        if fd_nodata is not None and direction == int(fd_nodata):
            break
        accumulations.append(
            float(fa_data[row, col]) * lluvia_mm
            if 0 <= row < fa_data.shape[0] and 0 <= col < fa_data.shape[1]
            else 0.0
        )
        offset = d8_offsets.get(direction)
        if offset is None:
            break
        row += offset[0]
        col += offset[1]
        coords.append(
            (
                fd_transform.c + col * fd_transform.a + row * fd_transform.b,
                fd_transform.f + col * fd_transform.d + row * fd_transform.e,
            )
        )
    if len(coords) < 2:
        return empty_geojson(punto_inicio, lluvia_mm, "No se pudo trazar flujo")
    line = LineString(coords)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {
                    "punto_inicio": list(punto_inicio),
                    "lluvia_mm": lluvia_mm,
                    "longitud_m": len(coords),
                    "acumulacion_max": max(accumulations) if accumulations else 0.0,
                    "acumulacion_media": sum(accumulations) / len(accumulations)
                    if accumulations
                    else 0.0,
                    "pasos": len(coords),
                },
            }
        ],
    }


def generar_zonificacion_impl(
    dem_path: str, flow_acc_path: str, *, threshold: int, get_wbt, build_empty_geojson
):
    import geopandas as gpd
    import rasterio
    from rasterio.features import shapes as rasterio_shapes
    from shapely.geometry import shape

    with tempfile.TemporaryDirectory() as tmpdir:
        pour_points, basins = (
            str(Path(tmpdir) / "pour_points.tif"),
            str(Path(tmpdir) / "basins.tif"),
        )
        with rasterio.open(flow_acc_path) as src:
            fa, meta, nodata = src.read(1), src.meta.copy(), src.nodata
        pp = np.where(fa >= threshold, 1, 0).astype(np.int16)
        if nodata is not None:
            pp[fa == nodata] = 0
        meta.update({"dtype": "int16", "count": 1, "nodata": 0})
        with rasterio.open(pour_points, "w", **meta) as dst:
            dst.write(pp, 1)
        get_wbt().watershed(dem_path, pour_points, basins)
        with rasterio.open(basins) as src:
            basin_data, basin_transform, basin_crs = src.read(1), src.transform, src.crs
        geometries, basin_ids = [], []
        for geom, value in rasterio_shapes(
            basin_data, mask=basin_data > 0, transform=basin_transform
        ):
            if value > 0:
                geometries.append(shape(geom))
                basin_ids.append(int(value))
    if not geometries:
        return build_empty_geojson(["basin_id", "geometry"])
    gdf = gpd.GeoDataFrame(
        {"basin_id": basin_ids, "geometry": geometries},
        geometry="geometry",
        crs=str(basin_crs) if basin_crs else "EPSG:4326",
    )
    try:
        gdf["superficie_ha"] = gdf.to_crs("EPSG:32720").geometry.area / 10_000
    except Exception:
        gdf["superficie_ha"] = 0.0
    return gdf
