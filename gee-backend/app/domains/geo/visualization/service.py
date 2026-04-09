"""
VisualizationService — orchestration layer for 3D terrain rendering.

Responsibilities:
  - Look up layer paths from the geo_layers table via GeoRepository.
  - Load DEM from disk via rasterio.
  - Call calculation functions from intelligence/calculations.py.
  - Call pure render functions from renderer.py.
  - Raise HTTPException(404) when no layer of the requested type is found.

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
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from app.domains.geo.models import TipoGeoLayer
from app.domains.geo.repository import GeoRepository
from app.domains.geo.visualization import renderer

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _empty_lines_gdf() -> Any:
    """Return an empty GeoDataFrame — lazy import to avoid top-level geopandas dep."""
    import geopandas as gpd  # noqa: PLC0415
    return gpd.GeoDataFrame({"geometry": []})


class VisualizationService:
    """Orchestrate data loading, calculations, and rendering for visualization."""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_layer_path(
        self,
        db: "Session",
        tipo: TipoGeoLayer,
        area_id: str | None = None,
    ) -> str:
        """Query geo_layers table for latest layer of given type.

        Args:
            db: SQLAlchemy session.
            tipo: Layer type enum value (e.g. TipoGeoLayer.DEM_RAW).
            area_id: Optional area identifier to scope the lookup.

        Returns:
            The archivo_path string for the found layer.

        Raises:
            HTTPException(404): If no layer of the given type is found.
        """
        repo = GeoRepository()
        if area_id:
            layer = repo.get_layer_by_tipo_and_area(db, tipo, area_id)
        else:
            layers, _total = repo.get_layers(db, tipo_filter=tipo, page=1, limit=1)
            layer = layers[0] if layers else None

        if not layer:
            raise HTTPException(
                status_code=404,
                detail=f"No layer of type '{tipo.value}' found. Run terrain analysis first.",
            )
        return layer.archivo_path

    def _load_dem(self, dem_path: Path) -> tuple[Any, Any]:
        """Load a DEM GeoTIFF from disk and return (elevation_array, transform).

        Args:
            dem_path: Filesystem path to the DEM GeoTIFF file.

        Returns:
            Tuple of (elevation 2-D numpy array, rasterio affine transform).

        Raises:
            HTTPException(404): If dem_path does not exist on disk.
        """
        import numpy as np  # noqa: PLC0415
        import rasterio  # noqa: PLC0415

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
        area_id: str | None = None,
    ) -> bytes:
        """Render 3D terrain surface with basin polygon overlays.

        Looks up DEM_RAW and FLOW_ACC layers from the database, then calls
        generar_zonificacion to delineate sub-basins and renders the 3D terrain
        with basin overlays.

        Args:
            db: SQLAlchemy session.
            area_id: Optional area ID to scope layer lookup.

        Returns:
            PNG image as bytes.

        Raises:
            HTTPException(404): If required layers are not found in the DB.
        """
        dem_path = self._get_layer_path(db, TipoGeoLayer.DEM_RAW, area_id)
        flow_acc_path = self._get_layer_path(db, TipoGeoLayer.FLOW_ACC, area_id)
        from app.domains.geo.intelligence.calculations import generar_zonificacion  # noqa: PLC0415

        elevation, transform = self._load_dem(dem_path)
        cuencas_gdf = generar_zonificacion(dem_path, flow_acc_path)
        return renderer.render_cuencas_3d(elevation, transform, cuencas_gdf)

    def render_escorrentia(
        self,
        db: "Session",
        lon: float = -63.0,
        lat: float = -31.0,
        lluvia_mm: float = 50.0,
        area_id: str | None = None,
    ) -> bytes:
        """Render escorrentia (runoff) flow paths as 3D polylines over DEM terrain.

        Looks up FLOW_DIR, FLOW_ACC, and DEM_RAW layers from the database, then
        traces a downstream flow path from the given starting point using D8 flow
        direction, weighted by rainfall amount.

        Args:
            db: SQLAlchemy session.
            lon: Longitude of the starting point (default: -63.0).
            lat: Latitude of the starting point (default: -31.0).
            lluvia_mm: Rainfall amount in mm (default: 50.0).
            area_id: Optional area ID to scope layer lookup.

        Returns:
            PNG image as bytes.

        Raises:
            HTTPException(404): If required layers are not found in the DB.
        """
        flow_dir_path = self._get_layer_path(db, TipoGeoLayer.FLOW_DIR, area_id)
        flow_acc_path = self._get_layer_path(db, TipoGeoLayer.FLOW_ACC, area_id)
        dem_path = self._get_layer_path(db, TipoGeoLayer.DEM_RAW, area_id)
        from app.domains.geo.intelligence.calculations import simular_escorrentia  # noqa: PLC0415

        elevation, transform = self._load_dem(dem_path)
        geojson_result = simular_escorrentia(
            flow_dir_path,
            flow_acc_path,
            punto_inicio=(lon, lat),
            lluvia_mm=lluvia_mm,
        )
        return renderer.render_escorrentia_3d(elevation, transform, geojson_result)

    def render_riesgo(
        self,
        db: "Session",
        area_id: str | None = None,
    ) -> bytes:
        """Render hydraulic risk zones as colored polygons over DEM terrain.

        Looks up DEM_RAW, FLOW_ACC, and SLOPE layers from the database, then
        detects infrastructure conflict points where flow accumulation and slope
        thresholds indicate hydraulic risk, and renders them color-coded by level.

        Args:
            db: SQLAlchemy session.
            area_id: Optional area ID to scope layer lookup.

        Returns:
            PNG image as bytes.

        Raises:
            HTTPException(404): If required layers are not found in the DB.
        """
        dem_path = self._get_layer_path(db, TipoGeoLayer.DEM_RAW, area_id)
        flow_acc_path = self._get_layer_path(db, TipoGeoLayer.FLOW_ACC, area_id)
        slope_path = self._get_layer_path(db, TipoGeoLayer.SLOPE, area_id)
        from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto  # noqa: PLC0415

        empty = _empty_lines_gdf()
        elevation, transform = self._load_dem(dem_path)
        conflictos_gdf = detectar_puntos_conflicto(
            empty, empty, empty, flow_acc_path, slope_path,
        )
        return renderer.render_riesgo_3d(elevation, transform, conflictos_gdf)

    def render_animacion(
        self,
        db: "Session",
        area_id: str | None = None,
    ) -> bytes:
        """Produce an MP4 animation via animated camera flyover.

        Looks up DEM_RAW, FLOW_ACC, and SLOPE layers from the database, then
        combines terrain, basin delineation (generar_zonificacion) and conflict
        points (detectar_puntos_conflicto) into a fly-through animation.

        Args:
            db: SQLAlchemy session.
            area_id: Optional area ID to scope layer lookup.

        Returns:
            MP4 video as bytes.

        Raises:
            HTTPException(404): If required layers are not found in the DB.
        """
        dem_path = self._get_layer_path(db, TipoGeoLayer.DEM_RAW, area_id)
        flow_acc_path = self._get_layer_path(db, TipoGeoLayer.FLOW_ACC, area_id)
        slope_path = self._get_layer_path(db, TipoGeoLayer.SLOPE, area_id)
        from app.domains.geo.intelligence.calculations import (  # noqa: PLC0415
            detectar_puntos_conflicto,
            generar_zonificacion,
        )

        empty = _empty_lines_gdf()
        elevation, transform = self._load_dem(dem_path)
        cuencas_gdf = generar_zonificacion(dem_path, flow_acc_path)
        conflictos_gdf = detectar_puntos_conflicto(
            empty, empty, empty, flow_acc_path, slope_path,
        )
        return renderer.render_animacion_tormenta(
            elevation, transform, cuencas_gdf, conflictos_gdf
        )
