"""Support helpers for composite raster analysis."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import rasterize as rasterio_rasterize
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

logger = logging.getLogger(__name__)

DEFAULT_WATERWAYS_DIR = "/app/data/waterways"

DEFAULT_FLOOD_WEIGHTS: dict[str, float] = {
    "twi": 0.30,
    "hand": 0.30,
    "profile_curvature": 0.25,
    "tpi": 0.15,
}

DEFAULT_DRAINAGE_WEIGHTS: dict[str, float] = {
    "dist_drainage": 0.30,
    "flow_acc": 0.25,
    "hand": 0.20,
    "tpi": 0.25,
}


def merge_drainage_networks_impl(
    auto_drainage_path: str,
    waterways_dir: str = DEFAULT_WATERWAYS_DIR,
    output_path: str | None = None,
    reference_tif: str | None = None,
) -> str:
    if output_path is None:
        output_path = str(Path(auto_drainage_path).parent / "drainage_combined.geojson")

    combined_features: list[dict] = []
    target_crs = None
    reproject_fn = None
    area_dir = Path(auto_drainage_path).parent
    if reference_tif is None:
        for candidate in ["flow_acc.tif", "hand.tif"]:
            ref = area_dir / candidate
            if ref.exists():
                reference_tif = str(ref)
                break
    if reference_tif and Path(reference_tif).exists():
        try:
            with rasterio.open(reference_tif) as src:
                target_crs = src.crs
            if target_crs and str(target_crs) != "EPSG:4326":
                transformer = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_user_input(target_crs), always_xy=True)
                reproject_fn = lambda geom: shapely_transform(transformer.transform, geom)  # noqa: E731
        except Exception:
            logger.warning("merge_drainage_networks: failed to read CRS from %s", reference_tif, exc_info=True)

    auto_path = Path(auto_drainage_path)
    if auto_path.exists():
        with open(auto_path) as f:
            auto_data = json.load(f)
        for feat in auto_data.get("features", []):
            feat.setdefault("properties", {})["source"] = "auto"
            combined_features.append(feat)
    else:
        logger.warning("merge_drainage_networks: auto drainage not found at %s, skipping", auto_drainage_path)

    waterways_path = Path(waterways_dir)
    if waterways_path.is_dir():
        for geojson_file in sorted(waterways_path.glob("*.geojson")):
            try:
                with open(geojson_file) as f:
                    ww_data = json.load(f)
                for feat in ww_data.get("features", []):
                    if reproject_fn is not None:
                        feat["geometry"] = mapping(reproject_fn(shape(feat["geometry"])))
                    feat.setdefault("properties", {})["source"] = "real"
                    feat["properties"].setdefault("waterway_file", geojson_file.stem)
                    combined_features.append(feat)
            except Exception:
                logger.warning("merge_drainage_networks: failed to load %s, skipping", geojson_file.name, exc_info=True)
    else:
        logger.warning("merge_drainage_networks: waterways dir not found at %s", waterways_dir)

    combined = {"type": "FeatureCollection", "features": combined_features}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(combined, f)
    logger.info("merge_drainage_networks: wrote %d features to %s", len(combined_features), output_path)
    return output_path


def rasterize_drainage_impl(geojson_path: str, reference_tif: str, output_path: str) -> str:
    with open(geojson_path) as f:
        geojson_data = json.load(f)
    geometries = [(shape(feat["geometry"]), 1) for feat in geojson_data.get("features", [])]
    with rasterio.open(reference_tif) as src:
        meta = src.meta.copy()
        out_shape = (src.height, src.width)
        transform = src.transform
    burned = rasterio_rasterize(geometries, out_shape=out_shape, transform=transform, fill=0, dtype="uint8") if geometries else np.zeros(out_shape, dtype=np.uint8)
    meta.update({"dtype": "uint8", "count": 1, "nodata": None, "driver": "GTiff"})
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(burned, 1)
    return output_path


def load_layer(path: str) -> tuple[np.ndarray, np.ndarray, dict]:
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float64)
        nodata = src.nodata
        meta = src.meta.copy()
    nodata_mask = np.zeros(data.shape, dtype=bool)
    if nodata is not None:
        nodata_mask = data == nodata
    return data, nodata_mask, meta


def compute_flood_risk_impl(
    area_dir: str,
    output_path: str,
    normalize_percentile_fn,
    *,
    weights: dict[str, float] | None = None,
) -> str:
    w = weights or DEFAULT_FLOOD_WEIGHTS.copy()
    area = Path(area_dir)
    hand_data, hand_nd, meta = load_layer(str(area / "hand.tif"))
    twi_data, twi_nd, _ = load_layer(str(area / "twi.tif"))
    curv_data, curv_nd, _ = load_layer(str(area / "profile_curvature.tif"))
    tpi_data, tpi_nd, _ = load_layer(str(area / "tpi.tif"))
    nodata_mask = hand_nd | twi_nd | curv_nd | tpi_nd
    hand_inv = np.where(nodata_mask, 0.0, np.max(hand_data[~nodata_mask]) - hand_data)
    curv_inv = np.where(nodata_mask, 0.0, -curv_data)
    tpi_inv = np.where(nodata_mask, 0.0, -tpi_data)
    composite = (
        w["twi"] * normalize_percentile_fn(twi_data, nodata_mask)
        + w["hand"] * normalize_percentile_fn(hand_inv, nodata_mask)
        + w["profile_curvature"] * normalize_percentile_fn(curv_inv, nodata_mask)
        + w["tpi"] * normalize_percentile_fn(tpi_inv, nodata_mask)
    ).astype(np.float32) * np.float32(100.0)
    out_nodata = np.float32(-9999.0)
    composite[nodata_mask] = out_nodata
    meta.update({"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": float(out_nodata)})
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(composite, 1)
    return output_path


def compute_drainage_need_impl(
    area_dir: str,
    output_path: str,
    *,
    weights: dict[str, float] | None = None,
    get_wbt_fn,
    rasterize_drainage_fn,
    normalize_percentile_fn,
) -> str:
    w = weights or DEFAULT_DRAINAGE_WEIGHTS.copy()
    area = Path(area_dir)
    drainage_path = area / "drainage.tif"
    if not drainage_path.exists():
        combined_path = area / "drainage_combined.geojson"
        geojson_path = area / "drainage.geojson"
        source_geojson = combined_path if combined_path.exists() else geojson_path
        if source_geojson.exists():
            reference = area / "flow_acc.tif"
            if not reference.exists():
                reference = area / "hand.tif"
            rasterize_drainage_fn(str(source_geojson), str(reference), str(drainage_path))
        else:
            raise FileNotFoundError(
                f"drainage.tif not found in {area_dir}. Run the DEM pipeline first to generate the drainage network."
            )

    facc_data, facc_nd, meta = load_layer(str(area / "flow_acc.tif"))
    hand_data, hand_nd, _ = load_layer(str(area / "hand.tif"))
    tpi_data, tpi_nd, _ = load_layer(str(area / "tpi.tif"))

    with tempfile.TemporaryDirectory() as tmpdir:
        dist_output = str(Path(tmpdir) / "dist_drainage.tif")
        get_wbt_fn().euclidean_distance(str(drainage_path), dist_output)
        dist_data, dist_nd, _ = load_layer(dist_output)

    nodata_mask = facc_nd | hand_nd | dist_nd | tpi_nd
    hand_inv = np.where(nodata_mask, 0.0, np.max(hand_data[~nodata_mask]) - hand_data)
    tpi_inv = np.where(nodata_mask, 0.0, -tpi_data)
    with np.errstate(invalid="ignore"):
        facc_log = np.where(facc_data > 0, np.log1p(facc_data), 0.0)

    composite = (
        w["flow_acc"] * normalize_percentile_fn(facc_log, nodata_mask)
        + w["hand"] * normalize_percentile_fn(hand_inv, nodata_mask)
        + w["dist_drainage"] * normalize_percentile_fn(dist_data, nodata_mask)
        + w["tpi"] * normalize_percentile_fn(tpi_inv, nodata_mask)
    ).astype(np.float32) * np.float32(100.0)

    out_nodata = np.float32(-9999.0)
    composite[nodata_mask] = out_nodata
    meta.update({"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": float(out_nodata)})
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(composite, 1)
    return output_path
