from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np
from shapely.geometry import LineString, Point, mapping


def generate_cost_surface_impl(slope_raster_path: str, output_path: str, *, rasterio_module) -> str:
    if not Path(slope_raster_path).exists():
        raise FileNotFoundError(f"Slope raster not found: {slope_raster_path}")
    with rasterio_module.open(slope_raster_path) as src:
        slope, nodata, meta = src.read(1).astype(np.float64), src.nodata, src.meta.copy()
    valid_mask = np.isfinite(slope) if nodata is None else np.isfinite(slope) & (slope != nodata)
    if not np.any(valid_mask):
        raise ValueError("Slope raster contains only nodata — cannot generate cost surface")
    max_slope = float(np.max(slope[valid_mask])) or 1.0
    cost = np.ones(slope.shape, dtype=np.float32)
    cost[valid_mask] = (1.0 + (slope[valid_mask] / max_slope) * 10.0).astype(np.float32)
    out_nodata = np.float32(-9999.0)
    cost[~valid_mask] = out_nodata
    meta.update({"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": float(out_nodata)})
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio_module.open(output_path, "w", **meta) as dst:
        dst.write(cost, 1)
    return output_path


def cost_distance_impl(cost_surface_path: str, source_points: list[tuple[float, float]], output_accum_path: str, output_backlink_path: str, *, rasterio_module, get_wbt) -> tuple[str, str]:
    from rasterio.transform import rowcol

    if not Path(cost_surface_path).exists():
        raise FileNotFoundError(f"Cost surface raster not found: {cost_surface_path}")
    with tempfile.TemporaryDirectory() as tmpdir:
        source_raster_path = str(Path(tmpdir) / "sources.tif")
        with rasterio_module.open(cost_surface_path) as src:
            meta, height, width, transform = src.meta.copy(), src.height, src.width, src.transform
        source_data, points_burned = np.zeros((height, width), dtype=np.uint8), 0
        for lon, lat in source_points:
            try:
                r, c = rowcol(transform, lon, lat)
                if 0 <= r < height and 0 <= c < width:
                    source_data[r, c] = 1
                    points_burned += 1
            except Exception:
                pass
        if points_burned == 0:
            raise ValueError("No source points fall within the cost surface extent")
        source_meta = meta.copy()
        source_meta.update({"dtype": "uint8", "count": 1, "nodata": 0})
        with rasterio_module.open(source_raster_path, "w", **source_meta) as dst:
            dst.write(source_data, 1)
        Path(output_accum_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_backlink_path).parent.mkdir(parents=True, exist_ok=True)
        get_wbt().cost_distance(source_raster_path, cost_surface_path, output_accum_path, output_backlink_path)
    return output_accum_path, output_backlink_path


def least_cost_path_impl(cost_distance_path: str, backlink_path: str, target_point: tuple[float, float], *, rasterio_module, get_wbt) -> Optional[LineString]:
    from rasterio.transform import rowcol, xy

    if not Path(cost_distance_path).exists() or not Path(backlink_path).exists():
        return None
    with tempfile.TemporaryDirectory() as tmpdir:
        target_raster_path, output_path = str(Path(tmpdir) / "target.tif"), str(Path(tmpdir) / "pathway.tif")
        with rasterio_module.open(cost_distance_path) as src:
            meta, height, width, transform = src.meta.copy(), src.height, src.width, src.transform
        try:
            r, c = rowcol(transform, *target_point)
        except Exception:
            return None
        if r < 0 or r >= height or c < 0 or c >= width:
            return None
        target_data = np.zeros((height, width), dtype=np.uint8)
        target_data[r, c] = 1
        target_meta = meta.copy()
        target_meta.update({"dtype": "uint8", "count": 1, "nodata": 0})
        with rasterio_module.open(target_raster_path, "w", **target_meta) as dst:
            dst.write(target_data, 1)
        get_wbt().cost_pathway(target_raster_path, backlink_path, output_path)
        if not Path(output_path).exists():
            return None
        with rasterio_module.open(output_path) as src:
            pathway, pw_transform, pw_nodata = src.read(1), src.transform, src.nodata
        mask = (pathway > 0) & ((pathway != pw_nodata) if pw_nodata is not None else True)
        rows, cols = np.where(mask)
        if len(rows) < 2:
            return None
        with rasterio_module.open(cost_distance_path) as src:
            cost_values = src.read(1)[rows, cols]
        coords = [xy(pw_transform, int(row), int(col)) for row, col in zip(rows[np.argsort(cost_values)[::-1]], cols[np.argsort(cost_values)[::-1]])]
        return LineString(coords) if len(coords) >= 2 else None


def suggest_canal_routes_impl(gap_centroids: list[dict], canal_geometries: list[dict], slope_raster_path: str, *, output_dir: str | None, normalize_shape, extract_geometries, generate_cost_surface, cost_distance, least_cost_path):
    import logging
    import rasterio
    from rasterio.transform import rowcol
    from shapely.ops import nearest_points, unary_union

    logger = logging.getLogger(__name__)
    if not gap_centroids:
        return []
    if not Path(slope_raster_path).exists():
        raise FileNotFoundError(f"Slope raster not found: {slope_raster_path}")
    canal_shapes = extract_geometries(canal_geometries)
    if not canal_shapes:
        return []
    canal_union = unary_union(canal_shapes)
    tmpdir_obj = tempfile.TemporaryDirectory() if output_dir is None else None
    work_dir = tmpdir_obj.name if tmpdir_obj is not None else output_dir
    assert work_dir is not None
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    try:
        cost_surface_path = str(Path(work_dir) / "cost_surface.tif")
        generate_cost_surface(slope_raster_path, cost_surface_path)
        gap_points = [(normalize_shape(gap["geometry"]).x, normalize_shape(gap["geometry"]).y, str(gap.get("zone_id", ""))) for gap in gap_centroids if gap.get("geometry") is not None]
        if not gap_points:
            return []
        accum_path, backlink_path = str(Path(work_dir) / "cost_accum.tif"), str(Path(work_dir) / "cost_backlink.tif")
        try:
            cost_distance(cost_surface_path, [(lon, lat) for lon, lat, _ in gap_points], accum_path, backlink_path)
        except ValueError as exc:
            logger.warning("Cost distance failed: %s", exc)
            return []
        routes = []
        for lon, lat, zone_id in gap_points:
            _, nearest_canal_pt = nearest_points(Point(lon, lat), canal_union)
            target = (nearest_canal_pt.x, nearest_canal_pt.y)
            try:
                path_geom = least_cost_path(accum_path, backlink_path, target)
            except Exception as exc:
                routes.append({"geometry": None, "source_gap_id": zone_id, "target_point": mapping(nearest_canal_pt), "estimated_cost": None, "status": f"unreachable: {exc}"})
                continue
            if path_geom is None:
                routes.append({"geometry": None, "source_gap_id": zone_id, "target_point": mapping(nearest_canal_pt), "estimated_cost": None, "status": "unreachable: path could not be traced"})
                continue
            estimated_cost = None
            try:
                with rasterio.open(accum_path) as src:
                    r, c = rowcol(src.transform, *target)
                    if 0 <= r < src.height and 0 <= c < src.width:
                        val = float(src.read(1)[r, c])
                        if src.nodata is None or val != src.nodata:
                            estimated_cost = round(val, 2)
            except Exception:
                pass
            routes.append({"geometry": mapping(path_geom), "source_gap_id": zone_id, "target_point": mapping(nearest_canal_pt), "estimated_cost": estimated_cost, "status": "ok"})
        return routes
    finally:
        if tmpdir_obj is not None:
            tmpdir_obj.cleanup()


def sample_raster_along_line_impl(line_geom: Any, raster_path: str, *, num_points: int, rasterio_module) -> list[float]:
    if line_geom is None or line_geom.is_empty:
        return []
    try:
        points = [line_geom.interpolate(f, normalized=True) for f in np.linspace(0, 1, num_points)]
    except Exception:
        return []
    from rasterio.transform import rowcol

    values: list[float] = []
    try:
        with rasterio_module.open(raster_path) as src:
            data, nodata, transform = src.read(1), src.nodata, src.transform
            for pt in points:
                try:
                    r, c = rowcol(transform, pt.x, pt.y)
                    if 0 <= r < data.shape[0] and 0 <= c < data.shape[1]:
                        val = float(data[r, c])
                        if nodata is None or val != nodata:
                            values.append(val)
                except Exception:
                    pass
    except Exception:
        pass
    return values
