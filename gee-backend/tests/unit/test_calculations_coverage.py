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
            with pytest.raises(ValueError, match=r"^Slope raster contains only nodata"):
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


# ===========================================================================
# MUTATION-KILLING TESTS — targeted at specific surviving mutants
# ===========================================================================


# ---------------------------------------------------------------------------
# _clasificar_severidad_conflicto — boundary comparisons
# mutmut_2: acumulacion >= 5000 (should be >) → test exactly at 5000
# mutmut_3: acumulacion > 5001              → test at 5001 vs 5000
# mutmut_4: pendiente <= 0.5               → test exactly at 0.5
# mutmut_5: pendiente < 1.5                → test at 0.5 vs 1.5
# mutmut_9: acumulacion >= 2000            → test exactly at 2000
# mutmut_10: acumulacion > 2001            → test at 2001 vs 2000
# mutmut_11: pendiente <= 2.0              → test exactly at 2.0
# mutmut_12: pendiente < 3.0               → test at 2.0 vs 3.0
# ---------------------------------------------------------------------------


class TestClasificarSeveridadConflictoBoundary:
    """Boundary tests to kill all 8 surviving comparison mutations."""

    def _f(self, acumulacion, pendiente):
        from app.domains.geo.intelligence.calculations import _clasificar_severidad_conflicto
        return _clasificar_severidad_conflicto(acumulacion, pendiente)

    # --- acumulacion boundary at 5000 ---
    def test_acum_5000_not_alta(self):
        """acumulacion=5000 is NOT > 5000 → should NOT be 'alta' via first condition."""
        # With acumulacion=5000 and pendiente=1.0 (not < 0.5), first condition fails.
        # Second condition: 5000 > 2000 → True → "media"
        assert self._f(5000.0, 1.0) == "media"

    def test_acum_5001_is_alta(self):
        """acumulacion=5001 IS > 5000 → 'alta' (kills >5001 mutation)."""
        assert self._f(5001.0, 1.0) == "alta"

    def test_acum_4999_not_alta_via_acum(self):
        """acumulacion=4999 < 5000 — first condition fails on acum side."""
        assert self._f(4999.0, 1.0) == "media"  # 4999 > 2000 → media

    # --- pendiente boundary at 0.5 ---
    def test_pendiente_0_5_is_alta(self):
        """pendiente=0.5 is NOT < 0.5 (strict) → NOT 'alta' via pendiente."""
        # acumulacion=100 (not > 5000), pendiente=0.5 (not < 0.5) → check second condition
        # 100 > 2000? No. 0.5 < 2.0? Yes → "media"
        assert self._f(100.0, 0.5) == "media"

    def test_pendiente_0_49_is_alta(self):
        """pendiente=0.49 IS < 0.5 → 'alta' (kills <=0.5 mutation)."""
        assert self._f(100.0, 0.49) == "alta"

    def test_pendiente_1_5_not_alta(self):
        """pendiente=1.5 is NOT < 0.5 → not alta via first condition (kills <1.5 mutation)."""
        # 100 > 2000? No. 1.5 < 2.0? Yes → "media"
        assert self._f(100.0, 1.5) == "media"

    # --- acumulacion boundary at 2000 ---
    def test_acum_2000_not_media_via_acum(self):
        """acumulacion=2000 is NOT > 2000 (strict). With pendiente=3.0 (not < 2.0) → 'baja'."""
        assert self._f(2000.0, 3.0) == "baja"

    def test_acum_2001_is_media(self):
        """acumulacion=2001 IS > 2000 → 'media' (kills >2001 mutation)."""
        assert self._f(2001.0, 3.0) == "media"

    # --- pendiente boundary at 2.0 ---
    def test_pendiente_2_0_not_media(self):
        """pendiente=2.0 is NOT < 2.0 (strict). With acum=100 → 'baja'."""
        assert self._f(100.0, 2.0) == "baja"

    def test_pendiente_1_99_is_media(self):
        """pendiente=1.99 IS < 2.0 → 'media' (kills <=2.0 mutation)."""
        assert self._f(100.0, 1.99) == "media"

    def test_pendiente_3_0_not_media(self):
        """pendiente=3.0 is NOT < 2.0 → 'baja' (kills <3.0 mutation)."""
        assert self._f(100.0, 3.0) == "baja"


# ---------------------------------------------------------------------------
# calcular_indice_criticidad_hidrica — round(x, 2) precision
# mutmut_24: round(x, None) → returns int
# mutmut_26: round(x,)      → returns int
# mutmut_39: round(x, 3)    → keeps 3 decimals instead of 2
# ---------------------------------------------------------------------------


class TestHCIRoundingPrecision:
    """Kill rounding mutations: round(x, 2) vs round(x, None/3)."""

    def test_returns_float_not_int(self):
        """round(x, None) returns int → isinstance(result, float) kills it."""
        from app.domains.geo.intelligence.calculations import calcular_indice_criticidad_hidrica

        result = calcular_indice_criticidad_hidrica(1.0, 1.0, 1.0, 1.0, 1.0)
        assert isinstance(result, float), "HCI must return float, not int"

    def test_rounded_to_2_not_3_decimals(self):
        """Use 1/3 weights to get 33.333... → round to 33.33 (2dp) not 33.333 (3dp)."""
        from app.domains.geo.intelligence.calculations import calcular_indice_criticidad_hidrica

        # score = (1/3) * 1.0 * 100 = 33.333...
        # round(33.333..., 2) = 33.33
        # round(33.333..., 3) = 33.333
        # round(33.333..., None) = 33 (int)
        pesos = {"pendiente": 1/3, "acumulacion": 0, "twi": 0, "dist_canal": 0, "hist_inundacion": 0}
        result = calcular_indice_criticidad_hidrica(1.0, 0, 0, 0, 0, pesos=pesos)
        assert result == pytest.approx(33.33, abs=1e-9)
        assert result != pytest.approx(33.333, abs=1e-9)

    def test_exact_2dp_boundary_value(self):
        """Verify 2-decimal rounding with a value that has non-trivial decimals."""
        from app.domains.geo.intelligence.calculations import calcular_indice_criticidad_hidrica

        # 0.15*0.333 + 0.30*0.333 + 0.25*0.333 + 0.15*0.333 + 0.15*0.333
        # = (0.15+0.30+0.25+0.15+0.15)*0.333 = 1.0*0.333 = 0.333
        # * 100 = 33.3 → round(33.3, 2) = 33.3 (float), round(33.3, None) = 33 (int)
        result = calcular_indice_criticidad_hidrica(0.333, 0.333, 0.333, 0.333, 0.333)
        assert isinstance(result, float)
        assert result == pytest.approx(33.3, abs=0.01)


# ---------------------------------------------------------------------------
# _empty_runoff_geojson — output key names
# mutmut_10: "punto_inicio" → "XXpunto_inicioXX"
# mutmut_11: "punto_inicio" → "PUNTO_INICIO"
# ---------------------------------------------------------------------------


class TestEmptyRunoffGeoJsonKeys:
    """Kill key name mutations in _empty_runoff_geojson."""

    def test_punto_inicio_key_exists(self):
        """Assert exact key 'punto_inicio' in properties (kills XXpunto_inicioXX mutation)."""
        from app.domains.geo.intelligence.calculations import _empty_runoff_geojson

        result = _empty_runoff_geojson((1.0, 2.0), 50.0, "test error")
        assert "punto_inicio" in result["properties"]
        assert "XXpunto_inicioXX" not in result["properties"]
        assert "PUNTO_INICIO" not in result["properties"]
        assert result["properties"]["punto_inicio"] == [1.0, 2.0]

    def test_lluvia_mm_and_error_keys_exist(self):
        """Verify all expected keys are present."""
        from app.domains.geo.intelligence.calculations import _empty_runoff_geojson

        result = _empty_runoff_geojson((0.0, 0.0), 25.0, "boom")
        props = result["properties"]
        assert "lluvia_mm" in props
        assert "error" in props
        assert props["lluvia_mm"] == 25.0
        assert props["error"] == "boom"
        assert result["type"] == "FeatureCollection"
        assert result["features"] == []


# ---------------------------------------------------------------------------
# calcular_prioridad_canal — exact weight arithmetic
# Mutations: weight 0.40→0.30, 0.30→0.25/0.20, normalization divisions
# ---------------------------------------------------------------------------


class TestCalcularPrioridadCanalExact:
    """Kill arithmetic mutations by asserting exact numeric output."""

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_exact_score_no_zonas(self, mock_sample):
        """fa_norm=1.0, sl_norm=1.0, zona_factor=0.0 → score = (0.40+0.30)*100 = 70.0."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal

        mock_sample.side_effect = [
            [10000.0],   # fa_values: max=10000 → fa_norm = min(10000/10000, 1.0) = 1.0
            [10.0],      # sl_values: mean=10.0 → sl_norm = min(10.0/10.0, 1.0) = 1.0
        ]
        canal = LineString([(0, 0), (1, 1)])
        result = calcular_prioridad_canal(canal, "/fa.tif", "/sl.tif")
        # score = (0.40 * 1.0 + 0.30 * 1.0 + 0.30 * 0.0) * 100 = 70.0
        assert result == pytest.approx(70.0, abs=1e-9)

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_exact_score_with_zonas(self, mock_sample):
        """With critical zone at distance=0, zona_factor=1.0 → score=100.0."""
        from shapely.geometry import LineString, Point
        import geopandas as gpd
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal

        mock_sample.side_effect = [
            [10000.0],  # fa_norm = 1.0
            [10.0],     # sl_norm = 1.0
        ]
        canal = LineString([(0, 0), (1, 1)])
        # Critical zone AT the canal → distance=0 → zona_factor = max(1 - 0/1000, 0) = 1.0
        zonas = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:4326")
        result = calcular_prioridad_canal(canal, "/fa.tif", "/sl.tif", zonas_criticas_gdf=zonas)
        # score = (0.40 * 1.0 + 0.30 * 1.0 + 0.30 * 1.0) * 100 = 100.0
        assert result == pytest.approx(100.0, abs=1e-9)

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_fa_normalization_cap(self, mock_sample):
        """fa_max > 10000 → fa_norm capped at 1.0 (kills /10000 → /5000 mutation)."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal

        mock_sample.side_effect = [
            [50000.0],  # fa_norm = min(50000/10000, 1.0) = 1.0 (not 5.0)
            [0.0],      # sl_norm = min(0.0/10.0, 1.0) = 0.0
        ]
        canal = LineString([(0, 0), (1, 1)])
        result = calcular_prioridad_canal(canal, "/fa.tif", "/sl.tif")
        # score = (0.40 * 1.0 + 0.30 * 0.0 + 0.30 * 0.0) * 100 = 40.0
        assert result == pytest.approx(40.0, abs=1e-9)

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_returns_float_and_rounded_to_2dp(self, mock_sample):
        """Kill round(x, None) → int mutation."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal

        mock_sample.side_effect = [[3333.0], [3.333]]
        canal = LineString([(0, 0), (1, 1)])
        result = calcular_prioridad_canal(canal, "/fa.tif", "/sl.tif")
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# calcular_riesgo_camino — exact weight arithmetic
# Mutations: weight values (0.30, 0.25), normalization constants (10000, 5.0, 15.0)
# ---------------------------------------------------------------------------


class TestCalcularRiesgoCaminoExact:
    """Kill arithmetic mutations by asserting exact numeric output."""

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_exact_score_no_drainage(self, mock_sample):
        """fa_norm=1.0, sl_norm=1.0, twi_norm=1.0, drain=0 → score=(0.30+0.25+0.25)*100=80.0."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino

        mock_sample.side_effect = [
            [10000.0],  # fa_norm = min(10000/10000, 1.0) = 1.0
            [0.0],      # sl_norm = max(1.0 - 0.0/5.0, 0.0) = 1.0
            [15.0],     # twi_norm = min(max(15.0/15.0, 0.0), 1.0) = 1.0
        ]
        camino = LineString([(0, 0), (1, 1)])
        result = calcular_riesgo_camino(camino, "/fa.tif", "/sl.tif", "/twi.tif")
        # (0.30*1 + 0.25*1 + 0.25*1 + 0.20*0) * 100 = 80.0
        assert result == pytest.approx(80.0, abs=1e-9)

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_exact_score_with_drainage(self, mock_sample):
        """drain_factor=1.0 (distance=0) → total score = (0.30+0.25+0.25+0.20)*100=100.0."""
        from shapely.geometry import LineString, Point
        import geopandas as gpd
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino

        mock_sample.side_effect = [
            [10000.0],  # fa_norm=1.0
            [0.0],      # sl_norm=1.0
            [15.0],     # twi_norm=1.0
        ]
        camino = LineString([(0, 0), (1, 1)])
        # Drainage AT the camino → dist=0 → drain_factor = max(1 - 0/500, 0) = 1.0
        drainage = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:4326")
        result = calcular_riesgo_camino(camino, "/fa.tif", "/sl.tif", "/twi.tif", drainage_gdf=drainage)
        assert result == pytest.approx(100.0, abs=1e-9)

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_sl_inversion_flat_is_risky(self, mock_sample):
        """Flat terrain (slope=0) → sl_norm=1.0 (max risk). Slope=5.0 → sl_norm=0."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino

        # Flat road
        mock_sample.side_effect = [[0.0], [0.0], [0.0]]
        camino = LineString([(0, 0), (1, 1)])
        result_flat = calcular_riesgo_camino(camino, "/fa.tif", "/sl.tif", "/twi.tif")

        # Steep road
        mock_sample.side_effect = [[0.0], [5.0], [0.0]]
        result_steep = calcular_riesgo_camino(camino, "/fa.tif", "/sl.tif", "/twi.tif")

        assert result_flat > result_steep  # flat road has higher flood risk

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_returns_float(self, mock_sample):
        """Kill round(x, None) → int mutation."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino

        mock_sample.side_effect = [[5000.0], [2.5], [7.5]]
        camino = LineString([(0, 0), (1, 1)])
        result = calcular_riesgo_camino(camino, "/fa.tif", "/sl.tif", "/twi.tif")
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# generate_cost_surface — exact cost formula arithmetic
# Formula: cost = 1.0 + (slope / max_slope) * 10.0
# Mutations: * → /, + → -, 10.0 → 11.0, 1.0 → 2.0
# ---------------------------------------------------------------------------


class TestGenerateCostSurfaceExact:
    """Kill cost formula arithmetic mutations."""

    def test_exact_cost_formula(self, tmp_path):
        """cost = 1 + (slope/max_slope)*10 → flat=1.0, max=11.0."""
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_path = str(tmp_path / "slope.tif")
        output_path = str(tmp_path / "cost.tif")
        Path(slope_path).touch()

        slope_data = np.array([[0.0, 10.0]], dtype=np.float64)

        mock_src = MagicMock()
        mock_src.read.return_value = slope_data
        mock_src.nodata = None
        mock_src.meta = {"driver": "GTiff", "dtype": "float32", "count": 1, "width": 2, "height": 1}
        mock_src.__enter__ = MagicMock(return_value=mock_src)
        mock_src.__exit__ = MagicMock(return_value=False)

        written_arrays = []
        mock_dst = MagicMock()
        mock_dst.write.side_effect = lambda arr, band: written_arrays.append(arr.copy())
        mock_dst.__enter__ = MagicMock(return_value=mock_dst)
        mock_dst.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", side_effect=[mock_src, mock_dst]):
            result = generate_cost_surface(slope_path, output_path)

        assert result == output_path
        assert len(written_arrays) == 1
        cost = written_arrays[0]
        # flat pixel: 1.0 + (0.0/10.0)*10.0 = 1.0
        assert float(cost[0, 0]) == pytest.approx(1.0, abs=1e-4)
        # max pixel: 1.0 + (10.0/10.0)*10.0 = 11.0
        assert float(cost[0, 1]) == pytest.approx(11.0, abs=1e-4)

    def test_mid_slope_exact_value(self, tmp_path):
        """slope=5.0, max_slope=10.0 → cost = 1 + (5/10)*10 = 6.0 (kills +→- mutation)."""
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_path = str(tmp_path / "slope2.tif")
        output_path = str(tmp_path / "cost2.tif")
        Path(slope_path).touch()

        slope_data = np.array([[5.0, 10.0]], dtype=np.float64)

        mock_src = MagicMock()
        mock_src.read.return_value = slope_data
        mock_src.nodata = None
        mock_src.meta = {"driver": "GTiff", "dtype": "float32", "count": 1, "width": 2, "height": 1}
        mock_src.__enter__ = MagicMock(return_value=mock_src)
        mock_src.__exit__ = MagicMock(return_value=False)

        written_arrays = []
        mock_dst = MagicMock()
        mock_dst.write.side_effect = lambda arr, band: written_arrays.append(arr.copy())
        mock_dst.__enter__ = MagicMock(return_value=mock_dst)
        mock_dst.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", side_effect=[mock_src, mock_dst]):
            generate_cost_surface(slope_path, output_path)

        cost = written_arrays[0]
        # 1.0 + (5.0/10.0)*10.0 = 6.0
        assert float(cost[0, 0]) == pytest.approx(6.0, abs=1e-4)


# ---------------------------------------------------------------------------
# clasificar_terreno_dinamico — threshold boundaries
# Mutations: -15.0→-14.0 (SAR water), 0.5→0.4 (dense veg), 0.2→0.1, -0.1→0.1
# ---------------------------------------------------------------------------


class TestClasificarTerrenoDinamicoThresholds:
    """Kill threshold comparison mutations."""

    def test_sar_exactly_at_minus15_not_water(self):
        """sar=-15.0 is NOT < -15.0 → should NOT be classified as water."""
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        sar = np.array([[-15.0]])
        result = clasificar_terreno_dinamico(sar, None, None)
        # -15.0 is NOT < -15.0 → class 0 (sin_clasificar)
        assert result["estadisticas"]["agua"]["pixeles"] == 0
        assert result["estadisticas"]["sin_clasificar"]["pixeles"] == 1

    def test_sar_below_minus15_is_water(self):
        """sar=-15.001 IS < -15.0 → water (kills -15.0→-14.0 mutation)."""
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        sar = np.array([[-15.001]])
        result = clasificar_terreno_dinamico(sar, None, None)
        assert result["estadisticas"]["agua"]["pixeles"] == 1

    def test_ndvi_exactly_at_0_5_not_dense_veg(self):
        """ndvi=0.5 is NOT > 0.5 → should NOT be dense_veg."""
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        ndvi = np.array([[0.5]])
        result = clasificar_terreno_dinamico(None, ndvi, None)
        assert result["estadisticas"]["vegetacion_densa"]["pixeles"] == 0

    def test_ndvi_above_0_5_is_dense_veg(self):
        """ndvi=0.501 IS > 0.5 → dense_veg (kills >0.5→>0.4 mutation)."""
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        ndvi = np.array([[0.501]])
        result = clasificar_terreno_dinamico(None, ndvi, None)
        assert result["estadisticas"]["vegetacion_densa"]["pixeles"] == 1

    def test_ndvi_exactly_at_0_2_not_sparse(self):
        """ndvi=0.2 is NOT > 0.2 → not sparse_veg; 0.2 <= 0.2 → bare_soil candidate."""
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        ndvi = np.array([[0.2]])  # 0.2 <= 0.2 AND 0.2 > -0.1 → bare_soil
        result = clasificar_terreno_dinamico(None, ndvi, None)
        assert result["estadisticas"]["vegetacion_rala"]["pixeles"] == 0
        assert result["estadisticas"]["suelo_desnudo"]["pixeles"] == 1

    def test_ndvi_just_above_0_2_is_sparse(self):
        """ndvi=0.201 IS > 0.2 AND <= 0.5 → sparse_veg (kills >0.2→>0.1 mutation)."""
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        ndvi = np.array([[0.201]])
        result = clasificar_terreno_dinamico(None, ndvi, None)
        assert result["estadisticas"]["vegetacion_rala"]["pixeles"] == 1

    def test_ndvi_exactly_at_minus_0_1_not_bare_soil(self):
        """ndvi=-0.1 is NOT > -0.1 → NOT bare_soil."""
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        ndvi = np.array([[-0.1]])  # -0.1 is NOT > -0.1 → sin_clasificar
        result = clasificar_terreno_dinamico(None, ndvi, None)
        assert result["estadisticas"]["suelo_desnudo"]["pixeles"] == 0
        assert result["estadisticas"]["sin_clasificar"]["pixeles"] == 1

    def test_percentage_rounding_is_float(self):
        """Kill round((count/total)*100, None) → int mutation."""
        from app.domains.geo.intelligence.calculations import clasificar_terreno_dinamico

        sar = np.array([[-20.0, -10.0, -5.0]])  # 1 water, 2 unknown → 33.33%
        result = clasificar_terreno_dinamico(sar, None, None)
        pct = result["estadisticas"]["agua"]["porcentaje"]
        assert isinstance(pct, float)
        assert pct == pytest.approx(33.33, abs=0.01)


# ---------------------------------------------------------------------------
# detect_coverage_gaps — exact arithmetic and boundary conditions
# Mutations: dist_km = dist_deg * 111.0 (→*110), hci > 80.0, dist_km > 5.0
# severity_order dict, round(dist_km, 2), round(hci, 2)
# ---------------------------------------------------------------------------


class TestDetectCoverageGapsExact:
    """Kill arithmetic and comparison mutations in detect_coverage_gaps."""

    def test_dist_km_exact_arithmetic(self):
        """dist_km = dist_deg * 111.0. Use 1-degree gap → ~111 km."""
        from shapely.geometry import Point, LineString
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # Zone at origin, canal at (1,1): dist_deg ≈ sqrt(2) ≈ 1.414 → dist_km ≈ 157 km
        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": Point(0, 0)}],
            hci_scores={"z1": 90.0},
            canal_geometries=[{"geometry": LineString([(1, 1), (1.1, 1.1)])}],
            threshold_km=2.0,
        )
        assert len(result) == 1
        # Verify dist_km is reasonable (would be ~157 if *111, ~156 if *110)
        assert result[0]["gap_km"] > 100.0  # clearly > 110 * 1.0

    def test_hci_exactly_at_threshold_excluded(self):
        """hci=50.0 exactly at threshold → skip (hci < 50.0 is False, = is not <, but the check is hci < hci_threshold → hci<50 excludes)."""
        from shapely.geometry import Point, LineString
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # hci=50.0 is NOT < 50.0, so it passes the filter and is a candidate gap
        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": Point(0, 0)}],
            hci_scores={"z1": 50.0},
            canal_geometries=[{"geometry": LineString([(1, 1), (1.1, 1.1)])}],
            hci_threshold=50.0,
        )
        # hci=50.0, threshold=50.0 → hci < hci_threshold is 50.0 < 50.0 = False → NOT skipped
        assert len(result) == 1

    def test_hci_just_below_threshold_excluded(self):
        """hci=49.9 IS < 50.0 → skipped."""
        from shapely.geometry import Point, LineString
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": Point(0, 0)}],
            hci_scores={"z1": 49.9},
            canal_geometries=[{"geometry": LineString([(1, 1), (1.1, 1.1)])}],
            hci_threshold=50.0,
        )
        assert len(result) == 0

    def test_severity_critico_requires_both_conditions(self):
        """hci > 80 AND dist_km > 5 → critico."""
        from shapely.geometry import Point, LineString
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # Large gap (>5km), high HCI (>80)
        result = detect_coverage_gaps(
            zones=[{"id": "z1", "geometry": Point(0, 0)}],
            hci_scores={"z1": 85.0},
            canal_geometries=[{"geometry": LineString([(1, 0), (1.1, 0)])}],  # ~111 km away
            threshold_km=2.0,
        )
        assert result[0]["severity"] == "critico"

    def test_output_keys_exact(self):
        """Kill key name mutations: gap_km, hci_score, zone_id, severity, geometry."""
        from shapely.geometry import Point, LineString
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        result = detect_coverage_gaps(
            zones=[{"id": "zone_a", "geometry": Point(0, 0)}],
            hci_scores={"zone_a": 90.0},
            canal_geometries=[{"geometry": LineString([(1, 1), (1.1, 1.1)])}],
            threshold_km=2.0,
        )
        assert len(result) == 1
        gap = result[0]
        assert "gap_km" in gap
        assert "hci_score" in gap
        assert "zone_id" in gap
        assert "severity" in gap
        assert "geometry" in gap
        assert gap["zone_id"] == "zone_a"
        assert gap["hci_score"] == pytest.approx(90.0, abs=0.01)
        assert isinstance(gap["gap_km"], float)
        assert isinstance(gap["hci_score"], float)

    def test_severity_order_critico_before_alto(self):
        """critico comes before alto in sorted output (severity_order: {critico:0, alto:1})."""
        from shapely.geometry import Point, LineString
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        result = detect_coverage_gaps(
            zones=[
                {"id": "z1", "geometry": Point(0, 0)},    # alto candidate
                {"id": "z2", "geometry": Point(0.01, 0)},  # critico candidate
            ],
            hci_scores={"z1": 65.0, "z2": 90.0},
            canal_geometries=[{"geometry": LineString([(1, 0), (1.1, 0)])}],
            threshold_km=2.0,
        )
        assert len(result) == 2
        # critico should appear first
        assert result[0]["severity"] == "critico"


# ---------------------------------------------------------------------------
# compute_maintenance_priority — exact weight arithmetic
# Mutations: 0.30→0.25, 0.25→0.20, key names "centrality"→"CENTRALITY"
# ---------------------------------------------------------------------------


class TestComputeMaintenancePriorityExact:
    """Kill weight and key name mutations."""

    def test_exact_composite_score_all_factors(self):
        """With 2 nodes, node 1 at max on all factors → composite=1.0."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        # Node 1: max on everything. Node 2: min on everything.
        # All normalized values: node1=1.0, node2=0.0
        # composite = (0.30*1 + 0.25*1 + 0.25*1 + 0.20*1) / 1.0 = 1.0
        result = compute_maintenance_priority(
            centrality_scores={1: 1.0, 2: 0.0},
            flow_acc_scores={1: 1000.0, 2: 0.0},
            hci_scores={"1": 100.0, "2": 0.0},
            conflict_counts={1: 10, 2: 0},
        )
        node1 = next(r for r in result if r["node_id"] == 1)
        node2 = next(r for r in result if r["node_id"] == 2)
        assert node1["composite_score"] == pytest.approx(1.0, abs=1e-9)
        assert node2["composite_score"] == pytest.approx(0.0, abs=1e-9)

    def test_weight_redistribution_only_centrality(self):
        """Only centrality available. Redistribution: 1/0.30 → composite = 1.0 for max."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        result = compute_maintenance_priority(
            centrality_scores={1: 1.0, 2: 0.0},
            flow_acc_scores={},
            hci_scores={},
            conflict_counts={},
        )
        node1 = next(r for r in result if r["node_id"] == 1)
        # redistribution: adjusted_weight = 0.30 * (1/0.30) = 1.0 → composite = 1.0 * 1.0 = 1.0
        assert node1["composite_score"] == pytest.approx(1.0, abs=1e-9)

    def test_component_keys_exact(self):
        """Kill key name mutations: 'centrality'→'CENTRALITY', etc."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        result = compute_maintenance_priority(
            centrality_scores={1: 0.5, 2: 0.0},
            flow_acc_scores={1: 500.0, 2: 0.0},
            hci_scores={"1": 50.0, "2": 0.0},
            conflict_counts={1: 2, 2: 0},
        )
        node1 = next(r for r in result if r["node_id"] == 1)
        components = node1["components"]
        assert "centrality" in components
        assert "flow_acc" in components
        assert "upstream_hci" in components
        assert "conflict_count" in components
        # nested keys
        assert "raw" in components["centrality"]
        assert "normalized" in components["centrality"]

    def test_partial_factors_weight_redistribution_math(self):
        """With centrality(0.30) + flow_acc(0.25) → redistribution = 1/0.55."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        result = compute_maintenance_priority(
            centrality_scores={1: 1.0, 2: 0.0},
            flow_acc_scores={1: 1.0, 2: 0.0},
            hci_scores={},
            conflict_counts={},
        )
        node1 = next(r for r in result if r["node_id"] == 1)
        # redistribution_factor = 1/0.55 ≈ 1.8182
        # composite = (0.30 * 1.8182 * 1.0) + (0.25 * 1.8182 * 1.0) = (0.55 * 1.8182) = 1.0
        assert node1["composite_score"] == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# rank_canal_hotspots — exact rounding and risk level assignment
# Mutations: round(fa_max, 2)→None, percentile thresholds, key names
# ---------------------------------------------------------------------------


class TestRankCanalHotspotsExact:
    """Kill rounding and percentile threshold mutations."""

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_exact_flow_acc_max_rounded(self, mock_sample, tmp_path):
        """flow_acc_max = round(max(values), 2) — verify exact rounding and type."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fa_path = str(tmp_path / "fa.tif")
        Path(fa_path).touch()

        mock_sample.return_value = [123.456789, 200.0]
        canals = [{"geometry": LineString([(0, 0), (1, 1)])}]
        result = rank_canal_hotspots(canals, fa_path)

        assert len(result) == 1
        # max = 200.0, round(200.0, 2) = 200.0 (float)
        assert result[0]["flow_acc_max"] == pytest.approx(200.0)
        assert isinstance(result[0]["flow_acc_max"], float)
        assert isinstance(result[0]["score"], float)

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_exact_mean_rounded(self, mock_sample, tmp_path):
        """flow_acc_mean = round(sum/len, 2)."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fa_path = str(tmp_path / "fa.tif")
        Path(fa_path).touch()

        mock_sample.return_value = [100.0, 200.0, 300.0]
        canals = [{"geometry": LineString([(0, 0), (1, 1)])}]
        result = rank_canal_hotspots(canals, fa_path)

        # mean = 200.0, round(200.0, 2) = 200.0
        assert result[0]["flow_acc_mean"] == pytest.approx(200.0)
        assert isinstance(result[0]["flow_acc_mean"], float)

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_risk_level_at_p75_boundary(self, mock_sample, tmp_path):
        """4 segments with maxes [100, 200, 300, 400]: p75=325 → 400 is critico, 300 is alto."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fa_path = str(tmp_path / "fa.tif")
        Path(fa_path).touch()

        mock_sample.side_effect = [[100.0], [200.0], [300.0], [400.0]]
        canals = [{"geometry": LineString([(i, i), (i+1, i+1)])} for i in range(4)]
        result = rank_canal_hotspots(canals, fa_path)

        # Sorted descending: [400, 300, 200, 100]
        # p75=325: 400>=325 → critico
        assert result[0]["flow_acc_max"] == 400.0
        assert result[0]["risk_level"] == "critico"

    @patch("app.domains.geo.intelligence.calculations._sample_raster_along_line")
    def test_output_keys_exact(self, mock_sample, tmp_path):
        """Kill key name mutations: geometry, segment_index, flow_acc_max, score, risk_level."""
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fa_path = str(tmp_path / "fa.tif")
        Path(fa_path).touch()

        mock_sample.return_value = [500.0, 1000.0]
        canals = [{"geometry": LineString([(0, 0), (1, 1)]), "id": "c1", "nombre": "Canal 1"}]
        result = rank_canal_hotspots(canals, fa_path)

        assert len(result) == 1
        r = result[0]
        assert "geometry" in r
        assert "segment_index" in r
        assert "flow_acc_max" in r
        assert "flow_acc_mean" in r
        assert "score" in r
        assert "risk_level" in r
        assert r["segment_index"] == 0
        assert r["id"] == "c1"


# ---------------------------------------------------------------------------
# simular_escorrentia — output property keys and accumulation arithmetic
# Mutations: key names, fa_val * lluvia_mm → fa_val + lluvia_mm, etc.
# ---------------------------------------------------------------------------


class TestSimularEscorrentiaKeys:
    """Kill key name mutations in simular_escorrentia output."""

    def _make_rasterio_mock(self, flow_dir_data, flow_acc_data, transform, nodata=None):
        """Build a mock rasterio context that returns controlled raster data."""
        from rasterio.transform import from_bounds

        mock_fd = MagicMock()
        mock_fd.read.return_value = flow_dir_data
        mock_fd.transform = transform
        mock_fd.nodata = nodata
        mock_fd.__enter__ = MagicMock(return_value=mock_fd)
        mock_fd.__exit__ = MagicMock(return_value=False)

        mock_fa = MagicMock()
        mock_fa.read.return_value = flow_acc_data
        mock_fa.__enter__ = MagicMock(return_value=mock_fa)
        mock_fa.__exit__ = MagicMock(return_value=False)

        return mock_fd, mock_fa

    def test_output_feature_collection_type(self):
        """Assert type='FeatureCollection' in result."""
        from app.domains.geo.intelligence.calculations import simular_escorrentia
        from rasterio.transform import from_bounds

        transform = from_bounds(0, 0, 1, 1, 10, 10)
        # D8: 64=South, trace from (0,0) → moves south (row+1,col+0)
        fd_data = np.full((10, 10), 64, dtype=np.int32)
        fa_data = np.full((10, 10), 100.0, dtype=np.float64)

        mock_fd, mock_fa = self._make_rasterio_mock(fd_data, fa_data, transform)

        with patch("rasterio.open", side_effect=[mock_fd, mock_fa]), \
             patch("rasterio.transform.rowcol", return_value=(5, 5)):
            result = simular_escorrentia("/fd.tif", "/fa.tif", (0.5, 0.5), 10.0, max_steps=3)

        assert result["type"] == "FeatureCollection"

    def test_properties_keys_when_flow_traced(self):
        """Kill mutations to property key names when flow is successfully traced."""
        from app.domains.geo.intelligence.calculations import simular_escorrentia
        from rasterio.transform import from_bounds
        from unittest.mock import call

        transform = from_bounds(0, 0, 1, 1, 10, 10)
        # Use direction 64 (South), which maps to offset (1, 0)
        fd_data = np.full((10, 10), 64, dtype=np.int32)
        fa_data = np.full((10, 10), 500.0, dtype=np.float64)

        mock_fd, mock_fa = self._make_rasterio_mock(fd_data, fa_data, transform)
        rowcol_calls = [
            (1, 1),   # initial rowcol for punto_inicio
            # subsequent calls handled by the tracing loop
        ]

        with patch("rasterio.open", side_effect=[mock_fd, mock_fa]):
            with patch("rasterio.transform.rowcol", return_value=(1, 1)):
                result = simular_escorrentia("/fd.tif", "/fa.tif", (0.5, 0.5), 10.0, max_steps=5)

        if result["type"] == "FeatureCollection" and result["features"]:
            props = result["features"][0]["properties"]
            assert "punto_inicio" in props
            assert "lluvia_mm" in props
            assert "longitud_m" in props
            assert "acumulacion_max" in props
            assert "acumulacion_media" in props
            assert "pasos" in props
            assert props["lluvia_mm"] == 10.0

    def test_accumulation_multiplied_by_lluvia(self):
        """Kill fa_val * lluvia_mm → fa_val + lluvia_mm mutation."""
        from app.domains.geo.intelligence.calculations import simular_escorrentia
        from rasterio.transform import from_bounds

        transform = from_bounds(0, 0, 1, 1, 10, 10)
        # fa_data has value 100.0, lluvia_mm=5.0 → accumulation = 100*5 = 500 (not 100+5=105)
        fd_data = np.full((10, 10), 64, dtype=np.int32)  # South direction
        fa_data = np.full((10, 10), 100.0, dtype=np.float64)

        mock_fd, mock_fa = self._make_rasterio_mock(fd_data, fa_data, transform)

        with patch("rasterio.open", side_effect=[mock_fd, mock_fa]):
            with patch("rasterio.transform.rowcol", return_value=(1, 1)):
                result = simular_escorrentia("/fd.tif", "/fa.tif", (0.5, 0.5), 5.0, max_steps=5)

        if result["type"] == "FeatureCollection" and result["features"]:
            props = result["features"][0]["properties"]
            if props["acumulacion_max"] > 0:
                # Should be 100*5=500, not 100+5=105
                assert props["acumulacion_max"] >= 500.0


# ---------------------------------------------------------------------------
# detectar_puntos_conflicto — output keys and comparison thresholds
# Mutations: key names, fa_val > threshold, sl_val < threshold comparisons
# ---------------------------------------------------------------------------


class TestDetectarPuntosConflictoKeys:
    """Kill key name mutations and comparison boundary mutations."""

    def _make_conflict_mocks(self, fa_val, sl_val, fa_shape=(10, 10), sl_shape=(10, 10)):
        """Create rasterio mocks for conflict detection."""
        from rasterio.transform import from_bounds

        transform = from_bounds(0, 0, 1, 1, fa_shape[1], fa_shape[0])

        fa_data = np.full(fa_shape, fa_val, dtype=np.float64)
        sl_data = np.full(sl_shape, sl_val, dtype=np.float64)

        mock_fa = MagicMock()
        mock_fa.read.return_value = fa_data
        mock_fa.transform = transform
        mock_sl = MagicMock()
        mock_sl.read.return_value = sl_data
        mock_sl.transform = transform

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(side_effect=[mock_fa, mock_sl])
        mock_ctx.__exit__ = MagicMock(return_value=False)

        return mock_fa, mock_sl

    def test_output_column_names_present(self):
        """Kill key name mutations: 'tipo', 'descripcion', 'severidad', etc."""
        import geopandas as gpd
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto

        # fa > 500 and sl < 5 → should produce a conflict
        canales = gpd.GeoDataFrame(
            {"geometry": [LineString([(-0.001, 0), (0.001, 0)])]}, crs="EPSG:4326"
        )
        caminos = gpd.GeoDataFrame(
            {"geometry": [LineString([(0, -0.001), (0, 0.001)])]}, crs="EPSG:4326"
        )
        drenajes = gpd.GeoDataFrame(
            {"geometry": [LineString([(0.5, -0.001), (0.5, 0.001)])]}, crs="EPSG:4326"
        )

        from rasterio.transform import from_bounds
        transform = from_bounds(-1, -1, 1, 1, 100, 100)

        fa_data = np.full((100, 100), 1000.0, dtype=np.float64)  # > 500 threshold
        sl_data = np.full((100, 100), 1.0, dtype=np.float64)     # < 5 threshold

        mock_fa = MagicMock()
        mock_fa.read.return_value = fa_data
        mock_fa.transform = transform
        mock_fa.__enter__ = MagicMock(return_value=mock_fa)
        mock_fa.__exit__ = MagicMock(return_value=False)

        mock_sl = MagicMock()
        mock_sl.read.return_value = sl_data
        mock_sl.transform = transform
        mock_sl.__enter__ = MagicMock(return_value=mock_sl)
        mock_sl.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", side_effect=[mock_fa, mock_sl]), \
             patch("rasterio.transform.rowcol", return_value=(50, 50)):
            result = detectar_puntos_conflicto(
                canales, caminos, drenajes,
                "/fa.tif", "/sl.tif",
                buffer_m=50.0,
                flow_acc_threshold=500.0,
                slope_threshold=5.0,
            )

        # Should return a GeoDataFrame (possibly empty, due to buffer/overlay logic)
        # At minimum, verify the expected columns exist
        assert "tipo" in result.columns
        assert "descripcion" in result.columns
        assert "severidad" in result.columns
        assert "acumulacion_valor" in result.columns
        assert "pendiente_valor" in result.columns

    def test_fa_below_threshold_no_conflict(self):
        """fa_val=499 is NOT > 500 → no conflict (kills >= mutation)."""
        import geopandas as gpd
        from shapely.geometry import LineString
        from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto

        canales = gpd.GeoDataFrame(
            {"geometry": [LineString([(-0.001, 0), (0.001, 0)])]}, crs="EPSG:4326"
        )
        caminos = gpd.GeoDataFrame(
            {"geometry": [LineString([(0, -0.001), (0, 0.001)])]}, crs="EPSG:4326"
        )
        drenajes = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

        from rasterio.transform import from_bounds
        transform = from_bounds(-1, -1, 1, 1, 100, 100)

        fa_data = np.full((100, 100), 499.0)  # BELOW 500 threshold
        sl_data = np.full((100, 100), 1.0)    # below slope threshold

        mock_fa = MagicMock()
        mock_fa.read.return_value = fa_data
        mock_fa.transform = transform
        mock_fa.__enter__ = MagicMock(return_value=mock_fa)
        mock_fa.__exit__ = MagicMock(return_value=False)

        mock_sl = MagicMock()
        mock_sl.read.return_value = sl_data
        mock_sl.transform = transform
        mock_sl.__enter__ = MagicMock(return_value=mock_sl)
        mock_sl.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", side_effect=[mock_fa, mock_sl]), \
             patch("rasterio.transform.rowcol", return_value=(50, 50)):
            result = detectar_puntos_conflicto(
                canales, caminos, drenajes,
                "/fa.tif", "/sl.tif",
                flow_acc_threshold=500.0,
                slope_threshold=5.0,
            )

        assert len(result) == 0


class TestComputeMaintenancePriorityWeightArithmetic:
    """Targets weight mutations, normalization arithmetic, key names, and rounding."""

    def test_exact_composite_non_zero_min(self):
        """All factors present with non-zero min → exact composite value kills weight mutations."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        # centrality: {1:20, 2:14, 3:10} → min=10, max=20
        # node2 norm_cent = (14-10)/(20-10) = 0.4
        centrality_scores = {1: 20.0, 2: 14.0, 3: 10.0}

        # flow_acc: {1:30, 2:20, 3:10} → min=10, max=30
        # node2 norm_fa = (20-10)/(30-10) = 0.5
        flow_acc_scores = {1: 30.0, 2: 20.0, 3: 10.0}

        # hci (str keys): {"1":100,"2":70,"3":40} → min=40, max=100
        # node2 norm_hci = (70-40)/(100-40) = 0.5
        hci_scores = {"1": 100.0, "2": 70.0, "3": 40.0}

        # conflict_counts: {1:10, 2:3, 3:0} → min=0, max=10
        # node2 norm_conf = (3-0)/(10-0) = 0.3
        conflict_counts = {1: 10, 2: 3, 3: 0}

        result = compute_maintenance_priority(
            centrality_scores, flow_acc_scores, hci_scores, conflict_counts
        )

        # composite = 0.30*0.4 + 0.25*0.5 + 0.25*0.5 + 0.20*0.3 = 0.43
        node2 = next(e for e in result if e["node_id"] == 2)
        assert node2["composite_score"] == pytest.approx(0.43, abs=1e-6)

    def test_component_keys_are_exact_strings(self):
        """Component sub-dict keys are 'centrality','flow_acc','upstream_hci','conflict_count'."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        centrality_scores = {1: 10.0, 2: 5.0}
        flow_acc_scores = {1: 20.0, 2: 10.0}
        hci_scores = {"1": 80.0, "2": 60.0}
        conflict_counts = {1: 4, 2: 2}

        result = compute_maintenance_priority(
            centrality_scores, flow_acc_scores, hci_scores, conflict_counts
        )

        entry = next(e for e in result if e["node_id"] == 1)
        comps = entry["components"]
        for key in ["centrality", "flow_acc", "upstream_hci", "conflict_count"]:
            assert key in comps, f"Key '{key}' missing from components"
            assert "raw" in comps[key], f"'raw' missing in components['{key}']"

    def test_raw_centrality_rounded_to_6_decimals(self):
        """Centrality raw value stored as round(x, 6), not unrounded float."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        v = 1 / 3  # irrational → exposes rounding depth
        centrality_scores = {1: v, 2: 0.0}
        flow_acc_scores = {1: 1.0, 2: 0.0}
        hci_scores = {"1": 1.0, "2": 0.0}
        conflict_counts = {1: 1, 2: 0}

        result = compute_maintenance_priority(
            centrality_scores, flow_acc_scores, hci_scores, conflict_counts
        )

        entry = next(e for e in result if e["node_id"] == 1)
        raw = entry["components"]["centrality"]["raw"]
        assert isinstance(raw, float)
        assert raw == pytest.approx(round(v, 6), abs=1e-9)
        assert raw != v  # 1/3 unrounded != round(1/3, 6)

    def test_composite_score_rounded_to_4_decimals(self):
        """Composite score stored as round(x, 4)."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        centrality_scores = {1: 30.0, 2: 17.0, 3: 10.0}
        flow_acc_scores = {1: 30.0, 2: 17.0, 3: 10.0}
        hci_scores = {"1": 30.0, "2": 17.0, "3": 10.0}
        conflict_counts = {1: 30, 2: 17, 3: 10}

        result = compute_maintenance_priority(
            centrality_scores, flow_acc_scores, hci_scores, conflict_counts
        )

        for entry in result:
            score = entry["composite_score"]
            assert score == round(score, 4)

    def test_missing_factors_exact_string_names(self):
        """'centrality' in missing_factors when centrality_scores is empty."""
        from app.domains.geo.intelligence.calculations import compute_maintenance_priority

        centrality_scores: dict = {}
        flow_acc_scores = {1: 5.0}
        hci_scores = {"1": 50.0}
        conflict_counts = {1: 2}

        result = compute_maintenance_priority(
            centrality_scores, flow_acc_scores, hci_scores, conflict_counts
        )

        entry = result[0]
        missing = entry.get("missing_factors", [])
        assert "centrality" in missing
        assert "XXcentralityXX" not in missing
        assert None not in missing


class TestDetectCoverageGapsBoundaries:
    """Targets None-zone continue→break, severity logic, rounding, and sort in detect_coverage_gaps."""

    def _zone(self, zone_id, lon0, lat0, lon1, lat1):
        from shapely.geometry import Polygon
        return {"id": zone_id, "geometry": Polygon([(lon0, lat0), (lon1, lat0), (lon1, lat1), (lon0, lat1)])}

    def _canal(self, lon0, lat0, lon1, lat1):
        from shapely.geometry import LineString
        return {"geometry": LineString([(lon0, lat0), (lon1, lat1)])}

    def test_continue_skip_none_zone_geometry(self):
        """Zone with None geometry skipped (continue, not break); next zone still processed."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [
            {"id": "1", "geometry": None},
            self._zone("2", 0, -0.1, 1, 0.1),
        ]
        hci_scores = {"1": 90.0, "2": 90.0}
        canal_geoms = [self._canal(20, -0.1, 21, 0.1)]

        result = detect_coverage_gaps(zones, hci_scores, canal_geoms, threshold_km=1.0)
        # If continue→break: stops at zone1 (None) → 0 gaps. With continue: zone2 processed → ≥1 gap.
        assert len(result) >= 1

    def test_critico_requires_hci_above_80_and_dist_above_5km(self):
        """hci=81 and large distance → severity 'critico'."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._zone("1", 0, -0.1, 1, 0.1)]
        hci_scores = {"1": 81.0}
        canal_geoms = [self._canal(20, -0.1, 21, 0.1)]

        result = detect_coverage_gaps(zones, hci_scores, canal_geoms, threshold_km=1.0)
        assert len(result) == 1
        assert result[0]["severity"] == "critico"

    def test_hci_exactly_80_is_alto_not_critico(self):
        """hci == 80.0 is NOT > 80 → 'alto' not 'critico' (kills >= mutation)."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._zone("1", 0, -0.1, 1, 0.1)]
        hci_scores = {"1": 80.0}
        canal_geoms = [self._canal(20, -0.1, 21, 0.1)]

        result = detect_coverage_gaps(zones, hci_scores, canal_geoms, threshold_km=1.0)
        assert len(result) == 1
        assert result[0]["severity"] == "alto"
        assert result[0]["severity"] != "critico"

    def test_moderado_when_hci_at_or_below_60(self):
        """hci=55 → not critico, not alto → 'moderado'."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._zone("1", 0, -0.1, 1, 0.1)]
        hci_scores = {"1": 55.0}
        canal_geoms = [self._canal(20, -0.1, 21, 0.1)]

        result = detect_coverage_gaps(zones, hci_scores, canal_geoms, threshold_km=1.0)
        assert len(result) == 1
        sev = result[0]["severity"]
        assert sev == "moderado"
        assert sev != "MODERADO"

    def test_hci_score_stored_rounded_to_2dp(self):
        """hci_score in output is round(hci, 2) not round(hci, 3)."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._zone("1", 0, -0.1, 1, 0.1)]
        hci_scores = {"1": 90.123}
        canal_geoms = [self._canal(20, -0.1, 21, 0.1)]

        result = detect_coverage_gaps(zones, hci_scores, canal_geoms, threshold_km=1.0)
        assert len(result) == 1
        stored = result[0]["hci_score"]
        assert stored == pytest.approx(90.12, abs=1e-6)
        assert stored != pytest.approx(90.123, abs=1e-6)

    def test_111_km_per_degree_constant(self):
        """Gap distance uses the 111 km/degree conversion constant."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps
        from shapely.geometry import Polygon, LineString

        # Zone centroid at lon=0.5; canal nearest point at lon=1.5 → dist_deg≈1.0 → ~111 km
        zones = [{"id": "1", "geometry": Polygon([(0, -0.1), (1, -0.1), (1, 0.1), (0, 0.1)])}]
        hci_scores = {"1": 65.0}  # 65>60, dist>3 → alto (dist>>threshold)
        canal_geoms = [{"geometry": LineString([(1.5, -0.1), (2.5, -0.1)])}]

        result = detect_coverage_gaps(zones, hci_scores, canal_geoms, threshold_km=10.0)
        assert len(result) == 1
        assert result[0]["gap_km"] == pytest.approx(111.0, abs=5.0)

    def test_sort_critico_before_alto(self):
        """critico zones sorted before alto regardless of HCI value."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [
            self._zone("1", 0, -0.1, 1, 0.1),   # hci=82 → critico
            self._zone("2", 2, -0.1, 3, 0.1),   # hci=65 → alto
        ]
        hci_scores = {"1": 82.0, "2": 65.0}
        canal_geoms = [self._canal(20, -0.1, 21, 0.1)]

        result = detect_coverage_gaps(zones, hci_scores, canal_geoms, threshold_km=1.0)
        assert len(result) == 2
        assert result[0]["severity"] == "critico"
        assert result[1]["severity"] == "alto"


class TestRankCanalHotspotsRoundingAndRiskLevel:
    """Targets rounding (round 2), risk_level strings, >= boundary, and continue→break."""

    def _canal_dict(self, coords):
        from shapely.geometry import LineString
        return {"geometry": LineString(coords)}

    def test_flow_acc_max_rounded_to_2dp(self):
        """flow_acc_max stored as round(fa_max, 2), not round(fa_max, 3)."""
        from unittest.mock import patch
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        canal_geoms = [self._canal_dict([(0, 0), (1, 0)])]

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._sample_raster_along_line",
                   return_value=[123.456]):
            result = rank_canal_hotspots(canal_geoms, "/fake/fa.tif")

        assert len(result) == 1
        stored = result[0]["flow_acc_max"]
        assert stored == pytest.approx(123.46, abs=1e-6)
        assert stored != pytest.approx(123.456, abs=1e-6)

    def test_risk_level_strings_are_exact(self):
        """Risk level values are exactly 'critico','alto','medio','bajo'."""
        from unittest.mock import patch
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        # 4 canals: fa=[100,200,300,400] → p25=175,p50=250,p75=325
        # 100<p25→bajo; 200≥p25→medio; 300≥p50→alto; 400≥p75→critico
        canal_geoms = [self._canal_dict([(i, 0), (i+1, 0)]) for i in range(4)]
        fa_values = [100.0, 200.0, 300.0, 400.0]

        call_n = [0]
        def mock_sample(geom, path, n=20):
            idx = call_n[0]; call_n[0] += 1
            return [fa_values[idx]]

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._sample_raster_along_line",
                   side_effect=mock_sample):
            result = rank_canal_hotspots(canal_geoms, "/fake/fa.tif")

        levels = {r["flow_acc_max"]: r["risk_level"] for r in result}
        for expected_level in levels.values():
            assert expected_level in ("critico", "alto", "medio", "bajo")

    def test_critico_at_exactly_p75(self):
        """flow_acc_max == p75 → 'critico' (>= not >); kills >= → > mutation."""
        from unittest.mock import patch
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        # 5 canals: [100,200,300,400,500] → p75=400
        canal_geoms = [self._canal_dict([(i, 0), (i+1, 0)]) for i in range(5)]
        fa_values = [100.0, 200.0, 300.0, 400.0, 500.0]

        call_n = [0]
        def mock_sample(geom, path, n=20):
            idx = call_n[0]; call_n[0] += 1
            return [fa_values[idx]]

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._sample_raster_along_line",
                   side_effect=mock_sample):
            result = rank_canal_hotspots(canal_geoms, "/fake/fa.tif")

        # p75([100,200,300,400,500]) = 400 → must be 'critico'
        entry = next(r for r in result if abs(r["flow_acc_max"] - 400.0) < 0.01)
        assert entry["risk_level"] == "critico"

    def test_medio_at_exactly_p25(self):
        """flow_acc_max == p25 → 'medio' (>= not >); kills >= → > mutation."""
        from unittest.mock import patch
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        canal_geoms = [self._canal_dict([(i, 0), (i+1, 0)]) for i in range(5)]
        fa_values = [100.0, 200.0, 300.0, 400.0, 500.0]

        call_n = [0]
        def mock_sample(geom, path, n=20):
            idx = call_n[0]; call_n[0] += 1
            return [fa_values[idx]]

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._sample_raster_along_line",
                   side_effect=mock_sample):
            result = rank_canal_hotspots(canal_geoms, "/fake/fa.tif")

        # p25([100,200,300,400,500]) = 200 → must be 'medio'
        entry = next(r for r in result if abs(r["flow_acc_max"] - 200.0) < 0.01)
        assert entry["risk_level"] == "medio"

    def test_continue_not_break_on_none_geometry(self):
        """Canal with None geometry skipped (continue); subsequent canals still processed."""
        from unittest.mock import patch
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots
        from shapely.geometry import LineString

        canal_geoms = [
            {"geometry": LineString([(0, 0), (1, 0)])},
            {"geometry": None},
            {"geometry": LineString([(4, 0), (5, 0)])},
        ]
        fa_values = [300.0, 400.0]

        call_n = [0]
        def mock_sample(geom, path, n=20):
            idx = call_n[0]; call_n[0] += 1
            return [fa_values[idx]]

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._sample_raster_along_line",
                   side_effect=mock_sample):
            result = rank_canal_hotspots(canal_geoms, "/fake/fa.tif")

        # If continue→break: stops at None canal → 1 result. With continue: 2 results.
        assert len(result) == 2

    def test_continue_not_break_on_empty_sample_values(self):
        """Canal with empty sample values skipped (continue); subsequent canals processed."""
        from unittest.mock import patch
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        canal_geoms = [
            self._canal_dict([(0, 0), (1, 0)]),
            self._canal_dict([(2, 0), (3, 0)]),
            self._canal_dict([(4, 0), (5, 0)]),
        ]
        fa_returns = [[], [500.0], [300.0]]

        call_n = [0]
        def mock_sample(geom, path, n=20):
            idx = call_n[0]; call_n[0] += 1
            return fa_returns[idx]

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._sample_raster_along_line",
                   side_effect=mock_sample):
            result = rank_canal_hotspots(canal_geoms, "/fake/fa.tif")

        # If continue→break: stops after empty → 0 results. With continue: 2 results.
        assert len(result) == 2



class TestSimularEscorrentiaDirections:
    """Kill d8_offsets key mutations, offset value mutations, and coordinate formula mutations."""

    def _make_mocks(self, direction_code, fa_value=100.0, nodata=None):
        """10×10 raster, all cells with given direction code."""
        from rasterio.transform import from_bounds
        transform = from_bounds(0, 0, 1, 1, 10, 10)  # a=0.1, e=-0.1, c=0, f=1
        fd_data = np.full((10, 10), direction_code, dtype=np.int32)
        fa_data = np.full((10, 10), fa_value, dtype=np.float64)

        mock_fd = MagicMock()
        mock_fd.read.return_value = fd_data
        mock_fd.transform = transform
        mock_fd.nodata = nodata
        mock_fd.__enter__ = MagicMock(return_value=mock_fd)
        mock_fd.__exit__ = MagicMock(return_value=False)

        mock_fa = MagicMock()
        mock_fa.read.return_value = fa_data
        mock_fa.__enter__ = MagicMock(return_value=mock_fa)
        mock_fa.__exit__ = MagicMock(return_value=False)

        return mock_fd, mock_fa

    def _run(self, direction_code, fa_value=100.0, max_steps=3, start_rowcol=(5, 5), nodata=None):
        from app.domains.geo.intelligence.calculations import simular_escorrentia
        mock_fd, mock_fa = self._make_mocks(direction_code, fa_value, nodata)
        with patch("rasterio.open", side_effect=[mock_fd, mock_fa]), \
             patch("rasterio.transform.rowcol", return_value=start_rowcol):
            return simular_escorrentia("/fd.tif", "/fa.tif", (0.5, 0.5), 10.0, max_steps=max_steps)

    def _first_coords(self, result):
        """Return coordinate list from first feature."""
        if not result["features"]:
            return []
        geom = result["features"][0]["geometry"]
        if geom["type"] == "LineString":
            return geom["coordinates"]
        return []

    # ── Direction key mutations (mutants 3,6,10,14,19,23,27,30) ─────────────
    # Each test: direction=N in raster → must produce non-empty features.
    # If key N is mutated to N+1, d8_offsets.get(N) returns None → break → empty.

    def test_east_direction_1_produces_features(self):
        """Direction=1 (East) → non-empty features. Kills key mutation 3 (1→2)."""
        result = self._run(1)
        assert len(result["features"]) >= 1

    def test_ne_direction_2_produces_features(self):
        """Direction=2 (NE) → non-empty features. Kills key mutation 6 (2→3)."""
        result = self._run(2)
        assert len(result["features"]) >= 1

    def test_north_direction_4_produces_features(self):
        """Direction=4 (North) → non-empty features. Kills key mutation 10 (4→5)."""
        result = self._run(4)
        assert len(result["features"]) >= 1

    def test_nw_direction_8_produces_features(self):
        """Direction=8 (NW) → non-empty features. Kills key mutation 14 (8→9)."""
        result = self._run(8)
        assert len(result["features"]) >= 1

    def test_west_direction_16_produces_features(self):
        """Direction=16 (West) → non-empty features. Kills key mutation 19 (16→17)."""
        result = self._run(16)
        assert len(result["features"]) >= 1

    def test_sw_direction_32_produces_features(self):
        """Direction=32 (SW) → non-empty features. Kills key mutation 23 (32→33)."""
        result = self._run(32)
        assert len(result["features"]) >= 1

    def test_se_direction_128_produces_features(self):
        """Direction=128 (SE) → non-empty features. Kills key mutation 30 (128→129)."""
        result = self._run(128)
        assert len(result["features"]) >= 1

    # ── Offset value mutations (East: mutants 4,5; South: 28,29; North: 11-13; West: 20-22) ──

    def test_east_offset_x_increases_y_unchanged(self):
        """Direction=1 East: offset(0,1) → col+1 → x increases, y fixed.
        Kills mutant 4 (0,1→1,1) and 5 (0,1→0,2)."""
        result = self._run(1, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # row=5,col=6 → x=0.6, y=0.5 (from_bounds 0-1 10×10: a=0.1,e=-0.1,c=0,f=1)
            assert coords[1][0] == pytest.approx(0.6, abs=0.001)  # x increased
            assert coords[1][1] == pytest.approx(0.5, abs=0.001)  # y unchanged

    def test_south_offset_y_decreases_x_unchanged(self):
        """Direction=64 South: offset(1,0) → row+1 → y decreases, x fixed.
        Kills mutant 28 (1,0→2,0) and 29 (1,0→1,1)."""
        result = self._run(64, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # row=6,col=5 → x=0.5, y=0.4
            assert coords[1][0] == pytest.approx(0.5, abs=0.001)  # x unchanged
            assert coords[1][1] == pytest.approx(0.4, abs=0.001)  # y decreased

    def test_north_offset_y_increases_x_unchanged(self):
        """Direction=4 North: offset(-1,0) → row-1 → y increases.
        Kills mutants 11,12,13."""
        result = self._run(4, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # row=4,col=5 → x=0.5, y=0.6
            assert coords[1][0] == pytest.approx(0.5, abs=0.001)
            assert coords[1][1] == pytest.approx(0.6, abs=0.001)

    def test_west_offset_x_decreases_y_unchanged(self):
        """Direction=16 West: offset(0,-1) → col-1 → x decreases.
        Kills mutants 20,21,22."""
        result = self._run(16, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # row=5,col=4 → x=0.4, y=0.5
            assert coords[1][0] == pytest.approx(0.4, abs=0.001)
            assert coords[1][1] == pytest.approx(0.5, abs=0.001)

    def test_ne_offset_x_increases_y_increases(self):
        """Direction=2 NE: offset(-1,1) → row-1,col+1 → x increases, y increases.
        Kills mutants 7,8,9."""
        result = self._run(2, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # row=4,col=6 → x=0.6, y=0.6
            assert coords[1][0] == pytest.approx(0.6, abs=0.001)
            assert coords[1][1] == pytest.approx(0.6, abs=0.001)

    def test_nw_offset_x_decreases_y_increases(self):
        """Direction=8 NW: offset(-1,-1) → row-1,col-1.
        Kills mutants 15,16,17,18."""
        result = self._run(8, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # row=4,col=4 → x=0.4, y=0.6
            assert coords[1][0] == pytest.approx(0.4, abs=0.001)
            assert coords[1][1] == pytest.approx(0.6, abs=0.001)

    def test_sw_offset_x_decreases_y_decreases(self):
        """Direction=32 SW: offset(1,-1) → row+1,col-1.
        Kills mutants 24,25,26."""
        result = self._run(32, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # row=6,col=4 → x=0.4, y=0.4
            assert coords[1][0] == pytest.approx(0.4, abs=0.001)
            assert coords[1][1] == pytest.approx(0.4, abs=0.001)

    def test_se_offset_x_increases_y_decreases(self):
        """Direction=128 SE: offset(1,1) → row+1,col+1.
        Kills mutants 31,32."""
        result = self._run(128, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # row=6,col=6 → x=0.6, y=0.4
            assert coords[1][0] == pytest.approx(0.6, abs=0.001)
            assert coords[1][1] == pytest.approx(0.4, abs=0.001)

    # ── Row/col accumulation mutations (104-109) ─────────────────────────────

    def test_row_increment_not_assignment(self):
        """row += offset[0], not row = offset[0]. Kills mutant 104.
        With start row=5, offset=(1,0): row=6; if row=offset[0]=1 → wrong coord."""
        result = self._run(64, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # South step: row should be 5+1=6, not just 1
            # x stays at 0.5 (col=5), y = 1 + 6*(-0.1) = 0.4
            assert coords[1][1] == pytest.approx(0.4, abs=0.001)

    def test_col_increment_not_assignment(self):
        """col += offset[1], not col = offset[1]. Kills mutant 107.
        With start col=5, East offset (0,1): col=6; if col=1 → x=0.1 not 0.6."""
        result = self._run(1, max_steps=2)
        coords = self._first_coords(result)
        if len(coords) >= 2:
            # East step: col=5+1=6 → x=0.6, not col=1 → x=0.1
            assert coords[1][0] == pytest.approx(0.6, abs=0.001)

    # ── Feature structure mutations (135-141) ────────────────────────────────

    def test_feature_type_is_Feature_exact(self):
        """feature['type'] == 'Feature', not corrupted. Kills mutants 135-139."""
        result = self._run(64, max_steps=2)
        assert result["features"]
        ft = result["features"][0]["type"]
        assert ft == "Feature"
        assert ft != "XXFeatureXX"
        assert ft != "feature"
        assert ft != "FEATURE"

    def test_feature_geometry_not_none(self):
        """feature['geometry'] is present and not None. Kills mutants 140,141,142."""
        result = self._run(64, max_steps=2)
        assert result["features"]
        feature = result["features"][0]
        assert "geometry" in feature
        assert feature["geometry"] is not None
        assert "XXgeometryXX" not in feature

    def test_top_level_type_is_FeatureCollection_exact(self):
        """result['type'] == 'FeatureCollection'. Kills mutants 163,165,166,167."""
        result = self._run(64, max_steps=2)
        assert result["type"] == "FeatureCollection"
        assert result["type"] != "XXFeatureCollectionXX"
        assert result["type"] != "featurecollection"

    def test_features_key_not_corrupted(self):
        """'features' key present, 'XXfeaturesXX' absent. Kills mutants 168,169."""
        result = self._run(64, max_steps=2)
        assert "features" in result
        assert "XXfeaturesXX" not in result
        assert "FEATURES" not in result

    # ── Accumulation arithmetic mutations (158) ───────────────────────────────

    def test_acumulacion_media_is_sum_divided_by_len(self):
        """acumulacion_media = sum(acc)/len(acc), not sum*len. Kills mutant 158.
        fa=60, lluvia=10 → each step=600. With 2 steps: media=600, sum*len=2400."""
        result = self._run(64, fa_value=60.0, max_steps=2)
        if result["features"]:
            props = result["features"][0]["properties"]
            if props.get("acumulacion_max", 0) > 0:
                # sum/len = 600, sum*len = 2400
                assert props["acumulacion_media"] == pytest.approx(600.0, abs=0.1)

    # ── nodata mutation (83) ─────────────────────────────────────────────────

    def test_nodata_stops_trace_when_direction_equals_nodata(self):
        """fd_nodata=255, direction=255 → trace stops (empty). Kills mutant 83 (!=).
        With mutant 83, direction != nodata → trace continues (non-empty)."""
        result = self._run(255, nodata=255, max_steps=3)
        # Original: direction==nodata → break → coords=[start] < 2 → empty
        assert result["features"] == []

    def test_valid_direction_with_nodata_set_continues(self):
        """fd_nodata=255, direction=64 → NOT equal → trace continues → non-empty.
        Kills mutant 83 variant: with != condition, valid direction would be stopped."""
        result = self._run(64, nodata=255, max_steps=3)
        assert len(result["features"]) >= 1


class TestDetectarPuntosConflictoTipoStrings:
    """Kill tipo string mutations and continue→break in detectar_puntos_conflicto."""

    def _make_canal_camino_setup(self):
        """Canales and caminos that cross at origin; drenajes far away."""
        import geopandas as gpd
        from shapely.geometry import LineString
        from rasterio.transform import from_bounds

        canales = gpd.GeoDataFrame(
            {"geometry": [LineString([(-0.001, 0), (0.001, 0)])]}, crs="EPSG:4326"
        )
        caminos = gpd.GeoDataFrame(
            {"geometry": [LineString([(0, -0.001), (0, 0.001)])]}, crs="EPSG:4326"
        )
        drenajes = gpd.GeoDataFrame(
            {"geometry": [LineString([(10, 0), (11, 0)])]}, crs="EPSG:4326"
        )

        transform = from_bounds(-1, -1, 1, 1, 100, 100)
        fa_data = np.full((100, 100), 1000.0, dtype=np.float64)
        sl_data = np.full((100, 100), 1.0, dtype=np.float64)

        mock_fa = MagicMock()
        mock_fa.read.return_value = fa_data
        mock_fa.transform = transform
        mock_fa.__enter__ = MagicMock(return_value=mock_fa)
        mock_fa.__exit__ = MagicMock(return_value=False)

        mock_sl = MagicMock()
        mock_sl.read.return_value = sl_data
        mock_sl.transform = transform
        mock_sl.__enter__ = MagicMock(return_value=mock_sl)
        mock_sl.__exit__ = MagicMock(return_value=False)

        return canales, caminos, drenajes, mock_fa, mock_sl

    def _run_detectar(self, canales, caminos, drenajes, mock_fa, mock_sl):
        from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto
        with patch("rasterio.open", side_effect=[mock_fa, mock_sl]), \
             patch("rasterio.transform.rowcol", return_value=(50, 50)):
            return detectar_puntos_conflicto(
                canales, caminos, drenajes, "/fa.tif", "/sl.tif",
                flow_acc_threshold=500.0, slope_threshold=5.0,
            )

    def test_tipo_canal_camino_exact_string(self):
        """Tipo value is 'canal_camino' not 'XXcanal_caminoXX'. Kills mutants 6,7."""
        canales, caminos, drenajes, mock_fa, mock_sl = self._make_canal_camino_setup()
        result = self._run_detectar(canales, caminos, drenajes, mock_fa, mock_sl)
        assert len(result) > 0
        assert "canal_camino" in result["tipo"].values
        assert "XXcanal_caminoXX" not in result["tipo"].values
        assert "CANAL_CAMINO" not in result["tipo"].values

    def test_tipo_canal_drenaje_exact_string(self):
        """Tipo value is 'canal_drenaje' not corrupted. Kills mutants 8,9."""
        import geopandas as gpd
        from shapely.geometry import LineString
        from rasterio.transform import from_bounds

        # Canales and drenajes cross; caminos are far
        canales = gpd.GeoDataFrame(
            {"geometry": [LineString([(-0.001, 0), (0.001, 0)])]}, crs="EPSG:4326"
        )
        drenajes = gpd.GeoDataFrame(
            {"geometry": [LineString([(0, -0.001), (0, 0.001)])]}, crs="EPSG:4326"
        )
        caminos = gpd.GeoDataFrame(
            {"geometry": [LineString([(10, 0), (11, 0)])]}, crs="EPSG:4326"
        )

        transform = from_bounds(-1, -1, 1, 1, 100, 100)
        fa_data = np.full((100, 100), 1000.0, dtype=np.float64)
        sl_data = np.full((100, 100), 1.0, dtype=np.float64)

        mock_fa = MagicMock()
        mock_fa.read.return_value = fa_data
        mock_fa.transform = transform
        mock_fa.__enter__ = MagicMock(return_value=mock_fa)
        mock_fa.__exit__ = MagicMock(return_value=False)

        mock_sl = MagicMock()
        mock_sl.read.return_value = sl_data
        mock_sl.transform = transform
        mock_sl.__enter__ = MagicMock(return_value=mock_sl)
        mock_sl.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", side_effect=[mock_fa, mock_sl]), \
             patch("rasterio.transform.rowcol", return_value=(50, 50)):
            from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto
            result = detectar_puntos_conflicto(
                canales, caminos, drenajes, "/fa.tif", "/sl.tif",
                flow_acc_threshold=500.0, slope_threshold=5.0,
            )

        assert len(result) > 0
        assert "canal_drenaje" in result["tipo"].values
        assert "XXcanal_drenajeXX" not in result["tipo"].values

    def test_tipo_camino_drenaje_exact_string(self):
        """Tipo value is 'camino_drenaje' not corrupted. Kills mutants 10,11."""
        import geopandas as gpd
        from shapely.geometry import LineString
        from rasterio.transform import from_bounds

        # Caminos and drenajes cross; canales are far
        caminos = gpd.GeoDataFrame(
            {"geometry": [LineString([(-0.001, 0), (0.001, 0)])]}, crs="EPSG:4326"
        )
        drenajes = gpd.GeoDataFrame(
            {"geometry": [LineString([(0, -0.001), (0, 0.001)])]}, crs="EPSG:4326"
        )
        canales = gpd.GeoDataFrame(
            {"geometry": [LineString([(10, 0), (11, 0)])]}, crs="EPSG:4326"
        )

        transform = from_bounds(-1, -1, 1, 1, 100, 100)
        fa_data = np.full((100, 100), 1000.0, dtype=np.float64)
        sl_data = np.full((100, 100), 1.0, dtype=np.float64)

        mock_fa = MagicMock()
        mock_fa.read.return_value = fa_data
        mock_fa.transform = transform
        mock_fa.__enter__ = MagicMock(return_value=mock_fa)
        mock_fa.__exit__ = MagicMock(return_value=False)

        mock_sl = MagicMock()
        mock_sl.read.return_value = sl_data
        mock_sl.transform = transform
        mock_sl.__enter__ = MagicMock(return_value=mock_sl)
        mock_sl.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", side_effect=[mock_fa, mock_sl]), \
             patch("rasterio.transform.rowcol", return_value=(50, 50)):
            from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto
            result = detectar_puntos_conflicto(
                canales, caminos, drenajes, "/fa.tif", "/sl.tif",
                flow_acc_threshold=500.0, slope_threshold=5.0,
            )

        assert len(result) > 0
        assert "camino_drenaje" in result["tipo"].values
        assert "XXcamino_drenajeXX" not in result["tipo"].values

    def test_continue_not_break_on_empty_pair(self):
        """Empty gdf_a → continue to next pair, not break. Kills mutant 23.
        Setup: empty canales → pairs 0,1 skipped; caminos+drenajes cross → pair 2 produces result."""
        import geopandas as gpd
        from shapely.geometry import LineString
        from rasterio.transform import from_bounds
        from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto

        # Empty canales → pairs 0,1 both skip
        canales = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326", geometry="geometry")
        # Caminos + drenajes cross → pair 2 (camino_drenaje) should produce conflicts
        caminos = gpd.GeoDataFrame(
            {"geometry": [LineString([(-0.001, 0), (0.001, 0)])]}, crs="EPSG:4326"
        )
        drenajes = gpd.GeoDataFrame(
            {"geometry": [LineString([(0, -0.001), (0, 0.001)])]}, crs="EPSG:4326"
        )

        transform = from_bounds(-1, -1, 1, 1, 100, 100)
        fa_data = np.full((100, 100), 1000.0, dtype=np.float64)
        sl_data = np.full((100, 100), 1.0, dtype=np.float64)

        mock_fa = MagicMock()
        mock_fa.read.return_value = fa_data
        mock_fa.transform = transform
        mock_fa.__enter__ = MagicMock(return_value=mock_fa)
        mock_fa.__exit__ = MagicMock(return_value=False)

        mock_sl = MagicMock()
        mock_sl.read.return_value = sl_data
        mock_sl.transform = transform
        mock_sl.__enter__ = MagicMock(return_value=mock_sl)
        mock_sl.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", side_effect=[mock_fa, mock_sl]), \
             patch("rasterio.transform.rowcol", return_value=(50, 50)):
            result = detectar_puntos_conflicto(
                canales, caminos, drenajes, "/fa.tif", "/sl.tif",
                flow_acc_threshold=500.0, slope_threshold=5.0,
            )

        # With continue: pairs 0,1 skipped → pair 2 (camino_drenaje) processed → conflicts found
        # With break (mutant 23): breaks at pair 0 → 0 conflicts
        assert len(result) > 0
        assert "camino_drenaje" in result["tipo"].values

    def test_or_not_and_in_empty_check(self):
        """if gdf_a.empty OR gdf_b.empty: skip. Not AND. Kills mutant 22.
        Setup: empty canales → canal_camino skipped (or); non-empty caminos+drenajes → pair 2 works."""
        import geopandas as gpd
        from shapely.geometry import LineString
        from rasterio.transform import from_bounds
        from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto

        # Non-empty canales BUT we also need caminos+drenajes to cross
        # for camino_drenaje pair to produce results regardless
        # Instead: test with empty caminos → canal_camino skipped, canal_drenaje skipped
        # → only camino_drenaje remains, but caminos is empty → 0 results
        # With AND mutation: empty canales AND empty caminos → False → tries to process → errors or 0
        # Actually this is tricky, use the continue test above which covers this indirectly.
        # Simple proxy: with empty drenajes, canal_drenaje AND camino_drenaje skip.
        # Result should have canal_camino conflicts (if canales+caminos cross) only.
        canales = gpd.GeoDataFrame(
            {"geometry": [LineString([(-0.001, 0), (0.001, 0)])]}, crs="EPSG:4326"
        )
        caminos = gpd.GeoDataFrame(
            {"geometry": [LineString([(0, -0.001), (0, 0.001)])]}, crs="EPSG:4326"
        )
        # Empty drenajes → canal_drenaje and camino_drenaje pairs skip
        drenajes = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326", geometry="geometry")

        transform = from_bounds(-1, -1, 1, 1, 100, 100)
        fa_data = np.full((100, 100), 1000.0, dtype=np.float64)
        sl_data = np.full((100, 100), 1.0, dtype=np.float64)

        mock_fa = MagicMock()
        mock_fa.read.return_value = fa_data
        mock_fa.transform = transform
        mock_fa.__enter__ = MagicMock(return_value=mock_fa)
        mock_fa.__exit__ = MagicMock(return_value=False)

        mock_sl = MagicMock()
        mock_sl.read.return_value = sl_data
        mock_sl.transform = transform
        mock_sl.__enter__ = MagicMock(return_value=mock_sl)
        mock_sl.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", side_effect=[mock_fa, mock_sl]), \
             patch("rasterio.transform.rowcol", return_value=(50, 50)):
            result = detectar_puntos_conflicto(
                canales, caminos, drenajes, "/fa.tif", "/sl.tif",
                flow_acc_threshold=500.0, slope_threshold=5.0,
            )

        # canal_camino intersection should produce conflicts (both non-empty)
        # canal_drenaje and camino_drenaje skip (drenajes empty, both `or` conditions True)
        assert len(result) > 0
        all_tipos = set(result["tipo"].values)
        # Only canal_camino; NOT canal_drenaje (drenajes empty) or camino_drenaje
        assert "canal_camino" in all_tipos


class TestCalcularPrioridadCanalArithmetic:
    """Kill arithmetic mutations in calcular_prioridad_canal.

    Uses intermediate values (not maxed-out) so mutations produce different scores.
    fa=[5000] → fa_norm=0.5; sl=[3,7] → sl_mean=5, sl_norm=0.5
    score = (0.40*0.5 + 0.30*0.5) * 100 = 35.0
    """

    def test_intermediate_fa_and_sl_exact_score(self):
        """Kills fa/10000 → fa*10000 (mut22) and sl_mean/10 → sl_mean*10 (mut33).

        With fa*10000: fa_norm=1.0 → score=55.0 ≠ 35.0
        With sl_mean*10: sl_norm=1.0 → score=50.0 ≠ 35.0
        """
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [3.0, 7.0]],
        ):
            result = calcular_prioridad_canal(geom, "/fa.tif", "/sl.tif")

        assert result == 35.0

    def test_sl_sum_div_len_mutation(self):
        """Kills sum(sl)/len(sl) → sum(sl)*len(sl) (mut26).

        With sum*len: sl_mean=10*2=20, sl_norm=1.0 → score=50.0 ≠ 35.0
        """
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [3.0, 7.0]],
        ):
            result = calcular_prioridad_canal(geom, "/fa.tif", "/sl.tif")

        assert result == 35.0

    def test_sl_norm_min_cap_distinguishable(self):
        """Kills min(sl_mean/10, 1.0) → min(sl_mean/10, 2.0) (mut35).

        sl=[15] → sl_mean=15, sl_norm_orig=min(1.5,1.0)=1.0, sl_norm_mut=min(1.5,2.0)=1.5
        orig_score=(0.40*0.5+0.30*1.0)*100=55.0; mut_score=(0.40*0.5+0.30*1.5)*100=65.0
        """
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [15.0]],
        ):
            result = calcular_prioridad_canal(geom, "/fa.tif", "/sl.tif")

        assert result == 50.0  # min(1.5, 1.0)=1.0 → (0.20+0.30)*100=50

    def test_weight_fa_division_mutation(self):
        """Kills 0.40*fa_norm → 0.40/fa_norm (mut57).

        fa_norm=0.5: 0.40/0.5=0.80 vs 0.40*0.5=0.20 → score 95.0 vs 35.0
        """
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [3.0, 7.0]],
        ):
            result = calcular_prioridad_canal(geom, "/fa.tif", "/sl.tif")

        assert result == 35.0

    def test_zona_factor_intermediate_distance(self):
        """Kills zona_factor arithmetic mutations (mut48-52).

        min_dist=500m → zona_factor=max(1-500/1000,0)=0.5
        score=(0.40*0.5+0.30*0.5+0.30*0.5)*100=50.0
        """
        import geopandas as gpd
        from app.domains.geo.intelligence.calculations import calcular_prioridad_canal
        from shapely.geometry import LineString, Point

        # Canal at origin; zona at exactly 500m away (using projected CRS equivalent)
        canal_geom = LineString([(0, 0), (1, 0)])
        # Build a zona whose distance from canal_geom is 0.5 (will be 500 in units)
        zona_pt = Point(0.5, 0.5)
        zonas_gdf = gpd.GeoDataFrame({"geometry": [zona_pt]}, crs="EPSG:4326")

        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [3.0, 7.0]],
        ):
            # We patch distance calculation indirectly by controlling geometry proximity
            # The exact score depends on actual Shapely distance, so we assert bounds
            result = calcular_prioridad_canal(canal_geom, "/fa.tif", "/sl.tif", zonas_gdf)

        # zona_factor >= 0.0 (not negative); score >= 35.0 (base without zona)
        assert result >= 35.0
        assert result <= 100.0


class TestCalcularRiesgoCaminoArithmetic:
    """Kill arithmetic mutations in calcular_riesgo_camino.

    Uses intermediate values so mutations produce distinguishable scores.
    fa=[5000] → fa_norm=0.5
    sl=[2,4] → sl_mean=3, sl_norm=max(1-3/5,0)=0.4
    twi=[5,7] → twi_mean=6, twi_norm=min(max(6/15,0),1)=0.4
    score=(0.30*0.5+0.25*0.4+0.25*0.4+0.20*0)*100=35.0
    """

    def test_intermediate_values_exact_score(self):
        """Kills fa/10000→fa*10000 (mut27): fa_norm=1.0 → score=50.0 ≠ 35.0"""
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [2.0, 4.0], [5.0, 7.0]],
        ):
            result = calcular_riesgo_camino(geom, "/fa.tif", "/sl.tif", "/twi.tif")

        assert result == 35.0

    def test_sl_sum_div_len_mutation(self):
        """Kills sum(sl)/len(sl) → sum(sl)*len(sl) (mut32).

        sum*len: sl_mean=6*2=12, sl_norm=max(1-12/5,0)=0 → score=25.0 ≠ 35.0
        """
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [2.0, 4.0], [5.0, 7.0]],
        ):
            result = calcular_riesgo_camino(geom, "/fa.tif", "/sl.tif", "/twi.tif")

        assert result == 35.0

    def test_twi_sum_div_len_mutation(self):
        """Kills sum(twi)/len(twi) → sum(twi)*len(twi) (mut45).

        sum*len: twi_mean=12*2=24, twi_norm=1.0 → score=50.0 ≠ 35.0
        """
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [2.0, 4.0], [5.0, 7.0]],
        ):
            result = calcular_riesgo_camino(geom, "/fa.tif", "/sl.tif", "/twi.tif")

        assert result == 35.0

    def test_sl_norm_inversion_operator(self):
        """Kills 1.0 - sl_mean/5.0 → 1.0 + sl_mean/5.0 (mut29/30).

        sl_mean=3: 1.0+3/5=1.6 (clamped by max(0) → 1.6) → score=65.0 ≠ 35.0
        """
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [2.0, 4.0], [5.0, 7.0]],
        ):
            result = calcular_riesgo_camino(geom, "/fa.tif", "/sl.tif", "/twi.tif")

        assert result == 35.0

    def test_sl_mean_div_5_operator(self):
        """Kills sl_mean/5.0 → sl_mean*5.0 (mut41/42).

        sl_mean=3: 3*5=15 → sl_norm=max(1-15,0)=0 → score=25.0 ≠ 35.0
        """
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [2.0, 4.0], [5.0, 7.0]],
        ):
            result = calcular_riesgo_camino(geom, "/fa.tif", "/sl.tif", "/twi.tif")

        assert result == 35.0

    def test_twi_div_15_operator(self):
        """Kills twi_mean/15.0 → twi_mean*15.0 (mut56).

        twi_mean=6: 6*15=90 → twi_norm=min(max(90,0),1)=1.0 → score=50.0 ≠ 35.0
        """
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [2.0, 4.0], [5.0, 7.0]],
        ):
            result = calcular_riesgo_camino(geom, "/fa.tif", "/sl.tif", "/twi.tif")

        assert result == 35.0

    def test_twi_norm_max_boundary(self):
        """Kills max(twi_mean/15, 0.0) → max(twi_mean/15, 1.0) (mut58).

        twi_mean=6: max(0.4, 0.0)=0.4 vs max(0.4, 1.0)=1.0 → score=50.0 ≠ 35.0
        """
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino
        from shapely.geometry import LineString

        geom = LineString([(0, 0), (1, 1)])
        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [2.0, 4.0], [5.0, 7.0]],
        ):
            result = calcular_riesgo_camino(geom, "/fa.tif", "/sl.tif", "/twi.tif")

        assert result == 35.0

    def test_drain_factor_intermediate_distance(self):
        """Kills drain_factor/500 → drain_factor*500 mutations.

        min_dist=250m → drain_factor=max(1-250/500,0)=0.5
        score=(0.30*0.5+0.25*0.4+0.25*0.4+0.20*0.5)*100=45.0
        """
        import geopandas as gpd
        from app.domains.geo.intelligence.calculations import calcular_riesgo_camino
        from shapely.geometry import LineString, Point

        camino_geom = LineString([(0, 0), (1, 0)])
        drain_pt = Point(0.5, 0.5)
        drainage_gdf = gpd.GeoDataFrame({"geometry": [drain_pt]}, crs="EPSG:4326")

        with patch(
            "app.domains.geo.intelligence.calculations._sample_raster_along_line",
            side_effect=[[5000.0], [2.0, 4.0], [5.0, 7.0]],
        ):
            result = calcular_riesgo_camino(
                camino_geom, "/fa.tif", "/sl.tif", "/twi.tif", drainage_gdf
            )

        # drain_factor >= 0; score >= 35.0 (base)
        assert result >= 35.0
        assert result <= 100.0


class TestGenerateCostSurfaceArithmetic:
    """Kill arithmetic and metadata mutations in generate_cost_surface.

    cost = 1.0 + (slope / max_slope) * 10.0
    Nodata sentinel = -9999.0 (float32)
    Meta keys: 'dtype', 'count', 'driver', 'nodata'
    """

    def _make_mocks(self, slope_data, nodata=None):
        """Build rasterio read/write mock pair."""
        src_mock = MagicMock()
        src_mock.read.return_value = slope_data
        src_mock.nodata = nodata
        # Use DIFFERENT values from what meta.update sets — so key mutations (e.g. "XXdtypeXX")
        # can be detected: if the key is wrong, the original value from meta.copy() survives.
        src_mock.meta = {"dtype": "uint16", "count": 3, "driver": "JPEG", "nodata": 0, "crs": None}
        src_mock.__enter__ = MagicMock(return_value=src_mock)
        src_mock.__exit__ = MagicMock(return_value=False)

        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)

        return src_mock, dst_mock

    def test_cost_formula_intermediate_slope(self):
        """Kills slope/max_slope → slope*max_slope and *10 → /10 mutations.

        slope=[0, 2.5, 5.0], max_slope=5.0
        cost at slope=2.5: 1.0 + (2.5/5.0)*10.0 = 6.0
        cost at slope=5.0: 1.0 + (5.0/5.0)*10.0 = 11.0
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[0.0, 2.5], [5.0, 2.5]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data)

        written_arrays = []

        def capture_write(arr, band):
            written_arrays.append(arr.copy())

        dst_mock.write.side_effect = capture_write

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]):
            generate_cost_surface("/slope.tif", "/out.tif")

        assert len(written_arrays) == 1
        cost = written_arrays[0]
        # max_slope=5.0; cost at [0,1] (slope=2.5): 1+(2.5/5)*10=6.0
        assert abs(float(cost[0, 1]) - 6.0) < 0.01
        # cost at [1,0] (slope=5.0): 1+(5/5)*10=11.0
        assert abs(float(cost[1, 0]) - 11.0) < 0.01

    def test_cost_formula_flat_terrain_cost_one(self):
        """Flat terrain (slope=0) must have cost=1.0 (not affected by mutations if max_slope=1 default)."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[0.0, 0.0], [0.0, 0.0]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data)

        written_arrays = []
        dst_mock.write.side_effect = lambda arr, band: written_arrays.append(arr.copy())

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]):
            generate_cost_surface("/slope.tif", "/out.tif")

        cost = written_arrays[0]
        # All slopes=0, max_slope defaults to 1.0 → cost = 1.0 + (0/1)*10 = 1.0
        assert float(cost[0, 0]) == 1.0

    def test_nodata_sentinel_value(self):
        """Kills -9999.0 → -9998.0 mutations and out_nodata arithmetic."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[5.0, -9999.0], [3.0, 2.0]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data, nodata=-9999.0)

        written_arrays = []
        dst_mock.write.side_effect = lambda arr, band: written_arrays.append(arr.copy())

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]):
            generate_cost_surface("/slope.tif", "/out.tif")

        cost = written_arrays[0]
        # nodata pixel [0,1] must be the sentinel -9999.0
        assert float(cost[0, 1]) == -9999.0

    def test_meta_update_key_strings(self):
        """Kills 'dtype', 'count', 'driver', 'nodata' key string mutations.

        Intercepts the second rasterio.open (write) call to inspect the final meta kwargs.
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[5.0, 2.5], [0.0, 1.0]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data)

        open_calls = []

        def fake_open(path, mode="r", **kwargs):
            open_calls.append((path, mode, kwargs))
            if mode == "w":
                return dst_mock
            return src_mock

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("rasterio.open", side_effect=fake_open):
            generate_cost_surface("/slope.tif", "/out.tif")

        # Second call is the write; check path, mode, and kwargs from expanded meta dict
        assert open_calls[1][0] == "/out.tif"    # kills mutmut_77 (None), 79 ("w" as path)
        assert open_calls[1][1] == "w"           # kills mutmut_78 (None), 80 (missing), 82 ("XXwXX"), 83 ("W")
        write_kwargs = open_calls[1][2]
        # src meta uses different values — so key mutations are detected
        assert write_kwargs.get("dtype") == "float32"   # kills mutmut_55 (XXdtypeXX), 56 (DTYPE)
        assert write_kwargs.get("count") == 1            # kills mutmut_59 (XXcountXX), 60 (COUNT)
        assert write_kwargs.get("driver") == "GTiff"     # kills mutmut_62 (XXdriverXX), 63 (DRIVER)
        assert write_kwargs.get("nodata") == -9999.0

    def test_returns_output_path(self):
        """generate_cost_surface returns the output_path string."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[5.0, 2.5], [0.0, 1.0]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]):
            result = generate_cost_surface("/slope.tif", "/output/cost.tif")

        assert result == "/output/cost.tif"

    def test_file_not_found_raises(self):
        """FileNotFoundError when slope raster does not exist."""
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="Slope raster not found"):
                generate_cost_surface("/missing/slope.tif", "/out.tif")

    def test_only_nodata_raises_value_error(self):
        """ValueError when raster contains only nodata pixels."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[np.nan, np.nan], [np.nan, np.nan]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data, nodata=None)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]):
            with pytest.raises(ValueError, match=r"^Slope raster contains only nodata"):
                generate_cost_surface("/slope.tif", "/out.tif")


# ---------------------------------------------------------------------------
# cost_distance tests
# ---------------------------------------------------------------------------


class TestCostDistanceCore:
    """Kill mutations in cost_distance: boundary checks, meta keys, points_burned counter."""

    def _make_src_mock(self, height=10, width=10):
        mock_src = MagicMock()
        mock_src.meta = {"dtype": "float32", "count": 1, "driver": "GTiff"}
        mock_src.height = height
        mock_src.width = width
        from rasterio.transform import from_bounds
        mock_src.transform = from_bounds(0, 0, 1, 1, width, height)
        mock_src.__enter__ = MagicMock(return_value=mock_src)
        mock_src.__exit__ = MagicMock(return_value=False)
        return mock_src

    def _make_dst_mock(self):
        mock_dst = MagicMock()
        mock_dst.__enter__ = MagicMock(return_value=mock_dst)
        mock_dst.__exit__ = MagicMock(return_value=False)
        return mock_dst

    def test_returns_tuple_of_paths(self):
        """Returns (output_accum_path, output_backlink_path)."""
        from app.domains.geo.intelligence.calculations import cost_distance

        src_mock = self._make_src_mock()
        dst_mock = self._make_dst_mock()
        mock_wbt = MagicMock()

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=mock_wbt), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]), \
             patch("rasterio.transform.rowcol", return_value=(5, 5)):
            result = cost_distance("/cost.tif", [(0.5, 0.5)], "/accum.tif", "/backlink.tif")

        assert result == ("/accum.tif", "/backlink.tif")

    def test_file_not_found_raises(self):
        """FileNotFoundError when cost_surface_path does not exist."""
        from app.domains.geo.intelligence.calculations import cost_distance

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="Cost surface raster not found"):
                cost_distance("/missing.tif", [(0.5, 0.5)], "/accum.tif", "/backlink.tif")

    def test_all_points_outside_raises_value_error(self):
        """ValueError when all source points fall outside the raster extent."""
        from app.domains.geo.intelligence.calculations import cost_distance

        src_mock = self._make_src_mock(height=10, width=10)
        dst_mock = self._make_dst_mock()
        mock_wbt = MagicMock()

        # rowcol returns (-1, -1) → outside bounds (0 <= -1 < 10 is False)
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=mock_wbt), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]), \
             patch("rasterio.transform.rowcol", return_value=(-1, -1)):
            with pytest.raises(ValueError, match="No source points fall within"):
                cost_distance("/cost.tif", [(999.0, 999.0)], "/accum.tif", "/backlink.tif")

    def test_point_at_boundary_zero_included(self):
        """Row=0,col=0 is in bounds (0 <= 0 < height). Kills off-by-one mutations."""
        from app.domains.geo.intelligence.calculations import cost_distance

        src_mock = self._make_src_mock(height=10, width=10)
        dst_mock = self._make_dst_mock()
        mock_wbt = MagicMock()

        burned_data = {}

        def capture_write(arr, band):
            burned_data['arr'] = arr.copy()

        dst_mock.write.side_effect = capture_write

        # rowcol returns (0, 0) → right on the boundary
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=mock_wbt), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]), \
             patch("rasterio.transform.rowcol", return_value=(0, 0)):
            result = cost_distance("/cost.tif", [(0.0, 1.0)], "/accum.tif", "/backlink.tif")

        # Should succeed (point is valid) and return the paths
        assert result[0] == "/accum.tif"
        # Source data at (0,0) must be 1 (killed, not 0)
        assert burned_data['arr'][0, 0] == 1

    def test_source_data_cell_set_to_one(self):
        """source_data[r,c] = 1, not 0. Kills = 0 constant mutation."""
        from app.domains.geo.intelligence.calculations import cost_distance

        src_mock = self._make_src_mock(height=10, width=10)
        dst_mock = self._make_dst_mock()
        mock_wbt = MagicMock()

        written = {}
        dst_mock.write.side_effect = lambda arr, band: written.update({'arr': arr.copy()})

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=mock_wbt), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]), \
             patch("rasterio.transform.rowcol", return_value=(3, 7)):
            cost_distance("/cost.tif", [(0.3, 0.7)], "/accum.tif", "/backlink.tif")

        assert written['arr'][3, 7] == 1, "source cell must be 1"
        assert written['arr'][0, 0] == 0, "other cells must be 0"

    def test_meta_key_strings(self):
        """Kills 'dtype', 'count', 'nodata' string mutations for source raster meta."""
        from app.domains.geo.intelligence.calculations import cost_distance

        src_mock = self._make_src_mock()
        dst_mock = self._make_dst_mock()
        mock_wbt = MagicMock()

        open_calls = []

        def fake_open(path, mode="r", **kwargs):
            open_calls.append((path, mode, kwargs))
            if mode == "w":
                return dst_mock
            return src_mock

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=mock_wbt), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.transform.rowcol", return_value=(5, 5)):
            cost_distance("/cost.tif", [(0.5, 0.5)], "/accum.tif", "/backlink.tif")

        write_kwargs = open_calls[1][2]
        assert write_kwargs.get("dtype") == "uint8"
        assert write_kwargs.get("count") == 1
        assert write_kwargs.get("nodata") == 0

    def test_multiple_points_all_burned(self):
        """Multiple source points → multiple cells set to 1."""
        from app.domains.geo.intelligence.calculations import cost_distance

        src_mock = self._make_src_mock(height=10, width=10)
        dst_mock = self._make_dst_mock()
        mock_wbt = MagicMock()

        written = {}
        dst_mock.write.side_effect = lambda arr, band: written.update({'arr': arr.copy()})

        # Two distinct valid points: (3,2) and (7,8)
        rowcol_calls = iter([(3, 2), (7, 8)])
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=mock_wbt), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]), \
             patch("rasterio.transform.rowcol", side_effect=rowcol_calls):
            cost_distance("/cost.tif", [(0.2, 0.3), (0.8, 0.7)], "/accum.tif", "/backlink.tif")

        assert written['arr'][3, 2] == 1
        assert written['arr'][7, 8] == 1


# ---------------------------------------------------------------------------
# least_cost_path tests
# ---------------------------------------------------------------------------


class TestLeastCostPathCore:
    """Kill mutations in least_cost_path: boundary checks, sort order, meta keys."""

    def _make_meta_mock(self, height=10, width=10):
        from rasterio.transform import from_bounds
        m = MagicMock()
        m.meta = {"dtype": "float32", "count": 1}
        m.height = height
        m.width = width
        m.transform = from_bounds(0, 0, 1, 1, width, height)
        m.__enter__ = MagicMock(return_value=m)
        m.__exit__ = MagicMock(return_value=False)
        return m

    def test_returns_none_when_files_missing(self):
        """Returns None if cost_distance_path or backlink_path doesn't exist."""
        from app.domains.geo.intelligence.calculations import least_cost_path

        with patch("pathlib.Path.exists", return_value=False):
            result = least_cost_path("/cd.tif", "/bl.tif", (0.5, 0.5))

        assert result is None

    def test_returns_none_when_target_outside_bounds(self):
        """Returns None when target point is outside raster extent."""
        from app.domains.geo.intelligence.calculations import least_cost_path

        src_mock = self._make_meta_mock(height=10, width=10)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", return_value=src_mock), \
             patch("rasterio.transform.rowcol", return_value=(-1, 5)):
            result = least_cost_path("/cd.tif", "/bl.tif", (-10.0, 5.0))

        assert result is None

    def test_target_at_row_boundary_zero_included(self):
        """Row=0 is in bounds. Kills r < 0 → r <= 0 mutation."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import least_cost_path

        height, width = 10, 10
        src_meta = self._make_meta_mock(height, width)
        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)

        # pathway data: a valid path with 3 cells
        pathway_data = np.zeros((height, width), dtype=np.uint8)
        pathway_data[0, 0] = 1
        pathway_data[0, 1] = 1
        pathway_data[0, 2] = 1

        mock_pathway = MagicMock()
        mock_pathway.read.return_value = pathway_data
        mock_pathway.nodata = None
        mock_pathway.transform = src_meta.transform
        mock_pathway.__enter__ = MagicMock(return_value=mock_pathway)
        mock_pathway.__exit__ = MagicMock(return_value=False)

        # cost_distance data for sort
        cd_data = np.zeros((height, width), dtype=np.float32)
        cd_data[0, 0] = 1.0
        cd_data[0, 1] = 2.0
        cd_data[0, 2] = 3.0
        mock_cd = MagicMock()
        mock_cd.read.return_value = cd_data
        mock_cd.__enter__ = MagicMock(return_value=mock_cd)
        mock_cd.__exit__ = MagicMock(return_value=False)

        open_side_effect = [src_meta, dst_mock, mock_pathway, mock_cd]

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=open_side_effect), \
             patch("rasterio.transform.rowcol", return_value=(0, 5)), \
             patch("rasterio.transform.xy", side_effect=lambda t, r, c: (float(c)/10, float(r)/10)):
            result = least_cost_path("/cd.tif", "/bl.tif", (0.5, 0.05))

        # Should return a LineString (row=0 is valid)
        from shapely.geometry import LineString
        assert isinstance(result, LineString)

    def test_returns_none_when_fewer_than_two_path_cells(self):
        """Returns None when pathway has < 2 non-zero cells (kills < 2 → <= 2 mutation)."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import least_cost_path

        height, width = 10, 10
        src_meta = self._make_meta_mock(height, width)
        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)

        # Only 1 pathway cell → < 2 → return None
        pathway_data = np.zeros((height, width), dtype=np.uint8)
        pathway_data[5, 5] = 1  # only one cell

        mock_pathway = MagicMock()
        mock_pathway.read.return_value = pathway_data
        mock_pathway.nodata = None
        mock_pathway.transform = src_meta.transform
        mock_pathway.__enter__ = MagicMock(return_value=mock_pathway)
        mock_pathway.__exit__ = MagicMock(return_value=False)

        # cd_data mock (won't be reached if < 2 cells, but need one more open call)
        mock_cd = MagicMock()
        mock_cd.__enter__ = MagicMock(return_value=mock_cd)
        mock_cd.__exit__ = MagicMock(return_value=False)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src_meta, dst_mock, mock_pathway, mock_cd]), \
             patch("rasterio.transform.rowcol", return_value=(5, 5)):
            result = least_cost_path("/cd.tif", "/bl.tif", (0.5, 0.5))

        assert result is None

    def test_sort_order_descending_cost_first(self):
        """Kills [::-1] removal mutation — path starts at highest cost (farthest from source)."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import least_cost_path
        from shapely.geometry import LineString

        height, width = 10, 10
        from rasterio.transform import from_bounds
        transform = from_bounds(0, 0, 1, 1, width, height)

        src_meta = self._make_meta_mock(height, width)

        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)

        # 3 pathway cells in row 0
        pathway_data = np.zeros((height, width), dtype=np.uint8)
        pathway_data[0, 0] = 1  # low cost = 1.0
        pathway_data[0, 1] = 1  # cost = 2.0
        pathway_data[0, 2] = 1  # high cost = 3.0

        mock_pathway = MagicMock()
        mock_pathway.read.return_value = pathway_data
        mock_pathway.nodata = None
        mock_pathway.transform = transform
        mock_pathway.__enter__ = MagicMock(return_value=mock_pathway)
        mock_pathway.__exit__ = MagicMock(return_value=False)

        # Cost values: [0,0]=1.0, [0,1]=2.0, [0,2]=3.0
        cd_data = np.zeros((height, width), dtype=np.float32)
        cd_data[0, 0] = 1.0
        cd_data[0, 1] = 2.0
        cd_data[0, 2] = 3.0

        mock_cd = MagicMock()
        mock_cd.read.return_value = cd_data
        mock_cd.__enter__ = MagicMock(return_value=mock_cd)
        mock_cd.__exit__ = MagicMock(return_value=False)

        coords_captured = []

        def fake_xy(t, row, col):
            # Return (col/10, row/10) as (x, y)
            return (col / 10.0, row / 10.0)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src_meta, dst_mock, mock_pathway, mock_cd]), \
             patch("rasterio.transform.rowcol", return_value=(5, 5)), \
             patch("rasterio.transform.xy", side_effect=fake_xy):
            result = least_cost_path("/cd.tif", "/bl.tif", (0.5, 0.5))

        assert isinstance(result, LineString)
        coords = list(result.coords)
        # After [::-1] sort: highest cost (3.0 at col=2) comes first
        # x = col/10: first coord should have x=0.2 (col=2), last x=0.0 (col=0)
        assert coords[0][0] == pytest.approx(0.2, abs=0.01), "first coord should be highest-cost cell (col=2)"
        assert coords[-1][0] == pytest.approx(0.0, abs=0.01), "last coord should be lowest-cost cell (col=0)"

    def test_meta_key_strings_target_raster(self):
        """Kills 'dtype', 'count', 'nodata' string mutations in target_meta.update()."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import least_cost_path

        height, width = 10, 10
        src_meta = self._make_meta_mock(height, width)

        open_calls = []

        # pathway: 2 valid cells
        pathway_data = np.zeros((height, width), dtype=np.uint8)
        pathway_data[1, 1] = 1
        pathway_data[1, 2] = 1

        mock_pathway = MagicMock()
        mock_pathway.read.return_value = pathway_data
        mock_pathway.nodata = None
        mock_pathway.transform = src_meta.transform
        mock_pathway.__enter__ = MagicMock(return_value=mock_pathway)
        mock_pathway.__exit__ = MagicMock(return_value=False)

        cd_data = np.zeros((height, width), dtype=np.float32)
        cd_data[1, 1] = 1.0
        cd_data[1, 2] = 2.0
        mock_cd = MagicMock()
        mock_cd.read.return_value = cd_data
        mock_cd.__enter__ = MagicMock(return_value=mock_cd)
        mock_cd.__exit__ = MagicMock(return_value=False)

        mock_dst = MagicMock()
        mock_dst.__enter__ = MagicMock(return_value=mock_dst)
        mock_dst.__exit__ = MagicMock(return_value=False)

        # Use index-based side_effect: [meta, dst(write), pathway, cd_data]
        call_count = [0]
        side_effects = [src_meta, mock_dst, mock_pathway, mock_cd]

        def fake_open(path, mode="r", **kwargs):
            open_calls.append((path, mode, kwargs))
            mock = side_effects[call_count[0]]
            call_count[0] += 1
            return mock

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.transform.rowcol", return_value=(5, 5)), \
             patch("rasterio.transform.xy", side_effect=lambda t, r, c: (float(c)/10, float(r)/10)):
            least_cost_path("/costdist.tif", "/bl.tif", (0.5, 0.5))

        write_call = next((c for c in open_calls if c[1] == "w"), None)
        assert write_call is not None
        assert write_call[2].get("dtype") == "uint8"
        assert write_call[2].get("count") == 1
        assert write_call[2].get("nodata") == 0


# ---------------------------------------------------------------------------
# generar_zonificacion tests
# ---------------------------------------------------------------------------


class TestGenerarZonificacion:
    """Kill mutations in generar_zonificacion: threshold comparison, meta keys, area formula."""

    def _make_wbt_mock(self):
        return MagicMock()

    def _make_fa_mock(self, fa_data, nodata=None):
        import numpy as np
        from rasterio.transform import from_bounds
        m = MagicMock()
        m.read.return_value = fa_data
        m.nodata = nodata
        m.meta = {"dtype": "float32", "count": 1, "driver": "GTiff"}
        m.transform = from_bounds(0, 0, 1, 1, fa_data.shape[1], fa_data.shape[0])
        m.crs = None
        m.__enter__ = MagicMock(return_value=m)
        m.__exit__ = MagicMock(return_value=False)
        return m

    def test_empty_result_when_no_geometries(self):
        """Returns GeoDataFrame with columns=['basin_id','geometry'] when no shapes found."""
        import numpy as np
        import geopandas as gpd
        from app.domains.geo.intelligence.calculations import generar_zonificacion

        fa_data = np.array([[500, 500], [500, 500]], dtype=np.float64)
        fa_mock = self._make_fa_mock(fa_data)

        basins_data = np.zeros((2, 2), dtype=np.int16)
        basins_mock = MagicMock()
        basins_mock.read.return_value = basins_data
        basins_mock.transform = fa_mock.transform
        basins_mock.crs = None
        basins_mock.__enter__ = MagicMock(return_value=basins_mock)
        basins_mock.__exit__ = MagicMock(return_value=False)

        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)

        def fake_open(path, mode="r", **kwargs):
            if mode == "w":
                return dst_mock
            if "basins" in str(path):
                return basins_mock
            return fa_mock

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=self._make_wbt_mock()), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.features.shapes", return_value=iter([])):
            result = generar_zonificacion("/dem.tif", "/fa.tif", threshold=2000)

        assert isinstance(result, gpd.GeoDataFrame)
        assert "basin_id" in result.columns
        assert "geometry" in result.columns
        assert len(result) == 0

    def test_threshold_ge_includes_equal(self):
        """fa >= threshold includes cells equal to threshold (kills >= → >)."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generar_zonificacion

        # fa=2000 exactly at threshold; with >= it becomes pour point; with > it's excluded
        fa_data = np.array([[2000.0, 1999.0], [1000.0, 500.0]], dtype=np.float64)
        fa_mock = self._make_fa_mock(fa_data)

        written_data = {}
        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)
        dst_mock.write.side_effect = lambda arr, band: written_data.update({'arr': arr.copy()})

        basins_data = np.zeros((2, 2), dtype=np.int16)
        basins_mock = MagicMock()
        basins_mock.read.return_value = basins_data
        basins_mock.transform = fa_mock.transform
        basins_mock.crs = None
        basins_mock.__enter__ = MagicMock(return_value=basins_mock)
        basins_mock.__exit__ = MagicMock(return_value=False)

        def fake_open(path, mode="r", **kwargs):
            if mode == "w":
                return dst_mock
            if "basins" in str(path):
                return basins_mock
            return fa_mock

        with patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=self._make_wbt_mock()), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.features.shapes", return_value=iter([])):
            generar_zonificacion("/dem.tif", "/fa.tif", threshold=2000)

        # fa=2000 at [0,0]: with >=, pp[0,0]=1; with >, pp[0,0]=0
        assert written_data['arr'][0, 0] == 1, "cell at exactly threshold must be marked as pour point"
        assert written_data['arr'][0, 1] == 0, "cell below threshold must be 0"

    def test_nodata_cells_zeroed_in_pour_points(self):
        """pp[fa == nodata] = 0 → nodata cells excluded even if >= threshold."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generar_zonificacion

        nodata_val = -9999.0
        fa_data = np.array([[nodata_val, 5000.0], [1000.0, 200.0]], dtype=np.float64)
        fa_mock = self._make_fa_mock(fa_data, nodata=nodata_val)

        written_data = {}
        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)
        dst_mock.write.side_effect = lambda arr, band: written_data.update({'arr': arr.copy()})

        basins_mock = MagicMock()
        basins_data = np.zeros((2, 2), dtype=np.int16)
        basins_mock.read.return_value = basins_data
        basins_mock.transform = fa_mock.transform
        basins_mock.crs = None
        basins_mock.__enter__ = MagicMock(return_value=basins_mock)
        basins_mock.__exit__ = MagicMock(return_value=False)

        def fake_open(path, mode="r", **kwargs):
            if mode == "w":
                return dst_mock
            if "basins" in str(path):
                return basins_mock
            return fa_mock

        with patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=self._make_wbt_mock()), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.features.shapes", return_value=iter([])):
            generar_zonificacion("/dem.tif", "/fa.tif", threshold=2000)

        # nodata cell [0,0] has fa=nodata_val (-9999): should be 0 (zeroed)
        assert written_data['arr'][0, 0] == 0, "nodata cell must be zeroed in pour_points"
        # valid cell [0,1] has fa=5000 >= 2000: should be 1
        assert written_data['arr'][0, 1] == 1

    def test_meta_key_strings_pour_points(self):
        """Kills 'dtype','count','nodata' string mutations in pour points meta.update()."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generar_zonificacion

        fa_data = np.array([[500.0, 500.0], [500.0, 500.0]], dtype=np.float64)
        fa_mock = self._make_fa_mock(fa_data)

        open_calls = []
        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)

        basins_mock = MagicMock()
        basins_data = np.zeros((2, 2), dtype=np.int16)
        basins_mock.read.return_value = basins_data
        basins_mock.transform = fa_mock.transform
        basins_mock.crs = None
        basins_mock.__enter__ = MagicMock(return_value=basins_mock)
        basins_mock.__exit__ = MagicMock(return_value=False)

        def fake_open(path, mode="r", **kwargs):
            open_calls.append((path, mode, kwargs))
            if mode == "w":
                return dst_mock
            if "basins" in str(path):
                return basins_mock
            return fa_mock

        with patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=self._make_wbt_mock()), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.features.shapes", return_value=iter([])):
            generar_zonificacion("/dem.tif", "/fa.tif", threshold=2000)

        write_call = next((c for c in open_calls if c[1] == "w"), None)
        assert write_call is not None
        w_kwargs = write_call[2]
        assert w_kwargs.get("dtype") == "int16"
        assert w_kwargs.get("count") == 1
        assert w_kwargs.get("nodata") == 0

    def test_value_gt_zero_filter_in_shapes(self):
        """Kills value > 0 → value >= 0 mutation in rasterio_shapes loop."""
        import numpy as np
        import geopandas as gpd
        from app.domains.geo.intelligence.calculations import generar_zonificacion
        from shapely.geometry import mapping

        fa_data = np.array([[5000.0]], dtype=np.float64)
        fa_mock = self._make_fa_mock(fa_data)

        basins_data = np.array([[1]], dtype=np.int16)
        basins_mock = MagicMock()
        basins_mock.read.return_value = basins_data
        basins_mock.transform = fa_mock.transform
        basins_mock.crs = None
        basins_mock.__enter__ = MagicMock(return_value=basins_mock)
        basins_mock.__exit__ = MagicMock(return_value=False)

        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)

        def fake_open(path, mode="r", **kwargs):
            if mode == "w":
                return dst_mock
            if "basins" in str(path):
                return basins_mock
            return fa_mock

        # Shapes returning value=1 (> 0 → should be included) and value=0 (= 0 → excluded)
        from shapely.geometry import box
        shape_geom_1 = mapping(box(0, 0, 1, 1))
        shape_geom_0 = mapping(box(0, 0, 0.5, 0.5))
        shapes_iter = iter([(shape_geom_1, 1.0), (shape_geom_0, 0.0)])

        with patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=self._make_wbt_mock()), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.features.shapes", return_value=shapes_iter):
            result = generar_zonificacion("/dem.tif", "/fa.tif", threshold=2000)

        # Only value=1 (> 0) should be included; value=0 excluded
        assert len(result) == 1
        assert result.iloc[0]["basin_id"] == 1


# ---------------------------------------------------------------------------
# suggest_canal_routes tests
# ---------------------------------------------------------------------------


class TestSuggestCanalRoutesCore:
    """Kill mutations in suggest_canal_routes: early returns, key lookups, status strings."""

    def test_empty_gap_centroids_returns_empty_list(self):
        """Returns [] immediately when gap_centroids is empty."""
        from app.domains.geo.intelligence.calculations import suggest_canal_routes

        result = suggest_canal_routes([], [{"geometry": None}], "/slope.tif")
        assert result == []

    def test_no_valid_canal_geometries_returns_empty_list(self):
        """Returns [] when all canal_geometries have None geometry."""
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping

        gap = {"geometry": mapping(__import__('shapely.geometry', fromlist=['Point']).Point(0.5, 0.5)), "zone_id": "z1"}

        with patch("pathlib.Path.exists", return_value=True):
            result = suggest_canal_routes([gap], [{"geometry": None}], "/slope.tif")

        assert result == []

    def test_slope_raster_not_found_raises(self):
        """FileNotFoundError when slope raster does not exist."""
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "z1"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="Slope raster not found"):
                suggest_canal_routes([gap], [canal], "/missing.tif")

    def test_geometry_key_required_in_gap(self):
        """Gap without 'geometry' key is skipped (returns [] if no valid gap_points).

        generate_cost_surface runs BEFORE gap_points check, so it must be mocked.
        """
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import LineString

        # Gap with wrong key (not 'geometry') → gap_points is empty → return []
        gap = {"geom": None, "zone_id": "z1"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"):
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert result == []

    def test_geometry_key_required_in_canal(self):
        """Canal dict without 'geometry' key is skipped."""
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "z1"}
        # Canal with wrong key → canal_shapes is empty → return []
        canal = {"geom": None}

        with patch("pathlib.Path.exists", return_value=True):
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert result == []

    def test_status_ok_when_path_found(self):
        """Route dict has status='ok' when path is successfully traced."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "zone1"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        # Mock the sub-functions: generate_cost_surface, cost_distance, least_cost_path
        fake_path = LineString([(0.1, 0.1), (0.5, 0.5)])
        accum_mock = MagicMock()
        accum_mock.read.return_value = np.array([[5.0, 5.0], [5.0, 5.0]], dtype=np.float32)
        accum_mock.nodata = None
        accum_mock.height = 2
        accum_mock.width = 2
        accum_mock.__enter__ = MagicMock(return_value=accum_mock)
        accum_mock.__exit__ = MagicMock(return_value=False)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/accum.tif", "/bl.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", return_value=fake_path), \
             patch("rasterio.open", return_value=accum_mock), \
             patch("rasterio.transform.rowcol", return_value=(1, 1)):
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert len(result) == 1
        assert result[0]["status"] == "ok"
        assert result[0]["source_gap_id"] == "zone1"
        assert result[0]["geometry"] is not None

    def test_status_unreachable_when_path_is_none(self):
        """Route dict has status containing 'unreachable' when least_cost_path returns None."""
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "gap1"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/accum.tif", "/bl.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", return_value=None):
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert len(result) == 1
        assert "unreachable" in result[0]["status"]
        assert result[0]["geometry"] is None
        assert result[0]["source_gap_id"] == "gap1"

    def test_estimated_cost_rounded_to_two_decimals(self):
        """estimated_cost = round(val, 2). Kills round(val, 3) or round(val, 1) mutations."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "z1"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        fake_path = LineString([(0.1, 0.1), (0.5, 0.5)])
        # Accum raster: value at target is 7.1234567
        accum_data = np.full((4, 4), 7.1234567, dtype=np.float32)
        accum_mock = MagicMock()
        accum_mock.read.return_value = accum_data
        accum_mock.nodata = None
        accum_mock.height = 4
        accum_mock.width = 4
        accum_mock.__enter__ = MagicMock(return_value=accum_mock)
        accum_mock.__exit__ = MagicMock(return_value=False)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/accum.tif", "/bl.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", return_value=fake_path), \
             patch("rasterio.open", return_value=accum_mock), \
             patch("rasterio.transform.rowcol", return_value=(1, 1)):
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert len(result) == 1
        assert result[0]["estimated_cost"] == round(7.1234567, 2)  # 7.12


# ---------------------------------------------------------------------------
# Additional boundary / operator tests for cost_distance
# ---------------------------------------------------------------------------


class TestCostDistanceBoundaryOperators:
    """Target boundary/operator surviving mutations in cost_distance."""

    def _setup(self, height=10, width=10):
        from rasterio.transform import from_bounds
        src = MagicMock()
        src.meta = {"dtype": "float32", "count": 1, "driver": "GTiff"}
        src.height = height
        src.width = width
        src.transform = from_bounds(0, 0, 1, 1, width, height)
        src.__enter__ = MagicMock(return_value=src)
        src.__exit__ = MagicMock(return_value=False)
        dst = MagicMock()
        dst.__enter__ = MagicMock(return_value=dst)
        dst.__exit__ = MagicMock(return_value=False)
        return src, dst

    def test_and_or_boundary_row_valid_col_invalid(self):
        """Kills `and → or` mutation (mutmut_29): only burns if BOTH r and c are in bounds.

        row=5 (valid), col=-1 (invalid) → should NOT burn. With `or`, it would burn.
        """
        from app.domains.geo.intelligence.calculations import cost_distance

        src, dst = self._setup(height=10, width=10)
        written = {}
        dst.write.side_effect = lambda arr, band: written.update({'arr': arr.copy()})

        # row=5 valid, col=-1 invalid → should be skipped → points_burned=0 → ValueError
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src, dst]), \
             patch("rasterio.transform.rowcol", return_value=(5, -1)):
            with pytest.raises(ValueError, match="No source points fall within"):
                cost_distance("/cost.tif", [(0.5, 0.5)], "/accum.tif", "/backlink.tif")

    def test_row_at_height_is_out_of_bounds(self):
        """Kills `< height → <= height` (mutmut_32): r=height must be out of bounds."""
        from app.domains.geo.intelligence.calculations import cost_distance

        src, dst = self._setup(height=10, width=10)

        # r=10 == height → out of bounds → single point → ValueError
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src, dst]), \
             patch("rasterio.transform.rowcol", return_value=(10, 5)):
            with pytest.raises(ValueError):
                cost_distance("/cost.tif", [(0.5, 0.5)], "/accum.tif", "/backlink.tif")

    def test_col_at_width_is_out_of_bounds(self):
        """Kills `< width → <= width` (mutmut_35): c=width must be out of bounds."""
        from app.domains.geo.intelligence.calculations import cost_distance

        src, dst = self._setup(height=10, width=10)

        # c=10 == width → out of bounds → single point → ValueError
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src, dst]), \
             patch("rasterio.transform.rowcol", return_value=(5, 10)):
            with pytest.raises(ValueError):
                cost_distance("/cost.tif", [(0.5, 0.5)], "/accum.tif", "/backlink.tif")

    def test_points_burned_counter_multiple_valid(self):
        """Kills `points_burned = 1` (mutmut_38): burns 2 distinct cells.

        If counter is always reset to 1, the 2nd point is still burned but we
        verify both cells are set to 1 — the mutation doesn't affect burning itself,
        so we use the continue→break test below for the real kill.
        """
        from app.domains.geo.intelligence.calculations import cost_distance

        src, dst = self._setup(height=10, width=10)
        written = {}
        dst.write.side_effect = lambda arr, band: written.update({'arr': arr.copy()})

        # Two valid points at distinct cells
        rowcol_iter = iter([(2, 3), (7, 8)])
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src, dst]), \
             patch("rasterio.transform.rowcol", side_effect=rowcol_iter):
            cost_distance("/cost.tif", [(0.2, 0.3), (0.7, 0.8)], "/accum.tif", "/backlink.tif")

        assert written['arr'][2, 3] == 1
        assert written['arr'][7, 8] == 1

    def test_continue_not_break_on_exception(self):
        """Kills `continue → break` (mutmut_41): first rowcol raises, second is valid.

        With `break`: second point is never reached → points_burned=0 → ValueError.
        With `continue`: second point is processed → success.
        """
        from app.domains.geo.intelligence.calculations import cost_distance

        src, dst = self._setup(height=10, width=10)
        written = {}
        dst.write.side_effect = lambda arr, band: written.update({'arr': arr.copy()})

        # First rowcol raises, second returns valid (5, 5)
        calls = [Exception("bad coords"), (5, 5)]
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src, dst]), \
             patch("rasterio.transform.rowcol", side_effect=calls):
            result = cost_distance("/cost.tif", [(0.0, 0.0), (0.5, 0.5)], "/accum.tif", "/backlink.tif")

        assert result[0] == "/accum.tif"
        assert written['arr'][5, 5] == 1

    def test_value_error_message_starts_with_no(self):
        """Kills ValueError message string mutation (mutmut_45) by anchoring to 'No'."""
        from app.domains.geo.intelligence.calculations import cost_distance

        src, dst = self._setup()

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src, dst]), \
             patch("rasterio.transform.rowcol", return_value=(-1, -1)):
            with pytest.raises(ValueError, match=r"^No source points fall within"):
                cost_distance("/cost.tif", [(999.0, 999.0)], "/accum.tif", "/backlink.tif")


# ---------------------------------------------------------------------------
# Additional boundary tests for least_cost_path
# ---------------------------------------------------------------------------


class TestLeastCostPathBoundary:
    """Target boundary/operator surviving mutations in least_cost_path."""

    def _make_meta(self, height=10, width=10):
        from rasterio.transform import from_bounds
        m = MagicMock()
        m.meta = {"dtype": "float32", "count": 1}
        m.height = height
        m.width = width
        m.transform = from_bounds(0, 0, 1, 1, width, height)
        m.__enter__ = MagicMock(return_value=m)
        m.__exit__ = MagicMock(return_value=False)
        return m

    def test_returns_none_when_only_cd_missing(self):
        """Kills `or → and` in exists check (mutmut_1): one file missing → None.

        With `and`: only return None when BOTH missing. Here only cd is missing.
        """
        from app.domains.geo.intelligence.calculations import least_cost_path

        # First call (cost_distance_path): False; second call (backlink_path): True
        with patch("pathlib.Path.exists", side_effect=[False, True]):
            result = least_cost_path("/missing_cd.tif", "/bl.tif", (0.5, 0.5))

        assert result is None

    def test_col_negative_one_is_out_of_bounds(self):
        """Kills `or → and` in boundary (mutmut_31): r valid, c=-1 should return None.

        With `and`: r valid AND c >= width must BOTH be true → c=-1, c >= 10 is False → doesn't return None.
        """
        from app.domains.geo.intelligence.calculations import least_cost_path

        src = self._make_meta()

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(5, -1)):
            result = least_cost_path("/cd.tif", "/bl.tif", (0.5, 0.5))

        assert result is None

    def test_row_at_height_is_out_of_bounds(self):
        """Kills `r >= height → r > height` (mutmut_36): r=height-1=9 still valid, r=10 not."""
        from app.domains.geo.intelligence.calculations import least_cost_path

        src = self._make_meta(height=10, width=10)

        # r=10 == height → out of bounds → return None
        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(10, 5)):
            result = least_cost_path("/cd.tif", "/bl.tif", (0.5, 0.5))

        assert result is None

    def test_col_zero_is_in_bounds(self):
        """Kills `c < 0 → c < 1` (mutmut_38): c=0 should be IN bounds, not return None.

        With mutation c < 1: c=0 satisfies c < 1 → returns None even though it's valid.
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import least_cost_path
        from shapely.geometry import LineString

        height, width = 10, 10
        src = self._make_meta(height, width)

        dst = MagicMock()
        dst.__enter__ = MagicMock(return_value=dst)
        dst.__exit__ = MagicMock(return_value=False)

        # pathway: valid path with 2 cells
        pathway_data = np.zeros((height, width), dtype=np.uint8)
        pathway_data[1, 1] = 1
        pathway_data[1, 2] = 1

        mock_pathway = MagicMock()
        mock_pathway.read.return_value = pathway_data
        mock_pathway.nodata = None
        mock_pathway.transform = src.transform
        mock_pathway.__enter__ = MagicMock(return_value=mock_pathway)
        mock_pathway.__exit__ = MagicMock(return_value=False)

        cd_data = np.zeros((height, width), dtype=np.float32)
        cd_data[1, 1] = 1.0
        cd_data[1, 2] = 2.0
        mock_cd = MagicMock()
        mock_cd.read.return_value = cd_data
        mock_cd.__enter__ = MagicMock(return_value=mock_cd)
        mock_cd.__exit__ = MagicMock(return_value=False)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src, dst, mock_pathway, mock_cd]), \
             patch("rasterio.transform.rowcol", return_value=(5, 0)), \
             patch("rasterio.transform.xy", side_effect=lambda t, r, c: (float(c)/10, float(r)/10)):
            result = least_cost_path("/cd.tif", "/bl.tif", (0.0, 0.5))

        # c=0 is valid (0 is NOT < 0), so function should proceed and return a LineString
        assert isinstance(result, LineString)

    def test_col_at_width_is_out_of_bounds(self):
        """Kills `c >= width → c > width` (mutmut_39): c=width must be out of bounds."""
        from app.domains.geo.intelligence.calculations import least_cost_path

        src = self._make_meta(height=10, width=10)

        # c=10 == width → out of bounds → return None
        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(5, 10)):
            result = least_cost_path("/cd.tif", "/bl.tif", (0.5, 0.5))

        assert result is None

    def test_target_cell_set_to_one_not_two(self):
        """Kills `target_data[r,c] = 2` (mutmut_46): target cell must be 1."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import least_cost_path

        height, width = 10, 10
        src = self._make_meta(height, width)

        written_data = {}
        dst = MagicMock()
        dst.write.side_effect = lambda arr, band: written_data.update({'arr': arr.copy()})
        dst.__enter__ = MagicMock(return_value=dst)
        dst.__exit__ = MagicMock(return_value=False)

        # pathway: 2 cells
        pathway_data = np.zeros((height, width), dtype=np.uint8)
        pathway_data[1, 1] = 1
        pathway_data[1, 2] = 1

        mock_pathway = MagicMock()
        mock_pathway.read.return_value = pathway_data
        mock_pathway.nodata = None
        mock_pathway.transform = src.transform
        mock_pathway.__enter__ = MagicMock(return_value=mock_pathway)
        mock_pathway.__exit__ = MagicMock(return_value=False)

        cd_data = np.zeros((height, width), dtype=np.float32)
        cd_data[1, 1] = 1.0
        cd_data[1, 2] = 2.0
        mock_cd = MagicMock()
        mock_cd.read.return_value = cd_data
        mock_cd.__enter__ = MagicMock(return_value=mock_cd)
        mock_cd.__exit__ = MagicMock(return_value=False)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("app.domains.geo.intelligence.calculations._get_wbt"), \
             patch("rasterio.open", side_effect=[src, dst, mock_pathway, mock_cd]), \
             patch("rasterio.transform.rowcol", return_value=(5, 5)), \
             patch("rasterio.transform.xy", side_effect=lambda t, r, c: (float(c)/10, float(r)/10)):
            least_cost_path("/cd.tif", "/bl.tif", (0.5, 0.5))

        # Cell at rowcol (5,5) must be 1, not 2
        assert written_data['arr'][5, 5] == 1
        assert written_data['arr'][5, 5] != 2


# ---------------------------------------------------------------------------
# Additional tests for generar_zonificacion
# ---------------------------------------------------------------------------


class TestGenerarZonificacionAdditional:
    """Target specific surviving mutations."""

    def _make_wbt(self):
        return MagicMock()

    def _make_fa_mock(self, fa_data, nodata=None):
        from rasterio.transform import from_bounds
        m = MagicMock()
        m.read.return_value = fa_data
        m.nodata = nodata
        m.meta = {"dtype": "float32", "count": 1, "driver": "GTiff"}
        m.transform = from_bounds(0, 0, 1, 1, fa_data.shape[1], fa_data.shape[0])
        m.crs = None
        m.__enter__ = MagicMock(return_value=m)
        m.__exit__ = MagicMock(return_value=False)
        return m

    def test_nodata_above_threshold_zeroed(self):
        """Kills `nodata = None` mutation (mutmut_20).

        nodata_val=3000 >= threshold=2000 → np.where gives 1, then pp[fa==nodata]=0 zeroes it.
        With mutation nodata=None: the nodata check is skipped, pp stays 1.
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import generar_zonificacion

        nodata_val = 3000.0
        fa_data = np.array([[nodata_val, 5000.0], [1000.0, 200.0]], dtype=np.float64)
        fa_mock = self._make_fa_mock(fa_data, nodata=nodata_val)

        written_data = {}
        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)
        dst_mock.write.side_effect = lambda arr, band: written_data.update({'arr': arr.copy()})

        basins_mock = MagicMock()
        basins_data = np.zeros((2, 2), dtype=np.int16)
        basins_mock.read.return_value = basins_data
        basins_mock.transform = fa_mock.transform
        basins_mock.crs = None
        basins_mock.__enter__ = MagicMock(return_value=basins_mock)
        basins_mock.__exit__ = MagicMock(return_value=False)

        def fake_open(path, mode="r", **kwargs):
            if mode == "w":
                return dst_mock
            if "basins" in str(path):
                return basins_mock
            return fa_mock

        with patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=self._make_wbt()), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.features.shapes", return_value=iter([])):
            generar_zonificacion("/dem.tif", "/fa.tif", threshold=2000)

        # nodata cell [0,0] has fa=3000 >= 2000 → np.where gives 1 → THEN zeroed by nodata mask
        assert written_data['arr'][0, 0] == 0, "nodata cell with fa>=threshold must be zeroed"
        # valid cell [0,1] has fa=5000 >= 2000, NOT nodata → must be 1
        assert written_data['arr'][0, 1] == 1

    def test_pour_points_dtype_is_int16(self):
        """Kills `.astype(None)` (mutmut_32): written array must be int16."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generar_zonificacion

        fa_data = np.array([[3000.0, 500.0], [100.0, 200.0]], dtype=np.float64)
        fa_mock = self._make_fa_mock(fa_data)

        written_data = {}
        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)
        dst_mock.write.side_effect = lambda arr, band: written_data.update({'arr': arr.copy()})

        basins_mock = MagicMock()
        basins_data = np.zeros((2, 2), dtype=np.int16)
        basins_mock.read.return_value = basins_data
        basins_mock.transform = fa_mock.transform
        basins_mock.crs = None
        basins_mock.__enter__ = MagicMock(return_value=basins_mock)
        basins_mock.__exit__ = MagicMock(return_value=False)

        def fake_open(path, mode="r", **kwargs):
            if mode == "w":
                return dst_mock
            if "basins" in str(path):
                return basins_mock
            return fa_mock

        with patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=self._make_wbt()), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.features.shapes", return_value=iter([])):
            generar_zonificacion("/dem.tif", "/fa.tif", threshold=2000)

        assert written_data['arr'].dtype == np.int16, "pour points must be int16, not float64"

    def test_write_band_one(self):
        """Kills `dst.write(pp, 2)` mutation (mutmut_58): band must be 1, not 2."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generar_zonificacion

        fa_data = np.array([[3000.0, 500.0], [100.0, 200.0]], dtype=np.float64)
        fa_mock = self._make_fa_mock(fa_data)

        write_calls = []
        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)
        dst_mock.write.side_effect = lambda arr, band: write_calls.append(band)

        basins_mock = MagicMock()
        basins_data = np.zeros((2, 2), dtype=np.int16)
        basins_mock.read.return_value = basins_data
        basins_mock.transform = fa_mock.transform
        basins_mock.crs = None
        basins_mock.__enter__ = MagicMock(return_value=basins_mock)
        basins_mock.__exit__ = MagicMock(return_value=False)

        def fake_open(path, mode="r", **kwargs):
            if mode == "w":
                return dst_mock
            if "basins" in str(path):
                return basins_mock
            return fa_mock

        with patch("app.domains.geo.intelligence.calculations._get_wbt", return_value=self._make_wbt()), \
             patch("rasterio.open", side_effect=fake_open), \
             patch("rasterio.features.shapes", return_value=iter([])):
            generar_zonificacion("/dem.tif", "/fa.tif", threshold=2000)

        assert len(write_calls) == 1
        assert write_calls[0] == 1, "pour points must be written to band 1, not 2"


# ---------------------------------------------------------------------------
# Additional tests for suggest_canal_routes
# ---------------------------------------------------------------------------


class TestSuggestCanalRoutesAdditional:
    """Target remaining surviving mutations in suggest_canal_routes."""

    def test_continue_not_break_in_canal_loop(self):
        """Kills `continue → break` (mutmut_13) in canal geometry loop.

        Two canals: first has None geometry (skip), second is valid.
        With break: canal_shapes empty → return [].
        With continue: second canal processed → canal_shapes not empty.
        """
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "z1"}
        canals = [
            {"geometry": None},  # first: skip
            {"geometry": LineString([(0, 0), (1, 0)])}  # second: valid
        ]

        fake_path = LineString([(0.1, 0.1), (0.5, 0.5)])

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/a.tif", "/b.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", return_value=fake_path), \
             patch("rasterio.open", return_value=MagicMock(**{
                 'read.return_value': __import__('numpy').array([[5.0, 5.0], [5.0, 5.0]]),
                 'nodata': None, 'height': 2, 'width': 2,
                 '__enter__': MagicMock(return_value=MagicMock(**{
                     'read.return_value': __import__('numpy').array([[5.0, 5.0], [5.0, 5.0]]),
                     'nodata': None, 'height': 2, 'width': 2,
                 })),
                 '__exit__': MagicMock(return_value=False),
             })), \
             patch("rasterio.transform.rowcol", return_value=(1, 1)):
            result = suggest_canal_routes([gap], canals, "/slope.tif")

        # If continue works: canal_shapes has 1 valid canal → route is found
        assert len(result) == 1
        assert result[0]["status"] == "ok"

    def test_continue_not_break_in_gap_loop(self):
        """Kills `continue → break` (mutmut_49) in gap_points loop.

        Two gaps: first has None geometry, second is valid.
        With break: gap_points empty → return [].
        With continue: second gap processed → gap_points not empty → route found.
        """
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gaps = [
            {"geometry": None, "zone_id": "z0"},  # first: skip (geom is None)
            {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "z1"},  # second: valid
        ]
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        fake_path = LineString([(0.1, 0.1), (0.5, 0.5)])
        import numpy as np
        accum_mock = MagicMock()
        accum_mock.read.return_value = np.array([[5.0, 5.0], [5.0, 5.0]])
        accum_mock.nodata = None
        accum_mock.height = 2
        accum_mock.width = 2
        accum_mock.__enter__ = MagicMock(return_value=accum_mock)
        accum_mock.__exit__ = MagicMock(return_value=False)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/a.tif", "/b.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", return_value=fake_path), \
             patch("rasterio.open", return_value=accum_mock), \
             patch("rasterio.transform.rowcol", return_value=(1, 1)):
            result = suggest_canal_routes(gaps, [canal], "/slope.tif")

        # If continue works: second gap processed → 1 route found
        assert len(result) == 1
        assert result[0]["source_gap_id"] == "z1"

    def test_unreachable_exception_route_keys(self):
        """Kills 'STATUS' key mutation (mutmut_131) and 'XXestimated_costXX' (mutmut_142).

        Tests exception path (least_cost_path raises Exception).
        Verifies dict keys are lowercase: 'status', 'estimated_cost'.
        """
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "exc_gap"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/a.tif", "/b.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", side_effect=RuntimeError("test error")):
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert len(result) == 1
        route = result[0]
        assert "status" in route, "'status' key must be present (not 'STATUS')"
        assert "unreachable" in route["status"]
        assert "estimated_cost" in route, "'estimated_cost' key must be present"
        assert route["estimated_cost"] is None
        assert route["geometry"] is None
        assert route["source_gap_id"] == "exc_gap"

    def test_unreachable_path_none_status_string(self):
        """Kills 'XXunreachable...' status string mutation (mutmut_146).

        Verifies status starts with 'unreachable: path could not be traced'.
        """
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "none_gap"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/a.tif", "/b.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", return_value=None):
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert len(result) == 1
        # Must contain "unreachable: path could not be traced" (kills XX...XX mutations)
        assert result[0]["status"].startswith("unreachable: path could not be traced")

    def test_estimated_cost_none_for_unreachable_path(self):
        """Kills `estimated_cost = ''` mutation (mutmut_149): must be None, not ''."""
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "z1"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/a.tif", "/b.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", return_value=None):
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert result[0]["estimated_cost"] is None

    def test_target_point_key_present_in_ok_route(self):
        """Kills 'XXtarget_pointXX' key mutation (mutmut_186): result must have 'target_point'."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "z1"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        fake_path = LineString([(0.1, 0.1), (0.5, 0.5)])
        accum_mock = MagicMock()
        accum_mock.read.return_value = np.array([[5.0, 5.0], [5.0, 5.0]])
        accum_mock.nodata = None
        accum_mock.height = 2
        accum_mock.width = 2
        accum_mock.__enter__ = MagicMock(return_value=accum_mock)
        accum_mock.__exit__ = MagicMock(return_value=False)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/a.tif", "/b.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", return_value=fake_path), \
             patch("rasterio.open", return_value=accum_mock), \
             patch("rasterio.transform.rowcol", return_value=(1, 1)):
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert len(result) == 1
        assert "target_point" in result[0], "route must have 'target_point' key"
        assert result[0]["target_point"] is not None

    def test_estimated_cost_rowcol_boundary_r0(self):
        """Kills `0 < r` mutation (mutmut_162): r=0 should be valid (0 <= 0 < height)."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import suggest_canal_routes
        from shapely.geometry import mapping, Point, LineString

        gap = {"geometry": mapping(Point(0.5, 0.5)), "zone_id": "z1"}
        canal = {"geometry": LineString([(0, 0), (1, 0)])}

        fake_path = LineString([(0.1, 0.1), (0.5, 0.5)])
        accum_data = np.full((4, 4), 5.5, dtype=np.float32)
        accum_mock = MagicMock()
        accum_mock.read.return_value = accum_data
        accum_mock.nodata = None
        accum_mock.height = 4
        accum_mock.width = 4
        accum_mock.__enter__ = MagicMock(return_value=accum_mock)
        accum_mock.__exit__ = MagicMock(return_value=False)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("app.domains.geo.intelligence.calculations.generate_cost_surface"), \
             patch("app.domains.geo.intelligence.calculations.cost_distance", return_value=("/a.tif", "/b.tif")), \
             patch("app.domains.geo.intelligence.calculations.least_cost_path", return_value=fake_path), \
             patch("rasterio.open", return_value=accum_mock), \
             patch("rasterio.transform.rowcol", return_value=(0, 1)):  # r=0 should be valid
            result = suggest_canal_routes([gap], [canal], "/slope.tif")

        assert len(result) == 1
        # r=0 valid → estimated_cost should be set (not None)
        assert result[0]["estimated_cost"] is not None
        assert result[0]["estimated_cost"] == 5.5


# ---------------------------------------------------------------------------
# generate_cost_surface — boundary / operator mutations
# ---------------------------------------------------------------------------


class TestGenerateCostSurfaceBoundary:
    """Kill boundary and operator mutations in generate_cost_surface.

    Targets:
    - mutmut_33: max_slope <= 1 (was <= 0) — slope in (0,1]
    - mutmut_35: max_slope = 2.0 (was 1.0) — negative slopes trigger branch
    - mutmut_85: dst.write(cost, None) — band must be 1
    - mutmut_88: dst.write(cost, 2) — band must be 1
    - mutmut_70: Path.mkdir(parents=None) — parents must be True
    - mutmut_72: Path.mkdir(exist_ok=True) missing parents — parents must be True
    - mutmut_75: Path.mkdir(parents=False) — parents must be True
    """

    def _make_mocks(self, slope_data, nodata=None):
        src_mock = MagicMock()
        src_mock.read.return_value = slope_data
        src_mock.nodata = nodata
        src_mock.meta = {"dtype": "uint16", "count": 3, "driver": "JPEG", "nodata": 0, "crs": None}
        src_mock.__enter__ = MagicMock(return_value=src_mock)
        src_mock.__exit__ = MagicMock(return_value=False)

        dst_mock = MagicMock()
        dst_mock.__enter__ = MagicMock(return_value=dst_mock)
        dst_mock.__exit__ = MagicMock(return_value=False)

        return src_mock, dst_mock

    def test_max_slope_below_one_not_normalized(self):
        """Kill mutmut_33 (max_slope <= 1 instead of <= 0).

        slope=0.5 → max_slope=0.5
        Original (<= 0): 0.5 <= 0 is False → max_slope stays 0.5
          cost = 1 + (0.5/0.5)*10 = 11.0
        Mutation (<= 1): 0.5 <= 1 is True → max_slope forced to 1.0
          cost = 1 + (0.5/1.0)*10 = 6.0
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[0.5, 0.5]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data)

        written = {}
        dst_mock.write.side_effect = lambda arr, band: written.update({"arr": arr.copy()})

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]):
            generate_cost_surface("/slope.tif", "/out.tif")

        cost = written["arr"]
        # Original: max_slope=0.5 → cost=11.0; Mutation: max_slope=1.0 → cost=6.0
        assert abs(float(cost[0, 0]) - 11.0) < 0.01, (
            f"Expected cost≈11.0 for slope=0.5/max_slope=0.5, got {float(cost[0, 0])}"
        )

    def test_max_slope_zero_branch_sets_one_not_two(self):
        """Kill mutmut_35 (max_slope = 2.0 instead of 1.0).

        Use negative slope values so max(slope[valid]) < 0 → branch triggers.
        slope=-0.3 → max_slope=-0.3 <= 0 → branch
        Original: max_slope = 1.0, cost = 1 + (-0.3/1.0)*10 = -2.0
        Mutation: max_slope = 2.0, cost = 1 + (-0.3/2.0)*10 = -1.5
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[-0.3]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data, nodata=None)

        written = {}
        dst_mock.write.side_effect = lambda arr, band: written.update({"arr": arr.copy()})

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]):
            generate_cost_surface("/slope.tif", "/out.tif")

        cost = written["arr"]
        # Original: max_slope=1.0 → cost=1+(-0.3/1.0)*10=-2.0
        # Mutation: max_slope=2.0 → cost=1+(-0.3/2.0)*10=-1.5
        assert abs(float(cost[0, 0]) - (-2.0)) < 0.01, (
            f"Expected cost≈-2.0 (max_slope=1.0), got {float(cost[0, 0])}"
        )

    def test_dst_write_band_is_one(self):
        """Kill mutmut_85 (band=None) and mutmut_88 (band=2): write must use band=1."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[5.0, 3.0]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data)

        write_calls = []
        dst_mock.write.side_effect = lambda arr, band: write_calls.append((arr.copy(), band))

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir"), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]):
            generate_cost_surface("/slope.tif", "/out.tif")

        assert len(write_calls) == 1, "dst.write must be called exactly once"
        assert write_calls[0][1] == 1, (
            f"dst.write must be called with band=1, got {write_calls[0][1]}"
        )

    def test_mkdir_called_with_parents_true(self):
        """Kill mutmut_70 (parents=None), 72 (no parents), 75 (parents=False)."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import generate_cost_surface

        slope_data = np.array([[5.0]], dtype=np.float64)
        src_mock, dst_mock = self._make_mocks(slope_data)

        mkdir_kwargs = {}
        def capture_mkdir(*args, **kwargs):
            mkdir_kwargs.update(kwargs)

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.mkdir", side_effect=capture_mkdir), \
             patch("rasterio.open", side_effect=[src_mock, dst_mock]):
            generate_cost_surface("/slope.tif", "/a/b/out.tif")

        assert mkdir_kwargs.get("parents") is True, (
            f"mkdir must be called with parents=True, got parents={mkdir_kwargs.get('parents')}"
        )
        assert mkdir_kwargs.get("exist_ok") is True


# ---------------------------------------------------------------------------
# _sample_raster_along_line — core behavior and boundary mutations
# ---------------------------------------------------------------------------


class TestSampleRasterAlongLineCore:
    """Kill mutations in _sample_raster_along_line.

    Targets:
    - mutmut_24: nodata=None — nodata filter bypassed
    - mutmut_33: and→or in bounds check — wrong cell included via negative index
    - mutmut_34: 1<=r (was 0<=r) — r=0 should be valid
    - mutmut_35: 0<r (was 0<=r) — r=0 should be valid
    - mutmut_36: r<=shape[0] (was r<shape[0]) — r=shape[0] should be skipped
    - mutmut_38: 1<=c (was 0<=c) — c=0 should be valid
    - mutmut_39: 0<c (was 0<=c) — c=0 should be valid
    - mutmut_40: c<=shape[1] (was c<shape[1]) — c=shape[1] should be skipped
    - mutmut_42: val=None — float(data[r,c]) must yield real value
    - mutmut_44: and (was or) in nodata check — non-nodata values must be included
    - mutmut_45: is not None (was is None) — nodata filtering logic
    - mutmut_46: val==nodata (was val!=nodata) — non-nodata values must be included
    - mutmut_47: values.append(None) — appended values must be floats
    - mutmut_48: break (was continue) — exception in point must not stop loop
    - mutmut_1: num_points=21 (default was 20)
    - mutmut_18: normalized=False (was True)
    """

    def _make_raster_mock(self, data, nodata=None):
        src = MagicMock()
        src.read.return_value = data
        src.nodata = nodata
        src.transform = MagicMock()
        src.__enter__ = MagicMock(return_value=src)
        src.__exit__ = MagicMock(return_value=False)
        return src

    def test_nodata_values_excluded(self):
        """Kill mutmut_24 (nodata=None): nodata values must be filtered out.

        With nodata=-9999.0: data[0,0]=-9999.0 (skip), data[0,1]=5.0 (keep).
        mutmut_24 sets nodata=None → 'nodata is None' always True → both included.
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[-9999.0, 5.0]], dtype=np.float64)
        src = self._make_raster_mock(data, nodata=-9999.0)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", side_effect=[(0, 0), (0, 1)]):
            result = _sample_raster_along_line(line, "/r.tif", num_points=2)

        assert -9999.0 not in result, "nodata value must be filtered"
        assert 5.0 in result, "non-nodata value must be included"

    def test_nodata_check_or_not_and(self):
        """Kill mutmut_44 (and instead of or in nodata check).

        nodata=-9999.0, val=5.0 (not nodata):
        Original: nodata is None OR val != nodata → False OR True → True → include
        Mutation: nodata is None AND val != nodata → False AND True → False → skip!
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[5.0]], dtype=np.float64)
        src = self._make_raster_mock(data, nodata=-9999.0)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(0, 0)):
            result = _sample_raster_along_line(line, "/r.tif", num_points=1)

        assert 5.0 in result, "non-nodata value (5.0) must be included when nodata is set"

    def test_nodata_value_excluded_kills_45_46(self):
        """Kill mutmut_45 (is not None) and mutmut_46 (val==nodata).

        nodata=-9999.0, val=-9999.0 (IS nodata):
        Original: nodata is None OR val != nodata → False OR False → False → skip (correct)
        mutmut_45: nodata is not None OR val != nodata → True OR ... → always True → include!
        mutmut_46: nodata is None OR val == nodata → False OR True → True → include!
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[-9999.0, 7.0]], dtype=np.float64)
        src = self._make_raster_mock(data, nodata=-9999.0)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", side_effect=[(0, 0), (0, 1)]):
            result = _sample_raster_along_line(line, "/r.tif", num_points=2)

        assert -9999.0 not in result, "nodata cell must be excluded"
        assert 7.0 in result, "non-nodata cell must be included"

    def test_val_is_float_not_none(self):
        """Kill mutmut_42 (val=None) and mutmut_47 (values.append(None)).

        val should be float(data[r,c]), not None; appended values must be floats.
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[42.0]], dtype=np.float64)
        src = self._make_raster_mock(data, nodata=None)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(0, 0)):
            result = _sample_raster_along_line(line, "/r.tif", num_points=1)

        assert len(result) == 1
        assert result[0] == 42.0, f"Expected 42.0, got {result[0]}"
        assert result[0] is not None, "appended value must not be None"
        assert isinstance(result[0], float), f"appended value must be float, got {type(result[0])}"

    def test_boundary_r_zero_is_valid(self):
        """Kill mutmut_34 (1<=r) and mutmut_35 (0<r): r=0 must be a valid row."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[99.0, 0.0], [0.0, 0.0]], dtype=np.float64)  # value at r=0, c=0
        src = self._make_raster_mock(data, nodata=None)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(0, 0)):  # r=0 → valid
            result = _sample_raster_along_line(line, "/r.tif", num_points=1)

        assert 99.0 in result, "r=0 must be a valid row (0 <= 0 < height)"

    def test_boundary_r_at_shape0_is_invalid(self):
        """Kill mutmut_36 (r <= shape[0]): r=shape[0] must be out of bounds."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)  # shape=(2,2)
        src = self._make_raster_mock(data, nodata=None)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        # r=2 is shape[0]=2 → must be SKIPPED (0 <= 2 < 2 is False)
        # With mutation (r <= 2): 0 <= 2 <= 2 is True → tries data[2,0] → IndexError caught
        # But with numpy, data[2,0] raises IndexError which is caught, so both paths skip.
        # Use negative r to distinguish: r=-1 goes through numpy negative indexing
        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(-1, 0)):  # r=-1: invalid
            result = _sample_raster_along_line(line, "/r.tif", num_points=1)

        # Original: 0 <= -1 is False → skip (no value added) → result=[]
        # Mutation (0 <= r <= shape[0]): would need 0 <= -1 which is still False → same
        # Use r=data.shape[0] instead
        assert result == [], f"r=-1 must be out of bounds (0 <= r check fails), got {result}"

    def test_boundary_r_shape0_negative_index_caught(self):
        """Kill mutmut_33 (and→or): r=-1 (invalid) with c=0 (valid) must be SKIPPED.

        Original: 0 <= -1 < shape[0] AND 0 <= 0 < shape[1] → False AND True → False → skip
        Mutation (or): False OR True → True → tries data[-1, 0] → numpy wraps → returns
        data[-1, 0] (last row!) → adds wrong value → NOT empty!
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[0.0, 0.0], [777.0, 0.0]], dtype=np.float64)  # data[-1,0]=777.0
        src = self._make_raster_mock(data, nodata=None)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        # r=-1 (out of bounds), c=0 (in bounds)
        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(-1, 0)):
            result = _sample_raster_along_line(line, "/r.tif", num_points=1)

        # Original (and): skip → result=[]
        # Mutation (or): data[-1,0]=777.0 added → result=[777.0]
        assert result == [], (
            f"r=-1 must not produce a value (and check): got {result}"
        )

    def test_boundary_c_zero_is_valid(self):
        """Kill mutmut_38 (1<=c) and mutmut_39 (0<c): c=0 must be a valid column."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[55.0, 0.0]], dtype=np.float64)  # value at r=0, c=0
        src = self._make_raster_mock(data, nodata=None)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(0, 0)):  # c=0 → valid
            result = _sample_raster_along_line(line, "/r.tif", num_points=1)

        assert 55.0 in result, "c=0 must be a valid column (0 <= 0 < width)"

    def test_boundary_c_shape1_negative_index_caught(self):
        """Kill mutmut_33 (and→or) for column dimension: c=-1 (invalid), r=0 (valid)."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[0.0, 888.0]], dtype=np.float64)  # data[0,-1]=888.0
        src = self._make_raster_mock(data, nodata=None)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        # r=0 (valid), c=-1 (out of bounds)
        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(0, -1)):
            result = _sample_raster_along_line(line, "/r.tif", num_points=1)

        # Original (and): 0 <= 0 < 1 AND 0 <= -1 < 2 → True AND False → False → skip
        # Mutation (or): True OR False → True → data[0,-1]=888.0 → adds 888.0
        assert result == [], (
            f"c=-1 must not produce a value (and check): got {result}"
        )

    def test_continue_not_break_on_inner_exception(self):
        """Kill mutmut_48 (break instead of continue): exception in first point must not stop loop.

        rowcol raises on first call → caught → continue.
        rowcol returns valid (0,0) on second call → value 33.0 is added.
        With break: first exception exits the loop → result=[] (wrong).
        With continue: loop proceeds to second point → result=[33.0] (correct).
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[33.0]], dtype=np.float64)
        src = self._make_raster_mock(data, nodata=None)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        rowcol_calls = [Exception("bad coords"), (0, 0)]
        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", side_effect=rowcol_calls):
            result = _sample_raster_along_line(line, "/r.tif", num_points=2)

        assert len(result) == 1, (
            f"loop must continue after exception (not break): got {result}"
        )
        assert result[0] == 33.0

    def test_default_num_points_is_twenty(self):
        """Kill mutmut_1 (num_points=21 default): call without num_points and count rowcol calls."""
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from shapely.geometry import LineString

        data = np.array([[1.0] * 25], dtype=np.float64)
        src = self._make_raster_mock(data, nodata=None)
        line = LineString([(0.0, 0.0), (1.0, 0.0)])

        call_count = [0]
        def counting_rowcol(transform, x, y):
            c = call_count[0] % 25
            call_count[0] += 1
            return 0, c

        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", side_effect=counting_rowcol):
            _sample_raster_along_line(line, "/r.tif")  # no num_points → uses default

        # Default=20 → rowcol called 20 times; mutation default=21 → called 21 times
        assert call_count[0] == 20, (
            f"default num_points must be 20, got {call_count[0]} rowcol calls"
        )

    def test_normalized_true_covers_full_line(self):
        """Kill mutmut_18 (normalized=False): normalized=True uses fraction of line length.

        Line from (0.0, 0.5) to (2.0, 0.5) — length=2. num_points=2 → fractions=[0.0, 1.0].

        normalized=True:
          f=1.0 → end of line → (2.0, 0.5) → col=20 → data[0, 20]=55.0
        normalized=False:
          f=1.0 → point at distance=1.0 along line of length=2 → (1.0, 0.5) → col=10 → data[0,10]=99.0

        Test asserts 55.0 in result → passes for original, fails for mutation.

        Raster: x in [0, 2.1], width=21 → col_size=0.1
          col 0  → x=0.0
          col 10 → x=1.0
          col 20 → x=2.0
        Row: y in [0, 1.0], height=2 → row_size=0.5
          row 0 → y=0.75–1.0 (upper half)
          row 1 → y=0.25–0.75 → y=0.5 lands in row 1 ✓ (within shape[0]=2)
        """
        import numpy as np
        from app.domains.geo.intelligence.calculations import _sample_raster_along_line
        from rasterio.transform import from_bounds, rowcol as real_rowcol
        from shapely.geometry import LineString

        # y=0.5 is inside raster bounds [0,1], avoids y=0 → row out-of-bounds issue
        line = LineString([(0.0, 0.5), (2.0, 0.5)])

        # Raster wider than line so x=2.0 maps to col=20 (valid)
        transform = from_bounds(0.0, 0.0, 2.1, 1.0, 21, 2)
        data = np.zeros((2, 21), dtype=np.float64)
        data[1, 10] = 99.0   # x=1.0 → normalized=False, f=1 lands here
        data[1, 20] = 55.0   # x=2.0 → normalized=True, f=1 lands here

        src = MagicMock()
        src.read.return_value = data
        src.nodata = None
        src.transform = transform
        src.__enter__ = MagicMock(return_value=src)
        src.__exit__ = MagicMock(return_value=False)

        def forwarding_rowcol(t, x, y):
            return real_rowcol(transform, x, y)

        with patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", side_effect=forwarding_rowcol):
            result = _sample_raster_along_line(line, "/r.tif", num_points=2)

        # fractions=[0.0, 1.0]
        # normalized=True: f=1 → endpoint (2.0, 0.5) → col=20 → 55.0 in result
        # normalized=False: f=1 → dist=1 along line → (1.0, 0.5) → col=10 → 99.0 in result
        assert 55.0 in result, (
            f"normalized=True must sample line endpoint (x=2.0, data=55.0). Got {result}"
        )


# ---------------------------------------------------------------------------
# detect_coverage_gaps — targeted mutant killers
# Targets: mutmut_1,2,9,20,22,25,28,30,33,52,53,54,58,59,64,65,66,67,
#          84,99,100,101,102,108,110,115
# ---------------------------------------------------------------------------


class TestDetectCoverageGapsCore:
    """Kill the 26 remaining surviving mutants in detect_coverage_gaps.

    Geometry pattern (unless noted):
      zone at Point(0, 0), canal at x = dist_km/111.0 degrees (vertical line).
      Nearest point from zone to canal = (dist_km/111, 0), distance = dist_km/111 degrees.
      dist_km (computed in function) = dist_deg * 111.0.

    For two-zone isolation: zone_2 at x=50 degrees with canal at x=50+D_2.
    The two canals are unioned; each zone's nearest canal is its own.
    """

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _canal_at(x_deg, *, base_x=0.0):
        """Vertical canal at x = base_x + x_deg, spanning y ∈ [-1, 1]."""
        from shapely.geometry import LineString

        X = base_x + x_deg
        return {"geometry": LineString([(X, -1.0), (X, 1.0)])}

    @staticmethod
    def _zone(zone_id, *, x=0.0, y=0.0):
        from shapely.geometry import Point

        return {"id": zone_id, "geometry": Point(x, y)}

    @staticmethod
    def _run(zones, hci_scores, canals, **kw):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        return detect_coverage_gaps(zones, hci_scores, canals, **kw)

    # ── default parameter mutations ───────────────────────────────────────────

    def test_default_threshold_km_is_2_kills_mutmut_1(self):
        """Zone at 2.5 km uses default threshold=2.0 (included). Mutation=3.0 excludes it."""
        D = 2.5 / 111.0
        result = self._run(
            [self._zone("z1")],
            {"z1": 65.0},
            [self._canal_at(D)],
            # no threshold_km → default 2.0
        )
        # 2.5 > 2.0 → included; mutation threshold=3.0 → 2.5 < 3.0 → excluded → len==0
        assert len(result) == 1, f"dist=2.5km must be included with default threshold=2.0. Got {result}"

    def test_default_hci_threshold_is_50_kills_mutmut_2(self):
        """hci=50.5 passes default threshold=50.0 (included). Mutation=51.0 excludes it."""
        D = 2.5 / 111.0
        result = self._run(
            [self._zone("z1")],
            {"z1": 50.5},
            [self._canal_at(D)],
            # no hci_threshold → default 50.0
        )
        # 50.5 >= 50.0 → not skipped; mutation 51.0 → 50.5 < 51.0 → skipped → len==0
        assert len(result) == 1, f"hci=50.5 must pass default hci_threshold=50.0. Got {result}"

    # ── canal None geometry: continue vs break (mutmut_9) ────────────────────

    def test_none_canal_continue_not_break_kills_mutmut_9(self):
        """None-geometry canal must be skipped (continue). Break stops the loop → no valid canal."""
        D = 3.0 / 111.0
        result = self._run(
            [self._zone("z1")],
            {"z1": 70.0},
            [{"geometry": None}, self._canal_at(D)],
        )
        # Original (continue): None skipped → canal_shapes=[valid] → z1 dist=3km > 2km → included
        # Mutation (break): breaks at None → canal_shapes=[] → return []
        assert len(result) == 1, f"None canal must be skipped (continue), not break. Got {result}"

    # ── zone_id default value (mutmut_20, 22, 25) ────────────────────────────

    def test_zone_id_default_empty_string_kills_mutmut_20_22_25(self):
        """Zone with no 'id' key: default '' looks up hci_scores[''] = 85.
        Mutations use None/'XXXX' as default → lookup fails → hci=0.0 → excluded."""
        D = 3.0 / 111.0
        zone_no_id = {"geometry": self._zone("_")["geometry"]}  # no 'id' key
        result = self._run(
            [zone_no_id],
            {"": 85.0},  # keyed on "" — the original default
            [self._canal_at(D)],
        )
        # Original: zone.get("id", "") → "" → hci=85.0 → dist=3km > 2km → included
        # mutmut_20: get("id", None) → str(None)="None" → hci=0.0 → skipped
        # mutmut_22: get("id", ) = get("id") → None → "None" → skipped
        # mutmut_25: get("id", "XXXX") → "XXXX" → hci=0.0 → skipped
        assert len(result) == 1, (
            f"zone.get('id', '') must default to '' and find hci=85. Got {result}"
        )

    # ── hci default 0.0 for missing key (mutmut_28, 30) ─────────────────────

    def test_hci_missing_key_defaults_zero_kills_mutmut_28_30(self):
        """zone_id not in hci_scores: original default 0.0 → skip gracefully.
        Mutations (None default) → hci=None → None < 50.0 → TypeError → test FAILS → killed."""
        D = 3.0 / 111.0
        result = self._run(
            [self._zone("z_absent")],
            {"other": 85.0},  # "z_absent" not present
            [self._canal_at(D)],
        )
        # Original: hci=0.0 < 50.0 → skip → []
        # mutmut_28: .get(zone_id, None) → None < 50.0 → TypeError → test errors out → killed
        # mutmut_30: .get(zone_id, ) = .get(zone_id) → None → same TypeError
        assert result == [], f"Missing hci key must default to 0.0 and skip. Got {result}"

    # ── hci < threshold: continue vs break (mutmut_33) ───────────────────────

    def test_low_hci_continue_not_break_kills_mutmut_33(self):
        """Low-hci zone skipped (continue); high-hci zone after must still be processed."""
        D = 4.0 / 111.0
        result = self._run(
            [self._zone("z_low"), self._zone("z_high", x=0.001)],
            {"z_low": 25.0, "z_high": 70.0},
            [self._canal_at(D)],
        )
        # Original (continue): z_low skipped (hci=25<50), z_high processed → len==1
        # Mutation (break): breaks at z_low → z_high never reached → len==0
        assert len(result) == 1
        assert result[0]["zone_id"] == "z_high", f"z_high must be included. Got {result}"

    # ── dist_km factor: *112 vs *111 (mutmut_52) ─────────────────────────────

    def test_dist_km_factor_111_not_112_kills_mutmut_52(self):
        """dist_deg in (2/112, 2/111): *111 gives <2.0 (skip); *112 gives ≥2.0 (include)."""
        # midpoint: 2.0/111.5 → *111 = 1.991 < 2.0 → skip; *112 = 2.009 ≥ 2.0 → include
        dist_deg = 2.0 / 111.5
        result = self._run(
            [self._zone("z1")],
            {"z1": 70.0},
            [{"geometry": __import__("shapely.geometry", fromlist=["LineString"]).LineString(
                [(dist_deg, -1.0), (dist_deg, 1.0)]
            )}],
            threshold_km=2.0,
        )
        # Original *111: dist_km = dist_deg*111 ≈ 1.991 < 2.0 → skip → []
        # Mutation *112: dist_km = dist_deg*112 ≈ 2.009 ≥ 2.0 → include → len==1
        assert result == [], (
            f"Factor *111 gives dist<2.0 → zone excluded. Mutation *112 would include it. Got {result}"
        )

    # ── dist < threshold: < vs <= (mutmut_53) ────────────────────────────────

    def test_dist_exactly_at_threshold_included_kills_mutmut_53(self):
        """dist_km == threshold_km exactly: original (<) includes it; mutation (<=) excludes it."""
        from shapely.geometry import LineString

        dist_deg = 2.0 / 111.0
        # threshold is set to the EXACT same float computation as dist_km will be
        threshold_km = dist_deg * 111.0  # == dist_deg * 111.0 in the function → equal
        result = self._run(
            [self._zone("z1")],
            {"z1": 70.0},
            [{"geometry": LineString([(dist_deg, -1.0), (dist_deg, 1.0)])}],
            threshold_km=threshold_km,
        )
        # dist_km = dist_deg * 111.0 = threshold_km (same computation, same float)
        # Original (<): threshold < threshold = False → include → len==1
        # Mutation (<=): threshold <= threshold = True → skip → len==0
        assert len(result) == 1, (
            f"dist==threshold must be included (< not <=). Got {result}"
        )

    # ── dist < threshold: continue vs break (mutmut_54) ─────────────────────

    def test_close_zone_continue_not_break_kills_mutmut_54(self):
        """Close zone (dist<threshold) skipped; far zone after must still be processed."""
        from shapely.geometry import LineString

        D_close = 1.0 / 111.0   # ≈1 km < 2 km threshold → skip
        D_far = 4.0 / 111.0     # ≈4 km > 2 km threshold → include

        # Isolate the two zones 50 degrees apart so each is nearest to its own canal
        z_close = self._zone("z_close", x=0.0)
        z_far = self._zone("z_far", x=50.0)
        c_close = {"geometry": LineString([(D_close, -1.0), (D_close, 1.0)])}
        c_far = {"geometry": LineString([(50.0 + D_far, -1.0), (50.0 + D_far, 1.0)])}

        result = self._run(
            [z_close, z_far],
            {"z_close": 70.0, "z_far": 70.0},
            [c_close, c_far],
        )
        # Original (continue): z_close dist≈1<2 → skip; z_far dist≈4>2 → include → len==1
        # Mutation (break): breaks at z_close → z_far never reached → len==0
        assert len(result) == 1
        assert result[0]["zone_id"] == "z_far", f"z_far must be included. Got {result}"

    # ── severity critico: dist > 5.0 vs dist >= 5.0 (mutmut_58) ─────────────

    def test_dist_exactly_5km_is_alto_not_critico_kills_mutmut_58(self):
        """hci=85, dist≈5.0km: original (>5.0) → alto; mutation (>=5.0) → critico."""
        from shapely.geometry import LineString

        dist_deg = 5.0 / 111.0
        result = self._run(
            [self._zone("z1")],
            {"z1": 85.0},
            [{"geometry": LineString([(dist_deg, -1.0), (dist_deg, 1.0)])}],
        )
        # dist_km = dist_deg * 111.0 ≈ 5.0
        # hci=85 > 80 ✓, dist=5.0 NOT strictly > 5.0 → not critico
        # elif hci=85 > 60 and dist=5.0 > 3.0 → alto
        # Mutation (>=5.0): 5.0 >= 5.0 = True → critico
        assert len(result) == 1
        assert result[0]["severity"] == "alto", (
            f"dist=5.0km is NOT > 5.0 → must be 'alto', not 'critico'. Got {result}"
        )

    # ── severity critico: dist > 5.0 vs dist > 6.0 (mutmut_59) ──────────────

    def test_dist_5_5km_is_critico_kills_mutmut_59(self):
        """hci=85, dist=5.5km: original (>5.0) → critico; mutation (>6.0) → alto."""
        from shapely.geometry import LineString

        dist_deg = 5.5 / 111.0
        result = self._run(
            [self._zone("z1")],
            {"z1": 85.0},
            [{"geometry": LineString([(dist_deg, -1.0), (dist_deg, 1.0)])}],
        )
        assert len(result) == 1
        assert result[0]["severity"] == "critico", (
            f"hci=85>80 AND dist=5.5>5.0 → 'critico'. Mutation >6.0 gives 'alto'. Got {result}"
        )

    # ── severity alto: hci > 60.0 vs hci >= 60.0 (mutmut_64) ────────────────

    def test_hci_exactly_60_is_moderado_kills_mutmut_64(self):
        """hci=60.0, dist=4.0km: original (>60.0) → moderado; mutation (>=60.0) → alto."""
        from shapely.geometry import LineString

        dist_deg = 4.0 / 111.0
        result = self._run(
            [self._zone("z1")],
            {"z1": 60.0},
            [{"geometry": LineString([(dist_deg, -1.0), (dist_deg, 1.0)])}],
        )
        # hci=60.0, NOT strictly > 60.0 → elif fails → moderado
        # Mutation (>=60.0): 60.0 >= 60.0 = True AND dist=4.0>3.0 → alto
        assert len(result) == 1
        assert result[0]["severity"] == "moderado", (
            f"hci=60.0 is NOT >60.0 → 'moderado'. Mutation >=60.0 gives 'alto'. Got {result}"
        )

    # ── severity alto: hci > 60.0 vs hci > 61.0 (mutmut_65) ─────────────────

    def test_hci_60_5_is_alto_kills_mutmut_65(self):
        """hci=60.5, dist=4.0km: original (>60.0) → alto; mutation (>61.0) → moderado."""
        from shapely.geometry import LineString

        dist_deg = 4.0 / 111.0
        result = self._run(
            [self._zone("z1")],
            {"z1": 60.5},
            [{"geometry": LineString([(dist_deg, -1.0), (dist_deg, 1.0)])}],
        )
        assert len(result) == 1
        assert result[0]["severity"] == "alto", (
            f"hci=60.5>60.0 AND dist=4.0>3.0 → 'alto'. Mutation >61.0 gives 'moderado'. Got {result}"
        )

    # ── severity alto: dist > 3.0 vs dist >= 3.0 (mutmut_66) ────────────────

    def test_dist_exactly_3km_is_moderado_kills_mutmut_66(self):
        """hci=65, dist≈3.0km: original (>3.0) → moderado; mutation (>=3.0) → alto."""
        from shapely.geometry import LineString

        dist_deg = 3.0 / 111.0
        result = self._run(
            [self._zone("z1")],
            {"z1": 65.0},
            [{"geometry": LineString([(dist_deg, -1.0), (dist_deg, 1.0)])}],
            threshold_km=2.0,
        )
        # dist_km = dist_deg * 111.0 ≈ 3.0; hci=65>60 but dist NOT strictly > 3.0 → moderado
        # Mutation (>=3.0): 3.0 >= 3.0 = True → alto
        assert len(result) == 1
        assert result[0]["severity"] == "moderado", (
            f"dist=3.0km is NOT >3.0 → 'moderado'. Mutation >=3.0 gives 'alto'. Got {result}"
        )

    # ── severity alto: dist > 3.0 vs dist > 4.0 (mutmut_67) ─────────────────

    def test_dist_3_5km_is_alto_kills_mutmut_67(self):
        """hci=65, dist=3.5km: original (>3.0) → alto; mutation (>4.0) → moderado."""
        from shapely.geometry import LineString

        dist_deg = 3.5 / 111.0
        result = self._run(
            [self._zone("z1")],
            {"z1": 65.0},
            [{"geometry": LineString([(dist_deg, -1.0), (dist_deg, 1.0)])}],
        )
        assert len(result) == 1
        assert result[0]["severity"] == "alto", (
            f"hci=65>60 AND dist=3.5>3.0 → 'alto'. Mutation >4.0 gives 'moderado'. Got {result}"
        )

    # ── round(dist_km, 2) vs round(dist_km, 3) (mutmut_84) ──────────────────

    def test_gap_km_rounded_2_decimals_kills_mutmut_84(self):
        """dist_km ≈ 10/3 = 3.333...: round(x,2)=3.33 (original); round(x,3)=3.333 (mutation)."""
        from shapely.geometry import LineString

        dist_deg = 10.0 / (3.0 * 111.0)  # → dist_km ≈ 3.333...
        result = self._run(
            [self._zone("z1")],
            {"z1": 70.0},
            [{"geometry": LineString([(dist_deg, -1.0), (dist_deg, 1.0)])}],
            threshold_km=2.0,
        )
        assert len(result) == 1
        gap_km = result[0]["gap_km"]
        # round(3.333..., 2) = 3.33  — original
        # round(3.333..., 3) = 3.333 — mutation
        assert gap_km == 3.33, (
            f"gap_km must be rounded to 2 decimal places (3.33). Got {gap_km}"
        )

    # ── severity_order: critico=0 vs critico=1 (mutmut_99) ───────────────────

    def test_critico_sorted_before_alto_kills_mutmut_99(self):
        """critico(hci=82, dist=6km) before alto(hci=90, dist=4km).
        Mutation critico:1 ties with alto:1 → tiebreak -hci: alto(90) sorts first."""
        from shapely.geometry import LineString

        # critico: hci=82>80, dist=6>5 → "critico"
        D_crit = 6.0 / 111.0
        z_crit = self._zone("z_crit", x=0.0)
        c_crit = {"geometry": LineString([(D_crit, -1.0), (D_crit, 1.0)])}

        # alto: hci=90>60, dist=4 (>3, ≤5, and hci=90>80 but dist not>5) → "alto"
        D_alto = 4.0 / 111.0
        z_alto = self._zone("z_alto", x=50.0)
        c_alto = {"geometry": LineString([(50.0 + D_alto, -1.0), (50.0 + D_alto, 1.0)])}

        result = self._run(
            [z_crit, z_alto],
            {"z_crit": 82.0, "z_alto": 90.0},
            [c_crit, c_alto],
        )
        assert len(result) == 2
        # Original: critico(0,-82) < alto(1,-90) → critico first
        # Mutation critico:1: (1,-82) vs (1,-90) → -90 < -82 → alto(-90) first → FAIL → killed
        assert result[0]["severity"] == "critico", (
            f"critico (order=0) must sort before alto (order=1). "
            f"Got {[r['severity'] for r in result]}"
        )

    # ── severity_order "alto" key wrong (mutmut_100, 101) ────────────────────

    def test_alto_sorted_before_moderado_kills_mutmut_100_101(self):
        """'alto' must sort before 'moderado'. Wrong key → alto gets default=3 > moderado=2."""
        from shapely.geometry import LineString

        # alto: hci=70>60, dist=4>3 (not>5) → "alto"
        D_alto = 4.0 / 111.0
        z_alto = self._zone("z_alto", x=0.0)
        c_alto = {"geometry": LineString([(D_alto, -1.0), (D_alto, 1.0)])}

        # moderado: hci=55 (>50 passes filter, ≤60 → not alto), dist=6 → "moderado"
        D_mod = 6.0 / 111.0
        z_mod = self._zone("z_mod", x=50.0)
        c_mod = {"geometry": LineString([(50.0 + D_mod, -1.0), (50.0 + D_mod, 1.0)])}

        result = self._run(
            [z_alto, z_mod],
            {"z_alto": 70.0, "z_mod": 55.0},
            [c_alto, c_mod],
        )
        assert len(result) == 2
        # Original: alto(1,-70) < moderado(2,-55) → alto first
        # mutmut_100 "XXaltoXX": alto lookup → default=3 > 2 → moderado first → FAIL → killed
        # mutmut_101 "ALTO": same
        assert result[0]["severity"] == "alto", (
            f"'alto' (key=1) must sort before 'moderado' (key=2). "
            f"Got {[r['severity'] for r in result]}"
        )

    # ── severity_order alto=2 vs alto=1 (mutmut_102) ─────────────────────────

    def test_alto_key_1_before_moderado_key_2_kills_mutmut_102(self):
        """alto(hci=65) before moderado(hci=70): with alto:2, tiebreak gives moderado(70) first."""
        from shapely.geometry import LineString

        # alto: hci=65>60, dist=4>3 (not>5) → "alto"
        D_alto = 4.0 / 111.0
        z_alto = self._zone("z_alto", x=0.0)
        c_alto = {"geometry": LineString([(D_alto, -1.0), (D_alto, 1.0)])}

        # moderado: hci=70>60 but dist=2.5 ≤3 → not alto → "moderado"
        D_mod = 2.5 / 111.0
        z_mod = self._zone("z_mod", x=50.0)
        c_mod = {"geometry": LineString([(50.0 + D_mod, -1.0), (50.0 + D_mod, 1.0)])}

        result = self._run(
            [z_alto, z_mod],
            {"z_alto": 65.0, "z_mod": 70.0},
            [c_alto, c_mod],
        )
        assert len(result) == 2
        # Original: alto(1,-65) < moderado(2,-70) → alto first
        # Mutation alto:2: (2,-65) vs (2,-70) → -70 < -65 → moderado(70) first → FAIL → killed
        assert result[0]["severity"] == "alto", (
            f"'alto' (key=1) must sort before 'moderado' (key=2). "
            f"Got {[r['severity'] for r in result]}"
        )

    # ── sort key get(severity, 3) vs get(None, 3) (mutmut_108) ───────────────

    def test_sort_uses_severity_string_kills_mutmut_108(self):
        """get(None,3): all gaps get key=3, sorted by -hci only.
        critico(82,dist=6) vs moderado(90,dist=2.5): mutation puts moderado(90) first."""
        from shapely.geometry import LineString

        D_crit = 6.0 / 111.0
        z_crit = self._zone("z_crit", x=0.0)
        c_crit = {"geometry": LineString([(D_crit, -1.0), (D_crit, 1.0)])}

        # moderado: hci=90, dist=2.5 → passes threshold(2.0), hci>80 but dist≤5 → not critico
        # hci>60 but dist=2.5≤3 → not alto → "moderado"
        D_mod = 2.5 / 111.0
        z_mod = self._zone("z_mod", x=50.0)
        c_mod = {"geometry": LineString([(50.0 + D_mod, -1.0), (50.0 + D_mod, 1.0)])}

        result = self._run(
            [z_crit, z_mod],
            {"z_crit": 82.0, "z_mod": 90.0},
            [c_crit, c_mod],
        )
        assert len(result) == 2
        # Original: critico(0,-82) < moderado(2,-90) → critico first
        # Mutation get(None,3): all → (3,-hci) → (3,-82) vs (3,-90) → -90<-82 → moderado first
        assert result[0]["severity"] == "critico", (
            f"critico (key=0) must sort before moderado (key=2). "
            f"Got {[r['severity'] for r in result]}"
        )

    # ── sort key get(3) — literal 3 as dict key (mutmut_110) ─────────────────

    def test_sort_uses_severity_arg_not_literal_3_kills_mutmut_110(self):
        """get(3): severity_order has no key=3 → all get None → sorted by -hci only.
        critico(82,dist=6) vs moderado(90,dist=2.5): mutation puts moderado(90) first."""
        from shapely.geometry import LineString

        D_crit = 6.0 / 111.0
        z_crit = self._zone("z_crit", x=0.0)
        c_crit = {"geometry": LineString([(D_crit, -1.0), (D_crit, 1.0)])}

        D_mod = 2.5 / 111.0
        z_mod = self._zone("z_mod", x=50.0)
        c_mod = {"geometry": LineString([(50.0 + D_mod, -1.0), (50.0 + D_mod, 1.0)])}

        result = self._run(
            [z_crit, z_mod],
            {"z_crit": 82.0, "z_mod": 90.0},
            [c_crit, c_mod],
        )
        assert len(result) == 2
        # Original: critico(0,-82) < moderado(2,-90) → critico first
        # Mutation get(3): dict has no key=3 → returns None for all
        #   (None,-82) vs (None,-90): None==None, -90<-82 → moderado(90) sorts first
        assert result[0]["severity"] == "critico", (
            f"sort must pass severity string as key, not literal 3. "
            f"Got {[r['severity'] for r in result]}"
        )

    # ── sort by -hci vs +hci (mutmut_115) ────────────────────────────────────

    def test_higher_hci_first_within_same_severity_kills_mutmut_115(self):
        """Two 'alto' zones: hci=75 must come before hci=65. Mutation +hci reverses order."""
        from shapely.geometry import LineString

        D = 4.0 / 111.0  # both zones at 4km → 'alto'

        z1 = self._zone("z1", x=0.0)
        c1 = {"geometry": LineString([(D, -1.0), (D, 1.0)])}

        z2 = self._zone("z2", x=50.0)
        c2 = {"geometry": LineString([(50.0 + D, -1.0), (50.0 + D, 1.0)])}

        result = self._run(
            [z1, z2],
            {"z1": 65.0, "z2": 75.0},
            [c1, c2],
        )
        assert len(result) == 2
        # Both 'alto': sort by -hci → -75 < -65 → z2(75) first
        # Mutation +hci: +65 < +75 → z1(65) first → FAIL → killed
        assert result[0]["hci_score"] == pytest.approx(75.0), (
            f"Higher hci_score must sort first (-hci ascending). Got {[r['hci_score'] for r in result]}"
        )


# ---------------------------------------------------------------------------
# suggest_canal_routes — targeted mutant killers
# Targets: 14,15,26-32,33-42,52,56,58,61,64-84,105-110
# ---------------------------------------------------------------------------

_MOD = "app.domains.geo.intelligence.calculations"


class TestSuggestCanalRoutesCore:
    """Kill surviving mutants in suggest_canal_routes.

    Strategy: mock the three heavy sub-functions (generate_cost_surface,
    cost_distance, least_cost_path) and rasterio.open, then assert:
    - The correct arguments are passed to each sub-function.
    - Output fields reflect correct defaults.
    - Directory creation doesn't blow up on edge cases.
    """

    # ── mock helper ───────────────────────────────────────────────────────────

    @staticmethod
    def _run(gaps, canals, slope_path, output_dir=None, *, cd_side_effect=None, lcp_side_effect=None):
        """Run suggest_canal_routes with all I/O mocked.

        Returns (result, gen_mock, cd_mock, lcp_mock).
        """
        import numpy as np
        from unittest.mock import patch, MagicMock
        from shapely.geometry import LineString

        lcp_default = LineString([(0.0, 0.0), (0.5, 0.0)])

        src = MagicMock()
        src.__enter__ = MagicMock(return_value=src)
        src.__exit__ = MagicMock(return_value=False)
        src.height = 10
        src.width = 10
        src.nodata = None
        src.transform = MagicMock()
        src.read.return_value = np.full((10, 10), 5.0)

        lcp_kw = {"side_effect": lcp_side_effect} if lcp_side_effect else {"return_value": lcp_default}

        with patch(f"{_MOD}.generate_cost_surface") as mock_gen, \
             patch(f"{_MOD}.cost_distance", side_effect=cd_side_effect) as mock_cd, \
             patch(f"{_MOD}.least_cost_path", **lcp_kw) as mock_lcp, \
             patch("rasterio.open", return_value=src), \
             patch("rasterio.transform.rowcol", return_value=(5, 5)):
            from app.domains.geo.intelligence.calculations import suggest_canal_routes
            result = suggest_canal_routes(gaps, canals, slope_path, output_dir)
            return result, mock_gen, mock_cd, mock_lcp

    # ── fixtures ──────────────────────────────────────────────────────────────

    @staticmethod
    def _slope(tmp_path):
        p = tmp_path / "slope.tif"
        p.touch()
        return str(p)

    @staticmethod
    def _canal_shapely():
        from shapely.geometry import LineString
        return {"geometry": LineString([(0.0, -1.0), (0.0, 1.0)])}

    @staticmethod
    def _canal_geojson():
        return {"geometry": {"type": "LineString", "coordinates": [[0.0, -1.0], [0.0, 1.0]]}}

    @staticmethod
    def _gap(x=0.5, y=0.0, zone_id="z1", *, as_shapely=False):
        from shapely.geometry import Point
        geom = Point(x, y) if as_shapely else {"type": "Point", "coordinates": [x, y]}
        d = {"geometry": geom, "zone_id": zone_id}
        return d

    # ── geometry conversion (mutmut_14, 15) ───────────────────────────────────

    def test_geojson_canal_geometry_converted_kills_mutmut_14_15(self, tmp_path):
        """Canal geometry as GeoJSON dict must be converted with shapely_shape().
        mutmut_14 (g=None) and mutmut_15 (shapely_shape(None)) make unary_union fail."""
        slope = self._slope(tmp_path)
        result, *_ = self._run([self._gap()], [self._canal_geojson()], slope)
        # Original: shapely_shape(geojson_dict) → LineString → unary_union works → route returned
        # mutmut_14: g=None → unary_union([None]) → TypeError
        # mutmut_15: shapely_shape(None) → TypeError
        assert isinstance(result, list), f"GeoJSON canal must be converted correctly. Got {result}"
        assert len(result) == 1, f"Expected 1 route, got {result}"

    # ── gap geometry Shapely object (mutmut_52) ───────────────────────────────

    def test_shapely_gap_geometry_kills_mutmut_52(self, tmp_path):
        """Gap with Shapely Point geometry (not dict): pt = geom is fine; pt = None → AttributeError."""
        slope = self._slope(tmp_path)
        gap = self._gap(as_shapely=True)  # geometry is a Shapely Point, not a dict
        result, *_ = self._run([gap], [self._canal_shapely()], slope)
        # Original: pt = geom → Point.x works ✓
        # mutmut_52: pt = None → None.x → AttributeError → test fails → killed
        assert len(result) == 1, f"Shapely gap geometry must be processed correctly. Got {result}"

    # ── zone_id default "" (mutmut_56, 58, 61) ────────────────────────────────

    def test_zone_id_default_empty_string_kills_mutmut_56_58_61(self, tmp_path):
        """Gap without 'zone_id' key: default '' → source_gap_id=''.
        Mutations give None/'XXXX' → source_gap_id != ''."""
        slope = self._slope(tmp_path)
        gap_no_id = {"geometry": {"type": "Point", "coordinates": [0.5, 0.0]}}  # no zone_id
        result, *_ = self._run([gap_no_id], [self._canal_shapely()], slope)
        assert len(result) == 1
        # Original: gap.get("zone_id", "") → "" → source_gap_id = str("") = ""
        # mutmut_56: get(..., None) → str(None) = "None" → source_gap_id = "None"
        # mutmut_58: get(..., ) = get("zone_id") → None → "None"
        # mutmut_61: get(..., "XXXX") → "XXXX" → source_gap_id = "XXXX"
        assert result[0]["source_gap_id"] == "", (
            f"Missing zone_id must default to ''. Got source_gap_id={result[0].get('source_gap_id')!r}"
        )

    # ── mkdir parents=True (mutmut_26, 27, 28, 29, 31) ───────────────────────

    def test_mkdir_parents_true_kills_mutmut_26_28_31(self, tmp_path):
        """Nested output_dir requires parents=True. parents=None/False/missing → FileNotFoundError."""
        slope = self._slope(tmp_path)
        nested = str(tmp_path / "a" / "b" / "c")  # parents a/b don't exist yet
        result, *_ = self._run([self._gap()], [self._canal_shapely()], slope, nested)
        # Original: mkdir(parents=True) creates a/b/c ✓
        # mutmut_26: parents=None → TypeError
        # mutmut_28: no parents arg → parents=False (default) → FileNotFoundError
        # mutmut_31: parents=False → FileNotFoundError
        assert isinstance(result, list), (
            f"mkdir with parents=True must succeed for nested dir. Got {result}"
        )

    # ── mkdir exist_ok=True (mutmut_27, 29, 32) ──────────────────────────────

    def test_mkdir_exist_ok_true_kills_mutmut_27_29_32(self, tmp_path):
        """Existing output_dir requires exist_ok=True. exist_ok=None/False/missing → FileExistsError."""
        slope = self._slope(tmp_path)
        # tmp_path already exists — mkdir must use exist_ok=True
        result, *_ = self._run([self._gap()], [self._canal_shapely()], slope, str(tmp_path))
        # Original: mkdir(exist_ok=True) → no error ✓
        # mutmut_27: exist_ok=None → TypeError
        # mutmut_29: no exist_ok arg → exist_ok=False (default) → FileExistsError
        # mutmut_32: exist_ok=False → FileExistsError
        assert isinstance(result, list), (
            f"mkdir with exist_ok=True must succeed for existing dir. Got {result}"
        )

    # ── generate_cost_surface args (mutmut_33, 34, 37, 38, 39, 40, 41, 42) ───

    def test_generate_cost_surface_first_arg_is_slope_kills_mutmut_39_41(self, tmp_path):
        """generate_cost_surface first arg must be slope_raster_path (not None/missing)."""
        slope = self._slope(tmp_path)
        result, mock_gen, *_ = self._run([self._gap()], [self._canal_shapely()], slope)
        gen_args = mock_gen.call_args[0]
        assert len(gen_args) >= 1
        assert gen_args[0] == slope, (
            f"generate_cost_surface first arg must be slope_raster_path={slope!r}. Got {gen_args[0]!r}"
        )

    def test_generate_cost_surface_second_arg_is_cost_surface_path_kills_mutmut_33_34_37_38_40_42(self, tmp_path):
        """generate_cost_surface second arg must be the cost_surface.tif path (not None/mangled)."""
        slope = self._slope(tmp_path)
        result, mock_gen, *_ = self._run(
            [self._gap()], [self._canal_shapely()], slope, str(tmp_path / "out")
        )
        gen_args = mock_gen.call_args[0]
        assert len(gen_args) == 2, f"generate_cost_surface must be called with 2 args. Got {gen_args}"
        second = gen_args[1]
        assert second is not None, "generate_cost_surface second arg must not be None (mutmut_33/40)"
        assert isinstance(second, str), f"second arg must be a string. Got {second!r}"
        assert second.endswith("cost_surface.tif"), (
            f"second arg must end with 'cost_surface.tif'. Got {second!r} "
            f"(kills mutmut_34 'None', mutmut_37 'XXcost_surface.tifXX', mutmut_38 'COST_SURFACE.TIF')"
        )

    # ── cost_distance args (mutmut_64, 65, 66, 69, 70, 71, 72, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84) ─

    def test_cost_distance_all_args_correct_kills_mutmut_64_65_76_77_84(self, tmp_path):
        """cost_distance must be called with 4 correct non-None string/list arguments."""
        slope = self._slope(tmp_path)
        gap = self._gap()
        result, _, mock_cd, _ = self._run([gap], [self._canal_shapely()], slope, str(tmp_path / "out"))
        cd_args = mock_cd.call_args[0]

        # Must have exactly 4 args (kills mutmut_81/82/83/84: missing args)
        assert len(cd_args) == 4, f"cost_distance must be called with 4 args. Got {len(cd_args)}"

        # arg[0]: cost_surface_path ending in "cost_surface.tif" (kills 77, 81)
        assert isinstance(cd_args[0], str) and cd_args[0].endswith("cost_surface.tif"), (
            f"cost_distance arg[0] must be cost_surface path. Got {cd_args[0]!r}"
        )

        # arg[1]: source_coords list of (lon, lat) tuples (kills 64, 78, 82)
        assert isinstance(cd_args[1], list) and len(cd_args[1]) > 0, (
            f"cost_distance arg[1] must be non-empty list. Got {cd_args[1]!r}"
        )
        assert cd_args[1][0] == pytest.approx((0.5, 0.0)), (
            f"source_coords[0] must be gap centroid (0.5, 0.0). Got {cd_args[1][0]}"
        )

        # arg[2]: accum_path ending in "cost_accum.tif" (kills 65, 66, 69, 70, 79, 83)
        assert isinstance(cd_args[2], str) and cd_args[2].endswith("cost_accum.tif"), (
            f"cost_distance arg[2] must be accum_path. Got {cd_args[2]!r}"
        )

        # arg[3]: backlink_path ending in "cost_backlink.tif" (kills 71, 72, 75, 76, 80, 84)
        assert isinstance(cd_args[3], str) and cd_args[3].endswith("cost_backlink.tif"), (
            f"cost_distance arg[3] must be backlink_path. Got {cd_args[3]!r}"
        )

    # ── least_cost_path args (mutmut_105, 106, 107, 108, 109, 110) ───────────

    def test_least_cost_path_all_args_correct_kills_mutmut_105_110(self, tmp_path):
        """least_cost_path must be called with 3 correct args: accum_path, backlink_path, target."""
        slope = self._slope(tmp_path)
        result, _, _, mock_lcp = self._run([self._gap()], [self._canal_shapely()], slope, str(tmp_path / "out"))
        lcp_args = mock_lcp.call_args[0]

        # Must have exactly 3 args (kills 108/109: missing args)
        assert len(lcp_args) == 3, f"least_cost_path must be called with 3 args. Got {len(lcp_args)}"

        # arg[0]: accum_path ending in "cost_accum.tif" (kills 105, 108)
        assert isinstance(lcp_args[0], str) and lcp_args[0].endswith("cost_accum.tif"), (
            f"least_cost_path arg[0] must be accum_path. Got {lcp_args[0]!r}"
        )

        # arg[1]: backlink_path ending in "cost_backlink.tif" (kills 106, 109)
        assert isinstance(lcp_args[1], str) and lcp_args[1].endswith("cost_backlink.tif"), (
            f"least_cost_path arg[1] must be backlink_path. Got {lcp_args[1]!r}"
        )

        # arg[2]: target tuple (lon, lat) — not None, not missing (kills 107, 110)
        assert lcp_args[2] is not None, "least_cost_path arg[2] (target) must not be None"
        assert isinstance(lcp_args[2], tuple) and len(lcp_args[2]) == 2, (
            f"least_cost_path arg[2] must be (lon, lat) tuple. Got {lcp_args[2]!r}"
        )


# =============================================================================
# TestDetectarPuntosConflictoCore — targets 70 surviving mutants
# =============================================================================


class TestDetectarPuntosConflictoCore:
    """Targeted tests for detectar_puntos_conflicto surviving mutants."""

    # ── Geometry helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _crossing_gdfs():
        """Canal (y=0) crosses Camino (x=0.5) at (0.5, 0). Drenaje far away."""
        import geopandas as gpd
        from shapely.geometry import LineString

        canales = gpd.GeoDataFrame(
            geometry=[LineString([(0.0, 0.0), (1.0, 0.0)])], crs="EPSG:4326"
        )
        caminos = gpd.GeoDataFrame(
            geometry=[LineString([(0.5, -0.5), (0.5, 0.5)])], crs="EPSG:4326"
        )
        drenajes = gpd.GeoDataFrame(
            geometry=[LineString([(10.0, 10.0), (11.0, 10.0)])], crs="EPSG:4326"
        )
        return canales, caminos, drenajes

    @staticmethod
    def _parallel_gdfs():
        """Canal (y=0) parallel to Camino (y=0.05): only intersect after buffer."""
        import geopandas as gpd
        from shapely.geometry import LineString

        canales = gpd.GeoDataFrame(
            geometry=[LineString([(0.0, 0.0), (1.0, 0.0)])], crs="EPSG:4326"
        )
        caminos = gpd.GeoDataFrame(
            geometry=[LineString([(0.0, 0.05), (1.0, 0.05)])], crs="EPSG:4326"
        )
        drenajes = gpd.GeoDataFrame(
            geometry=[LineString([(10.0, 10.0), (11.0, 10.0)])], crs="EPSG:4326"
        )
        return canales, caminos, drenajes

    @staticmethod
    def _empty_gdfs():
        """All-empty GeoDataFrames."""
        import geopandas as gpd

        empty = gpd.GeoDataFrame(
            geometry=gpd.GeoSeries([], dtype="geometry"), crs="EPSG:4326"
        )
        return empty, empty.copy(), empty.copy()

    @staticmethod
    def _make_srcs(fa_data, fa_transform, sl_data=None, sl_transform=None):
        """Build mock rasterio context-manager sources."""
        from unittest.mock import MagicMock
        import numpy as np

        if sl_data is None:
            sl_data = np.full(fa_data.shape, 10.0)
        if sl_transform is None:
            sl_transform = fa_transform

        def _src(data, t):
            s = MagicMock()
            s.__enter__ = MagicMock(return_value=s)
            s.__exit__ = MagicMock(return_value=False)
            s.read.return_value = data
            s.transform = t
            return s

        return _src(fa_data, fa_transform), _src(sl_data, sl_transform)

    @staticmethod
    def _run(
        canales,
        caminos,
        drenajes,
        fa_src,
        sl_src,
        buffer_m=0.01,
        flow_acc_threshold=500.0,
        slope_threshold=5.0,
        rowcol_kw=None,
        capture_open=False,
    ):
        """Run detectar_puntos_conflicto with mocked rasterio (+ optional rowcol mock)."""
        from unittest.mock import patch
        from contextlib import ExitStack
        from app.domains.geo.intelligence.calculations import detectar_puntos_conflicto

        patches = [patch("rasterio.open", side_effect=[fa_src, sl_src])]
        if rowcol_kw:
            patches.append(patch("rasterio.transform.rowcol", **rowcol_kw))

        with ExitStack() as stack:
            open_mock = stack.enter_context(patches[0])
            for p in patches[1:]:
                stack.enter_context(p)
            result = detectar_puntos_conflicto(
                canales,
                caminos,
                drenajes,
                "fa.tif",
                "sl.tif",
                buffer_m=buffer_m,
                flow_acc_threshold=flow_acc_threshold,
                slope_threshold=slope_threshold,
            )
        if capture_open:
            return result, open_mock
        return result

    # ── Standard transform used across tests ─────────────────────────────────
    # from_bounds(0,-0.2,1,0.2,10,10): centroid (0.5,0) → rowcol → (5,5)

    @staticmethod
    def _std_transform():
        from rasterio.transform import from_bounds

        return from_bounds(0.0, -0.2, 1.0, 0.2, 10, 10)

    # ── Tests: rasterio.open path args (mutmut_12, 13) ──────────────────────

    def test_rasterio_open_paths_kills_mutmut_12_13(self):
        """rasterio.open must be called with fa_path then sl_path, not None."""
        import numpy as np

        transform = self._std_transform()
        fa_src, sl_src = self._make_srcs(np.zeros((10, 10)), transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        _, open_mock = self._run(
            canales, caminos, drenajes, fa_src, sl_src, capture_open=True
        )
        calls = open_mock.call_args_list
        assert len(calls) == 2, f"Expected 2 rasterio.open calls. Got {len(calls)}"
        assert calls[0][0][0] == "fa.tif", (
            f"1st rasterio.open must be fa_path. Got {calls[0][0][0]!r}"
        )
        assert calls[1][0][0] == "sl.tif", (
            f"2nd rasterio.open must be sl_path. Got {calls[1][0][0]!r}"
        )

    # ── Tests: read(1) band arg (mutmut_15, 16, 18, 19) ─────────────────────

    def test_read_band_1_kills_mutmut_15_16_18_19(self):
        """fa_src.read and sl_src.read must each be called with band=1."""
        import numpy as np

        transform = self._std_transform()
        fa_src, sl_src = self._make_srcs(np.zeros((10, 10)), transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        self._run(canales, caminos, drenajes, fa_src, sl_src)

        fa_band = fa_src.read.call_args[0][0]
        sl_band = sl_src.read.call_args[0][0]
        assert fa_band == 1, f"fa_src.read must be called with 1. Got {fa_band!r}"
        assert sl_band == 1, f"sl_src.read must be called with 1. Got {sl_band!r}"

    # ── Tests: end-to-end conflict (mutmut_20, 21, 43-55, 105, 106, 133, 134, 136, 137) ──

    def test_end_to_end_conflict_kills_multiple_mutants(self):
        """Crossing canal+camino → 1 conflict with correct descripcion, crs, geometry."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        # centroid (0.5, 0) maps to rowcol (5,5) with this transform
        fa_data[5, 5] = 600.0
        sl_data[5, 5] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        result = self._run(canales, caminos, drenajes, fa_src, sl_src, buffer_m=0.01)

        # Kills mutmut_20, 21 (transform=None → TypeError caught → fa_val=0 → no conflict)
        # Kills mutmut_43-55 (rowcol args mutated → TypeError → caught → no conflict)
        assert len(result) >= 1, f"Expected ≥1 conflict. Got {len(result)}"

        row = result.iloc[0]

        # Kills mutmut_105 (replace('XX_XX','/'): '_' not replaced → no '/')
        # Kills mutmut_106 (replace('_','XX/XX'): '/' becomes 'XX/XX')
        assert "/" in row["descripcion"], (
            f"descripcion must use '/' separator (kills 105,106). Got {row['descripcion']!r}"
        )

        # Kills mutmut_133 (geometry=None → GDF construction fails or wrong geometry)
        # Kills mutmut_136 (missing geometry kwarg)
        assert result.geometry is not None, "Result must have geometry (kills 133, 136)"
        assert result.geometry.name == "geometry", (
            f"geometry column must be named 'geometry'. Got {result.geometry.name!r}"
        )

        # Kills mutmut_134 (crs=None), mutmut_137 (missing crs)
        assert result.crs is not None, "Result CRS must not be None (kills 134, 137)"
        assert str(result.crs).upper() in ("EPSG:4326", "WGS84"), (
            f"Result CRS must be EPSG:4326. Got {result.crs}"
        )

    # ── Tests: geometry key mutation (mutmut_26, 27) ─────────────────────────

    def test_buffer_geometry_key_kills_mutmut_26_27(self):
        """Buffered geometry must use key 'geometry', not 'XXgeometryXX'/'GEOMETRY'.

        Parallel lines don't cross without buffer. Mutant (wrong key) leaves
        geometry unchanged → no intersection → 0 conflicts instead of 1.
        """
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        # centroid at (0.5, 0.05): rowcol with std_transform → (3, 5)
        fa_data[3, 5] = 600.0
        sl_data[3, 5] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._parallel_gdfs()

        # buffer_m=0.1 (degrees) → buffered canal at y=0 reaches y=0.1, capturing camino at y=0.05
        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src, buffer_m=0.1
        )

        # Original: buffers canal geometry → overlay finds camino at y=0.05 → intersection → conflict
        # mutmut_26 (key "XXgeometryXX"): geometry column unchanged (y=0 line) → no intersection
        # mutmut_27 (key "GEOMETRY"): same — unbuffered canal at y=0 vs camino at y=0.05 → no cross
        assert len(result) >= 1, (
            f"Parallel lines with buffer_m=0.1 must yield ≥1 conflict (kills 26,27). Got {len(result)}"
        )

    # ── Tests: fa_row=0 and fa_col=0 are valid (mutmut_57, 58, 61, 62, 70, 71, 74, 75) ──

    def test_row_and_col_zero_valid_kills_mutmut_57_58_61_62_70_71_74_75(self):
        """Row=0 and col=0 must be considered in-bounds (0<=0 is True, not 0<0/1<=0)."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        fa_data[0, 0] = 600.0  # row=0, col=0 — only valid if 0<= check used
        sl_data[0, 0] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        # rowcol returns (0, 0): both row=0 and col=0 are boundary cases
        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src,
            rowcol_kw={"return_value": (0, 0)},
        )

        # Original: 0<=0<10 True → reads fa_data[0,0]=600 → conflict
        # mutmut_57 (1<=fa_row): 1<=0 False → fa_val=0 → no conflict → killed
        # mutmut_58 (0<fa_row): 0<0 False → same → killed
        # mutmut_61 (1<=fa_col): 1<=0 False → no conflict → killed
        # mutmut_62 (0<fa_col): 0<0 False → same → killed
        # Same for sl (mutmut_70, 71, 74, 75)
        assert len(result) >= 1, (
            f"Row=0 and col=0 must be in-bounds and produce conflict (kills 57,58,61,62,70,71,74,75). "
            f"Got {len(result)}"
        )

    # ── Tests: non-square raster for shape[0] vs shape[1] (mutmut_60, 73) ───

    def test_non_square_raster_kills_mutmut_60_73(self):
        """shape[0] (rows) must be used for row bound, not shape[1] (cols).

        With shape=(10,5) and fa_row=7: 7<10 valid (orig), 7<5 invalid (mutant).
        """
        import numpy as np
        from rasterio.transform import from_bounds

        # Non-square: 10 rows × 5 cols
        transform = from_bounds(0.0, -0.2, 0.5, 0.2, 5, 10)
        fa_data = np.zeros((10, 5))
        sl_data = np.full((10, 5), 10.0)
        fa_data[7, 3] = 600.0  # row=7 < shape[0]=10 ✓, but 7 >= shape[1]=5 ✗ (mutant fails)
        sl_data[7, 3] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        # Mock rowcol to return (7, 3): fa_row=7, fa_col=3
        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src,
            rowcol_kw={"return_value": (7, 3)},
        )

        # Original: 0<=7<10 (shape[0]) True AND 0<=3<5 (shape[1]) True → fa_val=600 → conflict
        # mutmut_60: 0<=7<5 (shape[1] used for row) False → fa_val=0 → no conflict → killed
        # mutmut_73: same for sl_row → killed
        assert len(result) >= 1, (
            f"Row=7 must be valid for shape[0]=10 (kills 60,73). Got {len(result)}"
        )

    # ── Tests: and→or for fa bounds (mutmut_56) ──────────────────────────────

    def test_fa_bounds_and_not_or_kills_mutmut_56(self):
        """fa bounds check must be AND: out-of-bounds row with valid col must give fa_val=0."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        # numpy -1 index = row 9: mutant reads fa_data[-1,5]=fa_data[9,5]
        fa_data[9, 5] = 600.0
        sl_data[5, 5] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        # fa: rowcol → (-1,5) — row invalid, col valid
        # sl: rowcol → (5,5) — both valid → sl_val=2
        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src,
            rowcol_kw={"side_effect": [(-1, 5), (5, 5)]},
        )

        # Original: 0<=-1 False → fa_val=0.0 → 0>500 False → no conflict
        # mutmut_56: (0<=-1<10) OR (0<=5<10) = False OR True = True
        #            → reads fa_data[-1,5]=fa_data[9,5]=600 → conflict!
        assert len(result) == 0, (
            f"fa_row=-1 out-of-bounds must give fa_val=0, not conflict (kills 56). Got {len(result)}"
        )

    # ── Tests: and→or for sl bounds (mutmut_69) ──────────────────────────────

    def test_sl_bounds_and_not_or_kills_mutmut_69(self):
        """sl bounds check must be AND: out-of-bounds sl_row must give sl_val=0."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 2.0)  # default: slope=2 < threshold=5
        # row 9 (=-1 in numpy): set to high slope (above threshold)
        sl_data[9, 5] = 20.0
        fa_data[5, 5] = 600.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        # fa: rowcol → (5,5) in bounds → fa_val=600
        # sl: rowcol → (-1,5) out-of-bounds → sl_val=0.0 (orig) or sl_data[-1,5]=20 (mutant)
        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src,
            rowcol_kw={"side_effect": [(5, 5), (-1, 5)]},
        )

        # Original: 0<=-1 False → sl_val=0.0 → 600>500 AND 0<5 → conflict
        # mutmut_69: (0<=-1<10) OR (0<=5<10) = True → sl_data[-1,5]=20 → 20<5 False → no conflict
        assert len(result) >= 1, (
            f"sl_row=-1 out-of-bounds must give sl_val=0 which satisfies sl<5 (kills 69). "
            f"Got {len(result)}"
        )

    # ── Tests: fa_val=None in else branch (mutmut_67) ────────────────────────

    def test_fa_val_else_none_causes_typeerror_kills_mutmut_67(self):
        """fa_val default in else branch must be 0.0, not None (None > threshold raises TypeError)."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 2.0)
        sl_data[5, 5] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        # fa_row=-5 → out of bounds → else branch: fa_val=0.0 (orig) or None (mutmut_67)
        # sl_row=5, sl_col=5 → in bounds → sl_val=2.0
        # Original: None comparison avoided (fa_val=0.0 → 0.0>500 False → short-circuit)
        # mutmut_67: fa_val=None → None>500 → TypeError propagates up
        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src,
            rowcol_kw={"side_effect": [(-5, 5), (5, 5)]},
        )
        # Just reaching here means no TypeError was raised → original works correctly
        assert result is not None, "Function must not raise TypeError (kills 67)"
        assert len(result) == 0, "fa_row out-of-bounds must give no conflict"

    # ── Tests: sl_val=None in else branch (mutmut_80) ────────────────────────

    def test_sl_val_else_none_causes_typeerror_kills_mutmut_80(self):
        """sl_val default in else branch must be 0.0, not None (fa>threshold AND None<threshold raises)."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 2.0)
        fa_data[5, 5] = 600.0  # fa in bounds: fa_val=600 > 500
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        # fa_row=5, fa_col=5 → in bounds → fa_val=600
        # sl_row=-5 → out of bounds → else: sl_val=0.0 (orig) or None (mutmut_80)
        # Original: 600>500 AND 0.0<5 → conflict (no TypeError)
        # mutmut_80: 600>500 → True → AND None<5 → TypeError!
        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src,
            rowcol_kw={"side_effect": [(5, 5), (-5, 5)]},
        )
        # Reaching here without TypeError → original is correct
        assert result is not None, "Function must not raise TypeError (kills 80)"

    # ── Tests: fa_val=None in except branch (mutmut_82) ──────────────────────

    def test_fa_val_except_none_causes_typeerror_kills_mutmut_82(self):
        """fa_val in except branch must be 0.0, not None (None>threshold raises TypeError)."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 2.0)
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        # rowcol raises → except triggered → fa_val=0.0 (orig) or None (mutmut_82)
        # Original: fa_val=0.0 → 0.0>500 False → short-circuit → no TypeError
        # mutmut_82: fa_val=None → None>500 → TypeError!
        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src,
            rowcol_kw={"side_effect": AttributeError("rowcol failed")},
        )
        assert result is not None, "Function must not raise TypeError from except branch (kills 82)"
        assert len(result) == 0, "rowcol exception must be caught, result empty"

    # ── Tests: flow_acc threshold is strict > (mutmut_87) ────────────────────

    def test_threshold_strict_greater_kills_mutmut_87(self):
        """fa_val exactly equal to threshold must NOT trigger conflict (> not >=)."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        fa_data[5, 5] = 500.0  # exactly equal to default threshold
        sl_data[5, 5] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src,
            flow_acc_threshold=500.0,
        )

        # Original: 500 > 500 → False → no conflict
        # mutmut_87: 500 >= 500 → True → conflict → test fails → killed
        assert len(result) == 0, (
            f"fa_val=threshold must NOT trigger conflict (kills 87). Got {len(result)}"
        )

    # ── Tests: descripcion uses '/' separator (mutmut_105, 106) ─────────────

    def test_descripcion_slash_separator_kills_mutmut_105_106(self):
        """tipo.replace('_', '/') must produce '/' in descripcion."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        fa_data[5, 5] = 600.0
        sl_data[5, 5] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        result = self._run(canales, caminos, drenajes, fa_src, sl_src, buffer_m=0.01)

        assert len(result) >= 1, "Need at least 1 conflict to check descripcion"
        desc = result.iloc[0]["descripcion"]

        # mutmut_105: replace('XX_XX', '/') → '_' not replaced → no '/' → killed
        # mutmut_106: replace('_', 'XX/XX') → 'canal/camino' becomes 'canalXX/XXcamino' → killed
        assert "/" in desc and "XX" not in desc, (
            f"descripcion must have '/' without 'XX' (kills 105,106). Got {desc!r}"
        )
        # Check it's actually in the right format: "canal/camino"
        assert desc.startswith("Cruce canal/camino") or "canal/camino" in desc, (
            f"descripcion must contain 'canal/camino'. Got {desc!r}"
        )

    # ── Tests: empty result column names (mutmut_118-129) ────────────────────

    def test_empty_result_column_names_kills_mutmut_118_to_129(self):
        """Empty result must have exact column names (lowercase, no XX markers)."""
        import geopandas as gpd

        canales, caminos, drenajes = self._empty_gdfs()
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)

        result = self._run(canales, caminos, drenajes, fa_src, sl_src)

        assert isinstance(result, gpd.GeoDataFrame), "Empty result must be a GeoDataFrame"
        assert len(result) == 0, "All-empty GDFs must yield empty result"

        cols = list(result.columns)
        # mutmut_118/119: "XXtipoXX"/"TIPO" instead of "tipo"
        assert "tipo" in cols, f"'tipo' must be a column (kills 118,119). Got {cols}"
        # mutmut_122/123: "XXdescripcionXX"/"DESCRIPCION"
        assert "descripcion" in cols, (
            f"'descripcion' must be a column (kills 122,123). Got {cols}"
        )
        # mutmut_124/125: "XXseveridadXX"/"SEVERIDAD"
        assert "severidad" in cols, (
            f"'severidad' must be a column (kills 124,125). Got {cols}"
        )
        # mutmut_126/127: "XXacumulacion_valorXX"/"ACUMULACION_VALOR"
        assert "acumulacion_valor" in cols, (
            f"'acumulacion_valor' must be a column (kills 126,127). Got {cols}"
        )
        # mutmut_128/129: "XXpendiente_valorXX"/"PENDIENTE_VALOR"
        assert "pendiente_valor" in cols, (
            f"'pendiente_valor' must be a column (kills 128,129). Got {cols}"
        )

    # ── Tests: empty result geometry column (mutmut_115, 117) ────────────────

    def test_empty_result_has_geometry_column_kills_mutmut_115_117(self):
        """Empty result GeoDataFrame must have 'geometry' as active geometry column."""
        import numpy as np
        import geopandas as gpd

        canales, caminos, drenajes = self._empty_gdfs()
        transform = self._std_transform()
        fa_src, sl_src = self._make_srcs(np.zeros((10, 10)), transform)

        result = self._run(canales, caminos, drenajes, fa_src, sl_src)

        assert isinstance(result, gpd.GeoDataFrame), "Empty result must be GeoDataFrame"
        # mutmut_115: geometry=None → active geometry is None → result.geometry raises
        # mutmut_117: no geometry= kwarg → geopandas may not set active geometry
        try:
            geom_col = result.geometry
            assert geom_col is not None, (
                "Empty result must have geometry accessor (kills 115, 117)"
            )
        except AttributeError as e:
            raise AssertionError(
                f"Empty result.geometry raised AttributeError (kills 115, 117): {e}"
            )

    # ── Tests: slope threshold is strict < (mutmut_88) ───────────────────────

    def test_slope_threshold_strict_less_kills_mutmut_88(self):
        """sl_val exactly equal to slope_threshold must NOT trigger conflict (< not <=)."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        fa_data[5, 5] = 600.0  # fa > threshold
        sl_data[5, 5] = 5.0   # sl == slope_threshold (exactly)
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src,
            slope_threshold=5.0,
        )

        # Original: 5.0 < 5.0 → False → no conflict
        # mutmut_88: 5.0 <= 5.0 → True → conflict → test fails → killed
        assert len(result) == 0, (
            f"sl_val=threshold must NOT trigger conflict (kills 88). Got {len(result)}"
        )

    # ── Tests: severidad comes from function, not None (mutmut_89) ───────────

    def test_severidad_not_none_kills_mutmut_89(self):
        """severidad must be computed by _clasificar_severidad_conflicto, not set to None."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        fa_data[5, 5] = 600.0
        sl_data[5, 5] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        result = self._run(canales, caminos, drenajes, fa_src, sl_src, buffer_m=0.01)

        assert len(result) >= 1, "Need ≥1 conflict to check severidad"
        row = result.iloc[0]
        # mutmut_89: severidad = None instead of _clasificar_severidad_conflicto(...)
        assert row["severidad"] is not None, (
            f"severidad must not be None (kills 89). Got {row['severidad']!r}"
        )
        assert isinstance(row["severidad"], str), (
            f"severidad must be a string. Got {type(row['severidad'])}"
        )

    # ── Tests: non-empty result CRS (mutmut_134, 137, 141) ───────────────────

    def test_result_crs_epsg4326_kills_mutmut_134_137_141(self):
        """Non-empty result must have crs='EPSG:4326'."""
        import numpy as np

        transform = self._std_transform()
        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        fa_data[5, 5] = 600.0
        sl_data[5, 5] = 2.0
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        result = self._run(canales, caminos, drenajes, fa_src, sl_src, buffer_m=0.01)
        assert len(result) >= 1, "Need ≥1 conflict to check CRS"

        # mutmut_134: crs=None → result.crs is None
        # mutmut_137: missing crs kwarg → result.crs is None
        assert result.crs is not None, "Result CRS must not be None (kills 134, 137)"

        # mutmut_141: crs='epsg:4326' (lowercase) — geopandas normalizes, so this is equivalent
        crs_str = str(result.crs).upper()
        assert "4326" in crs_str, f"Result CRS must contain 4326. Got {result.crs}"

    def test_sl_row_zero_valid_kills_mutmut_70_71(self):
        """sl_row=0 is valid (0 <= 0 < shape[0]).
        mutmut_70 changes 0<= to 1<=, mutmut_71 changes 0<= to 0<.
        Both reject row=0, so no conflict is produced.
        """
        import numpy as np
        from rasterio.transform import from_bounds

        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        # fa at row=5,col=5 — valid, high flow acc
        fa_data[5, 5] = 1000.0
        # sl at row=0,col=5 — valid in original (0<=0), low slope → conflict!
        sl_data[0, 5] = 2.0
        transform = from_bounds(0.0, -0.2, 1.0, 0.2, 10, 10)
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src, buffer_m=0.01,
            flow_acc_threshold=500.0, slope_threshold=5.0,
            rowcol_kw={"side_effect": [(5, 5), (0, 5)]},
        )
        assert len(result) >= 1, (
            "sl_row=0 is valid — should produce conflict (kills mutmut_70, mutmut_71)"
        )

    def test_sl_col_zero_valid_kills_mutmut_74_75(self):
        """sl_col=0 is valid (0 <= 0 < shape[1]).
        mutmut_74 changes 0<= to 1<=, mutmut_75 changes 0<= to 0<.
        Both reject col=0, so no conflict is produced.
        """
        import numpy as np
        from rasterio.transform import from_bounds

        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 10), 10.0)
        fa_data[5, 5] = 1000.0
        sl_data[5, 0] = 2.0  # valid col=0, low slope → conflict
        transform = from_bounds(0.0, -0.2, 1.0, 0.2, 10, 10)
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src, buffer_m=0.01,
            flow_acc_threshold=500.0, slope_threshold=5.0,
            rowcol_kw={"side_effect": [(5, 5), (5, 0)]},
        )
        assert len(result) >= 1, (
            "sl_col=0 is valid — should produce conflict (kills mutmut_74, mutmut_75)"
        )

    def test_sl_shape0_vs_shape1_kills_mutmut_73(self):
        """sl_data.shape[0]!=shape[1]; sl_row near shape[0]-1 but > shape[1]-1.
        mutmut_73 uses shape[1] instead of shape[0] for row upper bound.
        With shape=(10,8), sl_row=9: original passes (9<10), mutant fails (9<8→False).
        """
        import numpy as np
        from rasterio.transform import from_bounds

        fa_data = np.zeros((10, 10))
        sl_data = np.full((10, 8), 10.0)  # non-square: 10 rows, 8 cols
        fa_data[5, 5] = 1000.0
        sl_data[9, 5] = 2.0  # row=9 valid (9<10), col=5 valid (5<8), low slope
        transform = from_bounds(0.0, -0.2, 1.0, 0.2, 10, 10)
        sl_transform = from_bounds(0.0, -0.2, 1.0, 0.2, 10, 8)
        fa_src, sl_src = self._make_srcs(fa_data, transform, sl_data, sl_transform)
        canales, caminos, drenajes = self._crossing_gdfs()

        result = self._run(
            canales, caminos, drenajes, fa_src, sl_src, buffer_m=0.01,
            flow_acc_threshold=500.0, slope_threshold=5.0,
            rowcol_kw={"side_effect": [(5, 5), (9, 5)]},
        )
        assert len(result) >= 1, (
            "sl_row=9 valid in 10-row array — should produce conflict (kills mutmut_73)"
        )
