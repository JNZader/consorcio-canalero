"""
VisualizationService — orchestration layer for 3D terrain rendering.

Responsibilities:
  - Load DEM from disk via rasterio (path passed directly from router).
  - Call calculation functions from intelligence/calculations.py.
  - Call pure render functions from renderer.py.
  - Raise HTTPException(404) when the DEM file is not found.

Does NOT contain rendering logic — that lives in renderer.py.
Does NOT contain geo calculation logic — that lives in calculations.py.

Calculation functions wired in this phase:
  - generar_zonificacion(dem_path, flow_acc_path, threshold) → cuencas_gdf
  - simular_escorrentia(flow_dir_path, flow_acc_path, punto_inicio, lluvia_mm) → geojson
  - detectar_puntos_conflicto(canales_gdf, caminos_gdf, drenajes_gdf, flow_acc_path, slope_path)
    → conflictos_gdf

Note: canales, caminos, drenajes GeoDataFrames are empty for now — the infrastructure
domain stores point assets, not linestrings. detectar_puntos_conflicto skips empty GDFs.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import geopandas as gpd
import numpy as np
import rasterio
from fastapi import HTTPException

from app.domains.geo.visualization import renderer
from app.domains.geo.intelligence.calculations import (
    detectar_puntos_conflicto,
    generar_zonificacion,
    simular_escorrentia,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Empty GeoDataFrames used as placeholders for infrastructure linestrings
# until the infrastructure domain exposes canal/road LineString geometries.
_EMPTY_LINES_GDF = gpd.GeoDataFrame({"geometry": []})


class VisualizationService:
    """Orchestrate data loading, calculations, and rendering for visualization."""

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

    def render_cuencas(
        self,
        db: "Session",
        dem_path: Path,
        flow_acc_path: Path,
    ) -> bytes:
        """Render 3D terrain surface with basin polygon overlays.

        Calls generar_zonificacion to delineate sub-basins, then loads the DEM
        and renders the 3D terrain with basin overlays.

        Args:
            db: SQLAlchemy session (reserved for future DB wiring).
            dem_path: Path to the DEM GeoTIFF file.
            flow_acc_path: Path to the flow accumulation raster.

        Returns:
            PNG image as bytes.

        Raises:
            HTTPException(404): If dem_path does not exist.
        """
        elevation, transform = self._load_dem(dem_path)
        cuencas_gdf = generar_zonificacion(str(dem_path), str(flow_acc_path))
        return renderer.render_cuencas_3d(elevation, transform, cuencas_gdf)

    def render_escorrentia(
        self,
        db: "Session",
        dem_path: Path,
        flow_dir_path: Path,
        flow_acc_path: Path,
        lon: float = -63.0,
        lat: float = -31.0,
        lluvia_mm: float = 50.0,
    ) -> bytes:
        """Render escorrentia (runoff) flow paths as 3D polylines over DEM terrain.

        Traces a downstream flow path from the given starting point using D8 flow
        direction, weighted by rainfall amount.

        Args:
            db: SQLAlchemy session (reserved for future DB wiring).
            dem_path: Path to the DEM GeoTIFF file (used as visual terrain base).
            flow_dir_path: Path to the D8 flow direction raster.
            flow_acc_path: Path to the flow accumulation raster.
            lon: Longitude of the starting point (default: -63.0).
            lat: Latitude of the starting point (default: -31.0).
            lluvia_mm: Rainfall amount in mm (default: 50.0).

        Returns:
            PNG image as bytes.

        Raises:
            HTTPException(404): If dem_path does not exist.
        """
        elevation, transform = self._load_dem(dem_path)
        geojson_result = simular_escorrentia(
            str(flow_dir_path),
            str(flow_acc_path),
            punto_inicio=(lon, lat),
            lluvia_mm=lluvia_mm,
        )
        return renderer.render_escorrentia_3d(elevation, transform, geojson_result)

    def render_riesgo(
        self,
        db: "Session",
        dem_path: Path,
        flow_acc_path: Path,
        slope_path: Path,
    ) -> bytes:
        """Render hydraulic risk zones as colored polygons over DEM terrain.

        Detects infrastructure conflict points where flow accumulation and slope
        thresholds indicate hydraulic risk, then renders them color-coded by level.

        Args:
            db: SQLAlchemy session (reserved for future DB wiring).
            dem_path: Path to the DEM GeoTIFF file.
            flow_acc_path: Path to the flow accumulation raster.
            slope_path: Path to the slope raster.

        Returns:
            PNG image as bytes.

        Raises:
            HTTPException(404): If dem_path does not exist.
        """
        elevation, transform = self._load_dem(dem_path)
        conflictos_gdf = detectar_puntos_conflicto(
            _EMPTY_LINES_GDF,
            _EMPTY_LINES_GDF,
            _EMPTY_LINES_GDF,
            str(flow_acc_path),
            str(slope_path),
        )
        return renderer.render_riesgo_3d(elevation, transform, conflictos_gdf)

    def render_animacion(
        self,
        db: "Session",
        dem_path: Path,
        flow_acc_path: Path,
        slope_path: Path,
    ) -> bytes:
        """Produce an MP4 animation via animated camera flyover.

        Combines terrain, basin delineation (generar_zonificacion) and conflict
        points (detectar_puntos_conflicto) into a fly-through animation.

        Args:
            db: SQLAlchemy session (reserved for future DB wiring).
            dem_path: Path to the DEM GeoTIFF file.
            flow_acc_path: Path to the flow accumulation raster.
            slope_path: Path to the slope raster.

        Returns:
            MP4 video as bytes.

        Raises:
            HTTPException(404): If dem_path does not exist.
        """
        elevation, transform = self._load_dem(dem_path)
        cuencas_gdf = generar_zonificacion(str(dem_path), str(flow_acc_path))
        conflictos_gdf = detectar_puntos_conflicto(
            _EMPTY_LINES_GDF,
            _EMPTY_LINES_GDF,
            _EMPTY_LINES_GDF,
            str(flow_acc_path),
            str(slope_path),
        )
        return renderer.render_animacion_tormenta(
            elevation, transform, cuencas_gdf, conflictos_gdf
        )
