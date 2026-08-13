"""
Composite raster analysis: flood risk, drainage need, and zonal statistics.

Higher-level functions that consume the terrain primitives from processing.py.
Each function takes file paths and returns file paths — no Celery, no DB.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from pyproj import CRS, Transformer
from rasterio.features import rasterize as rasterize_geometry
from rasterio.features import shapes as raster_shapes
from rasterio.mask import mask as rasterio_mask
import shapely
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union
from app.domains.geo.composites_support import (
    # Re-exported so ``composites.DEFAULT_*_WEIGHTS`` resolves for
    # tasks_composite_support (redundant alias = explicit re-export, ruff-clean).
    DEFAULT_DRAINAGE_WEIGHTS as DEFAULT_DRAINAGE_WEIGHTS,
    DEFAULT_FLOOD_WEIGHTS as DEFAULT_FLOOD_WEIGHTS,
    DEFAULT_WATERWAYS_DIR as _DEFAULT_WATERWAYS_DIR,
    compute_drainage_need_impl,
    compute_flood_risk_impl,
    merge_drainage_networks_impl,
    rasterize_drainage_impl,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Drainage network merge (real waterways + DEM-generated)
# ---------------------------------------------------------------------------


def merge_drainage_networks(
    auto_drainage_path: str,
    waterways_dir: str = _DEFAULT_WATERWAYS_DIR,
    output_path: str | None = None,
    reference_tif: str | None = None,
) -> str:
    """Merge DEM-generated drainage with real waterway GeoJSON files.

    Loads the auto-generated drainage network from the DEM pipeline and
    all ``*.geojson`` files from *waterways_dir*, tagging each feature
    with a ``source`` property ("auto" or "real") so downstream
    consumers can distinguish them.

    Real waterway files are assumed to be in EPSG:4326.  When a
    *reference_tif* is provided (or auto-detected next to the drainage
    file), waterway geometries are reprojected to match the raster CRS
    so that ``rasterize_drainage`` burns them onto the correct pixels.

    Args:
        auto_drainage_path: Path to the DEM-extracted drainage.geojson.
        waterways_dir: Directory containing real waterway GeoJSON files.
        output_path: Where to write the combined FeatureCollection.
            Defaults to ``drainage_combined.geojson`` next to *auto_drainage_path*.
        reference_tif: Optional reference raster to detect target CRS.
            Falls back to flow_acc.tif or hand.tif in the same directory.

    Returns:
        The output path on success.
    """
    return merge_drainage_networks_impl(
        auto_drainage_path,
        waterways_dir=waterways_dir,
        output_path=output_path,
        reference_tif=reference_tif,
    )


# ---------------------------------------------------------------------------
# WhiteboxTools singleton (reuse pattern from processing.py)
# ---------------------------------------------------------------------------

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
# Drainage vector → raster conversion
# ---------------------------------------------------------------------------


def rasterize_drainage(
    geojson_path: str,
    reference_tif: str,
    output_path: str,
) -> str:
    """Rasterize a drainage GeoJSON into a binary raster matching a reference grid.

    Burns vector features from the GeoJSON as 1 onto a 0-background raster,
    using the CRS, transform, and shape of *reference_tif*.

    Args:
        geojson_path: Path to drainage.geojson (FeatureCollection).
        reference_tif: Any existing GeoTIFF to use as spatial reference.
        output_path: Where to write the binary drainage raster.

    Returns:
        output_path on success.
    """
    return rasterize_drainage_impl(geojson_path, reference_tif, output_path)


# ---------------------------------------------------------------------------
# a) Percentile normalization
# ---------------------------------------------------------------------------


def normalize_percentile(
    data: np.ndarray,
    nodata_mask: np.ndarray,
    low: float = 2.0,
    high: float = 98.0,
) -> np.ndarray:
    """Normalize valid pixels to [0, 1] using percentile clipping.

    Pixels outside the [low, high] percentile range are clamped to 0 or 1.
    Nodata pixels are excluded from percentile computation and set to 0
    in the output (caller applies nodata mask separately).

    Args:
        data: Input raster band as 2D array.
        nodata_mask: Boolean mask where True = nodata pixel.
        low: Lower percentile for clipping (default 2.0).
        high: Upper percentile for clipping (default 98.0).

    Returns:
        Float32 array with values in [0, 1]. All-nodata returns zeros.
    """
    valid = data[~nodata_mask]

    if valid.size == 0:
        logger.warning("normalize_percentile: all pixels are nodata, returning zeros")
        return np.zeros(data.shape, dtype=np.float32)

    p_low = np.percentile(valid, low)
    p_high = np.percentile(valid, high)

    if p_high == p_low:
        # Single-value band — return uniform 0.5
        result = np.full(data.shape, 0.5, dtype=np.float32)
        result[nodata_mask] = 0.0
        return result

    normalized = (data.astype(np.float64) - p_low) / (p_high - p_low)
    result = np.clip(normalized, 0.0, 1.0).astype(np.float32)
    result[nodata_mask] = 0.0

    return result


# ---------------------------------------------------------------------------
# b) Flood risk composite
# ---------------------------------------------------------------------------


def compute_flood_risk(
    area_dir: str,
    output_path: str,
    weights: dict[str, float] | None = None,
) -> str:
    """Compute a flood risk composite raster from terrain analysis layers.

    Combines TWI, HAND (inverted), profile curvature (inverted — concavities
    trap water), and TPI (inverted — depressions accumulate water) into a
    single weighted index scaled to [0, 100].

    Slope was removed because on flat terrain (e.g. Pampas) it provides
    almost no discrimination.  Profile curvature and TPI capture micro-
    topography that drives real water accumulation.

    Higher values indicate higher flood risk.

    Args:
        area_dir: Directory containing the input layers
            (hand.tif, twi.tif, profile_curvature.tif, tpi.tif).
        output_path: Where to write the composite GeoTIFF.
        weights: Optional weight overrides.
            Keys: twi, hand, profile_curvature, tpi.  Must sum to 1.0.

    Returns:
        output_path on success.
    """
    return compute_flood_risk_impl(
        area_dir,
        output_path,
        normalize_percentile,
        weights=weights,
    )


# ---------------------------------------------------------------------------
# c) Drainage need composite
# ---------------------------------------------------------------------------


def compute_drainage_need(
    area_dir: str,
    output_path: str,
    weights: dict[str, float] | None = None,
) -> str:
    """Compute a drainage infrastructure need composite raster.

    Combines flow accumulation (log-scaled), HAND (inverted),
    distance-to-drainage, and TPI (inverted — depressions need drainage)
    into a single weighted index scaled to [0, 100].

    TWI is intentionally excluded because it is highly correlated with
    flow_acc on flat terrain (r=0.93), and flood_risk already uses TWI
    as its primary signal.

    Distance-to-drainage is computed from the binary drainage raster using
    WhiteboxTools euclidean_distance. Higher composite values indicate
    areas with greater need for drainage infrastructure.

    Args:
        area_dir: Directory containing the input layers
            (flow_acc.tif, hand.tif, drainage.tif, tpi.tif).
        output_path: Where to write the composite GeoTIFF.
        weights: Optional weight overrides. Keys: flow_acc, hand,
            dist_drainage, tpi. Must sum to 1.0.

    Returns:
        output_path on success.

    Raises:
        FileNotFoundError: If drainage.tif is missing from area_dir.
    """
    return compute_drainage_need_impl(
        area_dir,
        output_path,
        weights=weights,
        get_wbt_fn=_get_wbt,
        rasterize_drainage_fn=rasterize_drainage,
        normalize_percentile_fn=normalize_percentile,
    )


# ---------------------------------------------------------------------------
# d) Zonal statistics extraction
# ---------------------------------------------------------------------------

# Threshold above which a pixel is considered "high risk" (score > 70 of 100)
_HIGH_RISK_THRESHOLD = 70.0


def _as_shapely(geom: Any):
    """Coerce a GeoJSON mapping or shapely geometry into a shapely geometry."""
    if hasattr(geom, "__geo_interface__"):
        return geom
    if isinstance(geom, dict):
        return shape(geom)
    raise TypeError(f"unsupported geometry type: {type(geom)!r}")


def _pixel_area(src) -> tuple[float, float]:
    """Return ``(pixel_area_m2, pixel_area_ha)`` for an open raster.

    Projected rasters use the transform directly; geographic rasters are
    approximated at the raster's center latitude.
    """
    raster_crs = src.crs
    if raster_crs and raster_crs.is_projected:
        pixel_area_m2 = abs(src.transform.a * src.transform.e)
    else:
        bounds = src.bounds
        center_lat = (bounds.top + bounds.bottom) / 2
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * float(np.cos(np.radians(center_lat)))
        pixel_area_m2 = abs(src.transform.a) * m_per_deg_lon * abs(src.transform.e) * m_per_deg_lat
    return pixel_area_m2, pixel_area_m2 / 10_000.0


def extract_composite_zonal_stats(
    composite_path: str,
    zonas: list[dict[str, Any]],
    tipo: str,
    zona_crs: str | CRS = "EPSG:4326",
) -> list[dict[str, Any]]:
    """Extract per-zone statistics from a composite raster.

    For each zona geometry, masks the composite and computes summary
    statistics: mean, max, 90th percentile, and area (ha) where the
    composite score exceeds the high-risk threshold (70).

    Zone geometries are automatically reprojected to match the raster CRS
    when they differ (e.g. zones in EPSG:4326 vs raster in EPSG:32720).

    Args:
        composite_path: Path to a composite GeoTIFF (0-100 scale).
        zonas: List of zone dicts, each with ``id`` and ``geometry``
            (GeoJSON dict or shapely geometry).
        tipo: Composite type identifier (e.g. "flood_risk", "drainage_need").
        zona_crs: CRS of the input zone geometries (default EPSG:4326).

    Returns:
        List of result dicts ready for DB insertion. Zones that fall
        entirely in nodata are skipped (not included in output).
    """
    results: list[dict[str, Any]] = []

    with rasterio.open(composite_path) as src:
        raster_crs = src.crs
        nodata = src.nodata
        _, pixel_area_ha = _pixel_area(src)

        # Build a reprojection function if zone CRS differs from raster CRS
        _reproject_geom = None
        src_crs = CRS.from_user_input(zona_crs)
        dst_crs = CRS.from_user_input(raster_crs) if raster_crs else None
        if dst_crs and src_crs != dst_crs:
            transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
            _reproject_geom = lambda geom: shapely_transform(  # noqa: E731
                transformer.transform, geom
            )
            logger.info(
                "extract_composite_zonal_stats: reprojecting zones from %s to %s",
                src_crs,
                dst_crs,
            )

        for zona in zonas:
            zona_id = zona["id"]
            geom = zona["geometry"]

            # Accept both shapely and GeoJSON geometry → shapely object
            try:
                geom_shapely = _as_shapely(geom)
            except TypeError:
                logger.warning(
                    "extract_composite_zonal_stats: skipping zona %s — unsupported geometry type",
                    zona_id,
                )
                continue

            # Reproject zone geometry to raster CRS if needed
            if _reproject_geom is not None:
                geom_shapely = _reproject_geom(geom_shapely)

            geom_geojson = mapping(geom_shapely)

            try:
                out_image, _ = rasterio_mask(src, [geom_geojson], crop=True, all_touched=True)
            except Exception:
                logger.warning(
                    "extract_composite_zonal_stats: failed to mask zona %s, skipping",
                    zona_id,
                    exc_info=True,
                )
                continue

            data = out_image[0].astype(np.float64)

            # Build valid mask (exclude nodata)
            valid_mask = np.ones(data.shape, dtype=bool)
            if nodata is not None:
                valid_mask = data != nodata

            valid = data[valid_mask]

            if valid.size == 0:
                logger.info(
                    "extract_composite_zonal_stats: zona %s is all nodata, skipping",
                    zona_id,
                )
                continue

            mean_score = float(np.mean(valid))
            max_score = float(np.max(valid))
            p90_score = float(np.percentile(valid, 90))
            high_risk_pixels = int(np.sum(valid > _HIGH_RISK_THRESHOLD))
            area_high_risk_ha = float(high_risk_pixels * pixel_area_ha)

            results.append(
                {
                    "zona_id": zona_id,
                    "tipo": tipo,
                    "mean_score": round(mean_score, 2),
                    "max_score": round(max_score, 2),
                    "p90_score": round(p90_score, 2),
                    "area_high_risk_ha": round(area_high_risk_ha, 4),
                    "weights_used": None,  # caller sets from composite weights
                }
            )

    logger.info(
        "extract_composite_zonal_stats: %d/%d zonas produced stats for %s",
        len(results),
        len(zonas),
        tipo,
    )
    return results


# ---------------------------------------------------------------------------
# e) Zonal profile — class-binned stats for ONE geometry (ficha territorial)
# ---------------------------------------------------------------------------
# Default K for the relative low-confidence rule. Overridable per call; the
# API layer passes ``settings.ficha_low_confidence_pixel_ratio`` and datasets
# whose pixels are far coarser than a parcel (``precip_normal``) pass K = 0.
DEFAULT_LOW_CONFIDENCE_PIXEL_RATIO = 10.0

# Coverage ratio at or above which a geometry counts as fully covered. Pure
# tolerance: coverage is self-normalizing (valid weight over geometry weight,
# both read off the SAME fractional rasterization), so the 1 % slack only
# absorbs float noise — it hides neither edge inflation nor missing data.
_FULL_COVERAGE_RATIO = 0.99

# Edge pixels intersected against the geometry per vectorized chunk. Only pixels
# the geometry's BOUNDARY crosses need an exact intersection; their count grows
# with the perimeter, not the area (~3 300 pixels for the 60 000 ha envelope cap
# at 30 m), so one chunk normally covers a whole request.
_EDGE_CHUNK = 100_000

# Substrings identifying the rasterio "geometry does not intersect the raster"
# ValueError. Any OTHER ValueError (invalid geometry, driver failure) is a real
# error and must propagate instead of being reported as "no coverage".
_NO_OVERLAP_TOKENS = ("do not overlap", "outside bounds")


def _coverage_fractions(
    geom_shapely,
    transform: Affine,
    shape_hw: tuple[int, int],
) -> np.ndarray:
    """Fraction of each pixel of a window that the geometry covers, in ``[0, 1]``.

    Whole-pixel counting under ``all_touched=True`` overstates the covered area
    by 4 % (25 ha parcel) to 44 % (2.25 ha parcel) — the edge ring is counted at
    full pixel area. The weights here are EXACT areal fractions instead:

    * pixels the geometry's boundary does not cross are wholly in or wholly out,
      so one ``all_touched=False`` rasterization (center-in-polygon) settles them
      at 1.0 or 0.0 with no error at all;
    * pixels the boundary DOES cross get ``geometry ∩ pixel / pixel_area`` from a
      vectorized shapely intersection, in chunks of ``_EDGE_CHUNK``.

    Cost therefore scales with the geometry's perimeter, not its area. The
    earlier supersampled estimate (8x8 subcells per pixel) was dropped because it
    is quantized by construction and cannot meet the spec's 1 % area tolerance on
    small parcels: measured over the sides x offsets sweep in
    ``test_extract_zonal_profile``, its worst case is 10.2 % at 8 subcells and
    still 1.2 % at 64 subcells (4 096 subcells/pixel), where exact intersection
    is both cheaper and correct to float precision.

    An invalid geometry (self-intersection, bowtie) is repaired with
    ``buffer(0)`` first: shapely intersection is undefined on it, and rasterizing
    it while skipping its edge pixels would silently mix two accountings.
    """
    height, width = shape_hw
    fractions = np.zeros((height, width), dtype=np.float64)
    if height == 0 or width == 0:
        return fractions

    geom = geom_shapely if geom_shapely.is_valid else geom_shapely.buffer(0)
    if geom.is_empty:
        return fractions

    pixel_area = abs(transform.a * transform.e - transform.b * transform.d)
    if pixel_area <= 0:
        return fractions

    interior = rasterize_geometry(
        [(mapping(geom), 1)],
        out_shape=(height, width),
        transform=transform,
        all_touched=False,
        fill=0,
        dtype="uint8",
    )
    fractions[interior.astype(bool)] = 1.0

    boundary = geom.boundary
    if boundary.is_empty:
        return fractions

    edge = rasterize_geometry(
        [(mapping(boundary), 1)],
        out_shape=(height, width),
        transform=transform,
        all_touched=True,
        fill=0,
        dtype="uint8",
    )
    rows, cols = np.nonzero(edge)
    for start in range(0, rows.size, _EDGE_CHUNK):
        chunk_rows = rows[start : start + _EDGE_CHUNK]
        chunk_cols = cols[start : start + _EDGE_CHUNK]
        x0, y0 = transform * (chunk_cols.astype(np.float64), chunk_rows.astype(np.float64))
        x1, y1 = transform * (chunk_cols + 1.0, chunk_rows + 1.0)
        cells = shapely.box(
            np.minimum(x0, x1), np.minimum(y0, y1), np.maximum(x0, x1), np.maximum(y0, y1)
        )
        overlap = shapely.area(shapely.intersection(geom, cells))
        fractions[chunk_rows, chunk_cols] = np.clip(overlap / pixel_area, 0.0, 1.0)
    return fractions


def _aligned_window(
    transform: Affine,
    bounds: tuple[float, float, float, float],
) -> tuple[int, int, int, int]:
    """Whole-pixel window of ``transform``'s grid that contains ``bounds``.

    Returned as ``(row_off, col_off, height, width)``. Offsets may be NEGATIVE
    and the window may run past the raster: it describes the grid, not the
    raster's extent, which is exactly what the geometry-side accounting needs.
    """
    minx, miny, maxx, maxy = bounds
    inverse = ~transform
    xs = np.array([minx, minx, maxx, maxx], dtype=np.float64)
    ys = np.array([miny, maxy, miny, maxy], dtype=np.float64)
    cols, rows = inverse * (xs, ys)
    col_off = int(np.floor(cols.min()))
    row_off = int(np.floor(rows.min()))
    width = max(1, int(np.ceil(cols.max())) - col_off)
    height = max(1, int(np.ceil(rows.max())) - row_off)
    return row_off, col_off, height, width


def _bin_pixels(
    valid: np.ndarray,
    weights: np.ndarray,
    breaks: list[dict],
    pixel_area_ha: float,
) -> list[dict[str, Any]]:
    """Bin valid pixel values into the given class breaks.

    Bins are half-open ``[min, max)``; the LAST bin is closed ``[min, max]`` so
    the raster maximum is never dropped. Values outside every break are counted
    in ``valid_pixels`` (and in mean/max/p90) but belong to no bin, so bin
    percentages can sum to less than 100 for a raster that exceeds its legend.

    ``ha`` and ``pct`` are FRACTIONAL-WEIGHT quantities: a pixel the geometry
    only half covers contributes 0.5 pixel of area. ``pixels`` stays a raw
    integer diagnostic (how many pixels were sampled), so ``pixels`` and ``ha``
    are deliberately not proportional at the geometry edge.
    """
    total_weight = float(np.sum(weights)) if weights.size else 0.0
    result: list[dict[str, Any]] = []
    last_index = len(breaks) - 1
    for index, cfg in enumerate(breaks):
        bin_min = float(cfg["min"])
        bin_max = float(cfg["max"])
        if index == last_index:
            member = (valid >= bin_min) & (valid <= bin_max)
        else:
            member = (valid >= bin_min) & (valid < bin_max)
        pixels = int(np.count_nonzero(member))
        weight = float(np.sum(weights[member])) if pixels else 0.0
        result.append(
            {
                "label": cfg.get("label"),
                "min": bin_min,
                "max": bin_max,
                "color": cfg.get("color"),
                "pixels": pixels,
                "pct": round(weight / total_weight * 100.0, 2) if total_weight > 0 else 0.0,
                "ha": round(weight * pixel_area_ha, 4),
            }
        )
    return result


def extract_zonal_profile(
    raster_path: str,
    geom: Any,
    geom_crs: str | CRS = "EPSG:4326",
    breaks: list[dict] | None = None,
    geom_area_m2: float | None = None,
    low_confidence_pixel_ratio: float = DEFAULT_LOW_CONFIDENCE_PIXEL_RATIO,
) -> dict[str, Any]:
    """Class-binned zonal statistics for ONE geometry over ONE raster.

    Unlike :func:`extract_composite_zonal_stats` — which is the DEM pipeline's
    batch helper and SKIPS zones it cannot resolve — this primitive ALWAYS
    returns a dict, so the caller can report "no coverage" instead of silently
    dropping a dataset from the response.

    Areas are FRACTIONAL, not whole-pixel. The geometry is rasterized ONCE into
    per-pixel coverage weights in ``[0, 1]`` (see :func:`_coverage_fractions`)
    over a window aligned to the raster's grid but covering the whole geometry —
    including any part that hangs off the raster — and area is weight x pixel
    area::

        total_weight    = sum of ALL weights (the whole geometry)
        valid_weight    = sum of weights over pixels that are inside the raster
                          AND not nodata/NaN
        covered_area_ha = valid_weight * pixel_area_ha
        coverage_ratio  = min(1.0, valid_weight / total_weight)
        coverage        = "none"    if valid_pixels == 0
                          "full"    if coverage_ratio >= 0.99
                          "partial" otherwise

    Both sides of the ratio are read off the SAME rasterization, so a geometry
    that is fully inside the raster with no nodata yields ``1.0`` by
    construction, while the weights of pixels beyond the raster's extent inflate
    only the denominator and surface as ``partial``. Coverage therefore needs no
    caller-supplied area and cannot be faked by ``rasterio_mask(crop=True)``
    clipping the window to the raster extent; ``geom_area_m2`` is still accepted
    but only feeds ``low_confidence``.

    ``valid_pixels`` and ``bins[].pixels`` remain RAW pixel counts (sampling
    diagnostics); ``covered_area_ha``, ``bins[].ha`` and ``bins[].pct`` are
    weighted. ``mean``/``max``/``p90`` are computed over valid pixel VALUES
    unweighted: they are distribution summaries of what was sampled, and the
    edge pixels a weighting would down-rank are exactly the ones whose value is
    still the best estimate available for the sliver of parcel inside them.

    Confidence is relative and per raster: ``low_confidence`` is
    ``(geom_area_m2 / pixel_area_m2) < K``. A global "fewer than N pixels" rule
    would flag every parcel against a ~5 km CHIRPS pixel, where a normals mean
    over one pixel is a legitimate value. ``K = 0`` never flags.

    Bin-edge convention: half-open ``[min, max)`` for every bin except the last,
    which is closed ``[min, max]`` so the raster maximum is never dropped.

    Args:
        raster_path: Path to the raster to sample.
        geom: GeoJSON mapping or shapely geometry of the zone.
        geom_crs: CRS of ``geom`` (default EPSG:4326). Reprojected to the
            raster CRS when they differ.
        breaks: Class breaks (``label``/``min``/``max``/``color``), typically
            ``class_breaks.RANGE_CONFIGS[tipo]``. ``None`` yields empty bins.
        geom_area_m2: Geometry area in a projected CRS (the caller already has
            it from ``ST_Area`` in EPSG:32720). Only used for
            ``low_confidence``; when omitted it is derived from the reprojected
            geometry if the raster CRS is projected, else confidence is not
            flagged. Coverage never depends on it.
        low_confidence_pixel_ratio: ``K`` for the relative confidence rule.

    Returns:
        ``{mean, max, p90, valid_pixels, pixel_area_ha, covered_area_ha,
        coverage_ratio, coverage, low_confidence, bins}``. ``mean``/``max``/
        ``p90`` are ``None`` when there is no valid pixel.

    Raises:
        ValueError: If the raster declares no CRS — the geometry cannot be
            placed on the grid, and reporting that as "no coverage" would be a
            silent wrong answer.
        Any exception other than the non-overlap ``ValueError`` from
        ``rasterio.mask`` propagates — an unreadable raster is a failure, not a
        zone without coverage.
    """
    break_list = breaks or []
    geom_shapely = _as_shapely(geom)

    with rasterio.open(raster_path) as src:
        if not src.crs:
            raise ValueError(
                f"raster has no CRS, cannot place the geometry on its grid: {raster_path}"
            )

        nodata = src.nodata
        pixel_area_m2, pixel_area_ha = _pixel_area(src)

        src_crs = CRS.from_user_input(geom_crs)
        dst_crs = CRS.from_user_input(src.crs)
        if src_crs != dst_crs:
            transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
            geom_shapely = shapely_transform(transformer.transform, geom_shapely)

        area_m2 = geom_area_m2
        if area_m2 is None and dst_crs.is_projected:
            area_m2 = float(geom_shapely.area)

        if area_m2 is not None and area_m2 > 0 and pixel_area_m2 > 0:
            low_confidence = (area_m2 / pixel_area_m2) < low_confidence_pixel_ratio
        else:
            low_confidence = False

        def _profile(valid: np.ndarray, weights: np.ndarray, total_weight: float) -> dict[str, Any]:
            valid_pixels = int(valid.size)
            valid_weight = float(np.sum(weights)) if valid_pixels else 0.0
            covered_area_ha = valid_weight * pixel_area_ha
            if valid_pixels == 0:
                coverage_ratio = 0.0
                coverage = "none"
            elif total_weight > 0:
                coverage_ratio = min(1.0, valid_weight / total_weight)
                coverage = "full" if coverage_ratio >= _FULL_COVERAGE_RATIO else "partial"
            else:
                # R3-009: the geometry itself carries no area (empty, degenerate
                # or a bowtie that repairs to nothing). There is no denominator,
                # so there is nothing to report as covered — and "full" with zero
                # hectares would be a confident wrong answer.
                logger.warning(
                    "extract_zonal_profile: geometry has zero rasterized area on %s "
                    "(degenerate or sub-precision) — reporting no coverage",
                    raster_path,
                )
                coverage_ratio = 0.0
                coverage = "none"
                covered_area_ha = 0.0
            return {
                "mean": round(float(np.mean(valid)), 2) if valid_pixels else None,
                "max": round(float(np.max(valid)), 2) if valid_pixels else None,
                "p90": round(float(np.percentile(valid, 90)), 2) if valid_pixels else None,
                "valid_pixels": valid_pixels,
                "pixel_area_ha": pixel_area_ha,
                "covered_area_ha": round(covered_area_ha, 4),
                "coverage_ratio": round(coverage_ratio, 4),
                "coverage": coverage,
                "low_confidence": low_confidence,
                "bins": (
                    _bin_pixels(valid, weights, break_list, pixel_area_ha) if valid_pixels else []
                ),
            }

        empty = np.empty(0, dtype=np.float64)
        try:
            # filled=False keeps the ORIGINAL pixel values and returns the
            # geometry mask separately: with filled=True a raster without a
            # nodata tag has its outside-geometry pixels stuffed with 0, which
            # then reads as a legitimate value and poisons mean and bins.
            out_image, out_transform = rasterio_mask(
                src,
                [mapping(geom_shapely)],
                crop=True,
                all_touched=True,
                filled=False,
            )
        except ValueError as exc:
            message = str(exc).lower()
            if not any(token in message for token in _NO_OVERLAP_TOKENS):
                raise
            logger.info(
                "extract_zonal_profile: geometry does not overlap %s — no coverage",
                raster_path,
            )
            return _profile(empty, empty, 0.0)

        band = out_image[0]
        data = np.asarray(np.ma.getdata(band), dtype=np.float64)
        outside_geometry = np.ma.getmaskarray(band)

        # Absence is read from the nodata tag ALONE — never from the value. An
        # exact ``0.0`` is a measurement for every dataset this primitive serves
        # (a ``flood_risk`` class, a real millimetre reading), and the CHIRPS
        # rasters that once carried the GEE clip's untagged zeros were
        # regenerated with ``unmask(-9999)`` + ``src_nodata``.
        valid_mask = ~outside_geometry & ~np.isnan(data)
        if nodata is not None:
            valid_mask &= data != nodata

        # ONE rasterization for both sides of the coverage ratio. The window is
        # the raster's own grid extended to whole pixels around the geometry, so
        # it may reach past the raster; the crop window rasterio returned is a
        # sub-rectangle of it (both are derived from the geometry's bounds, and
        # `all_touched=True` never reaches beyond them).
        ext_row_off, ext_col_off, ext_height, ext_width = _aligned_window(
            src.transform, geom_shapely.bounds
        )
        ext_transform = src.transform * Affine.translation(ext_col_off, ext_row_off)
        ext_fractions = _coverage_fractions(geom_shapely, ext_transform, (ext_height, ext_width))
        total_weight = float(ext_fractions.sum())

        # Weights of the crop window, sliced out of the extended grid so the two
        # accountings cannot drift. Pixels of the crop window that fall outside
        # the extended window (they should not, but float offsets are float
        # offsets) keep weight 0 rather than an invented one.
        crop_col, crop_row = ~src.transform * (out_transform.c, out_transform.f)
        row_delta = int(round(crop_row)) - ext_row_off
        col_delta = int(round(crop_col)) - ext_col_off
        fractions = np.zeros(data.shape, dtype=np.float64)
        row_start = max(0, row_delta)
        row_stop = min(ext_height, row_delta + data.shape[0])
        col_start = max(0, col_delta)
        col_stop = min(ext_width, col_delta + data.shape[1])
        if row_stop > row_start and col_stop > col_start:
            fractions[
                row_start - row_delta : row_stop - row_delta,
                col_start - col_delta : col_stop - col_delta,
            ] = ext_fractions[row_start:row_stop, col_start:col_stop]

        return _profile(data[valid_mask], fractions[valid_mask], total_weight)


# EPSG:32720 (UTM 20S) is the metric working CRS the whole ficha measures in.
# Simplify tolerances are METERS, so the class polygons are moved into this CRS
# before ``.simplify`` regardless of the raster's own CRS (the production
# flood/drainage COGs are already 32720, so that hop is a no-op there).
_WORK_CRS = CRS.from_epsg(32720)
_WGS84_CRS = CRS.from_epsg(4326)


def vectorize_zonal_classes(
    raster_path: str,
    geom: Any,
    breaks: list[dict],
    geom_crs: str | CRS = "EPSG:4326",
    simplify_tolerance_m: float = 8.0,
) -> list[dict[str, Any]]:
    """Vectorize ONE raster into per-class DISSOLVED GeoJSON polygons over ONE geometry.

    The on-map overlay counterpart of :func:`extract_zonal_profile`: instead of
    binning pixel VALUES into ``{clase, ha, pct}`` rows, it turns the same
    classified pixels into polygons the map can paint, clipped to ``geom``.

    Pipeline (the order matters — see the module notes on stair-step artefacts):

    1. mask the raster to ``geom`` (``crop=True, all_touched=True, filled=False``),
       exactly like ``extract_zonal_profile`` — same nodata / NaN / outside-geometry
       handling, so the class polygons cover precisely the pixels the panel counts;
    2. CLASSIFY the 2D array into class indices using the SAME half-open ``[min, max)``
       bins as ``_bin_pixels`` (closed on the last), so an overlay class is byte-for-byte
       the panel's ``RiesgoBins`` class;
    3. ``rasterio.features.shapes`` emits one geometry per connected same-class run in
       the RASTER CRS — NOT one per pixel;
    4. DISSOLVE per class (``unary_union``) so adjacent same-class pixels merge into a
       few polygons (the payload-bounding step);
    5. SIMPLIFY at ``simplify_tolerance_m`` metres in EPSG:32720 (topology preserving),
       BEFORE reprojecting, then ``buffer(0)`` to heal the self-intersections a
       raster stair-step + simplify can produce;
    6. reproject 32720 → 4326 through a reused ``Transformer`` and ``buffer(0)`` again,
       so only valid Polygon/MultiPolygon geometries in EPSG:4326 reach the client.

    Returns a list of ``{"clase": <label>, "geometry": <GeoJSON mapping, EPSG:4326>}``,
    one entry per class present in the zone. An empty list means the geometry does not
    overlap the raster, or every covered pixel is nodata, or nothing falls in a bin —
    never a fabricated feature.

    Raises:
        ValueError: if the raster declares no CRS (same contract as
            ``extract_zonal_profile`` — the caller maps read failures to
            ``raster_ilegible``). The non-overlap ``ValueError`` from
            ``rasterio.mask`` is caught here and reported as an empty list.
    """
    if not breaks:
        return []
    geom_shapely = _as_shapely(geom)

    with rasterio.open(raster_path) as src:
        if not src.crs:
            raise ValueError(
                f"raster has no CRS, cannot place the geometry on its grid: {raster_path}"
            )

        nodata = src.nodata
        src_crs = CRS.from_user_input(src.crs)
        geom_crs_resolved = CRS.from_user_input(geom_crs)
        if geom_crs_resolved != src_crs:
            to_raster = Transformer.from_crs(geom_crs_resolved, src_crs, always_xy=True)
            geom_shapely = shapely_transform(to_raster.transform, geom_shapely)

        try:
            out_image, out_transform = rasterio_mask(
                src,
                [mapping(geom_shapely)],
                crop=True,
                all_touched=True,
                filled=False,
            )
        except ValueError as exc:
            message = str(exc).lower()
            if not any(token in message for token in _NO_OVERLAP_TOKENS):
                raise
            logger.info(
                "vectorize_zonal_classes: geometry does not overlap %s — no features",
                raster_path,
            )
            return []

        band = out_image[0]
        data = np.asarray(np.ma.getdata(band), dtype=np.float64)
        outside_geometry = np.ma.getmaskarray(band)

        valid_mask = ~outside_geometry & ~np.isnan(data)
        if nodata is not None:
            valid_mask &= data != nodata

        # Same binning as ``_bin_pixels``: half-open ``[min, max)`` for every bin
        # except the last, which is closed. ``-1`` marks "valid pixel, no bin".
        classified = np.full(data.shape, -1, dtype=np.int32)
        last_index = len(breaks) - 1
        for index, cfg in enumerate(breaks):
            bin_min = float(cfg["min"])
            bin_max = float(cfg["max"])
            if index == last_index:
                member = (data >= bin_min) & (data <= bin_max)
            else:
                member = (data >= bin_min) & (data < bin_max)
            classified[member & valid_mask] = index

        shape_mask = valid_mask & (classified >= 0)
        if not shape_mask.any():
            return []

        # Reuse ONE transformer per call (composites.py:678 pattern). When the
        # raster is already 32720 (production), ``to_work`` is an identity hop.
        to_work = (
            None
            if src_crs == _WORK_CRS
            else Transformer.from_crs(src_crs, _WORK_CRS, always_xy=True).transform
        )
        work_to_wgs = Transformer.from_crs(_WORK_CRS, _WGS84_CRS, always_xy=True).transform

        grupos: dict[int, list[Any]] = {}
        for geom_dict, value in raster_shapes(classified, mask=shape_mask, transform=out_transform):
            grupos.setdefault(int(value), []).append(shape(geom_dict))

        features: list[dict[str, Any]] = []
        for clase_idx in sorted(grupos):
            fusionado = unary_union(grupos[clase_idx])  # dissolve same-class pixels
            if to_work is not None:
                fusionado = shapely_transform(to_work, fusionado)
            fusionado = fusionado.simplify(simplify_tolerance_m, preserve_topology=True)
            fusionado = fusionado.buffer(0)  # heal stair-step self-intersections
            fusionado = shapely_transform(work_to_wgs, fusionado)
            fusionado = fusionado.buffer(0)  # heal again after reproject
            if fusionado.is_empty:
                continue
            features.append(
                {"clase": breaks[clase_idx].get("label"), "geometry": mapping(fusionado)}
            )
        return features
