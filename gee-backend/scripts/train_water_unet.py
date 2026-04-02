"""
U-Net water segmentation training pipeline.

Downloads Sentinel-2 patches from Google Earth Engine, generates
pseudo-labels via NDWI thresholding, and trains a U-Net model
with ResNet34 encoder for binary water segmentation.

Usage:
    python scripts/train_water_unet.py --epochs 50 --batch-size 8
    python scripts/train_water_unet.py --patches 100 --lr 0.0001
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import ee
import numpy as np
import torch
import torch.nn as nn
from shapely.geometry import Point, Polygon, shape
from torch.utils.data import Dataset, DataLoader, random_split

import segmentation_models_pytorch as smp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("train_water_unet")

# ── Constants ──────────────────────────────────────────────────────────

PATCH_SIZE = 256  # pixels
SCALE = 10  # meters per pixel (Sentinel-2 10m bands)
NDWI_THRESHOLD = 0.1  # Low for thin canal detection in agricultural zones

# Sentinel-2 bands of interest
S2_BANDS = ["B2", "B3", "B4", "B8"]  # blue, green, red, nir
SCL_BAND = "SCL"

# SCL values to mask out: cloud shadow (3), cloud med (8),
# cloud high (9), cirrus (10)
SCL_EXCLUDE = {3, 8, 9, 10}

# Band scale factor (Sentinel-2 L2A reflectance values are 0-10000)
BAND_SCALE = 10000.0


# ── AOI Loading ───────────────────────────────────────────────────────


def _parse_kml_polygon(kml_root: ElementTree.Element) -> list[list[list[float]]]:
    """Extract polygon coordinates from a KML ElementTree root."""
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    # Try with namespace first, then without
    coord_elem = kml_root.find(".//kml:coordinates", ns)
    if coord_elem is None:
        coord_elem = kml_root.find(".//{http://www.opengis.net/kml/2.2}coordinates")
    if coord_elem is None:
        # Fallback: no namespace
        coord_elem = kml_root.find(".//coordinates")
    if coord_elem is None:
        raise ValueError("No <coordinates> element found in KML")

    raw = coord_elem.text.strip()
    ring: list[list[float]] = []
    for triplet in raw.split():
        parts = triplet.split(",")
        lon, lat = float(parts[0]), float(parts[1])
        ring.append([lon, lat])

    return [ring]


def load_aoi(filepath: str) -> tuple[Polygon, dict[str, float]]:
    """Load an Area of Interest from a GeoJSON, KML, or KMZ file.

    Args:
        filepath: Path to the AOI file (.geojson, .json, .kml, .kmz).

    Returns:
        Tuple of (shapely Polygon, bounding box dict with west/south/east/north).
    """
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix in (".geojson", ".json"):
        with open(path) as f:
            data = json.load(f)
        # Support both FeatureCollection and single Feature/Geometry
        if data.get("type") == "FeatureCollection":
            geom_data = data["features"][0]["geometry"]
        elif data.get("type") == "Feature":
            geom_data = data["geometry"]
        else:
            geom_data = data
        polygon = shape(geom_data)

    elif suffix == ".kml":
        tree = ElementTree.parse(path)
        coords = _parse_kml_polygon(tree.getroot())
        polygon = Polygon(coords[0])

    elif suffix == ".kmz":
        with zipfile.ZipFile(path, "r") as zf:
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError(f"No KML file found inside KMZ: {filepath}")
            with zf.open(kml_names[0]) as kml_file:
                tree = ElementTree.parse(kml_file)
        coords = _parse_kml_polygon(tree.getroot())
        polygon = Polygon(coords[0])

    else:
        raise ValueError(
            f"Unsupported AOI file format '{suffix}'. "
            "Use .geojson, .json, .kml, or .kmz."
        )

    if not polygon.is_valid:
        logger.warning("AOI polygon is invalid, attempting to fix with buffer(0)")
        polygon = polygon.buffer(0)

    bounds = polygon.bounds  # (minx, miny, maxx, maxy)
    bbox = {
        "west": bounds[0],
        "south": bounds[1],
        "east": bounds[2],
        "north": bounds[3],
    }

    logger.info(
        "Loaded AOI from %s — bbox: W=%.4f S=%.4f E=%.4f N=%.4f",
        path.name, bbox["west"], bbox["south"], bbox["east"], bbox["north"],
    )
    return polygon, bbox


# ── GEE Initialization ────────────────────────────────────────────────


def initialize_gee(credentials_dir: str = "/app/credentials") -> None:
    """Initialize Google Earth Engine with service account credentials.

    Resolution order:
    1. JSON file in ``credentials_dir`` (original behaviour).
    2. ``GEE_SERVICE_ACCOUNT_KEY`` env var containing the JSON string.
       When found, the content is written to a temp file so the rest of
       the pipeline stays unchanged.
    """
    cred_path = Path(credentials_dir)
    sa_key_files = list(cred_path.glob("*.json"))

    if not sa_key_files:
        # Fallback: check environment variable
        env_json = os.environ.get("GEE_SERVICE_ACCOUNT_KEY")
        if env_json:
            logger.info("No JSON file in %s — using GEE_SERVICE_ACCOUNT_KEY env var", credentials_dir)
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="gee-sa-", delete=False,
            )
            tmp.write(env_json)
            tmp.close()
            sa_key_path = Path(tmp.name)
        else:
            raise FileNotFoundError(
                f"No service account JSON found in {credentials_dir} and "
                "GEE_SERVICE_ACCOUNT_KEY env var is not set. "
                "Provide credentials via either method."
            )
    else:
        sa_key_path = sa_key_files[0]

    logger.info("Using GEE credentials: %s", sa_key_path.name)

    with open(sa_key_path) as f:
        sa_info = json.load(f)

    credentials = ee.ServiceAccountCredentials(
        sa_info.get("client_email", ""),
        key_data=json.dumps(sa_info),
    )
    ee.Initialize(credentials=credentials)
    logger.info("GEE initialized successfully")


# ── Patch Download ─────────────────────────────────────────────────────


def get_sentinel2_collection(
    aoi: ee.Geometry,
    max_cloud_cover: float = 20.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> ee.ImageCollection:
    """Get filtered Sentinel-2 L2A collection for the AOI."""
    import datetime

    if end_date is None:
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        start_date = (end_dt - datetime.timedelta(days=730)).strftime("%Y-%m-%d")

    logger.info("Date range: %s to %s", start_date, end_date)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_cover))
        .select(S2_BANDS + [SCL_BAND])
    )

    return collection


def sample_patch_points(
    aoi_polygon: Polygon,
    aoi_bounds: dict[str, float],
    num_points: int,
    seed: int = 42,
) -> list[dict[str, float]]:
    """Generate random sample points within the AOI polygon.

    Points are sampled inside the bounding box and filtered to keep only
    those that fall within the actual polygon boundary.
    """
    rng = np.random.default_rng(seed)
    target = num_points * 3  # oversample to account for download failures
    points: list[dict[str, float]] = []
    max_attempts = target * 20  # safety cap to avoid infinite loop
    attempts = 0

    while len(points) < target and attempts < max_attempts:
        lon = rng.uniform(aoi_bounds["west"], aoi_bounds["east"])
        lat = rng.uniform(aoi_bounds["south"], aoi_bounds["north"])
        attempts += 1
        if aoi_polygon.contains(Point(lon, lat)):
            points.append({"lon": lon, "lat": lat})

    if len(points) < target:
        logger.warning(
            "Only generated %d sample points (target was %d) after %d attempts",
            len(points), target, max_attempts,
        )

    return points


def download_patch(
    image: ee.Image,
    center_lon: float,
    center_lat: float,
    patch_size: int = PATCH_SIZE,
    scale: int = SCALE,
) -> np.ndarray | None:
    """Download a single patch from GEE as numpy array.

    Returns:
        Array of shape (5, H, W) — 4 spectral bands + SCL, or None on failure.
    """
    half_extent = (patch_size * scale) / 2.0
    point = ee.Geometry.Point([center_lon, center_lat])
    region = point.buffer(half_extent).bounds()

    try:
        # getPixels for the region
        bands_to_get = S2_BANDS + [SCL_BAND]
        url = image.select(bands_to_get).getDownloadURL(
            {
                "region": region,
                "scale": scale,
                "format": "NPY",
            }
        )

        import requests

        response = requests.get(url, timeout=60)
        response.raise_for_status()

        # Parse the numpy structured array from GEE
        data = np.load(
            __import__("io").BytesIO(response.content), allow_pickle=True
        )

        # GEE returns structured array with band names as fields
        if data.dtype.names:
            arrays = []
            for band in bands_to_get:
                band_data = data[band].astype(np.float32)
                if band_data.ndim == 1:
                    # Reshape 1D to 2D if needed
                    side = int(np.sqrt(len(band_data)))
                    if side * side != len(band_data):
                        return None
                    band_data = band_data.reshape(side, side)
                arrays.append(band_data)
            result = np.stack(arrays, axis=0)
        else:
            # Fallback: data is already a regular ndarray
            if data.ndim == 3:
                result = data.transpose(2, 0, 1).astype(np.float32)
            else:
                return None

        # Validate shape
        if result.shape[0] != 5:  # 4 bands + SCL
            return None
        if result.shape[1] < 16 or result.shape[2] < 16:
            return None

        return result

    except Exception as e:
        logger.debug("Failed to download patch at (%.4f, %.4f): %s", center_lon, center_lat, e)
        return None


def download_patches(
    num_patches: int,
    aoi_polygon: Polygon,
    aoi_bounds: dict[str, float],
    max_cloud_cover: float = 20.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[np.ndarray]:
    """Download Sentinel-2 patches from GEE.

    Args:
        num_patches: Number of patches to download.
        aoi_polygon: Shapely polygon defining the area of interest.
        aoi_bounds: Bounding box dict (west, south, east, north).
        max_cloud_cover: Maximum cloud cover percentage filter.
        start_date: Start date (YYYY-MM-DD) or None for 2 years back.
        end_date: End date (YYYY-MM-DD) or None for today.

    Returns:
        List of arrays, each shape (5, H, W) — 4 spectral bands + SCL.
    """
    # Convert shapely polygon coords to ee.Geometry.Polygon
    exterior_coords = list(aoi_polygon.exterior.coords)
    aoi = ee.Geometry.Polygon([[[lon, lat] for lon, lat in exterior_coords]])

    logger.info("Fetching Sentinel-2 collection for AOI...")
    collection = get_sentinel2_collection(aoi, max_cloud_cover, start_date, end_date)

    # Get list of image IDs
    image_list = collection.toList(500)
    num_images = image_list.size().getInfo()
    logger.info("Found %d Sentinel-2 images in collection", num_images)

    if num_images == 0:
        raise RuntimeError(
            "No Sentinel-2 images found. Check AOI, date range, and cloud cover filter."
        )

    # Generate sample points within the polygon
    sample_points = sample_patch_points(aoi_polygon, aoi_bounds, num_patches)

    patches: list[np.ndarray] = []
    failed = 0
    point_idx = 0

    while len(patches) < num_patches and point_idx < len(sample_points):
        point = sample_points[point_idx]
        point_idx += 1

        # Cycle through available images
        img_idx = point_idx % num_images
        image = ee.Image(image_list.get(img_idx))

        patch = download_patch(image, point["lon"], point["lat"])

        if patch is not None:
            patches.append(patch)
            if len(patches) % 10 == 0:
                logger.info(
                    "Downloaded %d / %d patches (failed: %d)",
                    len(patches),
                    num_patches,
                    failed,
                )
        else:
            failed += 1

        # Rate limiting to avoid GEE throttling
        time.sleep(0.5)

    logger.info(
        "Download complete: %d patches collected, %d failed",
        len(patches),
        failed,
    )
    return patches


# ── Dataset ────────────────────────────────────────────────────────────


def create_labels(
    spectral: np.ndarray, scl: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Create pseudo-labels from NDWI and apply SCL cloud masking.

    Args:
        spectral: (4, H, W) — blue, green, red, nir normalized to 0-1.
        scl: (H, W) — Scene Classification Layer values.

    Returns:
        Tuple of (valid_mask, water_label):
            valid_mask: (H, W) bool — True where pixel is usable (not cloud).
            water_label: (H, W) float32 — 1.0 for water, 0.0 for non-water.
    """
    green = spectral[1]  # B3
    nir = spectral[3]  # B8

    # Cloud mask from SCL
    cloud_mask = np.zeros_like(scl, dtype=bool)
    for val in SCL_EXCLUDE:
        cloud_mask |= scl == val
    valid_mask = ~cloud_mask

    # NDWI: (green - nir) / (green + nir)
    denom = green + nir
    denom = np.where(denom == 0, 1e-10, denom)
    ndwi = (green - nir) / denom

    water_label = (ndwi > NDWI_THRESHOLD).astype(np.float32)

    water_pct = water_label[valid_mask > 0].mean() * 100 if valid_mask.sum() > 0 else 0
    if water_pct > 0:
        logger.debug("Patch water coverage: %.2f%%", water_pct)

    return valid_mask, water_label


class WaterSegmentationDataset(Dataset):
    """PyTorch dataset for water segmentation training."""

    def __init__(self, patches: list[np.ndarray], target_size: int = PATCH_SIZE):
        """
        Args:
            patches: List of arrays, each (5, H, W) — 4 bands + SCL.
            target_size: Resize patches to this square size.
        """
        self.samples: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        self.target_size = target_size

        for raw_patch in patches:
            spectral = raw_patch[:4]  # (4, H, W) — blue, green, red, nir
            scl = raw_patch[4]  # (H, W) — Scene Classification

            # Normalize spectral bands: 0-10000 → 0-1
            spectral = np.clip(spectral / BAND_SCALE, 0.0, 1.0)

            valid_mask, water_label = create_labels(spectral, scl)

            # Skip patches with too much cloud (>50% invalid)
            valid_ratio = valid_mask.sum() / valid_mask.size
            if valid_ratio < 0.5:
                continue

            # Resize/crop to target size
            spectral, water_label, valid_mask = self._resize(
                spectral, water_label, valid_mask
            )

            self.samples.append(
                (
                    spectral.astype(np.float32),
                    water_label.astype(np.float32),
                    valid_mask.astype(np.float32),
                )
            )

        # Log water stats across dataset
        water_ratios = []
        for _, lbl, msk in self.samples:
            valid_px = msk.sum()
            if valid_px > 0:
                water_ratios.append(lbl[msk > 0].mean() * 100)
        avg_water = np.mean(water_ratios) if water_ratios else 0
        max_water = np.max(water_ratios) if water_ratios else 0
        logger.info(
            "Dataset: %d usable samples from %d patches | water coverage: avg=%.2f%%, max=%.2f%%",
            len(self.samples), len(patches), avg_water, max_water,
        )

        # ── Oversample patches that contain water ──
        WATER_THRESHOLD_PCT = 0.5  # minimum water coverage to count as "wet"
        wet_samples = []
        dry_samples = []
        for i, ratio in enumerate(water_ratios):
            if ratio > WATER_THRESHOLD_PCT:
                wet_samples.append(i)
            else:
                dry_samples.append(i)

        if wet_samples and dry_samples:
            # Duplicate wet samples so they represent ~50% of the dataset
            oversample_factor = max(1, len(dry_samples) // len(wet_samples))
            extra_samples = [self.samples[i] for i in wet_samples] * (oversample_factor - 1)
            self.samples.extend(extra_samples)
            logger.info(
                "Oversampling: %d wet patches (>%.1f%% water), %d dry patches | "
                "oversample factor: %dx | total samples after: %d",
                len(wet_samples), WATER_THRESHOLD_PCT, len(dry_samples),
                oversample_factor, len(self.samples),
            )
        else:
            logger.warning(
                "Oversampling skipped: %d wet, %d dry patches — need both for oversampling",
                len(wet_samples), len(dry_samples),
            )

        # ── Compute pos_weight for Focal Loss ──
        total_water_px = 0.0
        total_valid_px = 0.0
        for _, lbl, msk in self.samples:
            valid = msk > 0
            total_valid_px += valid.sum()
            total_water_px += lbl[valid].sum()

        total_dry_px = total_valid_px - total_water_px
        if total_water_px > 0:
            self.pos_weight = min(total_dry_px / total_water_px, 100.0)
        else:
            self.pos_weight = 100.0  # cap when no water pixels at all
        logger.info(
            "Pixel balance: %.0f water / %.0f dry → pos_weight=%.1f (capped at 100)",
            total_water_px, total_dry_px, self.pos_weight,
        )

    def _resize(
        self,
        spectral: np.ndarray,
        label: np.ndarray,
        mask: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Center-crop or pad to target_size."""
        _, h, w = spectral.shape
        th, tw = self.target_size, self.target_size

        if h >= th and w >= tw:
            # Center crop
            y0 = (h - th) // 2
            x0 = (w - tw) // 2
            spectral = spectral[:, y0 : y0 + th, x0 : x0 + tw]
            label = label[y0 : y0 + th, x0 : x0 + tw]
            mask = mask[y0 : y0 + th, x0 : x0 + tw]
        else:
            # Pad with zeros
            pad_spectral = np.zeros((4, th, tw), dtype=spectral.dtype)
            pad_label = np.zeros((th, tw), dtype=label.dtype)
            pad_mask = np.zeros((th, tw), dtype=mask.dtype)

            ph, pw = min(h, th), min(w, tw)
            pad_spectral[:, :ph, :pw] = spectral[:, :ph, :pw]
            pad_label[:ph, :pw] = label[:ph, :pw]
            pad_mask[:ph, :pw] = mask[:ph, :pw]

            spectral = pad_spectral
            label = pad_label
            mask = pad_mask

        return spectral, label, mask

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        spectral, label, valid_mask = self.samples[idx]
        return {
            "image": torch.from_numpy(spectral),  # (4, H, W)
            "label": torch.from_numpy(label).unsqueeze(0),  # (1, H, W)
            "valid_mask": torch.from_numpy(valid_mask).unsqueeze(0),  # (1, H, W)
        }


# ── Loss ───────────────────────────────────────────────────────────────


class FocalDiceLoss(nn.Module):
    """Combined Focal Loss + Dice loss with cloud masking.

    Focal Loss down-weights easy (majority-class) examples so the model
    focuses on the rare positive class (water).  Formula per-pixel:
        -alpha * (1 - p_t)^gamma * log(p_t)
    where p_t = p for positives, 1-p for negatives.
    """

    def __init__(
        self,
        focal_weight: float = 0.5,
        smooth: float = 1.0,
        alpha: float = 0.75,
        gamma: float = 2.0,
        pos_weight: float = 1.0,
    ):
        super().__init__()
        self.focal_weight = focal_weight
        self.smooth = smooth
        self.alpha = alpha
        self.gamma = gamma
        self.pos_weight = pos_weight

    def forward(
        self,
        pred: torch.Tensor,
        target: torch.Tensor,
        valid_mask: torch.Tensor,
    ) -> torch.Tensor:
        # ── Focal Loss component (masked) ──
        pred_clamped = torch.clamp(pred, 1e-7, 1.0 - 1e-7)

        # Per-pixel alpha: higher weight for positives (water)
        alpha_t = target * self.alpha + (1 - target) * (1 - self.alpha)

        # Apply pos_weight: scale the positive-class log term
        bce_term = (
            -target * self.pos_weight * torch.log(pred_clamped)
            - (1 - target) * torch.log(1 - pred_clamped)
        )

        # Focal modulation: (1 - p_t)^gamma
        p_t = target * pred_clamped + (1 - target) * (1 - pred_clamped)
        focal_mod = (1 - p_t) ** self.gamma

        focal_loss = alpha_t * focal_mod * bce_term
        focal_loss = (focal_loss * valid_mask).sum() / (valid_mask.sum() + 1e-8)

        # ── Dice component (masked) ──
        pred_masked = pred * valid_mask
        target_masked = target * valid_mask

        intersection = (pred_masked * target_masked).sum()
        union = pred_masked.sum() + target_masked.sum()
        dice_loss = 1.0 - (2.0 * intersection + self.smooth) / (union + self.smooth)

        return self.focal_weight * focal_loss + (1.0 - self.focal_weight) * dice_loss


# ── Metrics ────────────────────────────────────────────────────────────


def compute_metrics(
    pred: torch.Tensor,
    target: torch.Tensor,
    valid_mask: torch.Tensor,
    threshold: float = 0.5,
) -> dict[str, float]:
    """Compute segmentation metrics (masked)."""
    pred_bin = (pred > threshold).float() * valid_mask
    target_masked = target * valid_mask

    tp = (pred_bin * target_masked).sum().item()
    fp = (pred_bin * (1 - target_masked)).sum().item()
    fn = ((1 - pred_bin) * target_masked).sum().item()

    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)

    intersection = tp
    union = tp + fp + fn
    iou = intersection / (union + 1e-8)

    return {
        "iou": round(iou, 4),
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }


# ── Training ───────────────────────────────────────────────────────────


def train(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    epochs: int,
    lr: float,
    output_path: str,
    device: torch.device,
    pos_weight: float = 1.0,
) -> dict[str, Any]:
    """Train the U-Net model with early stopping."""
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", patience=5, factor=0.5
    )
    criterion = FocalDiceLoss(pos_weight=pos_weight)
    logger.info("Loss: FocalDiceLoss (alpha=0.75, gamma=2.0, pos_weight=%.1f)", pos_weight)

    best_val_loss = float("inf")
    patience_counter = 0
    patience = 10
    history: list[dict[str, Any]] = []

    for epoch in range(1, epochs + 1):
        # ── Train phase ──
        model.train()
        train_loss = 0.0
        train_metrics_accum: dict[str, float] = {"iou": 0, "f1": 0, "precision": 0, "recall": 0}
        train_batches = 0

        for batch in train_loader:
            images = batch["image"].to(device)
            labels = batch["label"].to(device)
            masks = batch["valid_mask"].to(device)

            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels, masks)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            metrics = compute_metrics(outputs.detach(), labels, masks)
            for k in train_metrics_accum:
                train_metrics_accum[k] += metrics[k]
            train_batches += 1

        avg_train_loss = train_loss / max(train_batches, 1)
        avg_train_metrics = {
            k: round(v / max(train_batches, 1), 4) for k, v in train_metrics_accum.items()
        }

        # ── Validation phase ──
        model.eval()
        val_loss = 0.0
        val_metrics_accum: dict[str, float] = {"iou": 0, "f1": 0, "precision": 0, "recall": 0}
        val_batches = 0

        with torch.no_grad():
            for batch in val_loader:
                images = batch["image"].to(device)
                labels = batch["label"].to(device)
                masks = batch["valid_mask"].to(device)

                outputs = model(images)
                loss = criterion(outputs, labels, masks)

                val_loss += loss.item()
                metrics = compute_metrics(outputs, labels, masks)
                for k in val_metrics_accum:
                    val_metrics_accum[k] += metrics[k]
                val_batches += 1

        avg_val_loss = val_loss / max(val_batches, 1)
        avg_val_metrics = {
            k: round(v / max(val_batches, 1), 4) for k, v in val_metrics_accum.items()
        }

        scheduler.step(avg_val_loss)

        epoch_data = {
            "epoch": epoch,
            "train_loss": round(avg_train_loss, 4),
            "val_loss": round(avg_val_loss, 4),
            "train_metrics": avg_train_metrics,
            "val_metrics": avg_val_metrics,
            "lr": optimizer.param_groups[0]["lr"],
        }
        history.append(epoch_data)

        logger.info(
            "Epoch %d/%d — train_loss: %.4f, val_loss: %.4f | "
            "val_IoU: %.4f, val_F1: %.4f, val_P: %.4f, val_R: %.4f",
            epoch,
            epochs,
            avg_train_loss,
            avg_val_loss,
            avg_val_metrics["iou"],
            avg_val_metrics["f1"],
            avg_val_metrics["precision"],
            avg_val_metrics["recall"],
        )

        # ── Early stopping ──
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0

            # Save best model (state_dict only, matching UNetStrategy._load_model)
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), output_file)
            logger.info("Saved best model to %s (val_loss: %.4f)", output_path, avg_val_loss)
        else:
            patience_counter += 1
            if patience_counter >= patience:
                logger.info(
                    "Early stopping at epoch %d (no improvement for %d epochs)",
                    epoch,
                    patience,
                )
                break

    return {
        "best_val_loss": round(best_val_loss, 4),
        "total_epochs": len(history),
        "final_metrics": history[-1]["val_metrics"] if history else {},
        "history": history,
    }


# ── Main ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train U-Net water segmentation model using Sentinel-2 data from GEE"
    )
    parser.add_argument("--epochs", type=int, default=50, help="Max training epochs (default: 50)")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size (default: 8)")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate (default: 1e-4)")
    parser.add_argument("--patches", type=int, default=80, help="Number of patches to download (default: 80)")
    parser.add_argument(
        "--output-path",
        type=str,
        default="/data/geo/models/water_unet.pth",
        help="Output path for trained model weights",
    )
    parser.add_argument(
        "--credentials-dir",
        type=str,
        default="/app/credentials",
        help="Directory containing GEE service account JSON",
    )
    parser.add_argument(
        "--max-cloud-cover",
        type=float,
        default=20.0,
        help="Max cloud cover percentage (default: 20)",
    )
    parser.add_argument(
        "--aoi-file",
        type=str,
        default="/app/capas/zona.geojson",
        help="Path to GeoJSON/KML/KMZ file defining the AOI (default: /app/capas/zona.geojson)",
    )
    parser.add_argument(
        "--ndwi-threshold",
        type=float,
        default=0.1,
        help="NDWI threshold for pseudo-labels (default: 0.1, lower=more water detected)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date for Sentinel-2 filter (YYYY-MM-DD). Default: 2 years back from end-date",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date for Sentinel-2 filter (YYYY-MM-DD). Default: today",
    )
    args = parser.parse_args()

    # Override global NDWI threshold from CLI
    global NDWI_THRESHOLD
    NDWI_THRESHOLD = args.ndwi_threshold

    logger.info("=" * 60)
    logger.info("U-Net Water Segmentation Training")
    logger.info("=" * 60)
    logger.info("Config: epochs=%d, batch_size=%d, lr=%.6f, patches=%d, ndwi_thresh=%.2f",
                args.epochs, args.batch_size, args.lr, args.patches, NDWI_THRESHOLD)
    logger.info("Output: %s", args.output_path)

    # ── Device ──
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)
    if device.type == "cuda":
        logger.info("GPU: %s", torch.cuda.get_device_name(0))
        logger.info("VRAM: %.1f GB", torch.cuda.get_device_properties(0).total_memory / 1e9)

    # ── Load AOI ──
    logger.info("Loading AOI from %s", args.aoi_file)
    aoi_polygon, aoi_bounds = load_aoi(args.aoi_file)

    # ── Initialize GEE ──
    logger.info("Initializing Google Earth Engine...")
    initialize_gee(args.credentials_dir)

    # ── Download patches ──
    logger.info("Downloading %d Sentinel-2 patches...", args.patches)
    raw_patches = download_patches(
        args.patches, aoi_polygon, aoi_bounds,
        args.max_cloud_cover, args.start_date, args.end_date,
    )

    if len(raw_patches) < 10:
        logger.error(
            "Only %d patches downloaded — need at least 10 for training. "
            "Check GEE credentials and network connectivity.",
            len(raw_patches),
        )
        sys.exit(1)

    # ── Create dataset ──
    dataset = WaterSegmentationDataset(raw_patches)

    if len(dataset) < 5:
        logger.error(
            "Only %d usable samples after filtering — not enough for training.", len(dataset)
        )
        sys.exit(1)

    # ── Train/val split (80/20) ──
    val_size = max(1, int(len(dataset) * 0.2))
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = random_split(
        dataset,
        [train_size, val_size],
        generator=torch.Generator().manual_seed(42),
    )
    logger.info("Split: %d train, %d val", train_size, val_size)

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=2,
        pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=2,
        pin_memory=(device.type == "cuda"),
    )

    # ── Model ──
    # Architecture MUST match UNetStrategy in water_segmentation.py:
    #   encoder_name="resnet34", in_channels=4, classes=1, activation="sigmoid"
    model = smp.Unet(
        encoder_name="resnet34",
        encoder_weights="imagenet",
        in_channels=4,
        classes=1,
        activation="sigmoid",
    )
    model = model.to(device)

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Model: U-Net ResNet34 — %dM params (%dM trainable)",
                total_params // 1_000_000, trainable_params // 1_000_000)

    # ── Train ──
    results = train(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        epochs=args.epochs,
        lr=args.lr,
        output_path=args.output_path,
        device=device,
        pos_weight=dataset.pos_weight,
    )

    # ── Final summary ──
    logger.info("=" * 60)
    logger.info("TRAINING COMPLETE")
    logger.info("=" * 60)
    logger.info("Total epochs: %d", results["total_epochs"])
    logger.info("Best val loss: %.4f", results["best_val_loss"])
    if results["final_metrics"]:
        logger.info("Final val metrics:")
        for k, v in results["final_metrics"].items():
            logger.info("  %s: %.4f", k, v)
    logger.info("Model saved to: %s", args.output_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
