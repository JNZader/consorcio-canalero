"""Ledger regression tests for the ficha zonal primitive (A2.7).

Synthetic 10x10 float32 GeoTIFFs written to ``tmp_path``. No database, no
``app.main`` import: the primitive is a leaf helper and must be testable
without the API process.

Covered ledger items:
    JDB-004  only the non-overlap ``ValueError`` is swallowed; any other
             exception propagates instead of silently dropping a dataset.
    JDB-005  partial coverage is detectable even when the crop window is
             entirely valid (coverage is geometry-relative, not window-relative).
    JDB-017  ``low_confidence`` is the relative pixel-ratio rule, and ``K = 0``
             never flags.
    JDB-026  bins are half-open ``[min, max)`` with the last bin closed.

Post-4R additions:
    R3-001   areas are fractional, not whole-pixel: an unaligned parcel's binned
             hectares match its true area instead of inflating by 4-44 %.
    R3-002   the inflation no longer masks missing data: an interior nodata hole
             surfaces as ``partial`` instead of being absorbed by the clamp.
    R3-008   the 1 % area tolerance holds across a sweep of parcel sizes and grid
             alignments, and on a thin strip that is all edge.
    R3-009   a geometry with no rasterized area is ``none``, never ``full`` with
             zero hectares.
    R1-001   only the rasterio non-overlap ``ValueError`` means "no coverage".
    R4-001   a raster WITHOUT a nodata tag must not gain phantom zeros.
    R4-002   a raster without a CRS is a failure, not a zone without coverage.
    R2-002   coverage is detected on a geographic raster with no ``geom_area_m2``.
    R3-005   the default ``geom_crs`` (EPSG:4326) reprojects onto a UTM raster.
    R3-006   ``class_breaks`` is a leaf module, verified by a real import.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box, mapping
from shapely.ops import transform as shapely_transform

from app.domains.geo import class_breaks, composites
from app.domains.geo.composites import extract_zonal_profile

CRS_32720 = "EPSG:32720"
CRS_4326 = "EPSG:4326"
PIXEL_M = 30.0
ORIGIN_X = 500_000.0
ORIGIN_Y = 6_500_000.0
SIZE = 10
NODATA = -9999.0

# Raster extent in EPSG:32720: 300 m x 300 m = 9 ha, 100 pixels of 0.09 ha.
RASTER_BOX = box(
    ORIGIN_X,
    ORIGIN_Y - SIZE * PIXEL_M,
    ORIGIN_X + SIZE * PIXEL_M,
    ORIGIN_Y,
)
RASTER_AREA_M2 = (SIZE * PIXEL_M) ** 2

FLOOD_BREAKS = class_breaks.RANGE_CONFIGS["flood_risk"]


def _write_raster(
    tmp_path,
    values: np.ndarray,
    name: str = "raster.tif",
    *,
    crs: str | None = CRS_32720,
    nodata: float | None = NODATA,
    origin: tuple[float, float] = (ORIGIN_X, ORIGIN_Y),
    pixel: float = PIXEL_M,
) -> str:
    path = tmp_path / name
    transform = from_origin(origin[0], origin[1], pixel, pixel)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(values.astype("float32"), 1)
    return str(path)


def _filled(value: float) -> np.ndarray:
    return np.full((SIZE, SIZE), value, dtype="float32")


def _bins_by_label(profile: dict) -> dict[str, dict]:
    return {b["label"]: b for b in profile["bins"]}


# ---------------------------------------------------------------------------
# class_breaks extraction (A2.1)
# ---------------------------------------------------------------------------


def test_tile_service_support_reexports_the_same_range_configs():
    from app.domains.geo import tile_service_support

    assert tile_service_support.RANGE_CONFIGS is class_breaks.RANGE_CONFIGS
    assert "flood_risk" in class_breaks.RANGE_CONFIGS
    assert "drainage_need" in class_breaks.RANGE_CONFIGS


def test_class_breaks_is_a_leaf_module():
    """R3-006: importing it must not drag tile-rendering code into the process.

    Asserted by actually importing it in a fresh interpreter and inspecting
    ``sys.modules``: a source-text scan of the top-level import lines only sees
    what ``class_breaks.py`` itself spells out, and would miss anything pulled
    in transitively through a package ``__init__``.
    """
    import app

    root = Path(app.__file__).resolve().parent.parent
    code = (
        "import sys\n"
        "import app.domains.geo.class_breaks  # noqa: F401\n"
        "print(','.join(sorted(m for m in sys.modules if 'tile_service' in m)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(root),
        env={**os.environ, "PYTHONPATH": str(root)},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"class_breaks pulled in tile rendering: {result.stdout}"


# ---------------------------------------------------------------------------
# (a) full coverage, exact percentages
# ---------------------------------------------------------------------------


def test_full_coverage_returns_exact_percentages(tmp_path):
    values = _filled(10.0)
    values[5:, :] = 60.0  # half "Bajo" (0-30), half "Alto" (55-75)
    raster = _write_raster(tmp_path, values)

    profile = extract_zonal_profile(
        raster,
        mapping(RASTER_BOX),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=RASTER_AREA_M2,
    )

    assert profile["valid_pixels"] == 100
    assert profile["coverage"] == "full"
    assert profile["coverage_ratio"] == 1.0
    assert profile["covered_area_ha"] == pytest.approx(9.0)
    assert profile["mean"] == pytest.approx(35.0)
    assert profile["max"] == pytest.approx(60.0)

    bins = _bins_by_label(profile)
    assert bins["Bajo"]["pixels"] == 50
    assert bins["Bajo"]["pct"] == pytest.approx(50.0)
    assert bins["Bajo"]["ha"] == pytest.approx(4.5)
    assert bins["Alto"]["pixels"] == 50
    assert bins["Alto"]["pct"] == pytest.approx(50.0)
    assert sum(b["pct"] for b in profile["bins"]) == pytest.approx(100.0, abs=0.5)


# ---------------------------------------------------------------------------
# (b) JDB-005 — partial coverage with a fully valid crop window
# ---------------------------------------------------------------------------


def test_partial_coverage_detected_when_crop_window_is_fully_valid(tmp_path):
    raster = _write_raster(tmp_path, _filled(40.0))

    # Twice the raster extent: the eastern half lies outside the raster, but the
    # crop window rasterio returns is clipped to the raster, so every pixel in
    # it is valid. Window-relative coverage would report "full".
    geom = box(
        ORIGIN_X,
        ORIGIN_Y - SIZE * PIXEL_M,
        ORIGIN_X + 2 * SIZE * PIXEL_M,
        ORIGIN_Y,
    )

    profile = extract_zonal_profile(
        raster,
        mapping(geom),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=geom.area,
    )

    assert profile["valid_pixels"] == 100  # crop window entirely valid
    assert profile["coverage"] == "partial"
    assert profile["coverage_ratio"] == pytest.approx(0.5, abs=0.01)
    assert profile["covered_area_ha"] == pytest.approx(9.0)


# ---------------------------------------------------------------------------
# (c) disjoint geometry — ValueError swallowed into coverage="none"
# ---------------------------------------------------------------------------


def test_disjoint_geometry_returns_no_coverage(tmp_path):
    raster = _write_raster(tmp_path, _filled(40.0))
    far_away = box(ORIGIN_X + 10_000, ORIGIN_Y + 10_000, ORIGIN_X + 10_300, ORIGIN_Y + 10_300)

    profile = extract_zonal_profile(
        raster,
        mapping(far_away),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=far_away.area,
    )

    assert profile["coverage"] == "none"
    assert profile["valid_pixels"] == 0
    assert profile["bins"] == []
    assert profile["mean"] is None
    assert profile["max"] is None
    assert profile["p90"] is None
    assert profile["covered_area_ha"] == 0.0


# ---------------------------------------------------------------------------
# (d) overlapping window, every pixel nodata
# ---------------------------------------------------------------------------


def test_all_nodata_window_returns_no_coverage(tmp_path):
    raster = _write_raster(tmp_path, _filled(NODATA))

    profile = extract_zonal_profile(
        raster,
        mapping(RASTER_BOX),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=RASTER_AREA_M2,
    )

    assert profile["coverage"] == "none"
    assert profile["valid_pixels"] == 0
    assert profile["bins"] == []


# ---------------------------------------------------------------------------
# (e) JDB-004 — a non-ValueError failure propagates
# ---------------------------------------------------------------------------


def test_non_value_error_failure_propagates(tmp_path, monkeypatch):
    raster = _write_raster(tmp_path, _filled(40.0))

    def _boom(*args, **kwargs):
        raise RuntimeError("raster driver exploded")

    monkeypatch.setattr(composites, "rasterio_mask", _boom)

    with pytest.raises(RuntimeError, match="raster driver exploded"):
        extract_zonal_profile(
            raster,
            mapping(RASTER_BOX),
            geom_crs=CRS_32720,
            breaks=FLOOD_BREAKS,
            geom_area_m2=RASTER_AREA_M2,
        )


# ---------------------------------------------------------------------------
# (f) JDB-026 — bin-edge convention
# ---------------------------------------------------------------------------


def test_value_on_a_bin_edge_belongs_to_the_upper_bin(tmp_path):
    # "Bajo" is [0, 30), "Medio" is [30, 55): 30.0 must land in "Medio" only.
    raster = _write_raster(tmp_path, _filled(30.0))

    profile = extract_zonal_profile(
        raster,
        mapping(RASTER_BOX),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=RASTER_AREA_M2,
    )

    bins = _bins_by_label(profile)
    assert bins["Bajo"]["pixels"] == 0
    assert bins["Medio"]["pixels"] == 100
    assert sum(b["pixels"] for b in profile["bins"]) == profile["valid_pixels"]


def test_last_bin_is_closed_so_the_maximum_is_never_dropped(tmp_path):
    # "Crítico" is [75, 100]: the raster maximum 100.0 must be counted.
    raster = _write_raster(tmp_path, _filled(100.0))

    profile = extract_zonal_profile(
        raster,
        mapping(RASTER_BOX),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=RASTER_AREA_M2,
    )

    bins = _bins_by_label(profile)
    assert bins["Crítico"]["pixels"] == 100
    assert bins["Crítico"]["pct"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# (g) JDB-017 — relative low-confidence rule
# ---------------------------------------------------------------------------


def _small_geom():
    """A 4 500 m2 box inside the raster: 5 pixels of 900 m2, below K = 10."""
    return box(ORIGIN_X, ORIGIN_Y - 50.0, ORIGIN_X + 90.0, ORIGIN_Y)


def test_low_confidence_true_below_the_pixel_ratio(tmp_path):
    raster = _write_raster(tmp_path, _filled(40.0))
    geom = _small_geom()

    profile = extract_zonal_profile(
        raster,
        mapping(geom),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=geom.area,
        low_confidence_pixel_ratio=10.0,
    )

    assert geom.area / (PIXEL_M**2) < 10.0
    assert profile["low_confidence"] is True


def test_low_confidence_false_above_the_pixel_ratio(tmp_path):
    raster = _write_raster(tmp_path, _filled(40.0))

    profile = extract_zonal_profile(
        raster,
        mapping(RASTER_BOX),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=RASTER_AREA_M2,
        low_confidence_pixel_ratio=10.0,
    )

    assert RASTER_AREA_M2 / (PIXEL_M**2) == 100.0
    assert profile["low_confidence"] is False


def test_pixel_ratio_zero_never_flags_low_confidence(tmp_path):
    """``precip_normal`` passes K = 0: sub-pixel sampling of normals is exact."""
    raster = _write_raster(tmp_path, _filled(40.0))
    geom = _small_geom()

    profile = extract_zonal_profile(
        raster,
        mapping(geom),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=geom.area,
        low_confidence_pixel_ratio=0.0,
    )

    assert profile["low_confidence"] is False


# ---------------------------------------------------------------------------
# (h) R3-001 — fractional pixel coverage: hectares match the true parcel area
# ---------------------------------------------------------------------------

BIG = 30  # 30 x 30 pixels of 30 m = 900 m x 900 m


def _big_values(value: float = 40.0) -> np.ndarray:
    return np.full((BIG, BIG), value, dtype="float32")


def _offset_box(side_m: float, offset_m: float = 15.0):
    """A ``side_m`` box shifted off the pixel grid by ``offset_m`` on both axes."""
    minx = ORIGIN_X + offset_m
    maxy = ORIGIN_Y - offset_m
    return box(minx, maxy - side_m, minx + side_m, maxy)


def test_unaligned_parcel_bin_hectares_match_its_true_area(tmp_path):
    """Whole-pixel counting reported 29.16 ha for this 25.00 ha parcel (+16.6 %)."""
    raster = _write_raster(tmp_path, _big_values(), name="big.tif")
    geom = _offset_box(500.0)

    profile = extract_zonal_profile(
        raster,
        mapping(geom),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=geom.area,
    )

    assert profile["coverage"] == "full"
    assert profile["covered_area_ha"] == pytest.approx(25.0, rel=0.01)
    assert sum(b["ha"] for b in profile["bins"]) == pytest.approx(25.0, rel=0.01)
    # Raw pixel counts stay raw: the edge ring is still sampled, it just no
    # longer contributes a whole pixel of area.
    assert profile["valid_pixels"] == 18 * 18


def test_small_unaligned_parcel_bin_hectares_match_its_true_area(tmp_path):
    """Whole-pixel counting reported 3.24 ha for this 2.25 ha parcel (+44 %)."""
    raster = _write_raster(tmp_path, _big_values(), name="big.tif")
    geom = _offset_box(150.0)

    profile = extract_zonal_profile(
        raster,
        mapping(geom),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=geom.area,
    )

    assert profile["coverage"] == "full"
    assert profile["covered_area_ha"] == pytest.approx(2.25, rel=0.01)
    assert sum(b["ha"] for b in profile["bins"]) == pytest.approx(2.25, rel=0.01)


# ---------------------------------------------------------------------------
# (h2) R3-008 — accuracy sweep over parcel size x grid alignment
# ---------------------------------------------------------------------------
# Two hand-picked boxes cannot tell an accurate estimator from a lucky one: the
# supersampled estimator this code used to carry scored 0.0 % on the 500 m box
# and 10.2 % on a 50 m box shifted 5 m off the grid. The sweep pins the SPEC's
# 1 % tolerance across sizes and alignments instead of at two points.
#
# Sides straddle the 30 m pixel both ways (50 m is under two pixels, 500 m is
# ~17); offsets sample the pixel at 0, 1/6, 5/12, 7/12 and 3/4 of its side, so no
# case is accidentally grid-aligned.


@pytest.mark.parametrize("side_m", [50.0, 100.0, 160.0, 200.0, 500.0])
@pytest.mark.parametrize("offset_m", [0.0, 5.0, 12.5, 17.5, 22.5])
def test_binned_hectares_match_true_area_for_any_size_and_alignment(tmp_path, side_m, offset_m):
    raster = _write_raster(tmp_path, _big_values(), name="big.tif")
    geom = _offset_box(side_m, offset_m)
    true_ha = geom.area / 10_000.0

    profile = extract_zonal_profile(
        raster,
        mapping(geom),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=geom.area,
    )

    # Fully interior, no nodata: coverage is complete by construction, because
    # numerator and denominator come from the same rasterization.
    assert profile["coverage"] == "full"
    assert profile["coverage_ratio"] == 1.0
    assert sum(b["ha"] for b in profile["bins"]) == pytest.approx(true_ha, rel=0.01)
    assert profile["covered_area_ha"] == pytest.approx(true_ha, rel=0.01)


def test_thin_strip_parcel_hectares_match_its_true_area(tmp_path):
    """A canal-side strip is mostly edge: 20 m wide is narrower than one pixel.

    Every pixel of it is a partial pixel, so this is the worst case for any
    edge-approximating estimator (the supersampled one read -25 % here).
    """
    values = np.full((110, 10), 40.0, dtype="float32")
    raster = _write_raster(tmp_path, values, name="strip.tif")
    geom = box(ORIGIN_X + 7.0, ORIGIN_Y - 3007.0, ORIGIN_X + 27.0, ORIGIN_Y - 7.0)
    true_ha = geom.area / 10_000.0  # 20 m x 3 000 m = 6 ha

    profile = extract_zonal_profile(
        raster,
        mapping(geom),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=geom.area,
    )

    assert profile["coverage"] == "full"
    assert profile["coverage_ratio"] == 1.0
    assert profile["covered_area_ha"] == pytest.approx(true_ha, rel=0.01)
    assert sum(b["ha"] for b in profile["bins"]) == pytest.approx(true_ha, rel=0.01)


# ---------------------------------------------------------------------------
# (i) R3-002 — an interior nodata hole is no longer absorbed by the clamp
# ---------------------------------------------------------------------------


def test_interior_nodata_hole_reports_partial_coverage(tmp_path):
    """30 fully-interior nodata pixels = 10.8 % of a 25 ha parcel.

    Under whole-pixel counting the edge inflation (+16.6 %) more than paid for
    the hole, so ``min(1.0, ratio)`` clamped to 1.0 and the parcel reported
    ``full`` while a tenth of it had no data at all.
    """
    values = _big_values()
    values[6:12, 6:11] = NODATA  # 6 rows x 5 cols, strictly inside the parcel
    raster = _write_raster(tmp_path, values, name="big.tif")
    geom = _offset_box(500.0)

    profile = extract_zonal_profile(
        raster,
        mapping(geom),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=geom.area,
    )

    assert profile["coverage"] == "partial"
    assert profile["coverage_ratio"] == pytest.approx(0.892, abs=0.02)
    assert profile["covered_area_ha"] == pytest.approx(25.0 - 2.7, rel=0.02)


# ---------------------------------------------------------------------------
# (i2) R3-009 — a geometry with no area is "none", never "full" with zero ha
# ---------------------------------------------------------------------------


def test_geometry_with_zero_rasterized_area_reports_no_coverage(tmp_path, monkeypatch):
    """The coverage denominator is the geometry's own weight; at zero it is unknowable.

    Reported as ``full`` it would be a confident wrong answer: a ficha claiming
    complete coverage of 0.0 ha. Forced through the seam because a real geometry
    that both survives ``rasterio_mask`` and rasterizes to nothing needs
    sub-float-precision coordinates.
    """
    raster = _write_raster(tmp_path, _filled(40.0))
    monkeypatch.setattr(
        composites,
        "_coverage_fractions",
        lambda geom, transform, shape_hw: np.zeros(shape_hw, dtype=np.float64),
    )

    profile = extract_zonal_profile(
        raster,
        mapping(RASTER_BOX),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=RASTER_AREA_M2,
    )

    assert profile["coverage"] == "none"
    assert profile["coverage_ratio"] == 0.0
    assert profile["covered_area_ha"] == 0.0


def test_self_intersecting_geometry_is_repaired_not_silently_zeroed(tmp_path):
    """A bowtie has ``area == 0`` in shapely but covers two real triangles.

    Taking its raw area would have made the denominator zero and dropped the
    dataset; the weights come from the repaired geometry, so it reports the
    2 x 1 012.5 m2 it actually covers.
    """
    raster = _write_raster(tmp_path, _filled(40.0))
    bowtie = Polygon(
        [
            (ORIGIN_X + 30.0, ORIGIN_Y - 30.0),
            (ORIGIN_X + 120.0, ORIGIN_Y - 120.0),
            (ORIGIN_X + 120.0, ORIGIN_Y - 30.0),
            (ORIGIN_X + 30.0, ORIGIN_Y - 120.0),
        ]
    )
    assert not bowtie.is_valid and bowtie.area == 0.0

    profile = extract_zonal_profile(
        raster, mapping(bowtie), geom_crs=CRS_32720, breaks=FLOOD_BREAKS
    )

    assert profile["coverage"] == "full"
    assert profile["covered_area_ha"] == pytest.approx(bowtie.buffer(0).area / 10_000.0, rel=0.01)


# ---------------------------------------------------------------------------
# (j) R1-001 — only the rasterio non-overlap ValueError means "no coverage"
# ---------------------------------------------------------------------------


def test_unrelated_value_error_propagates(tmp_path, monkeypatch):
    raster = _write_raster(tmp_path, _filled(40.0))

    def _boom(*args, **kwargs):
        raise ValueError("Invalid geometry: self-intersection at (1, 2)")

    monkeypatch.setattr(composites, "rasterio_mask", _boom)

    with pytest.raises(ValueError, match="self-intersection"):
        extract_zonal_profile(
            raster,
            mapping(RASTER_BOX),
            geom_crs=CRS_32720,
            breaks=FLOOD_BREAKS,
            geom_area_m2=RASTER_AREA_M2,
        )


# ---------------------------------------------------------------------------
# (k) R4-001 — a raster without a nodata tag must not gain phantom zeros
# ---------------------------------------------------------------------------


def test_raster_without_nodata_tag_does_not_gain_phantom_zeros(tmp_path):
    """``rasterio_mask(filled=True)`` stuffs 0 outside the shape when nodata is unset.

    The geometry is a diamond, so the crop window has corners OUTSIDE it; a
    filled read would score them 0 and both drag ``mean`` down and invent a
    "Bajo" class the raster does not contain.
    """
    raster = _write_raster(tmp_path, _filled(40.0), nodata=None)
    cx = ORIGIN_X + SIZE * PIXEL_M / 2
    cy = ORIGIN_Y - SIZE * PIXEL_M / 2
    half = SIZE * PIXEL_M / 2
    diamond = Polygon([(cx, cy + half), (cx + half, cy), (cx, cy - half), (cx - half, cy)])

    profile = extract_zonal_profile(
        raster,
        mapping(diamond),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=diamond.area,
    )

    bins = _bins_by_label(profile)
    assert profile["mean"] == pytest.approx(40.0)
    assert profile["max"] == pytest.approx(40.0)
    assert bins["Bajo"]["pixels"] == 0
    assert bins["Bajo"]["ha"] == 0.0
    assert bins["Medio"]["ha"] == pytest.approx(4.5, rel=0.03)
    assert profile["coverage"] == "full"


# ---------------------------------------------------------------------------
# (l) R4-002 — a raster without a CRS is a failure, not a zone without coverage
# ---------------------------------------------------------------------------


def test_raster_without_crs_raises(tmp_path):
    raster = _write_raster(tmp_path, _filled(40.0), crs=None)

    with pytest.raises(ValueError, match="no CRS"):
        extract_zonal_profile(
            raster,
            mapping(RASTER_BOX),
            geom_crs=CRS_32720,
            breaks=FLOOD_BREAKS,
            geom_area_m2=RASTER_AREA_M2,
        )


# ---------------------------------------------------------------------------
# (m) R2-002 — geographic raster, no geom_area_m2: coverage is still real
# ---------------------------------------------------------------------------

GEO_ORIGIN = (-63.0, -31.0)
GEO_PIXEL = 0.001
GEO_SIZE = 20


def test_geographic_raster_without_geom_area_detects_partial_coverage(tmp_path):
    """The old fallback reported ``full`` here because it had no area to divide by.

    Coverage now comes from the geometry's own weight in pixel units, which is
    dimensionless, so a geographic raster needs no projected area from the caller.
    """
    values = np.full((GEO_SIZE, GEO_SIZE), 40.0, dtype="float32")
    values[7:13, 7:12] = NODATA  # 30 interior pixels
    raster = _write_raster(
        tmp_path,
        values,
        name="geo.tif",
        crs=CRS_4326,
        origin=GEO_ORIGIN,
        pixel=GEO_PIXEL,
    )
    lon0, lat0 = GEO_ORIGIN
    geom = box(
        lon0 + 2 * GEO_PIXEL,
        lat0 - 18 * GEO_PIXEL,
        lon0 + 18 * GEO_PIXEL,
        lat0 - 2 * GEO_PIXEL,
    )

    profile = extract_zonal_profile(
        raster,
        mapping(geom),
        geom_crs=CRS_4326,
        breaks=FLOOD_BREAKS,
        geom_area_m2=None,
    )

    assert profile["coverage"] == "partial"
    # 30 nodata pixels out of the 16 x 16 = 256 the geometry covers.
    assert profile["coverage_ratio"] == pytest.approx(1 - 30 / 256, abs=0.02)
    assert profile["low_confidence"] is False


def test_geographic_raster_without_geom_area_reports_full_when_complete(tmp_path):
    values = np.full((GEO_SIZE, GEO_SIZE), 40.0, dtype="float32")
    raster = _write_raster(
        tmp_path,
        values,
        name="geo.tif",
        crs=CRS_4326,
        origin=GEO_ORIGIN,
        pixel=GEO_PIXEL,
    )
    lon0, lat0 = GEO_ORIGIN
    geom = box(
        lon0 + 2 * GEO_PIXEL,
        lat0 - 18 * GEO_PIXEL,
        lon0 + 18 * GEO_PIXEL,
        lat0 - 2 * GEO_PIXEL,
    )

    profile = extract_zonal_profile(
        raster, mapping(geom), geom_crs=CRS_4326, breaks=FLOOD_BREAKS, geom_area_m2=None
    )

    assert profile["coverage"] == "full"


# ---------------------------------------------------------------------------
# (n) R3-005 — the DEFAULT geom_crs (EPSG:4326) against a UTM raster
# ---------------------------------------------------------------------------


def test_default_geom_crs_is_reprojected_onto_a_utm_raster(tmp_path):
    raster = _write_raster(tmp_path, _filled(40.0))
    to_4326 = Transformer.from_crs(CRS_32720, CRS_4326, always_xy=True)
    geom_4326 = shapely_transform(to_4326.transform, RASTER_BOX)

    profile = extract_zonal_profile(
        raster,
        mapping(geom_4326),  # no geom_crs: the EPSG:4326 default must apply
        breaks=FLOOD_BREAKS,
    )

    assert profile["coverage"] == "full"
    assert profile["covered_area_ha"] == pytest.approx(9.0, rel=0.02)
    assert profile["mean"] == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# (o) treat_zero_as_nodata — the precip-only convention, OPT-IN by construction
# ---------------------------------------------------------------------------


def _half_zero() -> np.ndarray:
    """40.0 on the western half, a literal 0.0 on the eastern half."""
    values = _filled(40.0)
    values[:, SIZE // 2 :] = 0.0
    return values


def test_zero_pixels_are_data_when_the_flag_is_off(tmp_path):
    """The DEFAULT must never change: a 0 is a measurement for every classified dataset.

    ``flood_risk`` / ``drainage_need`` share this primitive and their class 0 is
    a real class. This is the guard that keeps the precipitation convention from
    leaking into them — it asserts the untouched behaviour, so it fails the day
    the flag stops being opt-in.
    """
    raster = _write_raster(tmp_path, _half_zero())

    profile = extract_zonal_profile(
        raster,
        mapping(RASTER_BOX),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=RASTER_AREA_M2,
    )

    assert profile["valid_pixels"] == 100  # the zeros count
    assert profile["mean"] == pytest.approx(20.0)  # …and drag the mean to half
    assert profile["coverage"] == "full"
    assert profile["coverage_ratio"] == 1.0


def test_treat_zero_as_nodata_drops_the_zeros_from_stats_and_from_coverage(tmp_path):
    """Opted in, a 0 is excluded exactly like a nodata pixel — on BOTH accountings.

    Excluding it only from the statistics would leave the worse half of the
    defect in place: a clean mean served under ``cobertura: total``, i.e. the
    reader still told the number covers the whole zone.
    """
    raster = _write_raster(tmp_path, _half_zero())

    profile = extract_zonal_profile(
        raster,
        mapping(RASTER_BOX),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=RASTER_AREA_M2,
        treat_zero_as_nodata=True,
    )

    assert profile["valid_pixels"] == 50
    assert profile["mean"] == pytest.approx(40.0)
    assert profile["max"] == pytest.approx(40.0)
    assert profile["coverage"] == "partial"
    assert profile["coverage_ratio"] == pytest.approx(0.5, abs=0.02)
    assert profile["covered_area_ha"] == pytest.approx(4.5, rel=0.02)


def test_treat_zero_as_nodata_over_an_all_zero_zone_is_no_coverage(tmp_path):
    """Every pixel fake → ``none``, not a confident 0.0 mean over the whole zone."""
    raster = _write_raster(tmp_path, _filled(0.0))

    profile = extract_zonal_profile(
        raster,
        mapping(RASTER_BOX),
        geom_crs=CRS_32720,
        breaks=FLOOD_BREAKS,
        geom_area_m2=RASTER_AREA_M2,
        treat_zero_as_nodata=True,
    )

    assert profile["valid_pixels"] == 0
    assert profile["mean"] is None
    assert profile["coverage"] == "none"
    assert profile["coverage_ratio"] == 0.0
