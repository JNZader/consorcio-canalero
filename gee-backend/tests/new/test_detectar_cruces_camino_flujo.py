"""Pure-function tests for ``detectar_cruces_camino_flujo_impl`` (flujo-caminos D3).

No database. Hand-built affine transforms and hand-built accumulation arrays, so
every property under test is a property of the derivation and not of a fixture.
One test class per mechanism, mapping the design's Testing Strategy rows
one-to-one:

* azimuth is derived FROM THE TRANSFORM, never from a hardcoded compass table;
* true local maxima, including the plateau rule that has to be invariant under a
  reversed digitization;
* the crossing derivation on a synthetic raster;
* the three-band crossing predicate, both edges exercised exactly;
* min-separation suppression that RECORDS what it suppressed;
* the network-level junction pass;
* canal crossings, unconditional, with non-Point intersections decomposed;
* the CRS contract — a test that fails if the code stamps 4326 without
  transforming.

The rasters are written as real GeoTIFFs into ``tmp_path`` because the function
under test opens paths with rasterio; the *content* is hand-built, so this is
still a pure-function test with a file-shaped argument, not an integration test.
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS
from shapely.geometry import LineString

from app.domains.geo.intelligence.calculations_hydrology_support import (
    D8_OFFSETS,
    CruceDerivationError,
    _decompose_intersection,
    azimut_desde_transform,
    clasificar_banda_cruce,
    detectar_cruces_camino_flujo_impl,
)

# A synthetic north-up UTM 20S transform: 30 m cells, origin at a round easting
# and northing so hand-computed row/col arithmetic is readable in the assertions.
CELL = 30.0
ORIGIN_X = 400_000.0
ORIGIN_Y = 6_400_000.0
UTM = CRS.from_epsg(32720)
NORTH_UP = Affine(CELL, 0.0, ORIGIN_X, 0.0, -CELL, ORIGIN_Y)

#: Seeds, as the design fixes them. Passed explicitly on every call — the
#: function takes them keyword-only and holds no default of its own.
SEEDS = {
    "acc_threshold_cells": 1000.0,
    "min_separation_m": 90.0,
    "parallel_min_angle_deg": 22.5,
    "parallel_high_angle_deg": 45.0,
    "bearing_window_m": 60.0,
}


def _empty_geojson(columns: list[str]):
    import geopandas as gpd

    return gpd.GeoDataFrame(columns=columns, geometry="geometry")


def _write_raster(path, data: np.ndarray, *, transform=NORTH_UP, nodata=-9999.0, crs=UTM) -> str:
    with rasterio.open(
        str(path),
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float64",
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(data.astype("float64"), 1)
    return str(path)


def _cell_center(row: int, col: int, transform=NORTH_UP) -> tuple[float, float]:
    x, y = transform * (col + 0.5, row + 0.5)
    return x, y


def _road_along_row(row: int, col_from: int, col_to: int, transform=NORTH_UP) -> LineString:
    """A due-EAST road along one raster row, in the raster's UTM frame."""
    start = _cell_center(row, col_from, transform)
    end = _cell_center(row, col_to, transform)
    return LineString([start, end])


def _road_along_col(col: int, row_from: int, row_to: int, transform=NORTH_UP) -> LineString:
    """A due-SOUTH road down one raster column, in the raster's UTM frame."""
    start = _cell_center(row_from, col, transform)
    end = _cell_center(row_to, col, transform)
    return LineString([start, end])


def _roads(rows: list[dict]):
    """Build a road GeoDataFrame in UTM, then hand it over in 4326.

    The function under test reprojects its inputs to the raster CRS itself; the
    caller always supplies 4326, exactly as the repository does.
    """
    import geopandas as gpd

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=UTM)
    return gdf.to_crs(4326)


def _canals(rows: list[dict]):
    import geopandas as gpd

    if not rows:
        return gpd.GeoDataFrame({"id": [], "geometry": []}, geometry="geometry", crs=4326)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=UTM)
    return gdf.to_crs(4326)


def _run(roads, canals, flow_dir_path, flow_acc_path, **overrides):
    params = {**SEEDS, **overrides}
    return detectar_cruces_camino_flujo_impl(
        roads,
        canals,
        flow_dir_path,
        flow_acc_path,
        build_empty_geojson=_empty_geojson,
        **params,
    )


def _flow_dir_all(code: int, shape: tuple[int, int]) -> np.ndarray:
    return np.full(shape, float(code))


# ---------------------------------------------------------------------------
# 2.8 — azimuth is derived from the transform, not from a compass table
# ---------------------------------------------------------------------------


class TestAzimuthFromTransform:
    """The compass meaning of a D8 code is a property of the RASTER, not of D8.

    ``D8_OFFSETS`` is array-space ``(Δrow, Δcol)``. ``1 = East`` only holds when
    the transform is north-up. A rotated or south-up raster silently rotates
    every direction this feature reports, so the azimuth is computed from the
    affine and the north-up case is merely the answer that falls out.
    """

    #: WBT's D8 codes against a north-up raster, as compass azimuths.
    EXPECTED = {
        1: 90.0,  # E
        2: 45.0,  # NE
        4: 0.0,  # N
        8: 315.0,  # NW
        16: 270.0,  # W
        32: 225.0,  # SW
        64: 180.0,  # S
        128: 135.0,  # SE
    }

    @pytest.mark.parametrize("code,expected", sorted(EXPECTED.items()))
    def test_all_eight_codes_on_a_north_up_transform(self, code: int, expected: float):
        assert azimut_desde_transform(code, NORTH_UP) == pytest.approx(expected)

    def test_offsets_are_array_space_row_col(self):
        """Guard the extraction: ``1`` must move one COLUMN east, zero rows."""
        assert D8_OFFSETS[1] == (0, 1)
        assert D8_OFFSETS[4] == (-1, 0)
        assert D8_OFFSETS[64] == (1, 0)
        assert len(D8_OFFSETS) == 8

    def test_a_rotated_transform_is_refused_by_name(self):
        rotated = Affine(CELL, 5.0, ORIGIN_X, 0.0, -CELL, ORIGIN_Y)  # t.b != 0
        with pytest.raises(CruceDerivationError, match="north-up"):
            azimut_desde_transform(1, rotated)

    def test_a_sheared_transform_is_refused(self):
        sheared = Affine(CELL, 0.0, ORIGIN_X, 5.0, -CELL, ORIGIN_Y)  # t.d != 0
        with pytest.raises(CruceDerivationError, match="north-up"):
            azimut_desde_transform(1, sheared)

    def test_a_south_up_transform_is_refused(self):
        south_up = Affine(CELL, 0.0, ORIGIN_X, 0.0, CELL, ORIGIN_Y)  # t.e >= 0
        with pytest.raises(CruceDerivationError, match="north-up"):
            azimut_desde_transform(1, south_up)

    def test_a_pointer_value_absent_from_the_table_has_no_azimuth(self):
        """Not a zero. A zero is a direction — due north — and would be a lie."""
        assert azimut_desde_transform(7, NORTH_UP) is None

    def test_nodata_pointer_has_no_azimuth(self):
        assert azimut_desde_transform(-9999, NORTH_UP) is None

    def test_area_is_read_from_the_transform_not_assumed(self, tmp_path):
        """``area_aporte_ha = fa_val * |t.a * t.e| / 10_000``.

        A 30 m cell is 900 m²; 1200 cells is 108 ha. Nothing here assumes the
        cell size — a 10 m transform on the same array gives a ninth of it.
        """
        shape = (5, 9)
        acc = np.full(shape, 10.0)
        acc[2, 4] = 1200.0
        fine = Affine(10.0, 0.0, ORIGIN_X, 0.0, -10.0, ORIGIN_Y)

        for transform, expected_ha in ((NORTH_UP, 108.0), (fine, 12.0)):
            tag = "coarse" if transform is NORTH_UP else "fine"
            fd = _write_raster(
                tmp_path / f"fd_{tag}.tif", _flow_dir_all(4, shape), transform=transform
            )
            fa = _write_raster(tmp_path / f"fa_{tag}.tif", acc, transform=transform)
            roads = _roads(
                [{"id": "t1", "geometry": _road_along_row(2, 0, 8, transform)}],
            )
            gdf, _, _ = _run(roads, _canals([]), fd, fa)
            assert len(gdf) == 1
            assert float(gdf.iloc[0]["area_aporte_ha"]) == pytest.approx(expected_ha)

    def test_a_rotated_raster_stops_the_whole_run(self, tmp_path):
        """The assertion is at open time, so a rotated DEM never reports at all."""
        shape = (5, 9)
        acc = np.full(shape, 10.0)
        acc[2, 4] = 5000.0
        rotated = Affine(CELL, 5.0, ORIGIN_X, 0.0, -CELL, ORIGIN_Y)
        fd = _write_raster(tmp_path / "fd_rot.tif", _flow_dir_all(4, shape), transform=rotated)
        fa = _write_raster(tmp_path / "fa_rot.tif", acc, transform=rotated)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])

        with pytest.raises(CruceDerivationError, match="north-up"):
            _run(roads, _canals([]), fd, fa)


# ---------------------------------------------------------------------------
# 2.10 — true local maxima
# ---------------------------------------------------------------------------


class TestTrueLocalMaxima:
    """A global sort is not a local-maximum test.

    On a road running ALONG a rising channel, "the highest cell of the profile"
    is the ramp's endpoint — an artefact of where the segment happens to stop,
    not a crossing. The candidate rule is therefore strictly local.
    """

    def test_a_monotone_ramp_yields_no_crossing(self, tmp_path):
        shape = (5, 9)
        acc = np.tile(np.linspace(1000.0, 9000.0, 9), (5, 1))
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])

        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 0, "a descending global sort would have returned the ramp endpoint"
        assert {e["motivo"] for e in excluidos} <= {"maximo_en_extremo"}

    @pytest.mark.parametrize("plateau_cols", [(3, 4), (3, 4, 5)])
    def test_a_plateau_yields_one_candidate_at_the_lexicographically_smallest_cell(
        self, tmp_path, plateau_cols: tuple[int, ...]
    ):
        shape = (5, 9)
        acc = np.full(shape, 100.0)
        for col in plateau_cols:
            acc[2, col] = 5000.0
        tag = str(len(plateau_cols))
        fd = _write_raster(tmp_path / f"fd{tag}.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / f"fa{tag}.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])

        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 1
        x, y = gdf.to_crs(UTM).iloc[0].geometry.coords[0]
        expected_x, expected_y = _cell_center(2, min(plateau_cols))
        assert x == pytest.approx(expected_x, abs=1.0)
        assert y == pytest.approx(expected_y, abs=1.0)

    @pytest.mark.parametrize("plateau_cols", [(3, 4), (3, 4, 5)])
    def test_the_plateau_cell_is_the_same_when_the_road_is_reversed(
        self, tmp_path, plateau_cols: tuple[int, ...]
    ):
        """The round-2 midpoint index fails EXACTLY here, on even lengths.

        Reversing the traversal maps index ``k`` of an ``L``-cell run to
        ``L-1-k``, so ``floor((L-1)/2)`` is invariant only for odd ``L``. The
        ``(row, col)`` minimum is a property of the cells, not of the visit
        order, so it holds for any plateau length.
        """
        shape = (5, 9)
        acc = np.full(shape, 100.0)
        for col in plateau_cols:
            acc[2, col] = 5000.0
        tag = f"rev{len(plateau_cols)}"
        fd = _write_raster(tmp_path / f"fd{tag}.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / f"fa{tag}.tif", acc)

        forward = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])
        backward = _roads([{"id": "t1", "geometry": _road_along_row(2, 8, 0)}])

        gdf_f, _, _ = _run(forward, _canals([]), fd, fa)
        gdf_b, _, _ = _run(backward, _canals([]), fd, fa)

        pf = gdf_f.to_crs(UTM).iloc[0].geometry
        pb = gdf_b.to_crs(UTM).iloc[0].geometry
        assert pf.distance(pb) < 1.0, "the plateau cell must not depend on digitization order"

    def test_a_maximum_at_a_lone_segment_endpoint_is_excluded_not_crossed(self, tmp_path):
        """A dead end: the ramp may continue past the segment, unverifiably."""
        shape = (5, 9)
        acc = np.full(shape, 100.0)
        acc[2, 8] = 9000.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])

        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 0
        assert any(e["motivo"] == "maximo_en_extremo" for e in excluidos)


# ---------------------------------------------------------------------------
# 2.11 — crossing derivation on a synthetic raster
# ---------------------------------------------------------------------------


class TestCrossingDerivation:
    def test_one_ridge_yields_exactly_one_crossing(self, tmp_path):
        """A polygon intersection would have returned TWO — the blob's rim.

        That is the whole reason the ``drainage`` layer is not used: it is a
        polygonised cell mask, and ``road ∩ polygon`` gives entry and exit
        boundary points, not the channel cell.
        """
        shape = (5, 9)
        acc = np.full(shape, 100.0)
        acc[2, 4] = 6000.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])

        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 1

    def test_the_returned_cell_is_the_argmax_so_the_area_is_read_there(self, tmp_path):
        """Never an adjacent cell, never a rim cell — there is nothing to snap."""
        shape = (5, 9)
        acc = np.full(shape, 100.0)
        acc[2, 3] = 4000.0
        acc[2, 4] = 6000.0
        acc[2, 5] = 4000.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])

        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 1
        expected_ha = 6000.0 * CELL * CELL / 10_000
        assert float(gdf.iloc[0]["area_aporte_ha"]) == pytest.approx(expected_ha)

    def test_a_ridge_below_the_threshold_yields_nothing(self, tmp_path):
        shape = (5, 9)
        acc = np.full(shape, 10.0)
        acc[2, 4] = 999.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])

        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 0
        assert not any(e["motivo"] == "flujo_paralelo" for e in excluidos), (
            "a sub-threshold rill is dropped silently, not reported individually"
        )

    def test_two_runs_over_the_same_input_are_identical(self, tmp_path):
        shape = (5, 15)
        acc = np.full(shape, 100.0)
        acc[2, 3] = 6000.0
        acc[2, 11] = 6000.0  # identical values — the tie-break must be data-only
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 14)}])

        first, _, _ = _run(roads, _canals([]), fd, fa)
        second, _, _ = _run(roads, _canals([]), fd, fa)

        assert list(first["orden_ranking"]) == list(second["orden_ranking"])
        assert [g.wkt for g in first.geometry] == [g.wkt for g in second.geometry]

    def test_the_returned_frame_carries_exactly_the_sealed_columns(self, tmp_path):
        """No ``severidad``, no ``acumulacion_valor``, no ``pendiente_valor``."""
        shape = (5, 9)
        acc = np.full(shape, 100.0)
        acc[2, 4] = 6000.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])

        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        assert set(gdf.columns) == {
            "tipo",
            "geometry",
            "tramo_ref",
            "canal_ref",
            "direccion_flujo_deg",
            "rumbo_camino_deg",
            "lado_cruce",
            "area_aporte_ha",
            "orden_ranking",
            "confianza",
            "nota",
        }

    def test_a_directionless_candidate_is_excluded_not_zero_filled(self, tmp_path):
        """RFA: never an unranked or zero-area point."""
        shape = (5, 9)
        acc = np.full(shape, 100.0)
        acc[2, 4] = 6000.0
        pointer = _flow_dir_all(4, shape)
        pointer[2, 4] = -9999.0  # nodata exactly at the candidate
        fd = _write_raster(tmp_path / "fd.tif", pointer)
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 8)}])

        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 0
        assert any(e["motivo"] == "sin_direccion" for e in excluidos)

    def test_the_motivos_are_a_closed_set(self, tmp_path):
        shape = (5, 15)
        acc = np.tile(np.linspace(1000.0, 9000.0, 15), (5, 1))
        acc[2, 6] = 20_000.0
        acc[2, 7] = 19_000.0
        pointer = _flow_dir_all(1, shape)  # due EAST, along the road → parallel
        pointer[2, 6] = -9999.0
        fd = _write_raster(tmp_path / "fd.tif", pointer)
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(2, 0, 14)}])

        _, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert {e["motivo"] for e in excluidos} <= {
            "sin_direccion",
            "flujo_paralelo",
            "suprimido_por_separacion",
            "maximo_en_extremo",
        }
        for entry in excluidos:
            assert entry["tramo_ref"] == "t1"


# ---------------------------------------------------------------------------
# 2.12 — the three-band crossing predicate
# ---------------------------------------------------------------------------


def _predicate_case(tmp_path, pointer_code: int, *, tag: str, road="row"):
    """One candidate on a due-east (or due-south) road, with a chosen D8 code."""
    shape = (9, 9)
    acc = np.full(shape, 100.0)
    acc[4, 4] = 6000.0
    pointer = _flow_dir_all(pointer_code, shape)
    fd = _write_raster(tmp_path / f"fd_{tag}.tif", pointer)
    fa = _write_raster(tmp_path / f"fa_{tag}.tif", acc)
    geometry = _road_along_row(4, 0, 8) if road == "row" else _road_along_col(4, 0, 8)
    roads = _roads([{"id": "t1", "geometry": geometry}])
    return roads, fd, fa


class TestCrossingPredicateThreeBands:
    """A binary cut at 30° claims a precision the inputs do not have.

    The D8 azimuth is quantized to 45° by construction and the road bearing is
    read off a rasterized polyline. Near the cut the binary verdict is a coin
    toss dressed as a measurement, so the middle band is kept AND marked.
    """

    def test_flow_along_the_road_is_excluded_as_parallel(self, tmp_path):
        roads, fd, fa = _predicate_case(tmp_path, 1, tag="par")  # E, road runs E
        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 0
        parallel = [e for e in excluidos if e["motivo"] == "flujo_paralelo"]
        assert len(parallel) == 1
        for key in ("theta_deg", "rumbo_camino_deg", "direccion_flujo_deg"):
            assert key in parallel[0], f"the exclusion must carry {key} to be auditable"
        assert parallel[0]["theta_deg"] == pytest.approx(0.0, abs=1e-6)

    def test_flow_at_170_degrees_to_the_road_is_treated_as_10_and_excluded(self, tmp_path):
        """θ is ACUTE. Anti-parallel is parallel for the purpose of crossing."""
        roads, fd, fa = _predicate_case(tmp_path, 16, tag="anti")  # W, road runs E
        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 0
        parallel = [e for e in excluidos if e["motivo"] == "flujo_paralelo"]
        assert parallel and parallel[0]["theta_deg"] == pytest.approx(0.0, abs=1e-6)

    def test_a_perpendicular_flow_is_high_confidence(self, tmp_path):
        roads, fd, fa = _predicate_case(tmp_path, 4, tag="perp")  # N, road runs E → θ=90
        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 1
        assert gdf.iloc[0]["confianza"] == "alta"

    def test_a_diagonal_flow_at_45_degrees_is_high_confidence(self, tmp_path):
        """The UPPER band edge, exercised EXACTLY at 45: ``θ >= 45`` is ``alta``."""
        roads, fd, fa = _predicate_case(tmp_path, 2, tag="ne")  # NE, road runs E → θ=45
        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 1
        assert gdf.iloc[0]["confianza"] == "alta", "45 belongs to the HIGH band, not the low one"

    @pytest.mark.parametrize(
        "theta,expected",
        [
            (0.0, None),
            (22.4999, None),
            (22.5, "baja"),  # the LOWER edge, EXACTLY
            (44.9999, "baja"),
            (45.0, "alta"),  # the UPPER edge, EXACTLY
            (90.0, "alta"),
        ],
    )
    def test_both_band_edges_are_exercised_exactly(self, theta: float, expected):
        """The edges belong to the band ABOVE them.

        Exercised on the predicate directly and not through the derivation,
        because the derivation's ``β`` is deliberately read off the *rasterized*
        traversal — that is the whole point of ``BEARING_WINDOW_M`` — so no road
        geometry produces a θ of exactly 22.5 through the full path. Testing the
        edge through a pipeline that cannot hit it would be testing nothing.
        """
        assert clasificar_banda_cruce(theta, 22.5, 45.0) == expected

    def test_a_mid_band_crossing_is_stored_with_baja(self, tmp_path):
        """22.5 ≤ θ < 45 — the quantization band. Kept, ranked, and MARKED.

        A road climbing one column per two rows has a true bearing of ~26.6°, and
        a due-north flow gives θ ≈ 26.6 — inside the band and far from both
        edges. ``bearing_window_m`` is widened to 180 m (6 cells) for this case,
        and that widening is the point rather than a workaround: at the 60 m seed
        the ±2-cell chord lands on a single diagonal stair-step of the rasterized
        traversal and reads 45°, which is precisely the rasterization error the
        design cites when it says the window exists "so rasterization stair-steps
        do not drive the angle test". A 2:1 road is the case where the seed is
        too narrow to see the road's real direction.
        """
        shape = (21, 21)
        acc = np.full(shape, 100.0)
        acc[10, 10] = 6000.0
        fd = _write_raster(tmp_path / "fd_mid.tif", _flow_dir_all(4, shape))  # N, 0°
        fa = _write_raster(tmp_path / "fa_mid.tif", acc)

        start = _cell_center(16, 7)
        end = _cell_center(4, 13)
        roads = _roads([{"id": "t1", "geometry": LineString([start, end])}])

        gdf, _, _ = _run(roads, _canals([]), fd, fa, bearing_window_m=180.0)

        assert len(gdf) == 1
        row = gdf.iloc[0]
        assert row["confianza"] == "baja"
        assert row["nota"], "a low-confidence row must say why"
        theta = min(
            abs(float(row["direccion_flujo_deg"]) - float(row["rumbo_camino_deg"])) % 180.0,
            180.0 - abs(float(row["direccion_flujo_deg"]) - float(row["rumbo_camino_deg"])) % 180.0,
        )
        assert 22.5 <= theta < 45.0

    def test_the_road_bearing_is_stored_not_implied(self, tmp_path):
        """``lado_cruce`` without its reference frame is a coin flip nobody can check."""
        roads, fd, fa = _predicate_case(tmp_path, 4, tag="bearing")
        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        row = gdf.iloc[0]
        assert row["rumbo_camino_deg"] is not None
        assert float(row["rumbo_camino_deg"]) == pytest.approx(90.0, abs=1.0)
        assert float(row["direccion_flujo_deg"]) == pytest.approx(0.0, abs=1e-6)

    def test_lado_cruce_flips_when_the_flow_azimuth_flips_180(self, tmp_path):
        north, fd_n, fa_n = _predicate_case(tmp_path, 4, tag="ladoN")
        south, fd_s, fa_s = _predicate_case(tmp_path, 64, tag="ladoS")

        gdf_n, _, _ = _run(north, _canals([]), fd_n, fa_n)
        gdf_s, _, _ = _run(south, _canals([]), fd_s, fa_s)

        assert gdf_n.iloc[0]["lado_cruce"] != gdf_s.iloc[0]["lado_cruce"]
        assert {gdf_n.iloc[0]["lado_cruce"], gdf_s.iloc[0]["lado_cruce"]} == {
            "izq_a_der",
            "der_a_izq",
        }

    def test_lado_cruce_flips_when_the_road_digitization_is_reversed(self, tmp_path):
        """It is defined relative to the STORED direction of travel, so it must."""
        shape = (9, 9)
        acc = np.full(shape, 100.0)
        acc[4, 4] = 6000.0
        fd = _write_raster(tmp_path / "fd_dig.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa_dig.tif", acc)

        forward = _roads([{"id": "t1", "geometry": _road_along_row(4, 0, 8)}])
        backward = _roads([{"id": "t1", "geometry": _road_along_row(4, 8, 0)}])

        gdf_f, _, _ = _run(forward, _canals([]), fd, fa)
        gdf_b, _, _ = _run(backward, _canals([]), fd, fa)

        assert gdf_f.iloc[0]["lado_cruce"] != gdf_b.iloc[0]["lado_cruce"]


# ---------------------------------------------------------------------------
# 2.13 — min-separation suppression RECORDS what it suppressed
# ---------------------------------------------------------------------------


class TestMinSeparationSuppression:
    """A meandering watercourse that really crosses twice is a real pattern.

    Suppression is kept because one ridge otherwise registers as three adjacent
    cells — the far more common failure — but every above-threshold candidate it
    swallows is recorded, so the double crossing stays visible in the run record
    and ``MIN_SEPARATION_M`` can be tuned from evidence.
    """

    def test_two_close_ridges_collapse_and_the_loser_is_recorded(self, tmp_path):
        shape = (9, 15)
        acc = np.full(shape, 100.0)
        acc[4, 6] = 8000.0
        acc[4, 8] = 6000.0  # 60 m away — inside the 90 m window
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(4, 0, 14)}])

        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 1, "the two ridges must collapse to one"
        assert float(gdf.iloc[0]["area_aporte_ha"]) == pytest.approx(
            8000.0 * CELL * CELL / 10_000
        ), "the head of the accumulation-descending order is the one that survives"

        suppressed = [e for e in excluidos if e["motivo"] == "suprimido_por_separacion"]
        assert len(suppressed) == 1
        assert suppressed[0]["acumulacion"] == pytest.approx(6000.0)
        assert suppressed[0]["distancia_m"] == pytest.approx(60.0, abs=CELL)

    def test_two_distant_ridges_both_survive(self, tmp_path):
        shape = (9, 15)
        acc = np.full(shape, 100.0)
        acc[4, 3] = 8000.0
        acc[4, 11] = 6000.0  # 240 m away — well outside the window
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(4, 0, 14)}])

        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 2
        assert not [e for e in excluidos if e["motivo"] == "suprimido_por_separacion"]

    def test_suppression_accepts_the_highest_accumulation_first(self, tmp_path):
        """Order: accumulation DESC, ties on along-road index ASC — a total order."""
        shape = (9, 15)
        acc = np.full(shape, 100.0)
        acc[4, 6] = 6000.0
        acc[4, 8] = 9000.0  # the LATER cell is the higher one
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(4, 0, 14)}])

        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 1
        assert float(gdf.iloc[0]["area_aporte_ha"]) == pytest.approx(9000.0 * CELL * CELL / 10_000)
        suppressed = [e for e in excluidos if e["motivo"] == "suprimido_por_separacion"]
        assert suppressed[0]["acumulacion"] == pytest.approx(6000.0)


# ---------------------------------------------------------------------------
# 2.14 — the network-level junction pass
# ---------------------------------------------------------------------------


class TestJunctionPass:
    """The native segmentation splits a continuous road AT junctions.

    So a real crossing landing on a shared node was dropped from BOTH abutting
    segments as ``maximo_en_extremo`` — a systematically missing class of
    crossings an operator would never notice. The per-segment rule stands; a
    second pass over shared nodes is what makes the exclusion honest.
    """

    @staticmethod
    def _abutting(tmp_path, tag: str, *, peak_at_node: bool, monotone: bool = False):
        shape = (9, 15)
        if monotone:
            acc = np.tile(np.linspace(2000.0, 9000.0, 15), (9, 1))
        else:
            acc = np.full(shape, 100.0)
            if peak_at_node:
                acc[4, 7] = 8000.0
        fd = _write_raster(tmp_path / f"fd_{tag}.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / f"fa_{tag}.tif", acc)
        west = {"id": "b_west", "geometry": _road_along_row(4, 0, 7)}
        east = {"id": "a_east", "geometry": _road_along_row(4, 7, 14)}
        return west, east, fd, fa

    def test_a_qualifying_node_emits_exactly_one_row(self, tmp_path):
        west, east, fd, fa = self._abutting(tmp_path, "one", peak_at_node=True)
        gdf, _, _ = _run(_roads([west, east]), _canals([]), fd, fa)

        assert len(gdf) == 1, "not zero (round 2) and not one per incident segment"

    def test_the_node_row_is_attributed_to_the_smallest_segment_id(self, tmp_path):
        """A data-only rule, so it reproduces regardless of feed order."""
        west, east, fd, fa = self._abutting(tmp_path, "attr", peak_at_node=True)

        forward, _, _ = _run(_roads([west, east]), _canals([]), fd, fa)
        reversed_feed, _, _ = _run(_roads([east, west]), _canals([]), fd, fa)

        assert forward.iloc[0]["tramo_ref"] == "a_east"
        assert reversed_feed.iloc[0]["tramo_ref"] == "a_east"

    def test_a_junction_on_a_monotone_ramp_is_rejected_like_any_ramp_cell(self, tmp_path):
        """The strict local-maximum test runs over the STITCHED profile.

        Without that criterion the junction pass would resurrect exactly the
        endpoint artefact the per-segment local-maximum rule exists to reject.
        """
        west, east, fd, fa = self._abutting(tmp_path, "ramp", peak_at_node=False, monotone=True)
        gdf, _, _ = _run(_roads([west, east]), _canals([]), fd, fa)

        assert len(gdf) == 0

    def test_a_lone_endpoint_still_yields_maximo_en_extremo(self, tmp_path):
        """After the pass, that motivo means only a TRUE dead end."""
        shape = (9, 15)
        acc = np.full(shape, 100.0)
        acc[4, 14] = 9000.0
        fd = _write_raster(tmp_path / "fd_lone.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa_lone.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(4, 0, 14)}])

        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 0
        assert any(e["motivo"] == "maximo_en_extremo" for e in excluidos)

    def test_a_junction_row_is_suppressed_by_a_near_in_segment_crossing(self, tmp_path):
        """It enters the same min-separation pass as everything else."""
        shape = (9, 15)
        acc = np.full(shape, 100.0)
        acc[4, 7] = 6000.0  # at the shared node
        acc[4, 9] = 9000.0  # 60 m east, in-segment and higher
        fd = _write_raster(tmp_path / "fd_sup.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa_sup.tif", acc)
        roads = _roads(
            [
                {"id": "b_west", "geometry": _road_along_row(4, 0, 7)},
                {"id": "a_east", "geometry": _road_along_row(4, 7, 14)},
            ]
        )

        gdf, excluidos, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 1
        assert float(gdf.iloc[0]["area_aporte_ha"]) == pytest.approx(9000.0 * CELL * CELL / 10_000)
        assert any(e["motivo"] == "suprimido_por_separacion" for e in excluidos)


# ---------------------------------------------------------------------------
# 2.15 — canal crossings are unconditional; non-Point intersections decompose
# ---------------------------------------------------------------------------


class TestCanalCrossings:
    """A canal crossing a road is a fact about two LINE geometries.

    It is true whether or not a DEM exists, whether or not the cell is nodata,
    and whether or not the point falls inside the raster footprint. Round 1 got
    this wrong by folding canal crossings into the raster-sampling path.
    """

    @staticmethod
    def _crossing_pair():
        road = _road_along_row(4, 0, 8)
        canal = _road_along_col(4, 0, 8)
        return road, canal

    def test_canal_rows_survive_an_all_nodata_raster(self, tmp_path):
        shape = (9, 9)
        nodata = np.full(shape, -9999.0)
        fd = _write_raster(tmp_path / "fd_nd.tif", nodata)
        fa = _write_raster(tmp_path / "fa_nd.tif", nodata)
        road, canal = self._crossing_pair()

        gdf, excluidos, _ = _run(
            _roads([{"id": "t1", "geometry": road}]),
            _canals([{"id": "c1", "geometry": canal}]),
            fd,
            fa,
        )

        canal_rows = gdf[gdf["tipo"] == "canal"]
        assert len(canal_rows) == 1
        row = canal_rows.iloc[0]
        assert row["direccion_flujo_deg"] is None
        assert row["lado_cruce"] is None
        assert row["area_aporte_ha"] is None
        assert row["orden_ranking"] is None, "canal rows are NEVER ranked"
        assert row["canal_ref"] == "c1"
        assert row["tramo_ref"] == "t1"
        assert excluidos == [], "a canal crossing is never an exclusion"

    def test_the_canal_derivation_runs_with_no_raster_at_all(self):
        road, canal = self._crossing_pair()

        gdf, excluidos, parametros = detectar_cruces_camino_flujo_impl(
            _roads([{"id": "t1", "geometry": road}]),
            _canals([{"id": "c1", "geometry": canal}]),
            None,
            None,
            build_empty_geojson=_empty_geojson,
            **SEEDS,
        )

        assert len(gdf) == 1
        assert gdf.iloc[0]["tipo"] == "canal"
        assert excluidos == []
        assert parametros["variante"] is None

    def test_canal_metrics_are_enriched_when_the_raster_can_supply_them(self, tmp_path):
        """Opportunistic, never a precondition — and STILL unranked."""
        shape = (9, 9)
        acc = np.full(shape, 3000.0)
        fd = _write_raster(tmp_path / "fd_en.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa_en.tif", acc)
        road, canal = self._crossing_pair()

        gdf, _, _ = _run(
            _roads([{"id": "t1", "geometry": road}]),
            _canals([{"id": "c1", "geometry": canal}]),
            fd,
            fa,
        )

        row = gdf[gdf["tipo"] == "canal"].iloc[0]
        assert row["direccion_flujo_deg"] == pytest.approx(0.0)
        assert row["area_aporte_ha"] is not None
        assert row["orden_ranking"] is None, (
            "a populated area does NOT make a canal crossing rankable — "
            "the rank is defined over the flujo_natural set"
        )

    def test_a_multipoint_intersection_becomes_one_row_per_point(self, tmp_path):
        shape = (15, 15)
        fd = _write_raster(tmp_path / "fd_mp.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa_mp.tif", np.full(shape, 100.0))

        road = _road_along_row(7, 0, 14)
        # A zig-zag canal that cuts the road twice.
        p1 = _cell_center(7, 3)
        p2 = _cell_center(7, 11)
        canal = LineString(
            [
                (p1[0], p1[1] + 200),
                (p1[0], p1[1] - 200),
                (p2[0], p2[1] - 200),
                (p2[0], p2[1] + 200),
            ]
        )

        gdf, _, _ = _run(
            _roads([{"id": "t1", "geometry": road}]),
            _canals([{"id": "c1", "geometry": canal}]),
            fd,
            fa,
        )

        canal_rows = gdf[gdf["tipo"] == "canal"]
        assert len(canal_rows) == 2
        assert all(g.geom_type == "Point" for g in canal_rows.geometry)

    def test_a_collinear_overlap_yields_one_midpoint_row_with_a_note(self, tmp_path):
        """A road on the canal's spoil bank is NORMAL, not exceptional.

        ``ST_Intersection`` returns a LINESTRING there, and inserting one into a
        Point column aborts the whole area's run. It becomes one row at the
        overlap midpoint, ``confianza='baja'``, with a note naming the shared
        length — surfaced, because a shared alignment is where a bank collapse
        takes the road with it.
        """
        shape = (15, 15)
        fd = _write_raster(tmp_path / "fd_ov.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa_ov.tif", np.full(shape, 100.0))

        # The canal shares the road's own VERTICES, which is what a shared
        # alignment digitized off the same base actually looks like. Building it
        # from independent coordinates would not survive the 4326 round-trip as
        # an exact overlap — reprojection is non-linear, so two "collinear" lines
        # come back a few nanometres apart and intersect in nothing at all.
        road = LineString([_cell_center(7, c) for c in (0, 4, 10, 14)])
        canal = LineString([_cell_center(7, 4), _cell_center(7, 10)])

        gdf, _, _ = _run(
            _roads([{"id": "t1", "geometry": road}]),
            _canals([{"id": "c1", "geometry": canal}]),
            fd,
            fa,
        )

        canal_rows = gdf[gdf["tipo"] == "canal"]
        assert len(canal_rows) == 1
        row = canal_rows.iloc[0]
        assert row.geometry.geom_type == "Point"
        assert row["confianza"] == "baja"
        assert row["nota"] and "m" in row["nota"]

        expected = _cell_center(7, 7)
        got = gdf[gdf["tipo"] == "canal"].to_crs(UTM).iloc[0].geometry
        assert got.x == pytest.approx(expected[0], abs=CELL)

    def test_an_empty_intersection_yields_no_row(self, tmp_path):
        shape = (15, 15)
        fd = _write_raster(tmp_path / "fd_no.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa_no.tif", np.full(shape, 100.0))

        road = _road_along_row(2, 0, 5)
        canal = _road_along_row(12, 8, 14)  # nowhere near it

        gdf, excluidos, _ = _run(
            _roads([{"id": "t1", "geometry": road}]),
            _canals([{"id": "c1", "geometry": canal}]),
            fd,
            fa,
        )

        assert len(gdf[gdf["tipo"] == "canal"]) == 0
        assert not [e for e in excluidos if e.get("canal_ref")]

    def test_an_unanticipated_intersection_type_raises_naming_both_ids(self):
        """Failing loudly beats a silent skip that quietly loses crossings.

        Exercised on the decomposer directly. Line×line intersection cannot
        actually produce a polygonal result, so this branch is a defensive guard
        against a geometry neither this design nor PostGIS's documented return
        set anticipated — and a guard whose behaviour is never asserted is a
        guard nobody can rely on.
        """
        from shapely.geometry import Polygon

        blob = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])

        with pytest.raises(CruceDerivationError) as exc:
            _decompose_intersection(blob, "t_road", "c_blob")

        message = str(exc.value)
        assert "t_road" in message and "c_blob" in message
        assert "Polygon" in message

    def test_a_polygonal_canal_clips_to_a_line_and_is_treated_as_an_overlap(self, tmp_path):
        """Not an error — a LineString result IS an anticipated shape.

        Recorded because it is the near-miss of the rule above: a road crossing
        a polygonal geometry yields the clipped LINE, which the overlap rule
        already covers. The hard error is reserved for a result that is neither
        point-like nor line-like.
        """
        from shapely.geometry import Polygon

        shape = (15, 15)
        fd = _write_raster(tmp_path / "fd_poly.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa_poly.tif", np.full(shape, 100.0))

        centre = _cell_center(7, 7)
        blob = Polygon(
            [
                (centre[0] - 200, centre[1] - 200),
                (centre[0] + 200, centre[1] - 200),
                (centre[0] + 200, centre[1] + 200),
                (centre[0] - 200, centre[1] + 200),
            ]
        )

        gdf, _, _ = _run(
            _roads([{"id": "t_road", "geometry": _road_along_row(7, 0, 14)}]),
            _canals([{"id": "c_blob", "geometry": blob}]),
            fd,
            fa,
        )

        canal_rows = gdf[gdf["tipo"] == "canal"]
        assert len(canal_rows) == 1
        assert canal_rows.iloc[0].geometry.geom_type == "Point"
        assert canal_rows.iloc[0]["confianza"] == "baja"


# ---------------------------------------------------------------------------
# 2.16 — the CRS contract
# ---------------------------------------------------------------------------


class TestCrsContract:
    """A hardcoded CRS tag is not a reprojection.

    ``calculations_hydrology_support.py:120-122`` stamps ``crs="EPSG:4326"`` on
    a frame built in raster space; a UTM point labelled 4326 lands in the Gulf of
    Guinea. These tests fail if this code repeats that.
    """

    def test_returned_geometry_is_really_in_4326(self, tmp_path):
        shape = (9, 9)
        acc = np.full(shape, 100.0)
        acc[4, 4] = 6000.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(4, 0, 8)}])

        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        assert gdf.crs is not None and gdf.crs.to_epsg() == 4326
        point = gdf.iloc[0].geometry
        assert -180.0 <= point.x <= 180.0
        assert -90.0 <= point.y <= 90.0
        # Argentina, not the Gulf of Guinea: a stamped UTM easting of ~400 000
        # would fail the longitude bound above, and 6 400 000 the latitude one.
        assert -75.0 < point.x < -50.0
        assert -40.0 < point.y < -20.0

    def test_azimuths_stay_utm_grid_and_are_not_reprojected(self, tmp_path):
        """Grid north, written down so nobody later "corrects" it."""
        shape = (9, 9)
        acc = np.full(shape, 100.0)
        acc[4, 4] = 6000.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(4, 0, 8)}])

        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        row = gdf.iloc[0]
        assert float(row["direccion_flujo_deg"]) == pytest.approx(0.0, abs=1e-9)
        assert float(row["rumbo_camino_deg"]) == pytest.approx(90.0, abs=1.0)

    def test_metric_work_happens_in_utm_not_in_degrees(self, tmp_path):
        """The ``:89`` defect: buffering an EPSG:4326 frame by "50" means 50 DEGREES.

        If separation were measured in degrees, 90 "metres" would be a distance
        larger than the planet and every candidate on the road would collapse
        into one. Two ridges 240 m apart surviving is the proof it did not.
        """
        shape = (9, 15)
        acc = np.full(shape, 100.0)
        acc[4, 3] = 8000.0
        acc[4, 11] = 6000.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        roads = _roads([{"id": "t1", "geometry": _road_along_row(4, 0, 14)}])

        gdf, _, _ = _run(roads, _canals([]), fd, fa)

        assert len(gdf) == 2


# ---------------------------------------------------------------------------
# Ranking scope and the recorded parameters
# ---------------------------------------------------------------------------


class TestRankingAndParameters:
    def test_rank_is_dense_over_flujo_natural_rows_only(self, tmp_path):
        shape = (15, 21)
        acc = np.full(shape, 100.0)
        acc[7, 3] = 9000.0
        acc[7, 11] = 7000.0
        acc[7, 19] = 5000.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)
        road = _road_along_row(7, 0, 20)
        canal = _road_along_col(15, 0, 14)

        gdf, _, _ = _run(
            _roads([{"id": "t1", "geometry": road}]),
            _canals([{"id": "c1", "geometry": canal}]),
            fd,
            fa,
        )

        natural = gdf[gdf["tipo"] == "flujo_natural"].sort_values("orden_ranking")
        assert list(natural["orden_ranking"]) == [1, 2, 3]
        assert list(natural["area_aporte_ha"]) == sorted(natural["area_aporte_ha"], reverse=True)
        assert gdf[gdf["tipo"] == "canal"]["orden_ranking"].isna().all()

    def test_the_five_parameters_are_recorded_verbatim(self, tmp_path):
        shape = (9, 9)
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", np.full(shape, 100.0))
        roads = _roads([{"id": "t1", "geometry": _road_along_row(4, 0, 8)}])

        _, _, parametros = _run(roads, _canals([]), fd, fa)

        for key, value in SEEDS.items():
            assert parametros[key] == value
        assert "segmentos_parcialmente_cubiertos" in parametros

    def test_partially_covered_segments_are_counted(self, tmp_path):
        """A crossing near the raster edge can be missed; the count says so."""
        shape = (9, 9)
        acc = np.full(shape, 100.0)
        acc[4, 4] = 6000.0
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", acc)

        inside = {"id": "t_in", "geometry": _road_along_row(4, 0, 8)}
        # Runs off the eastern edge of the 9-column raster.
        start = _cell_center(6, 4)
        straddling = {
            "id": "t_out",
            "geometry": LineString([start, (start[0] + 20 * CELL, start[1])]),
        }

        _, _, parametros = _run(_roads([inside, straddling]), _canals([]), fd, fa)

        assert parametros["segmentos_parcialmente_cubiertos"] == 1

    def test_a_segment_leaving_by_the_west_is_counted_too(self, tmp_path):
        """North and west put rows/cols NEGATIVE, which the bound test drops."""
        shape = (9, 9)
        fd = _write_raster(tmp_path / "fd.tif", _flow_dir_all(4, shape))
        fa = _write_raster(tmp_path / "fa.tif", np.full(shape, 100.0))

        start = _cell_center(4, 2)
        west = {"id": "t_w", "geometry": LineString([start, (start[0] - 20 * CELL, start[1])])}

        _, _, parametros = _run(_roads([west]), _canals([]), fd, fa)

        assert parametros["segmentos_parcialmente_cubiertos"] == 1


# ---------------------------------------------------------------------------
# Law 1 and Law 2 — proving checks, executable
# ---------------------------------------------------------------------------


class TestLaws:
    def test_the_derivation_invokes_no_whiteboxtools_tool(self):
        import inspect

        from app.domains.geo.intelligence import calculations_hydrology_support as module

        source = inspect.getsource(module.detectar_cruces_camino_flujo_impl)
        assert "get_wbt" not in source, "Law 1 — this change invokes no WBT tool at all"

    def test_the_derivation_reads_no_burned_or_drainage_product(self):
        """Law 2, checked against the CODE, not against the prose.

        The docstring names ``drainage`` precisely to say it is not used — that
        explanation is the opposite of a violation, and a grep that cannot tell
        the two apart would push the reason for the rule out of the file that
        obeys it. So the docstring is stripped and the executable body checked.
        """
        import ast
        import inspect

        from app.domains.geo.intelligence import calculations_hydrology_support as module

        tree = ast.parse(inspect.getsource(module.detectar_cruces_camino_flujo_impl).lstrip())
        function = tree.body[0]
        body = function.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        executable = "\n".join(ast.unparse(node) for node in body)

        for forbidden in ("drainage", "filled_hydro", "dem_burned"):
            assert forbidden not in executable, (
                f"Law 2 — a burned/fictional product ({forbidden}) never feeds this"
            )
