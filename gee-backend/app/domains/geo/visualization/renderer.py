"""
Pure PyVista render functions for 3D terrain visualization.

Headless rendering requires xvfb installed in the Docker image (libgl1-mesa-glx xvfb).
pyvista.start_xvfb() is called once at module import to initialize the virtual display.
Tested against pyvista>=0.43.0 (VTK-based, CPU-only).

Render functions are intentionally pure:
  - They receive numpy arrays and GeoDataFrames as input.
  - They return bytes (PNG or MP4).
  - They do NOT access the database, filesystem, or network.
All I/O (DEM loading, DB reads) lives in service.py.
"""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import geopandas as gpd

try:
    import pyvista  # type: ignore

    pyvista.start_xvfb()
except Exception:
    # Allow import in test environments where xvfb is not available.
    # The unit tests mock pyvista entirely so this is safe.
    pass

# Risk level → RGB color mapping (0-255 per channel)
_RISK_COLORS: dict[str, tuple[int, int, int]] = {
    "bajo": (0, 200, 0),  # green
    "medio": (255, 255, 0),  # yellow
    "alto": (255, 140, 0),  # orange
    "critico": (220, 0, 0),  # red
}
_DEFAULT_RISK_COLOR: tuple[int, int, int] = (128, 128, 128)  # grey for unknown levels

# Camera azimuth positions for the flyover animation (degrees)
_ANIMATION_AZIMUTHS: list[int] = [0, 45, 90, 135, 180, 225, 270, 315]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _dem_to_grid(elevation: np.ndarray, transform) -> "pyvista.StructuredGrid":
    """Convert a 2-D elevation array + affine transform to a PyVista StructuredGrid.

    Args:
        elevation: 2-D numpy array of DEM elevation values (rows=Y, cols=X).
        transform: Affine transform from rasterio providing pixel→world coord mapping.
                   Expected fields: .a (x pixel size), .c (x origin),
                   .e (y pixel size, negative), .f (y origin).

    Returns:
        pyvista.StructuredGrid with x, y, z points and an ``elevation`` scalar array.
    """
    rows, cols = elevation.shape

    col_idx = np.arange(cols, dtype=np.float64)
    row_idx = np.arange(rows, dtype=np.float64)
    col_grid, row_grid = np.meshgrid(col_idx, row_idx)

    # Affine pixel-to-world: x = c + a*col, y = f + e*row
    x = transform.c + transform.a * col_grid
    y = transform.f + transform.e * row_grid
    z = elevation.astype(np.float64)

    grid = pyvista.StructuredGrid(x, y, z)
    grid["elevation"] = z.ravel(order="F")
    return grid


def _screenshot_to_bytes(pl: "pyvista.Plotter") -> bytes:
    """Capture a screenshot from a Plotter and return PNG bytes.

    PyVista's ``screenshot(return_img=False)`` writes to a file and returns None.
    We use a temp file and read it back. If the call returns bytes directly
    (e.g., in a mocked test environment), we use those directly.

    Args:
        pl: A configured pyvista.Plotter instance (off_screen=True expected).

    Returns:
        PNG image as bytes, or b"" if capture failed.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = pl.screenshot(tmp_path, return_img=False)
        if result is None:
            # Production path: PyVista wrote to file, read it back
            if os.path.exists(tmp_path):
                with open(tmp_path, "rb") as f:
                    result = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if result is None:
        return b""
    return result if isinstance(result, bytes) else bytes(result)


def _add_polygon_overlay(
    pl: "pyvista.Plotter",
    geom,
    elevation: np.ndarray,
    transform,
    color: tuple[int, int, int] = (0, 100, 255),
) -> None:
    """Project a polygon exterior ring onto terrain surface and add to plotter.

    Args:
        pl: Active pyvista.Plotter.
        geom: Shapely geometry with an ``.exterior`` attribute.
        elevation: 2-D elevation array (used to compute z-offset above terrain).
        transform: Unused in overlay projection (kept for API consistency).
        color: RGB tuple (0-255) for the overlay line color.
    """
    try:
        exterior = geom.exterior
    except AttributeError:
        return  # Not a polygon-like geometry

    coords = list(exterior.coords)
    if not coords:
        return

    z_offset = float(elevation.max()) + 1.0  # render slightly above terrain surface
    pts = np.array([[c[0], c[1], z_offset] for c in coords])
    if len(pts) < 2:
        return

    n = len(pts)
    cells = np.hstack([[2, i, i + 1] for i in range(n - 1)])
    lines = pyvista.PolyData()
    lines.points = pts
    lines.lines = cells
    pl.add_mesh(lines, color=[c / 255.0 for c in color], line_width=2)


def _add_linestring_overlay(
    pl: "pyvista.Plotter",
    coords: list,
    elevation: np.ndarray,
    transform,
    color: tuple[int, int, int] = (0, 0, 200),
) -> None:
    """Project a LineString coordinate list onto terrain surface and add to plotter.

    Args:
        pl: Active pyvista.Plotter.
        coords: List of [x, y] or [x, y, z] coordinate pairs.
        elevation: 2-D elevation array (used to compute z-offset).
        transform: Unused in overlay projection (kept for API consistency).
        color: RGB tuple (0-255) for the line color.
    """
    if len(coords) < 2:
        return

    z_offset = float(elevation.max()) + 1.0
    pts = np.array([[c[0], c[1], z_offset] for c in coords])

    n = len(pts)
    cells = np.hstack([[2, i, i + 1] for i in range(n - 1)])
    lines = pyvista.PolyData()
    lines.points = pts
    lines.lines = cells
    pl.add_mesh(lines, color=[c / 255.0 for c in color], line_width=2)


# ---------------------------------------------------------------------------
# Public render functions
# ---------------------------------------------------------------------------


def render_cuencas_3d(
    elevation: np.ndarray,
    transform,
    cuencas_gdf: "gpd.GeoDataFrame",
) -> bytes:
    """Render a 3D terrain surface with basin polygon overlays.

    Args:
        elevation: 2-D numpy array of DEM elevation values.
        transform: Affine transform from rasterio (used to project polygon coords).
        cuencas_gdf: GeoDataFrame containing cuenca (basin) polygon geometries.
                     May be empty — terrain is rendered without overlays.

    Returns:
        PNG image as bytes.
    """
    grid = _dem_to_grid(elevation, transform)

    pl = pyvista.Plotter(off_screen=True)
    pl.add_mesh(grid, scalars="elevation", cmap="terrain")

    for geom in cuencas_gdf.geometry:
        if geom is None:
            continue
        _add_polygon_overlay(pl, geom, elevation, transform)

    png_bytes = _screenshot_to_bytes(pl)
    pl.close()
    return png_bytes


def render_escorrentia_3d(
    elevation: np.ndarray,
    transform,
    geojson_result: dict,
) -> bytes:
    """Render escorrentia (runoff) flow paths as 3D polylines over DEM terrain.

    Args:
        elevation: 2-D numpy array of DEM elevation values.
        transform: Affine transform from rasterio.
        geojson_result: GeoJSON FeatureCollection dict with LineString features.
                        May be empty — terrain is rendered without overlays.

    Returns:
        PNG image as bytes.
    """
    grid = _dem_to_grid(elevation, transform)

    pl = pyvista.Plotter(off_screen=True)
    pl.add_mesh(grid, scalars="elevation", cmap="Blues")

    for feature in geojson_result.get("features", []):
        geom = feature.get("geometry", {})
        if geom.get("type") != "LineString":
            continue
        _add_linestring_overlay(pl, geom.get("coordinates", []), elevation, transform)

    png_bytes = _screenshot_to_bytes(pl)
    pl.close()
    return png_bytes


def render_riesgo_3d(
    elevation: np.ndarray,
    transform,
    conflictos_gdf: "gpd.GeoDataFrame",
) -> bytes:
    """Render hydraulic risk zones as colored polygons over DEM terrain.

    Color encoding: bajo=green, medio=yellow, alto=orange, critico=red.

    Args:
        elevation: 2-D numpy array of DEM elevation values.
        transform: Affine transform from rasterio.
        conflictos_gdf: GeoDataFrame with a ``nivel_riesgo`` column.
                        May be empty — terrain is rendered without overlays.

    Returns:
        PNG image as bytes.
    """
    grid = _dem_to_grid(elevation, transform)

    pl = pyvista.Plotter(off_screen=True)
    pl.add_mesh(grid, scalars="elevation", cmap="terrain")

    has_nivel = "nivel_riesgo" in conflictos_gdf.columns
    for _, row in conflictos_gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        nivel = str(row["nivel_riesgo"]) if has_nivel else "bajo"
        color = _RISK_COLORS.get(nivel, _DEFAULT_RISK_COLOR)
        _add_polygon_overlay(pl, geom, elevation, transform, color=color)

    png_bytes = _screenshot_to_bytes(pl)
    pl.close()
    return png_bytes


def render_animacion_tormenta(
    elevation: np.ndarray,
    transform,
    cuencas_gdf: "gpd.GeoDataFrame",
    conflictos_gdf: "gpd.GeoDataFrame",
) -> bytes:
    """Produce an MP4 animation via animated camera flyover combining terrain,
    basins, and risk zones.

    VTK's movie writer requires a real filesystem path (not BytesIO), so we use
    a NamedTemporaryFile, write the MP4, read it back as bytes, then delete it.

    Args:
        elevation: 2-D numpy array of DEM elevation values.
        transform: Affine transform from rasterio.
        cuencas_gdf: GeoDataFrame with basin polygon geometries.
        conflictos_gdf: GeoDataFrame with risk zone geometries (may be empty).

    Returns:
        MP4 video as bytes.
    """
    grid = _dem_to_grid(elevation, transform)

    pl = pyvista.Plotter(off_screen=True)
    pl.add_mesh(grid, scalars="elevation", cmap="terrain")

    for geom in cuencas_gdf.geometry:
        if geom is None:
            continue
        _add_polygon_overlay(pl, geom, elevation, transform)

    has_nivel = "nivel_riesgo" in conflictos_gdf.columns
    for _, row in conflictos_gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        nivel = str(row["nivel_riesgo"]) if has_nivel else "bajo"
        color = _RISK_COLORS.get(nivel, _DEFAULT_RISK_COLOR)
        _add_polygon_overlay(pl, geom, elevation, transform, color=color)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    mp4_bytes: bytes = b""
    try:
        pl.open_movie(tmp_path)
        z_max = float(elevation.max())
        for azimuth in _ANIMATION_AZIMUTHS:
            pl.set_position([azimuth, 0, z_max * 3 + 100])
            pl.write_frame()
        pl.close()

        if os.path.exists(tmp_path):
            with open(tmp_path, "rb") as f:
                mp4_bytes = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return mp4_bytes
