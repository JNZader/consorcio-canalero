"""Unit tests for intelligence/calculations.py — covering uncovered functions.

Tests HCI, conflict detection, runoff simulation, zonification helpers,
canal priority, road risk, terrain classification, cost surface, cost distance,
and least-cost path. All rasterio/geopandas/shapely mocked.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# a) HCI — calcular_indice_criticidad_hidrica
# ---------------------------------------------------------------------------


class TestHCI:
    def test_default_weights(self):
        from app.domains.geo.intelligence.calculations import calcular_indice_criticidad_hidrica

        result = calcular_indice_criticidad_hidrica(
            pendiente=0.5, acumulacion=0.5, twi=0.5, dist_canal=0.5, hist_inundacion=0.5,
        )
        assert result == 50.0

    def test_all_zeros(self):
        from app.domains.geo.intelligence.calculations import calcular_indice_criticidad_hidrica

        result = calcular_indice_criticidad_hidrica(0, 0, 0, 0, 0)
        assert result == 0.0

    def test_all_ones(self):
        from app.domains.geo.intelligence.calculations import calcular_indice_criticidad_hidrica

        result = calcular_indice_criticidad_hidrica(1, 1, 1, 1, 1)
        assert result == 100.0

    def test_custom_weights(self):
        from app.domains.geo.intelligence.calculations import calcular_indice_criticidad_hidrica

        weights = {"pendiente": 1.0, "acumulacion": 0, "twi": 0, "dist_canal": 0, "hist_inundacion": 0}
        result = calcular_indice_criticidad_hidrica(
            pendiente=0.8, acumulacion=0, twi=0, dist_canal=0, hist_inundacion=0,
            pesos=weights,
        )
        assert result == 80.0

    def test_clamps_above_100(self):
        from app.domains.geo.intelligence.calculations import calcular_indice_criticidad_hidrica

        weights = {"pendiente": 2.0, "acumulacion": 0, "twi": 0, "dist_canal": 0, "hist_inundacion": 0}
        result = calcular_indice_criticidad_hidrica(
            pendiente=1.0, acumulacion=0, twi=0, dist_canal=0, hist_inundacion=0,
            pesos=weights,
        )
        assert result == 100.0


class TestClasificarNivelRiesgo:
    def test_critico(self):
        from app.domains.geo.intelligence.calculations import clasificar_nivel_riesgo
        assert clasificar_nivel_riesgo(80) == "critico"

    def test_alto(self):
        from app.domains.geo.intelligence.calculations import clasificar_nivel_riesgo
        assert clasificar_nivel_riesgo(60) == "alto"

    def test_medio(self):
        from app.domains.geo.intelligence.calculations import clasificar_nivel_riesgo
        assert clasificar_nivel_riesgo(30) == "medio"

    def test_bajo(self):
        from app.domains.geo.intelligence.calculations import clasificar_nivel_riesgo
        assert clasificar_nivel_riesgo(10) == "bajo"

    def test_boundary_75(self):
        from app.domains.geo.intelligence.calculations import clasificar_nivel_riesgo
        assert clasificar_nivel_riesgo(75) == "critico"

    def test_boundary_50(self):
        from app.domains.geo.intelligence.calculations import clasificar_nivel_riesgo
        assert clasificar_nivel_riesgo(50) == "alto"

    def test_boundary_25(self):
        from app.domains.geo.intelligence.calculations import clasificar_nivel_riesgo
        assert clasificar_nivel_riesgo(25) == "medio"


# ---------------------------------------------------------------------------
# b) Conflict detection helpers
# ---------------------------------------------------------------------------


class TestClasificarSeveridadConflicto:
    def test_alta_high_accumulation(self):
        from app.domains.geo.intelligence.calculations import _clasificar_severidad_conflicto
        assert _clasificar_severidad_conflicto(6000, 3.0) == "alta"

    def test_alta_very_low_slope(self):
        from app.domains.geo.intelligence.calculations import _clasificar_severidad_conflicto
        assert _clasificar_severidad_conflicto(1000, 0.3) == "alta"

    def test_media(self):
        from app.domains.geo.intelligence.calculations import _clasificar_severidad_conflicto
        assert _clasificar_severidad_conflicto(3000, 3.0) == "media"

    def test_baja(self):
        from app.domains.geo.intelligence.calculations import _clasificar_severidad_conflicto
        assert _clasificar_severidad_conflicto(1000, 3.0) == "baja"


try:
    import geopandas as _gpd
    import rasterio as _rio
    _HAS_GEO_DEPS = True
except ImportError:
    _HAS_GEO_DEPS = False

_skip_geo = pytest.mark.skipif(not _HAS_GEO_DEPS, reason="geopandas/rasterio not installed")


@_skip_geo
class TestDetectarPuntosConflicto:
    def test_empty_gdfs_return_empty(self):
        """When all GDFs are empty, returns empty GeoDataFrame."""
        import geopandas as gpd
        from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto

        empty_gdf = gpd.GeoDataFrame(columns=["geometry"], geometry="geometry")

        mock_src = MagicMock()
        mock_src.read.return_value = np.zeros((10, 10))
        mock_src.transform = MagicMock()
        mock_src.__enter__ = MagicMock(return_value=mock_src)
        mock_src.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_src):
            result = detectar_puntos_conflicto(
                canales_gdf=empty_gdf,
                caminos_gdf=empty_gdf,
                drenajes_gdf=empty_gdf,
                flow_acc_path="/fake/fa.tif",
                slope_path="/fake/slope.tif",
            )

            assert len(result) == 0


# ---------------------------------------------------------------------------
# c) Runoff simulation
# ---------------------------------------------------------------------------


@_skip_geo
class TestSimularEscorrentia:
    def test_point_outside_raster_returns_error(self):
        from app.domains.geo.intelligence.calculations import simular_escorrentia

        # rasterio is imported lazily INSIDE the function, so we must patch
        # rasterio.open (and rasterio.transform.rowcol) in sys.modules — not
        # as a calculations module-level attribute.
        mock_fd_src = MagicMock()
        mock_fd_src.read.return_value = np.zeros((10, 10), dtype=np.int32)
        mock_fd_src.transform = MagicMock()
        mock_fd_src.nodata = None
        mock_fd_src.__enter__ = MagicMock(return_value=mock_fd_src)
        mock_fd_src.__exit__ = MagicMock(return_value=False)

        mock_fa_src = MagicMock()
        mock_fa_src.read.return_value = np.zeros((10, 10))
        mock_fa_src.__enter__ = MagicMock(return_value=mock_fa_src)
        mock_fa_src.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", side_effect=[mock_fd_src, mock_fa_src]):
            with patch("rasterio.transform.rowcol", side_effect=Exception("outside")):
                result = simular_escorrentia(
                    "/fake/fd.tif", "/fake/fa.tif",
                    punto_inicio=(-999, -999),
                    lluvia_mm=50,
                )

                assert result["features"] == []
                assert "error" in result.get("properties", {})


class TestEmptyRunoffGeojson:
    def test_returns_proper_structure(self):
        from app.domains.geo.intelligence.calculations import _empty_runoff_geojson

        result = _empty_runoff_geojson((1.0, 2.0), 50.0, "test error")

        assert result["type"] == "FeatureCollection"
        assert result["features"] == []
        assert result["properties"]["error"] == "test error"
        assert result["properties"]["lluvia_mm"] == 50.0


# ---------------------------------------------------------------------------
# d) Canal priority
# ---------------------------------------------------------------------------


class TestCalcularPrioridadCanal:
    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_returns_zero_when_no_values(self, mock_sample):
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal

        mock_sample.return_value = []
        result = calcular_prioridad_canal(MagicMock(), "/fake/fa.tif", "/fake/slope.tif")
        assert result == 0.0

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_computes_score_without_critical_zones(self, mock_sample):
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal

        mock_sample.side_effect = [
            [5000, 8000, 3000],  # flow_acc
            [3.0, 5.0, 7.0],    # slope
        ]

        result = calcular_prioridad_canal(MagicMock(), "/fake/fa.tif", "/fake/slope.tif")
        assert 0 <= result <= 100

    @_skip_geo
    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_computes_score_with_critical_zones(self, mock_sample):
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal
        import geopandas as gpd
        from shapely.geometry import LineString, Point

        mock_sample.side_effect = [
            [5000, 8000],  # flow_acc
            [3.0, 5.0],   # slope
        ]

        # Must be a real Shapely geometry — GeoSeries.distance() cannot accept
        # a MagicMock and will raise a TypeError.
        canal_geom = LineString([(0, 0), (0.001, 0.001)])
        zonas = gpd.GeoDataFrame(
            {"geometry": [Point(0, 0)]},
            geometry="geometry",
        )

        result = calcular_prioridad_canal(
            canal_geom, "/fake/fa.tif", "/fake/slope.tif",
            zonas_criticas_gdf=zonas,
        )
        assert 0 <= result <= 100


# ---------------------------------------------------------------------------
# e) Road risk
# ---------------------------------------------------------------------------


class TestCalcularRiesgoCamino:
    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_returns_zero_when_no_values(self, mock_sample):
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino

        mock_sample.return_value = []
        result = calcular_riesgo_camino(MagicMock(), "/fake/fa.tif", "/fake/slope.tif", "/fake/twi.tif")
        assert result == 0.0

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_computes_score_without_drainage(self, mock_sample):
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino

        mock_sample.side_effect = [
            [5000, 8000],  # flow_acc
            [1.0, 2.0],   # slope (low = high risk)
            [12.0, 14.0], # twi (high = bad)
        ]

        result = calcular_riesgo_camino(MagicMock(), "/fake/fa.tif", "/fake/slope.tif", "/fake/twi.tif")
        assert 0 <= result <= 100

    @_skip_geo
    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_computes_score_with_drainage(self, mock_sample):
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino
        import geopandas as gpd
        from shapely.geometry import LineString, Point

        mock_sample.side_effect = [
            [5000],    # flow_acc
            [1.0],     # slope
            [12.0],    # twi
        ]

        drainage = gpd.GeoDataFrame(
            {"geometry": [Point(0, 0)]},
            geometry="geometry",
        )

        # Must be a real Shapely geometry — GeoSeries.distance() cannot accept
        # a MagicMock and will raise a TypeError.
        camino_geom = LineString([(0, 0), (0.001, 0.001)])
        result = calcular_riesgo_camino(
            camino_geom, "/fake/fa.tif", "/fake/slope.tif", "/fake/twi.tif",
            drainage_gdf=drainage,
        )
        assert 0 <= result <= 100


# ---------------------------------------------------------------------------
# f) Dynamic terrain classification
# ---------------------------------------------------------------------------


class TestClasificarTerrenoDinamico:
    def test_all_none_returns_empty(self):
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        result = clasificar_terreno_dinamico(None, None, None)
        assert result["clases"] == {}
        assert result["estadisticas"] == {}

    def test_sar_only_classifies_water(self):
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        sar = np.array([[-20, -10], [-16, -5]])  # -20, -16 are water
        result = clasificar_terreno_dinamico(sar, None, None)

        assert "clasificacion" in result
        stats = result["estadisticas"]
        assert stats["agua"]["pixeles"] == 2

    def test_optical_classifies_vegetation(self):
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        ndvi = np.array([[0.6, 0.3], [0.1, -0.2]])
        result = clasificar_terreno_dinamico(None, ndvi, None)

        stats = result["estadisticas"]
        assert stats["vegetacion_densa"]["pixeles"] == 1
        assert stats["vegetacion_rala"]["pixeles"] == 1
        assert stats["suelo_desnudo"]["pixeles"] == 1

    def test_combined_sar_and_optical(self):
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        sar = np.array([[-20, -10]])
        ndvi = np.array([[0.6, 0.6]])
        result = clasificar_terreno_dinamico(sar, ndvi, None)

        stats = result["estadisticas"]
        # SAR water takes priority over NDVI
        assert stats["agua"]["pixeles"] == 1
        # Second pixel: not water by SAR, dense veg by NDVI
        assert stats["vegetacion_densa"]["pixeles"] == 1

    def test_percentages_sum_to_100(self):
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        sar = np.array([[-20, -10, -5, -8]])
        result = clasificar_terreno_dinamico(sar, None, None)

        total_pct = sum(s["porcentaje"] for s in result["estadisticas"].values())
        assert total_pct == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# g) Cost surface generation
# ---------------------------------------------------------------------------


class TestGenerateCostSurface:
    def test_file_not_found(self):
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        with pytest.raises(FileNotFoundError):
            generate_cost_surface("/nonexistent/slope.tif", "/out/cost.tif")

    @_skip_geo
    def test_generates_cost_surface(self, tmp_path):
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_path = str(tmp_path / "slope.tif")
        output_path = str(tmp_path / "cost.tif")
        Path(slope_path).touch()

        slope_data = np.array([[0.0, 5.0], [10.0, 15.0]], dtype=np.float64)
        mock_src = MagicMock()
        mock_src.read.return_value = slope_data
        mock_src.nodata = None
        mock_src.meta = {"driver": "GTiff", "dtype": "float32", "count": 1}
        mock_src.__enter__ = MagicMock(return_value=mock_src)
        mock_src.__exit__ = MagicMock(return_value=False)

        mock_dst = MagicMock()
        mock_dst.__enter__ = MagicMock(return_value=mock_dst)
        mock_dst.__exit__ = MagicMock(return_value=False)

        # rasterio is imported lazily inside the function; patch sys.modules entry.
        with patch("rasterio.open", side_effect=[mock_src, mock_dst]):
            result = generate_cost_surface(slope_path, output_path)
            assert result == output_path

    @_skip_geo
    def test_all_nodata_raises_value_error(self, tmp_path):
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_path = str(tmp_path / "slope.tif")
        output_path = str(tmp_path / "cost.tif")
        Path(slope_path).touch()

        slope_data = np.array([[-9999.0, -9999.0]], dtype=np.float64)
        mock_src = MagicMock()
        mock_src.read.return_value = slope_data
        mock_src.nodata = -9999.0
        mock_src.meta = {"driver": "GTiff", "dtype": "float32", "count": 1}
        mock_src.__enter__ = MagicMock(return_value=mock_src)
        mock_src.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_src):
            with pytest.raises(ValueError, match="only nodata"):
                generate_cost_surface(slope_path, output_path)


# ---------------------------------------------------------------------------
# h) _sample_raster_along_line
# ---------------------------------------------------------------------------


class TestSampleRasterAlongLine:
    def test_none_geometry_returns_empty(self):
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line

        result = _sample_raster_along_line(None, "/fake.tif")
        assert result == []

    def test_empty_geometry_returns_empty(self):
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        empty = LineString()
        result = _sample_raster_along_line(empty, "/fake.tif")
        assert result == []

    @_skip_geo
    def test_samples_along_line(self):
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        line = LineString([(0, 0), (1, 1)])

        mock_src = MagicMock()
        mock_src.read.return_value = np.ones((100, 100)) * 42.0
        mock_src.nodata = None
        mock_src.transform = MagicMock()
        mock_src.__enter__ = MagicMock(return_value=mock_src)
        mock_src.__exit__ = MagicMock(return_value=False)

        # rasterio and rowcol are both imported lazily inside the function.
        # Patch sys.modules entries so the in-function imports pick up the mocks.
        with patch("rasterio.open", return_value=mock_src), \
             patch("rasterio.transform.rowcol", return_value=(5, 5)):
            result = _sample_raster_along_line(line, "/fake.tif", num_points=5)
            assert len(result) > 0


# ---------------------------------------------------------------------------
# i) Coverage gap detection
# ---------------------------------------------------------------------------


class TestDetectCoverageGaps:
    def test_no_canal_geometries_returns_empty(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
            hci_scores={"z1": 90.0},
            canal_geometries=[],
        )
        assert result == []

    def test_hci_below_threshold_skipped(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps
        from shapely.geometry import Point, LineString

        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": Point(0, 0)}],
            hci_scores={"z1": 30.0},
            canal_geometries=[{"geometry": LineString([(10, 10), (11, 11)])}],
            hci_threshold=50.0,
        )
        assert result == []

    def test_close_canal_not_flagged(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps
        from shapely.geometry import Point, LineString

        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": Point(0, 0)}],
            hci_scores={"z1": 90.0},
            canal_geometries=[{"geometry": LineString([(0, 0), (0.001, 0.001)])}],
            threshold_km=2.0,
        )
        assert result == []

    def test_detects_gap_critico(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps
        from shapely.geometry import Point, LineString

        # Distance ~111km (1 degree)
        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": Point(0, 0)}],
            hci_scores={"z1": 85.0},
            canal_geometries=[{"geometry": LineString([(1, 1), (1.1, 1.1)])}],
            threshold_km=2.0,
            hci_threshold=50.0,
        )
        assert len(result) == 1
        assert result[0]["severity"] == "critico"

    def test_detects_gap_alto(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps
        from shapely.geometry import Point, LineString

        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": Point(0, 0)}],
            hci_scores={"z1": 65.0},
            canal_geometries=[{"geometry": LineString([(0.05, 0.05), (0.06, 0.06)])}],
            threshold_km=2.0,
            hci_threshold=50.0,
        )
        assert len(result) == 1
        assert result[0]["severity"] == "alto"

    def test_sorts_by_severity_then_hci(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps
        from shapely.geometry import Point, LineString

        result = detect_coverage_gaps(
            zones=[
                {"id": "z1", "geometry": Point(0, 0)},
                {"id": "z2", "geometry": Point(0.5, 0.5)},
            ],
            hci_scores={"z1": 85.0, "z2": 65.0},
            canal_geometries=[{"geometry": LineString([(2, 2), (2.1, 2.1)])}],
            threshold_km=2.0,
            hci_threshold=50.0,
        )
        assert len(result) == 2
        assert result[0]["severity"] == "critico"

    def test_geojson_dict_geometries_accepted(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
            hci_scores={"z1": 90.0},
            canal_geometries=[{"geometry": {"type": "LineString", "coordinates": [[1, 1], [1.1, 1.1]]}}],
            threshold_km=2.0,
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# j) Maintenance priority
# ---------------------------------------------------------------------------


class TestComputeMaintenancePriority:
    def test_empty_inputs_returns_empty(self):
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        result = compute_maintenance_priority({}, {}, {}, {})
        assert result == []

    def test_single_node_all_factors(self):
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        result = compute_maintenance_priority(
            centrality_scores={1: 0.5},
            flow_acc_scores={1: 5000.0},
            hci_scores={"1": 60.0},
            conflict_counts={1: 3},
        )
        assert len(result) == 1
        assert 0 <= result[0]["composite_score"] <= 1
        assert result[0]["missing_factors"] is None

    def test_missing_factors_tracked(self):
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        result = compute_maintenance_priority(
            centrality_scores={1: 0.5},
            flow_acc_scores={},
            hci_scores={},
            conflict_counts={},
        )
        assert len(result) == 1
        assert "flow_acc" in result[0]["missing_factors"]
        assert "upstream_hci" in result[0]["missing_factors"]
        assert "conflict_count" in result[0]["missing_factors"]

    def test_multiple_nodes_sorted_descending(self):
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        result = compute_maintenance_priority(
            centrality_scores={1: 0.1, 2: 0.9},
            flow_acc_scores={1: 1000, 2: 9000},
            hci_scores={"1": 20.0, "2": 80.0},
            conflict_counts={1: 1, 2: 5},
        )
        assert len(result) == 2
        assert result[0]["composite_score"] >= result[1]["composite_score"]

    def test_weight_redistribution(self):
        """When some factors are missing, weights should be redistributed."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        # Need at least 2 nodes so min/max normalization produces non-zero values
        result = compute_maintenance_priority(
            centrality_scores={1: 1.0, 2: 0.0},
            flow_acc_scores={},
            hci_scores={},
            conflict_counts={},
        )
        # Node 1 has max centrality, node 2 has min -> node 1 score should be ~1.0
        node1 = next(r for r in result if r["node_id"] == 1)
        assert node1["composite_score"] == pytest.approx(1.0, abs=0.01)
        assert "flow_acc" in node1["missing_factors"]

    def test_node_with_no_available_factors_skipped(self):
        """A node that appears only in hci_scores with non-digit key is skipped."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        result = compute_maintenance_priority(
            centrality_scores={},
            flow_acc_scores={},
            hci_scores={"abc": 50.0},  # non-digit key, won't be in all_ids
            conflict_counts={},
        )
        assert result == []


# ---------------------------------------------------------------------------
# k) Rank canal hotspots
# ---------------------------------------------------------------------------


class TestRankCanalHotspots:
    def test_file_not_found(self):
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        with pytest.raises(FileNotFoundError):
            rank_canal_hotspots(
                [{"geometry": MagicMock()}],
                "/nonexistent/flow_acc.tif",
            )

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_empty_canals_returns_empty(self, mock_sample, tmp_path):
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fa_path = str(tmp_path / "fa.tif")
        Path(fa_path).touch()

        result = rank_canal_hotspots([], fa_path)
        assert result == []

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_ranks_by_flow_acc_max(self, mock_sample, tmp_path):
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots
        from shapely.geometry import LineString

        fa_path = str(tmp_path / "fa.tif")
        Path(fa_path).touch()

        mock_sample.side_effect = [
            [100, 200],   # canal 0
            [500, 1000],  # canal 1
            [300, 400],   # canal 2
        ]

        canals = [
            {"geometry": LineString([(0, 0), (1, 1)])},
            {"geometry": LineString([(2, 2), (3, 3)])},
            {"geometry": LineString([(4, 4), (5, 5)])},
        ]

        result = rank_canal_hotspots(canals, fa_path)

        assert len(result) == 3
        assert result[0]["flow_acc_max"] >= result[1]["flow_acc_max"]
        # All should have risk_level
        for r in result:
            assert r["risk_level"] in ("critico", "alto", "medio", "bajo")

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_handles_geojson_dict_geometry(self, mock_sample, tmp_path):
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fa_path = str(tmp_path / "fa.tif")
        Path(fa_path).touch()

        mock_sample.return_value = [100, 200]

        canals = [
            {"geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}},
        ]

        result = rank_canal_hotspots(canals, fa_path)
        assert len(result) == 1

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_skips_none_geometry(self, mock_sample, tmp_path):
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fa_path = str(tmp_path / "fa.tif")
        Path(fa_path).touch()

        canals = [{"geometry": None}]
        result = rank_canal_hotspots(canals, fa_path)
        assert result == []
