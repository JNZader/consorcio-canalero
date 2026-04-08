"""
Water segmentation using pluggable strategies.

Strategy 1: NDWI thresholding (fast, no model needed)
Strategy 2: U-Net semantic segmentation (more accurate, needs model weights)

Both strategies produce a binary water mask that gets vectorized
to PostGIS polygons for overlay on the map.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import shapes as rasterio_shapes
from shapely.geometry import shape

logger = logging.getLogger(__name__)


class WaterSegmentationStrategy(ABC):
    """Base class for water segmentation strategies."""

    @abstractmethod
    def segment(self, bands: dict[str, np.ndarray], profile: dict) -> np.ndarray:
        """Produce a binary water mask (1=water, 0=not water).

        Args:
            bands: Dict of band_name → 2D numpy array (float32, 0-1 range).
            profile: Rasterio profile of the input raster.

        Returns:
            Binary mask (uint8) same shape as input bands.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def requires_model(self) -> bool:
        return False


class NDWIStrategy(WaterSegmentationStrategy):
    """NDWI thresholding with morphological cleanup.

    Fast baseline strategy. Works well for clear water bodies,
    less accurate for shallow/turbid water.
    """

    def __init__(self, threshold: float = 0.1, min_area_px: int = 10):
        self.threshold = threshold
        self.min_area_px = min_area_px

    @property
    def name(self) -> str:
        return "ndwi"

    def segment(self, bands: dict[str, np.ndarray], profile: dict) -> np.ndarray:
        green = bands["green"]
        nir = bands["nir"]

        # Avoid division by zero
        denom = green + nir
        denom = np.where(denom == 0, 1e-10, denom)
        ndwi = (green - nir) / denom

        mask = (ndwi >= self.threshold).astype(np.uint8)

        # Morphological cleanup: remove small isolated pixels
        try:
            from scipy.ndimage import binary_opening, binary_closing, label

            struct = np.ones((3, 3))
            mask = binary_opening(mask, structure=struct).astype(np.uint8)
            mask = binary_closing(mask, structure=struct).astype(np.uint8)

            # Remove small connected components
            labeled, num_features = label(mask)
            for i in range(1, num_features + 1):
                if np.sum(labeled == i) < self.min_area_px:
                    mask[labeled == i] = 0
        except ImportError:
            pass  # scipy not available, skip morphological ops

        return mask


class UNetStrategy(WaterSegmentationStrategy):
    """U-Net semantic segmentation for water detection.

    Uses segmentation-models-pytorch with pre-trained encoder.
    Falls back to NDWI if model weights are not available.
    """

    MODEL_DIR = Path("/data/geo/models")
    MODEL_FILE = "water_unet.pth"

    def __init__(self, model_path: str | None = None):
        self._model_path = model_path or str(self.MODEL_DIR / self.MODEL_FILE)
        self._model = None

    @property
    def name(self) -> str:
        return "unet"

    @property
    def requires_model(self) -> bool:
        return True

    @property
    def model_available(self) -> bool:
        return Path(self._model_path).exists()

    def _load_model(self):
        """Lazy-load the U-Net model."""
        if self._model is not None:
            return

        import torch
        import segmentation_models_pytorch as smp

        # Create U-Net with pre-trained ResNet34 encoder
        self._model = smp.Unet(
            encoder_name="resnet34",
            encoder_weights=None,  # We load our own weights
            in_channels=4,  # B2(blue), B3(green), B4(red), B8(nir)
            classes=1,  # Binary: water/not-water
            activation="sigmoid",
        )

        if self.model_available:
            state_dict = torch.load(self._model_path, map_location="cpu")
            self._model.load_state_dict(state_dict)
            logger.info("Loaded U-Net weights from %s", self._model_path)
        else:
            logger.warning(
                "U-Net weights not found at %s — using random weights (untrained). "
                "Train the model or download pre-trained weights.",
                self._model_path,
            )

        self._model.eval()

    def segment(self, bands: dict[str, np.ndarray], profile: dict) -> np.ndarray:
        import torch

        self._load_model()

        # Stack bands into (1, C, H, W) tensor
        # Expected order: blue, green, red, nir
        band_order = ["blue", "green", "red", "nir"]
        available = [b for b in band_order if b in bands]

        if len(available) < 4:
            logger.warning(
                "U-Net needs 4 bands (blue/green/red/nir), got %d. Falling back to NDWI.",
                len(available),
            )
            return NDWIStrategy().segment(bands, profile)

        stack = np.stack([bands[b] for b in band_order], axis=0)  # (4, H, W)
        tensor = torch.from_numpy(stack).unsqueeze(0).float()  # (1, 4, H, W)

        # Pad to multiple of 32 (U-Net requirement)
        h, w = stack.shape[1], stack.shape[2]
        pad_h = (32 - h % 32) % 32
        pad_w = (32 - w % 32) % 32
        if pad_h > 0 or pad_w > 0:
            tensor = torch.nn.functional.pad(
                tensor, (0, pad_w, 0, pad_h), mode="reflect"
            )

        with torch.no_grad():
            assert self._model is not None
            output = self._model(tensor)  # (1, 1, H+pad, W+pad)

        # Remove padding and threshold
        mask = output[0, 0, :h, :w].numpy()
        mask = (mask > 0.5).astype(np.uint8)

        return mask


# ── Pipeline functions ──────────────────────────────────────────────


def get_strategy(name: str = "ndwi") -> WaterSegmentationStrategy:
    """Get a water segmentation strategy by name."""
    strategies = {
        "ndwi": NDWIStrategy,
        "unet": UNetStrategy,
    }
    cls = strategies.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown strategy: {name}. Available: {list(strategies.keys())}"
        )
    return cls()


def segment_raster(
    raster_path: str,
    output_path: str,
    strategy_name: str = "ndwi",
    band_mapping: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Run water segmentation on a local raster file.

    Args:
        raster_path: Path to multi-band GeoTIFF.
        output_path: Where to save the water mask.
        strategy_name: "ndwi" or "unet".
        band_mapping: Map of band_name → band_index (1-based).
                      Default assumes Sentinel-2 order.

    Returns:
        Dict with stats and output path.
    """
    strategy = get_strategy(strategy_name)

    if not band_mapping:
        # Default: assume Sentinel-2 10m bands order
        band_mapping = {"blue": 1, "green": 2, "red": 3, "nir": 4}

    with rasterio.open(raster_path) as src:
        profile = src.profile.copy()
        bands = {}
        for name, idx in band_mapping.items():
            if idx <= src.count:
                data = src.read(idx).astype(np.float32)
                # Normalize to 0-1 if values > 1
                if data.max() > 1:
                    data = data / 10000.0
                bands[name] = data

    if not bands:
        raise ValueError("No valid bands found in raster")

    mask = strategy.segment(bands, profile)

    # Save mask
    out_profile = profile.copy()
    out_profile.update(dtype="uint8", count=1, nodata=255)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **out_profile) as dst:
        dst.write(mask, 1)

    # Compute stats
    water_pixels = int(np.sum(mask == 1))
    total_pixels = int(mask.size)
    cell_size = abs(profile["transform"].a)
    water_area_ha = (water_pixels * cell_size**2) / 10_000

    return {
        "strategy": strategy.name,
        "model_available": strategy.model_available
        if hasattr(strategy, "model_available")
        else True,
        "output_path": output_path,
        "water_pixels": water_pixels,
        "total_pixels": total_pixels,
        "water_pct": round((water_pixels / total_pixels) * 100, 2)
        if total_pixels > 0
        else 0,
        "water_area_ha": round(water_area_ha, 2),
    }


def vectorize_water_mask(
    mask_path: str,
) -> list[dict[str, Any]]:
    """Convert a binary water mask raster to GeoJSON polygons.

    Args:
        mask_path: Path to the water mask raster (1=water, 0=dry).

    Returns:
        List of GeoJSON Feature dicts.
    """
    with rasterio.open(mask_path) as src:
        mask = src.read(1)
        transform = src.transform

    features = []
    for geom, value in rasterio_shapes(mask, mask=(mask == 1), transform=transform):
        if value == 1:
            area = shape(geom).area
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "class": "water",
                        "area_m2": round(area, 2),
                    },
                }
            )

    return features
