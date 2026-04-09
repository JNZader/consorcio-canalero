"""
VisualizationService — orchestration layer for 3D terrain rendering.

Responsibilities:
  - Load DEM from disk via rasterio (path passed directly from router).
  - Call pure render functions from renderer.py.
  - Raise HTTPException(404) when the DEM file is not found.

Does NOT contain rendering logic — that lives in renderer.py.

Open question (Phase 6 task 6.2): DEM path will be sourced from
SettingsService.get(db, "geo_dem_path") with fallback to /data/geo/dem.tif.
For now, dem_path is passed directly from the router.

Phase 3 simplification: cuencas/conflictos GeoDataFrames are empty by default.
Real DB wiring (IntelligenceRepository) is a future task.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import geopandas as gpd
import numpy as np
import rasterio
from fastapi import HTTPException

from app.domains.geo.visualization import renderer

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class VisualizationService:
    """Orchestrate data loading and rendering for the visualization subdomain."""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_dem(self, dem_path: Path) -> tuple[np.ndarray, object]:
        """Load a DEM GeoTIFF from disk and return (elevation_array, transform).

        Args:
            dem_path: Filesystem path to the DEM GeoTIFF file.

        Returns:
            Tuple of (elevation 2-D numpy array, rasterio affine transform).

        Raises:
            HTTPException(404): If dem_path does not exist on disk.
        """
        if not Path(dem_path).exists():
            raise HTTPException(
                status_code=404,
                detail=f"DEM not found: {dem_path}",
            )
        with rasterio.open(dem_path) as ds:
            elevation: np.ndarray = ds.read(1)
            transform = ds.transform
        return elevation, transform

    # ------------------------------------------------------------------
    # Public render methods
    # ------------------------------------------------------------------

    def render_cuencas(self, db: "Session", dem_path: Path) -> bytes:
        """Render 3D terrain surface with basin polygon overlays.

        Args:
            db: SQLAlchemy session (reserved for future DB wiring).
            dem_path: Path to the DEM GeoTIFF file.

        Returns:
            PNG image as bytes.

        Raises:
            HTTPException(404): If dem_path does not exist.
        """
        elevation, transform = self._load_dem(dem_path)
        cuencas_gdf = gpd.GeoDataFrame({"geometry": []})
        return renderer.render_cuencas_3d(elevation, transform, cuencas_gdf)

    def render_escorrentia(self, db: "Session", dem_path: Path) -> bytes:
        """Render escorrentia (runoff) flow paths as 3D polylines over DEM terrain.

        Args:
            db: SQLAlchemy session (reserved for future DB wiring).
            dem_path: Path to the DEM GeoTIFF file.

        Returns:
            PNG image as bytes.

        Raises:
            HTTPException(404): If dem_path does not exist.
        """
        elevation, transform = self._load_dem(dem_path)
        geojson_result: dict = {"type": "FeatureCollection", "features": []}
        return renderer.render_escorrentia_3d(elevation, transform, geojson_result)

    def render_riesgo(self, db: "Session", dem_path: Path) -> bytes:
        """Render hydraulic risk zones as colored polygons over DEM terrain.

        Args:
            db: SQLAlchemy session (reserved for future DB wiring).
            dem_path: Path to the DEM GeoTIFF file.

        Returns:
            PNG image as bytes.

        Raises:
            HTTPException(404): If dem_path does not exist.
        """
        elevation, transform = self._load_dem(dem_path)
        conflictos_gdf = gpd.GeoDataFrame({"geometry": [], "nivel_riesgo": []})
        return renderer.render_riesgo_3d(elevation, transform, conflictos_gdf)

    def render_animacion(self, db: "Session", dem_path: Path, fecha: str = "") -> bytes:
        """Produce an MP4 animation via animated camera flyover.

        Args:
            db: SQLAlchemy session (reserved for future DB wiring).
            dem_path: Path to the DEM GeoTIFF file.
            fecha: Storm date string (reserved for future filtering).

        Returns:
            MP4 video as bytes.

        Raises:
            HTTPException(404): If dem_path does not exist.
        """
        elevation, transform = self._load_dem(dem_path)
        cuencas_gdf = gpd.GeoDataFrame({"geometry": []})
        conflictos_gdf = gpd.GeoDataFrame({"geometry": [], "nivel_riesgo": []})
        return renderer.render_animacion_tormenta(
            elevation, transform, cuencas_gdf, conflictos_gdf
        )
