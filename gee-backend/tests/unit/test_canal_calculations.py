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
