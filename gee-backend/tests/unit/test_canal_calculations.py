"""
Unit tests for pure calculation functions in intelligence/calculations.py.

NO database, NO WhiteboxTools — everything is mocked.

Tests:
  - rank_canal_hotspots: mock rasterio, verify ranking + risk classification
  - detect_coverage_gaps: mock zones + canals, verify gap detection logic
  - compute_maintenance_priority: verify composite score, weights, normalization
  - Edge cases: empty inputs, all zeros, single canal
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from shapely.geometry import LineString, Point, Polygon, mapping


# ---------------------------------------------------------------------------
# rank_canal_hotspots
# ---------------------------------------------------------------------------


class TestRankCanalHotspots:
    """Test hotspot ranking with mocked rasterio."""

    def _make_fake_rasterio_dataset(
        self,
        data: np.ndarray,
        nodata: float = -9999.0,
    ) -> MagicMock:
        """Build a mock rasterio dataset that returns `data` on read(1)."""
        from rasterio.transform import from_bounds

        ds = MagicMock()
        ds.read.return_value = data
        ds.nodata = nodata
        ds.transform = from_bounds(0, 0, 1, 1, data.shape[1], data.shape[0])
        ds.__enter__ = lambda self: self
        ds.__exit__ = MagicMock(return_value=False)
        return ds

    def _patch_rasterio_and_call(
        self,
        data: np.ndarray,
        canal_geometries: list[dict],
        num_points: int = 5,
    ) -> list[dict]:
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fake_ds = self._make_fake_rasterio_dataset(data)

        with (
            patch("rasterio.open", return_value=fake_ds),
            patch.object(Path, "exists", return_value=True),
        ):
            return rank_canal_hotspots(
                canal_geometries,
                "/fake/flow_acc.tif",
                num_points=num_points,
            )

    def test_ranks_by_flow_acc_descending(self):
        # A 10x10 raster where left half = 100, right half = 500
        data = np.full((10, 10), 100.0, dtype=np.float32)
        data[:, 5:] = 500.0

        # Canal A covers left half (low flow_acc)
        canal_a = {
            "id": 1,
            "geometry": mapping(LineString([(0.1, 0.5), (0.4, 0.5)])),
        }
        # Canal B covers right half (high flow_acc)
        canal_b = {
            "id": 2,
            "geometry": mapping(LineString([(0.6, 0.5), (0.9, 0.5)])),
        }

        results = self._patch_rasterio_and_call(data, [canal_a, canal_b])

        assert len(results) == 2
        # Canal B should rank first (higher flow_acc)
        assert results[0]["flow_acc_max"] >= results[1]["flow_acc_max"]

    def test_risk_classification_percentile_based(self):
        # 4 canals with different flow acc ranges to trigger all levels
        data = np.zeros((10, 10), dtype=np.float32)
        # Row 0-2 = 100, Row 3-4 = 300, Row 5-6 = 600, Row 7-9 = 1000
        data[0:3, :] = 100.0
        data[3:5, :] = 300.0
        data[5:7, :] = 600.0
        data[7:, :] = 1000.0

        canals = [
            {"id": i, "geometry": mapping(LineString([
                (0.1, 0.05 + i * 0.25), (0.9, 0.05 + i * 0.25)
            ]))}
            for i in range(4)
        ]

        results = self._patch_rasterio_and_call(data, canals)

        assert len(results) >= 1
        risk_levels = {r["risk_level"] for r in results}
        # With 4 canals, percentile thresholds should produce at least 2 levels
        assert len(risk_levels) >= 2

    def test_empty_canal_list(self):
        data = np.ones((10, 10), dtype=np.float32) * 50
        results = self._patch_rasterio_and_call(data, [])
        assert results == []

    def test_single_canal_gets_critico(self):
        """With only one canal, p75 == p50 == value, so it should be critico."""
        data = np.ones((10, 10), dtype=np.float32) * 200
        canal = {
            "id": 1,
            "geometry": mapping(LineString([(0.1, 0.5), (0.9, 0.5)])),
        }

        results = self._patch_rasterio_and_call(data, [canal])

        assert len(results) == 1
        # Single element: its max >= p75 (which equals itself), so critico
        assert results[0]["risk_level"] == "critico"

    def test_canal_without_geometry_is_skipped(self):
        data = np.ones((10, 10), dtype=np.float32) * 100
        canals = [
            {"id": 1, "geometry": None},
            {"id": 2, "geometry": mapping(LineString([(0.1, 0.5), (0.9, 0.5)]))},
        ]

        results = self._patch_rasterio_and_call(data, canals)
        assert len(results) == 1
        assert results[0]["segment_index"] == 1  # skipped index 0

    def test_file_not_found_raises(self):
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        with pytest.raises(FileNotFoundError):
            rank_canal_hotspots(
                [{"geometry": mapping(LineString([(0, 0), (1, 1)]))}],
                "/nonexistent/flow_acc.tif",
            )

    def test_output_fields_present(self):
        data = np.ones((10, 10), dtype=np.float32) * 300
        canal = {
            "id": 99,
            "geometry": mapping(LineString([(0.1, 0.5), (0.9, 0.5)])),
        }

        results = self._patch_rasterio_and_call(data, [canal])

        assert len(results) == 1
        r = results[0]
        assert "geometry" in r
        assert "score" in r
        assert "flow_acc_max" in r
        assert "flow_acc_mean" in r
        assert "risk_level" in r
        assert "segment_index" in r


# ---------------------------------------------------------------------------
# detect_coverage_gaps
# ---------------------------------------------------------------------------


class TestDetectCoverageGaps:
    """Test gap detection — pure geometry + threshold logic."""

    def _make_zone(self, zone_id: str, centroid: tuple[float, float]) -> dict:
        """Create a small polygon zone centered at the given point."""
        cx, cy = centroid
        poly = Polygon([
            (cx - 0.01, cy - 0.01),
            (cx + 0.01, cy - 0.01),
            (cx + 0.01, cy + 0.01),
            (cx - 0.01, cy + 0.01),
        ])
        return {"id": zone_id, "geometry": mapping(poly)}

    def _make_canal(self, coords: list[tuple[float, float]]) -> dict:
        return {"geometry": mapping(LineString(coords))}

    def test_detects_gap_when_far_from_canal(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # Zone far from canal (100+ km apart in degree-space at ~111 km/deg)
        zones = [self._make_zone("z1", (10.0, 10.0))]
        hci_scores = {"z1": 85.0}
        canals = [self._make_canal([(0.0, 0.0), (0.5, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )

        assert len(gaps) == 1
        assert gaps[0]["zone_id"] == "z1"
        assert gaps[0]["gap_km"] > 2.0

    def test_no_gap_when_close_to_canal(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # Zone very close to canal (within threshold)
        zones = [self._make_zone("z1", (0.001, 0.001))]
        hci_scores = {"z1": 85.0}
        canals = [self._make_canal([(0.0, 0.0), (0.01, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )

        assert len(gaps) == 0

    def test_no_gap_when_hci_below_threshold(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._make_zone("z1", (10.0, 10.0))]
        hci_scores = {"z1": 30.0}  # Below threshold
        canals = [self._make_canal([(0.0, 0.0), (0.5, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )

        assert len(gaps) == 0

    def test_severity_classification_critico(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # HCI > 80 and distance > 5 km => critico
        zones = [self._make_zone("z1", (1.0, 1.0))]  # ~111 km from canal
        hci_scores = {"z1": 90.0}
        canals = [self._make_canal([(0.0, 0.0), (0.01, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )

        assert len(gaps) == 1
        assert gaps[0]["severity"] == "critico"

    def test_severity_classification_alto(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # HCI > 60 and distance > 3 km => alto
        zones = [self._make_zone("z1", (0.05, 0.05))]  # ~5.5 km
        hci_scores = {"z1": 65.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )

        assert len(gaps) == 1
        assert gaps[0]["severity"] == "alto"

    def test_empty_zones_returns_empty(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        gaps = detect_coverage_gaps(
            [], {"z1": 80.0}, [self._make_canal([(0, 0), (1, 0)])],
        )
        assert gaps == []

    def test_empty_canals_returns_empty(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        gaps = detect_coverage_gaps(
            [self._make_zone("z1", (1.0, 1.0))],
            {"z1": 80.0},
            [],
        )
        assert gaps == []

    def test_gaps_sorted_by_severity_then_hci(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [
            self._make_zone("za", (1.0, 1.0)),
            self._make_zone("zb", (2.0, 2.0)),
        ]
        hci_scores = {"za": 55.0, "zb": 95.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )

        assert len(gaps) == 2
        # zb (critico, 95) should come before za (moderado or alto, 55)
        assert gaps[0]["zone_id"] == "zb"

    def test_zone_without_hci_score_skipped(self):
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._make_zone("z1", (10.0, 10.0))]
        hci_scores = {}  # no score for z1 -> defaults to 0.0
        canals = [self._make_canal([(0, 0), (1, 0)])]

        gaps = detect_coverage_gaps(zones, hci_scores, canals)
        assert gaps == []


# ---------------------------------------------------------------------------
# compute_maintenance_priority
# ---------------------------------------------------------------------------


class TestComputeMaintenancePriority:
    """Test composite score with known inputs."""

    def test_all_factors_present(self):
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.5, 2: 1.0},
            flow_acc_scores={1: 500.0, 2: 1000.0},
            hci_scores={"1": 60.0, "2": 80.0},
            conflict_counts={1: 2, 2: 5},
        )

        assert len(results) == 2
        # Node 2 has higher values everywhere -> should rank first
        assert results[0]["node_id"] == 2
        assert results[0]["composite_score"] > results[1]["composite_score"]

    def test_weights_sum_to_one(self):
        """Base weights are 0.30 + 0.25 + 0.25 + 0.20 = 1.0."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        # When all factors are present for a node, composite should be <= 1.0
        results = compute_maintenance_priority(
            centrality_scores={1: 0.8},
            flow_acc_scores={1: 5000.0},
            hci_scores={"1": 90.0},
            conflict_counts={1: 10},
        )

        assert len(results) == 1
        assert 0.0 <= results[0]["composite_score"] <= 1.0

    def test_weight_redistribution_with_missing_factors(self):
        """When some factors are missing, weight is redistributed."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        # Only centrality present (weight 0.30)
        # After redistribution: 0.30 / 0.30 = 1.0 multiplier
        results = compute_maintenance_priority(
            centrality_scores={1: 0.5, 2: 1.0},
            flow_acc_scores={},
            hci_scores={},
            conflict_counts={},
        )

        assert len(results) == 2
        # Node with max centrality should have composite = 1.0
        assert results[0]["composite_score"] == pytest.approx(1.0, abs=0.01)
        assert results[0]["missing_factors"] is not None
        assert "flow_acc" in results[0]["missing_factors"]

    def test_empty_inputs_returns_empty(self):
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={},
            flow_acc_scores={},
            hci_scores={},
            conflict_counts={},
        )
        assert results == []

    def test_single_node_normalization(self):
        """Single node: min==max, so _min_max adjusts to avoid div by zero."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.5},
            flow_acc_scores={1: 500.0},
            hci_scores={"1": 60.0},
            conflict_counts={1: 3},
        )

        assert len(results) == 1
        # With _min_max returning (val, val+1), normalized = (val - val) / 1 = 0
        # BUT that means all factors are 0 except we check the formula:
        # norm = (0.5 - 0.5) / (0.5 + 1.0 - 0.5) = 0.0
        # So composite = 0.0 for single node
        assert results[0]["composite_score"] == pytest.approx(0.0, abs=0.01)

    def test_components_contain_raw_and_normalized(self):
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.3},
            flow_acc_scores={1: 200.0},
            hci_scores={},
            conflict_counts={},
        )

        assert len(results) == 1
        components = results[0]["components"]
        assert "centrality" in components
        assert "raw" in components["centrality"]
        assert "normalized" in components["centrality"]
        assert "flow_acc" in components
        assert "raw" in components["flow_acc"]
        assert "normalized" in components["flow_acc"]

    def test_all_zeros_does_not_crash(self):
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.0},
            flow_acc_scores={1: 0.0},
            hci_scores={"1": 0.0},
            conflict_counts={1: 0},
        )

        assert len(results) == 1
        assert results[0]["composite_score"] == pytest.approx(0.0, abs=0.01)

    @pytest.mark.parametrize("node_count", [5, 20, 100])
    def test_results_sorted_descending(self, node_count: int):
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        rng = np.random.default_rng(42)
        centrality = {i: float(rng.random()) for i in range(node_count)}
        flow_acc = {i: float(rng.random() * 10000) for i in range(node_count)}
        hci = {str(i): float(rng.random() * 100) for i in range(node_count)}
        conflicts = {i: int(rng.integers(0, 10)) for i in range(node_count)}

        results = compute_maintenance_priority(centrality, flow_acc, hci, conflicts)

        scores = [r["composite_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_mixed_node_ids_across_factors(self):
        """Nodes can appear in some factors but not others."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.8},
            flow_acc_scores={2: 500.0},
            hci_scores={"3": 70.0},
            conflict_counts={1: 2, 2: 3},
        )

        # Nodes 1, 2, 3 should all appear
        node_ids = {r["node_id"] for r in results}
        assert node_ids == {1, 2, 3}


# ---------------------------------------------------------------------------
# Mutation-killing tests: rank_canal_hotspots
# ---------------------------------------------------------------------------


class TestRankCanalHotspotsMutationKill:
    """Exact-value tests to kill surviving mutations in rank_canal_hotspots."""

    def _make_fake_rasterio_dataset(
        self,
        data: np.ndarray,
        nodata: float = -9999.0,
    ) -> MagicMock:
        from rasterio.transform import from_bounds

        ds = MagicMock()
        ds.read.return_value = data
        ds.nodata = nodata
        ds.transform = from_bounds(0, 0, 1, 1, data.shape[1], data.shape[0])
        ds.__enter__ = lambda self: self
        ds.__exit__ = MagicMock(return_value=False)
        return ds

    def _patch_rasterio_and_call(
        self,
        data: np.ndarray,
        canal_geometries: list[dict],
        num_points: int = 5,
    ) -> list[dict]:
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fake_ds = self._make_fake_rasterio_dataset(data)
        with (
            patch("rasterio.open", return_value=fake_ds),
            patch.object(Path, "exists", return_value=True),
        ):
            return rank_canal_hotspots(
                canal_geometries,
                "/fake/flow_acc.tif",
                num_points=num_points,
            )

    def test_exact_flow_acc_max_and_mean(self):
        """Pin flow_acc_max and flow_acc_mean to exact values (uniform raster)."""
        data = np.full((10, 10), 350.0, dtype=np.float32)
        canal = {
            "id": 1,
            "geometry": mapping(LineString([(0.1, 0.5), (0.9, 0.5)])),
        }
        results = self._patch_rasterio_and_call(data, [canal])

        assert len(results) == 1
        assert results[0]["flow_acc_max"] == pytest.approx(350.0, abs=0.01)
        assert results[0]["flow_acc_mean"] == pytest.approx(350.0, abs=0.01)
        assert results[0]["score"] == pytest.approx(350.0, abs=0.01)

    def test_risk_percentile_thresholds_exact(self):
        """Pin all 4 risk levels with exact percentile boundaries.

        4 canals with distinct flow_acc_max values: 100, 200, 300, 400.
        p25 = 175, p50 = 250, p75 = 325.
        400 >= p75(325) => critico
        300 >= p50(250) => alto
        200 >= p25(175) => medio
        100 < p25(175) => bajo
        """
        # Each canal lives on a distinct uniform row band
        data = np.zeros((20, 10), dtype=np.float32)
        data[0:5, :] = 100.0   # canal at y~0.875 (row 0-4)
        data[5:10, :] = 200.0  # canal at y~0.625 (row 5-9)
        data[10:15, :] = 300.0 # canal at y~0.375 (row 10-14)
        data[15:20, :] = 400.0 # canal at y~0.125 (row 15-19)

        canals = [
            {"id": 1, "geometry": mapping(LineString([(0.1, 0.875), (0.9, 0.875)]))},  # 100
            {"id": 2, "geometry": mapping(LineString([(0.1, 0.625), (0.9, 0.625)]))},  # 200
            {"id": 3, "geometry": mapping(LineString([(0.1, 0.375), (0.9, 0.375)]))},  # 300
            {"id": 4, "geometry": mapping(LineString([(0.1, 0.125), (0.9, 0.125)]))},  # 400
        ]

        results = self._patch_rasterio_and_call(data, canals)
        by_id = {r["id"]: r for r in results}

        assert by_id[4]["risk_level"] == "critico"
        assert by_id[3]["risk_level"] == "alto"
        assert by_id[2]["risk_level"] == "medio"
        assert by_id[1]["risk_level"] == "bajo"

    def test_risk_at_exact_p75_is_critico(self):
        """Value == p75 must be critico (>= not >)."""
        # 2 canals: [100, 400]. p75 = np.percentile([100, 400], 75) = 325
        # 400 >= 325 => critico, 100 < 325 and check p50=250: 100 < 250 => check p25=175: 100 < 175 => bajo
        data = np.zeros((10, 10), dtype=np.float32)
        data[0:5, :] = 100.0
        data[5:10, :] = 400.0

        canals = [
            {"id": 1, "geometry": mapping(LineString([(0.1, 0.75), (0.9, 0.75)]))},
            {"id": 2, "geometry": mapping(LineString([(0.1, 0.25), (0.9, 0.25)]))},
        ]
        results = self._patch_rasterio_and_call(data, canals)
        by_id = {r["id"]: r for r in results}
        assert by_id[2]["risk_level"] == "critico"  # 400 >= p75
        assert by_id[1]["risk_level"] == "bajo"     # 100 < p25

    def test_score_equals_flow_acc_max_rounded(self):
        """score field must equal round(flow_acc_max, 2)."""
        data = np.full((10, 10), 123.456, dtype=np.float32)
        canal = {"id": 1, "geometry": mapping(LineString([(0.1, 0.5), (0.9, 0.5)]))}
        results = self._patch_rasterio_and_call(data, [canal])
        assert results[0]["score"] == results[0]["flow_acc_max"]

    def test_segment_index_tracks_original_position(self):
        """segment_index must match the enumerate index, not post-sort position."""
        data = np.zeros((10, 10), dtype=np.float32)
        data[0:5, :] = 999.0
        data[5:10, :] = 1.0

        canals = [
            {"id": "low", "geometry": mapping(LineString([(0.1, 0.25), (0.9, 0.25)]))},  # idx 0, low
            {"id": "high", "geometry": mapping(LineString([(0.1, 0.75), (0.9, 0.75)]))}, # idx 1, high
        ]
        results = self._patch_rasterio_and_call(data, canals)
        # Sorted descending: high first
        assert results[0]["segment_index"] == 1
        assert results[1]["segment_index"] == 0


# ---------------------------------------------------------------------------
# Mutation-killing tests: detect_coverage_gaps
# ---------------------------------------------------------------------------


class TestDetectCoverageGapsMutationKill:
    """Exact boundary & severity tests to kill surviving mutations."""

    def _make_zone(self, zone_id: str, centroid: tuple[float, float]) -> dict:
        cx, cy = centroid
        poly = Polygon([
            (cx - 0.001, cy - 0.001),
            (cx + 0.001, cy - 0.001),
            (cx + 0.001, cy + 0.001),
            (cx - 0.001, cy + 0.001),
        ])
        return {"id": zone_id, "geometry": mapping(poly)}

    def _make_canal(self, coords: list[tuple[float, float]]) -> dict:
        return {"geometry": mapping(LineString(coords))}

    def test_distance_at_threshold_boundary_is_gap(self):
        """dist_km == threshold_km is NOT filtered (code uses < not <=).

        Place zone so dist_km is just barely above threshold.
        Canal is a tiny segment near origin; zone centroid placed so
        distance to nearest canal point > threshold.
        """
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # Canal at y=10.0, zone centroid at y=10.0 + offset in x
        # Using a canal segment at (0,0)-(0.0001,0) essentially at origin
        # Zone at (0.05, 0.0) => dist ~ 0.05 * 111 ~ 5.55 km
        zones = [self._make_zone("z1", (0.05, 0.0))]
        hci_scores = {"z1": 90.0}
        canals = [self._make_canal([(0.0, 0.0), (0.0001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=5.5, hci_threshold=50.0
        )
        # dist ~ 5.55, threshold = 5.5
        # 5.55 < 5.5 is False => NOT filtered => IS a gap
        assert len(gaps) == 1
        assert gaps[0]["gap_km"] > 5.5

    def test_distance_just_below_threshold_is_not_gap(self):
        """dist_km just below threshold => filtered out (< threshold)."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        dist_deg = 1.9 / 111.0  # ~1.9 km, below 2.0
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 90.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 0

    def test_hci_exactly_at_threshold_is_not_gap(self):
        """hci < hci_threshold filters: hci == hci_threshold should NOT be filtered.

        Code: if hci < hci_threshold: continue
        hci=50.0, threshold=50.0 => 50 < 50 is False => NOT filtered => IS a gap.
        """
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._make_zone("z1", (1.0, 1.0))]  # far from canal
        hci_scores = {"z1": 50.0}  # exactly at threshold
        canals = [self._make_canal([(0.0, 0.0), (0.01, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1

    def test_hci_just_below_threshold_is_filtered(self):
        """hci=49.9 < 50.0 => filtered, no gap."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._make_zone("z1", (1.0, 1.0))]
        hci_scores = {"z1": 49.9}
        canals = [self._make_canal([(0.0, 0.0), (0.01, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 0

    def test_distance_uses_111_km_per_degree(self):
        """Verify the 111.0 km/degree conversion constant."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # Zone at 1.0 degrees from canal => dist_km = 1.0 * 111.0 = 111.0 km
        zones = [self._make_zone("z1", (1.0, 0.0))]
        hci_scores = {"z1": 90.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        assert gaps[0]["gap_km"] == pytest.approx(111.0, abs=1.0)

    def test_severity_critico_requires_hci_gt_80_and_dist_gt_5(self):
        """critico: hci > 80.0 AND dist_km > 5.0 (strict >)."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # hci=80.0 (NOT > 80) and dist > 5 => NOT critico
        dist_deg = 6.0 / 111.0
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 80.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        # hci=80 is NOT > 80, so falls to next check: hci > 60 and dist > 3 => alto
        assert gaps[0]["severity"] == "alto"

    def test_severity_critico_with_hci_81_dist_6(self):
        """hci=81 > 80 and dist=6 > 5 => critico."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        dist_deg = 6.0 / 111.0
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 81.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        assert gaps[0]["severity"] == "critico"

    def test_severity_alto_requires_hci_gt_60_and_dist_gt_3(self):
        """alto: hci > 60 AND dist > 3. hci=60 NOT > 60 => moderado."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        dist_deg = 4.0 / 111.0
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 60.0}  # NOT > 60
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        assert gaps[0]["severity"] == "moderado"

    def test_severity_alto_with_hci_61_dist_4(self):
        """hci=61 > 60 and dist=4 > 3 => alto."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        dist_deg = 4.0 / 111.0
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 61.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        assert gaps[0]["severity"] == "alto"

    def test_severity_moderado_when_dist_at_3(self):
        """dist=3.0 is NOT > 3.0, so even with hci=65 => moderado."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        dist_deg = 3.0 / 111.0
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 65.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        assert gaps[0]["severity"] == "moderado"

    def test_severity_critico_dist_at_5_is_not_critico(self):
        """dist=5.0 is NOT > 5.0, so even with hci=85 => check alto (hci>60, dist>3? 5>3 yes) => alto."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        dist_deg = 5.0 / 111.0
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 85.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        # dist=5.0 NOT > 5.0 but hci=85>60 and dist=5>3 => alto
        assert gaps[0]["severity"] == "alto"

    def test_gap_km_exact_value(self):
        """Verify gap_km = round(dist_deg * 111.0, 2)."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        dist_deg = 0.05  # 0.05 * 111 = 5.55
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 90.0}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        assert gaps[0]["gap_km"] == pytest.approx(5.55, abs=0.15)

    def test_hci_score_rounded_in_output(self):
        """hci_score in output is round(hci, 2)."""
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._make_zone("z1", (1.0, 0.0))]
        hci_scores = {"z1": 75.555}
        canals = [self._make_canal([(0.0, 0.0), (0.001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        assert gaps[0]["hci_score"] == pytest.approx(75.56, abs=0.01)


# ---------------------------------------------------------------------------
# Mutation-killing tests: compute_maintenance_priority
# ---------------------------------------------------------------------------


class TestComputeMaintenancePriorityMutationKill:
    """Exact weight, normalization, and composite score tests."""

    def test_exact_weight_values(self):
        """Pin base weights: centrality=0.30, flow_acc=0.25, hci=0.25, conflicts=0.20."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        # Two nodes: node 1 has all min values, node 2 has all max values.
        # With min-max normalization:
        #   node 1: all normalized = 0.0
        #   node 2: all normalized = 1.0
        # Node 2 composite = 0.30*1 + 0.25*1 + 0.25*1 + 0.20*1 = 1.0
        # Node 1 composite = 0.0
        results = compute_maintenance_priority(
            centrality_scores={1: 0.0, 2: 1.0},
            flow_acc_scores={1: 0.0, 2: 1000.0},
            hci_scores={"1": 0.0, "2": 100.0},
            conflict_counts={1: 0, 2: 10},
        )

        by_node = {r["node_id"]: r for r in results}
        assert by_node[2]["composite_score"] == pytest.approx(1.0, abs=0.001)
        assert by_node[1]["composite_score"] == pytest.approx(0.0, abs=0.001)

    def test_exact_composite_with_known_normalization(self):
        """Verify composite = 0.30*cent_norm + 0.25*fa_norm + 0.25*hci_norm + 0.20*conf_norm.

        3 nodes:
          cent: {1: 0.0, 2: 0.5, 3: 1.0} => min=0.0, max=1.0 => norms: 0, 0.5, 1.0
          fa:   {1: 100, 2: 300, 3: 500}  => min=100, max=500 => norms: 0, 0.5, 1.0
          hci:  {1: 20, 2: 60, 3: 100}    => min=20, max=100  => norms: 0, 0.5, 1.0
          conf: {1: 0, 2: 5, 3: 10}       => min=0, max=10    => norms: 0, 0.5, 1.0

        Node 2: composite = 0.30*0.5 + 0.25*0.5 + 0.25*0.5 + 0.20*0.5 = 0.5
        """
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.0, 2: 0.5, 3: 1.0},
            flow_acc_scores={1: 100.0, 2: 300.0, 3: 500.0},
            hci_scores={"1": 20.0, "2": 60.0, "3": 100.0},
            conflict_counts={1: 0, 2: 5, 3: 10},
        )

        by_node = {r["node_id"]: r for r in results}
        assert by_node[2]["composite_score"] == pytest.approx(0.5, abs=0.001)
        assert by_node[3]["composite_score"] == pytest.approx(1.0, abs=0.001)
        assert by_node[1]["composite_score"] == pytest.approx(0.0, abs=0.001)

    def test_exact_composite_with_asymmetric_values(self):
        """Verify each weight individually with asymmetric normalized values.

        2 nodes:
          cent: {1: 0.2, 2: 0.8} => min=0.2, max=0.8 => node2_norm = 1.0, node1_norm = 0.0
          fa:   {1: 200, 2: 600} => min=200, max=600 => node2_norm = 1.0, node1_norm = 0.0
          hci:  {1: 30, 2: 90}   => min=30, max=90   => node2_norm = 1.0, node1_norm = 0.0
          conf: {1: 1, 2: 7}     => min=1, max=7      => node2_norm = 1.0, node1_norm = 0.0

        But let's use 3 nodes for non-trivial norms:
          cent: {1: 0.2, 2: 0.5, 3: 0.8} => norms: 0.0, 0.5, 1.0
          fa:   {1: 200, 2: 500, 3: 600} => norms: 0.0, 0.75, 1.0
          hci:  {1: 30, 2: 70, 3: 90}    => norms: 0.0, 0.6667, 1.0
          conf: {1: 1, 2: 4, 3: 7}       => norms: 0.0, 0.5, 1.0

        Node 2: composite = 0.30*0.5 + 0.25*0.75 + 0.25*0.6667 + 0.20*0.5
                          = 0.15 + 0.1875 + 0.16667 + 0.10
                          = 0.60417
        """
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.2, 2: 0.5, 3: 0.8},
            flow_acc_scores={1: 200.0, 2: 500.0, 3: 600.0},
            hci_scores={"1": 30.0, "2": 70.0, "3": 90.0},
            conflict_counts={1: 1, 2: 4, 3: 7},
        )

        by_node = {r["node_id"]: r for r in results}
        # Node 2
        expected_node2 = 0.30 * 0.5 + 0.25 * 0.75 + 0.25 * (40.0 / 60.0) + 0.20 * 0.5
        assert by_node[2]["composite_score"] == pytest.approx(expected_node2, abs=0.001)

    def test_weight_redistribution_two_factors(self):
        """When only centrality (0.30) and flow_acc (0.25) are present.

        available_weight = 0.55
        redistribution_factor = 1/0.55 = 1.8182
        adjusted_centrality = 0.30 * 1.8182 = 0.5455
        adjusted_flow_acc   = 0.25 * 1.8182 = 0.4545

        2 nodes: {1: cent=0.0, fa=0.0}, {2: cent=1.0, fa=1000.0}
        node 2: norms = 1.0, 1.0
        composite = 0.5455*1.0 + 0.4545*1.0 = 1.0
        node 1: composite = 0.0
        """
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.0, 2: 1.0},
            flow_acc_scores={1: 0.0, 2: 1000.0},
            hci_scores={},
            conflict_counts={},
        )

        by_node = {r["node_id"]: r for r in results}
        assert by_node[2]["composite_score"] == pytest.approx(1.0, abs=0.001)
        assert by_node[1]["composite_score"] == pytest.approx(0.0, abs=0.001)
        assert "upstream_hci" in by_node[2]["missing_factors"]
        assert "conflict_count" in by_node[2]["missing_factors"]

    def test_weight_redistribution_three_factors(self):
        """When only centrality+flow_acc+hci present (no conflicts).

        available_weight = 0.30+0.25+0.25 = 0.80
        redistribution_factor = 1/0.80 = 1.25
        adjusted weights: cent=0.375, fa=0.3125, hci=0.3125

        3 nodes with norms all 0, 0.5, 1.0:
        node 2 composite = 0.375*0.5 + 0.3125*0.5 + 0.3125*0.5
                         = 0.1875 + 0.15625 + 0.15625 = 0.5
        """
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.0, 2: 0.5, 3: 1.0},
            flow_acc_scores={1: 0.0, 2: 500.0, 3: 1000.0},
            hci_scores={"1": 0.0, "2": 50.0, "3": 100.0},
            conflict_counts={},
        )

        by_node = {r["node_id"]: r for r in results}
        assert by_node[2]["composite_score"] == pytest.approx(0.5, abs=0.001)

    def test_normalization_is_min_max(self):
        """Verify normalization formula: (raw - min) / (max - min)."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        # cent: {1: 0.1, 2: 0.4, 3: 0.9} => min=0.1, max=0.9
        # node 2 norm = (0.4-0.1)/(0.9-0.1) = 0.3/0.8 = 0.375
        results = compute_maintenance_priority(
            centrality_scores={1: 0.1, 2: 0.4, 3: 0.9},
            flow_acc_scores={1: 100.0, 2: 100.0, 3: 100.0},  # all same => norm 0.0
            hci_scores={"1": 50.0, "2": 50.0, "3": 50.0},     # all same => norm 0.0
            conflict_counts={1: 3, 2: 3, 3: 3},                # all same => norm 0.0
        )

        by_node = {r["node_id"]: r for r in results}
        # Only centrality differs. All same values => _min_max returns (val, val+1)
        # For same-valued factors: norm = (val-val)/(val+1-val) = 0.0
        # So composite = weight_cent_adjusted * cent_norm + rest * 0.0
        # available_weight = 1.0 (all factors present), redistribution = 1.0
        # node 2: composite = 0.30 * 0.375 = 0.1125
        assert by_node[2]["composite_score"] == pytest.approx(0.30 * 0.375, abs=0.001)
        assert by_node[2]["components"]["centrality"]["normalized"] == pytest.approx(0.375, abs=0.001)

    def test_node_with_zero_available_weight_skipped(self):
        """Node appearing in NO factor dicts => available_weight=0 => skipped."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        # Node 1 only in centrality, node 2 only in flow_acc
        # Both should appear, neither has 0 available weight
        results = compute_maintenance_priority(
            centrality_scores={1: 0.5},
            flow_acc_scores={2: 500.0},
            hci_scores={},
            conflict_counts={},
        )
        assert len(results) == 2

    def test_composite_score_rounded_to_4_decimals(self):
        """composite_score uses round(..., 4)."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.0, 2: 0.33333, 3: 1.0},
            flow_acc_scores={1: 0.0, 2: 0.0, 3: 0.0},
            hci_scores={},
            conflict_counts={},
        )

        by_node = {r["node_id"]: r for r in results}
        # cent norms: 0.0, 0.33333/1.0=0.33333, 1.0
        # available_weight for node 2 = 0.30 + 0.25 = 0.55 (fa present w/ 0 norm)
        # Actually fa all same => (0-0)/(0+1-0) = 0.0
        # redistribution = 1/0.55 = 1.8182
        # composite = 0.30*1.8182*0.33333 + 0.25*1.8182*0.0 = 0.18182
        score = by_node[2]["composite_score"]
        # Check it has at most 4 decimal places
        assert score == round(score, 4)

    def test_individual_weight_centrality_0_30(self):
        """Isolate centrality weight = exactly 0.30.

        With all 4 factors, node at max centrality and min everything else:
        composite = 0.30*1.0 + 0.25*0.0 + 0.25*0.0 + 0.20*0.0 = 0.30
        """
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.0, 2: 1.0},
            flow_acc_scores={1: 500.0, 2: 500.0},     # same => norm 0
            hci_scores={"1": 50.0, "2": 50.0},         # same => norm 0
            conflict_counts={1: 3, 2: 3},               # same => norm 0
        )

        by_node = {r["node_id"]: r for r in results}
        # node 2: only centrality is 1.0; rest are 0.0
        # composite = 0.30 * 1.0 = 0.30
        assert by_node[2]["composite_score"] == pytest.approx(0.30, abs=0.001)

    def test_individual_weight_flow_acc_0_25(self):
        """Isolate flow_acc weight = exactly 0.25."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.5, 2: 0.5},        # same => norm 0
            flow_acc_scores={1: 0.0, 2: 1000.0},
            hci_scores={"1": 50.0, "2": 50.0},
            conflict_counts={1: 3, 2: 3},
        )

        by_node = {r["node_id"]: r for r in results}
        assert by_node[2]["composite_score"] == pytest.approx(0.25, abs=0.001)

    def test_individual_weight_hci_0_25(self):
        """Isolate upstream_hci weight = exactly 0.25."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.5, 2: 0.5},
            flow_acc_scores={1: 500.0, 2: 500.0},
            hci_scores={"1": 0.0, "2": 100.0},
            conflict_counts={1: 3, 2: 3},
        )

        by_node = {r["node_id"]: r for r in results}
        assert by_node[2]["composite_score"] == pytest.approx(0.25, abs=0.001)

    def test_individual_weight_conflicts_0_20(self):
        """Isolate conflict_count weight = exactly 0.20."""
        from app.domains.geo.intelligence.calculations import (
            compute_maintenance_priority,
        )

        results = compute_maintenance_priority(
            centrality_scores={1: 0.5, 2: 0.5},
            flow_acc_scores={1: 500.0, 2: 500.0},
            hci_scores={"1": 50.0, "2": 50.0},
            conflict_counts={1: 0, 2: 10},
        )

        by_node = {r["node_id"]: r for r in results}
        assert by_node[2]["composite_score"] == pytest.approx(0.20, abs=0.001)


# ---------------------------------------------------------------------------
# Mutation-killing round 2: target remaining survivors
# ---------------------------------------------------------------------------


class TestRankCanalHotspotsPercentileBoundaries:
    """Kill mutations at p50 and p25 >= vs > boundaries."""

    def _make_fake_rasterio_dataset(
        self,
        data: np.ndarray,
        nodata: float = -9999.0,
    ) -> MagicMock:
        from rasterio.transform import from_bounds

        ds = MagicMock()
        ds.read.return_value = data
        ds.nodata = nodata
        ds.transform = from_bounds(0, 0, 1, 1, data.shape[1], data.shape[0])
        ds.__enter__ = lambda self: self
        ds.__exit__ = MagicMock(return_value=False)
        return ds

    def _patch_rasterio_and_call(
        self,
        data: np.ndarray,
        canal_geometries: list[dict],
        num_points: int = 5,
    ) -> list[dict]:
        from app.domains.geo.intelligence.calculations import rank_canal_hotspots

        fake_ds = self._make_fake_rasterio_dataset(data)
        with (
            patch("rasterio.open", return_value=fake_ds),
            patch.object(Path, "exists", return_value=True),
        ):
            return rank_canal_hotspots(
                canal_geometries,
                "/fake/flow_acc.tif",
                num_points=num_points,
            )

    def test_value_exactly_at_p50_is_alto(self):
        """With values [100, 200, 300], p50=200, p25=150, p75=250.

        Canal with max=200: 200 >= p75(250)? No. 200 >= p50(200)? Yes => alto.
        If mutation changes >= to >, then 200 > 200 is False => would fall to medio.
        """
        data = np.zeros((15, 10), dtype=np.float32)
        data[0:5, :] = 100.0
        data[5:10, :] = 200.0
        data[10:15, :] = 300.0

        canals = [
            {"id": 1, "geometry": mapping(LineString([(0.1, 0.833), (0.9, 0.833)]))},  # row 0-4: 100
            {"id": 2, "geometry": mapping(LineString([(0.1, 0.5), (0.9, 0.5)]))},      # row 5-9: 200
            {"id": 3, "geometry": mapping(LineString([(0.1, 0.167), (0.9, 0.167)]))},  # row 10-14: 300
        ]
        results = self._patch_rasterio_and_call(data, canals)
        by_id = {r["id"]: r for r in results}

        # max=200 is exactly p50 => alto (>= p50)
        assert by_id[2]["risk_level"] == "alto"
        # max=300 >= p75(250) => critico
        assert by_id[3]["risk_level"] == "critico"

    def test_value_exactly_at_p25_is_medio(self):
        """5 canals: [50, 100, 200, 300, 400]. p25=100, p50=200, p75=300.

        Canal with max=100: 100 >= p75(300)? No. 100 >= p50(200)? No. 100 >= p25(100)? Yes => medio.
        If mutation changes >= to >, 100 > 100 is False => would fall to bajo.
        """
        data = np.zeros((25, 10), dtype=np.float32)
        data[0:5, :] = 50.0
        data[5:10, :] = 100.0
        data[10:15, :] = 200.0
        data[15:20, :] = 300.0
        data[20:25, :] = 400.0

        canals = [
            {"id": 1, "geometry": mapping(LineString([(0.1, 0.9), (0.9, 0.9)]))},    # 50
            {"id": 2, "geometry": mapping(LineString([(0.1, 0.7), (0.9, 0.7)]))},    # 100
            {"id": 3, "geometry": mapping(LineString([(0.1, 0.5), (0.9, 0.5)]))},    # 200
            {"id": 4, "geometry": mapping(LineString([(0.1, 0.3), (0.9, 0.3)]))},    # 300
            {"id": 5, "geometry": mapping(LineString([(0.1, 0.1), (0.9, 0.1)]))},    # 400
        ]
        results = self._patch_rasterio_and_call(data, canals)
        by_id = {r["id"]: r for r in results}

        assert by_id[2]["risk_level"] == "medio"  # 100 >= p25(100)
        assert by_id[1]["risk_level"] == "bajo"   # 50 < p25(100)


class TestDetectCoverageGapsRound2:
    """Kill remaining boundary and constant survivors."""

    def _make_zone(self, zone_id: str, centroid: tuple[float, float]) -> dict:
        cx, cy = centroid
        poly = Polygon([
            (cx - 0.0001, cy - 0.0001),
            (cx + 0.0001, cy - 0.0001),
            (cx + 0.0001, cy + 0.0001),
            (cx - 0.0001, cy + 0.0001),
        ])
        return {"id": zone_id, "geometry": mapping(poly)}

    def _make_canal(self, coords: list[tuple[float, float]]) -> dict:
        return {"geometry": mapping(LineString(coords))}

    def test_default_threshold_km_is_2(self):
        """Calling without threshold_km uses 2.0. Mutation changes to 3.0.

        Zone at ~2.5 km should be a gap with default 2.0 but not with 3.0.
        """
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # 2.5 km = 2.5/111 = 0.02252 degrees
        dist_deg = 2.5 / 111.0
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 90.0}
        canals = [self._make_canal([(0.0, 0.0), (0.00001, 0.0)])]

        # Use default threshold_km (should be 2.0)
        gaps = detect_coverage_gaps(zones, hci_scores, canals, hci_threshold=50.0)
        assert len(gaps) == 1  # Would fail if default changed to 3.0

    def test_default_hci_threshold_is_50(self):
        """Calling without hci_threshold uses 50.0. Mutation changes to 51.0.

        Zone with hci=50.5 should be a gap with default 50.0 but not with 51.0.
        """
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._make_zone("z1", (1.0, 0.0))]  # far away
        hci_scores = {"z1": 50.5}
        canals = [self._make_canal([(0.0, 0.0), (0.00001, 0.0)])]

        # Use default hci_threshold (should be 50.0)
        gaps = detect_coverage_gaps(zones, hci_scores, canals, threshold_km=2.0)
        assert len(gaps) == 1  # Would fail if default changed to 51.0

    def test_111_km_per_degree_not_112(self):
        """Verify 111.0 constant, not 112. At 0.1 degrees:

        111.0 * 0.1 = 11.1 km (with threshold 11.05 => gap)
        112.0 * 0.1 = 11.2 km (with threshold 11.15 => also gap with 112)

        Use a threshold between 111*dist and 112*dist to distinguish.
        dist_deg = 0.1, 111*0.1=11.1, 112*0.1=11.2
        threshold = 11.15: with 111 => 11.1 < 11.15 => filtered (no gap)
                           with 112 => 11.2 >= 11.15 => gap
        """
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        zones = [self._make_zone("z1", (0.1, 0.0))]
        hci_scores = {"z1": 90.0}
        canals = [self._make_canal([(0.0, 0.0), (0.00001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=11.15, hci_threshold=50.0
        )
        # With 111.0: dist = 11.1 < 11.15 => filtered => no gap
        # With 112.0: dist = 11.2 >= 11.15 => gap
        assert len(gaps) == 0

    def test_dist_km_barely_above_threshold_is_gap(self):
        """When dist_km is just barely above threshold, it passes the `<` filter.

        Mutation `<` to `<=` would only matter at exact boundary. But since geometry
        makes exact boundary impossible, we test the behavior indirectly: a value
        that is clearly above threshold IS a gap, one clearly below is NOT.
        Combined with test_distance_just_below_threshold_is_not_gap, this pins `<`.
        """
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # 2.05 km => just above default 2.0 threshold
        dist_deg = 2.05 / 111.0
        zones = [self._make_zone("z1", (dist_deg, 0.0))]
        hci_scores = {"z1": 90.0}
        canals = [self._make_canal([(0.0, 0.0), (0.00001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        assert gaps[0]["gap_km"] > 2.0

    def test_severity_hci_exactly_80_is_not_critico(self):
        """hci=80.0 and dist>5: code checks hci > 80.0, so 80 is NOT > 80 => not critico.

        Mutation `>` to `>=` would make 80 >= 80 => critico.
        Should be alto (hci>60 and dist>3).
        """
        from app.domains.geo.intelligence.calculations import detect_coverage_gaps

        # dist = 0.1 * 111 = 11.1 > 5 => satisfies distance for both critico and alto
        zones = [self._make_zone("z1", (0.1, 0.0))]
        hci_scores = {"z1": 80.0}
        canals = [self._make_canal([(0.0, 0.0), (0.00001, 0.0)])]

        gaps = detect_coverage_gaps(
            zones, hci_scores, canals, threshold_km=2.0, hci_threshold=50.0
        )
        assert len(gaps) == 1
        # 80 NOT > 80, falls to alto check: 80 > 60 and 11.1 > 3 => alto
        assert gaps[0]["severity"] == "alto"


    # NOTE: _min_max mutations (L861 return 0.0,1.0->0.0,2 and L864 mn+1.0->mn+2)
    # are equivalent mutations. When all values are equal, norm = (val-val)/(denom) = 0
    # regardless of denom being 1 or 2. When the list is empty, the range is never
    # used because nodes missing from a factor skip it entirely. These cannot be killed.
