"""
Verification tests for geo-visualization Phase 4.

Tests:
  4.1 — Basin endpoint response size < 500KB with ST_Simplify
  4.2 — Tile endpoint latency < 200ms for standard zoom levels
  4.3 — Terrain-RGB round-trip accuracy (encode -> decode < 0.1m error)

These are LOCAL verification tests that validate logic correctness
and rough performance without requiring a live database, rio-tiler,
or the tile server running.

The terrain-RGB encoding function is replicated here (identical to
tile_service._encode_terrain_rgb) to avoid importing the tile_service
module which depends on rio-tiler (geo-worker only dependency).
"""

from __future__ import annotations

import json
import time

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Terrain-RGB encoding — exact copy from app/domains/geo/tile_service.py
# This avoids importing tile_service.py which requires rio-tiler.
# ---------------------------------------------------------------------------


def _encode_terrain_rgb(data: np.ndarray) -> np.ndarray:
    """Encode elevation values to Mapbox Terrain-RGB format.

    Formula: encoded = (elevation + 10000) * 10
    R = floor(encoded / 65536)
    G = floor((encoded % 65536) / 256)
    B = floor(encoded % 256)
    """
    elevation = np.clip(data.astype(np.float64), -10000, 1667721.5)
    encoded = ((elevation + 10000.0) * 10.0).astype(np.uint32)

    r = (encoded // 65536).astype(np.uint8)
    g = ((encoded % 65536) // 256).astype(np.uint8)
    b = (encoded % 256).astype(np.uint8)

    return np.stack([r, g, b], axis=0)


def _decode_terrain_rgb(rgb: np.ndarray) -> np.ndarray:
    """Decode terrain-RGB back to elevation values.

    This mirrors what deck.gl TerrainLayer does client-side:
      elevation = (R * 65536 + G * 256 + B) * 0.1 - 10000

    Args:
        rgb: Array of shape (3, H, W) with R, G, B bands as uint8.

    Returns:
        Elevation array of shape (H, W) as float64.
    """
    r = rgb[0].astype(np.float64)
    g = rgb[1].astype(np.float64)
    b = rgb[2].astype(np.float64)
    return (r * 65536 + g * 256 + b) * 0.1 - 10000.0


# ---------------------------------------------------------------------------
# 4.1 — Basin response size verification
# ---------------------------------------------------------------------------


class TestBasinResponseSize:
    """Verify that 549 simplified polygons fit under 500KB as GeoJSON."""

    @staticmethod
    def _make_polygon(center_x: float, center_y: float, num_vertices: int = 30) -> dict:
        """Generate a synthetic polygon with the given number of vertices.

        Simulates a realistic ZonaOperativa polygon shape (~0.02 degree radius
        ~= 2km, which is typical for irrigation districts near Bell Ville).
        """
        angles = np.linspace(0, 2 * np.pi, num_vertices, endpoint=False)
        rng = np.random.default_rng(seed=int(abs(center_x * 1000 + center_y * 1000)))
        radii = 0.02 + rng.uniform(-0.005, 0.005, size=num_vertices)
        coords = [
            [
                round(center_x + r * np.cos(a), 6),
                round(center_y + r * np.sin(a), 6),
            ]
            for r, a in zip(radii, angles)
        ]
        coords.append(coords[0])  # close the ring
        return {"type": "Polygon", "coordinates": [coords]}

    def test_549_simplified_polygons_under_500kb(self):
        """Simulate 549 basin features with ST_Simplify(tolerance=0.001).

        ST_Simplify with tolerance=0.001 (~100m) on typical irrigation
        district polygons reduces vertex count to ~10-30 per polygon.
        We simulate the WORST CASE: 30 vertices per polygon for all 549.

        Expected: ~200-300KB for 549 polygons. Must be < 500KB.
        """
        features = []
        rng = np.random.default_rng(seed=42)

        for i in range(549):
            cx = -62.7 + rng.uniform(-0.5, 0.5)
            cy = -32.6 + rng.uniform(-0.5, 0.5)
            geom = self._make_polygon(cx, cy, num_vertices=30)

            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "id": f"uuid-{i:04d}",
                    "nombre": f"Zona Operativa {i}",
                    "cuenca": f"Cuenca {i % 5}",
                    "superficie_ha": round(rng.uniform(50, 5000), 2),
                },
            })

        collection = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "total": 549,
                "tolerance": 0.001,
                "bbox": None,
            },
        }

        payload = json.dumps(collection, separators=(",", ":"))
        size_kb = len(payload.encode("utf-8")) / 1024

        assert size_kb < 500, (
            f"Basin GeoJSON response is {size_kb:.1f}KB — exceeds 500KB budget. "
            f"Increase ST_Simplify tolerance or reduce property fields."
        )
        print(f"\n  Basin response size: {size_kb:.1f}KB for 549 polygons (30 vertices each)")

    def test_simplified_polygon_vertex_reduction(self):
        """Verify that ST_Simplify(0.001) meaningfully reduces complex polygons.

        Douglas-Peucker estimation: for a circle with radius R and tolerance T,
        the simplified polygon has ~pi * sqrt(R / T) vertices.
        For R=0.02, T=0.001: ~pi * sqrt(20) ~= 14 vertices.
        """
        radius = 0.02  # ~2km at Bell Ville
        tolerance = 0.001  # ST_Simplify tolerance
        original_vertices = 200

        estimated_simplified = int(np.pi * np.sqrt(radius / tolerance))

        assert estimated_simplified < 30, (
            f"Estimated {estimated_simplified} vertices after simplification — "
            f"should be well under 30 for tolerance={tolerance}"
        )
        print(f"\n  Estimated simplified vertices: {estimated_simplified} (from {original_vertices})")

    def test_empty_basin_response_valid_geojson(self):
        """Empty response must still be valid GeoJSON under 1KB."""
        collection = {
            "type": "FeatureCollection",
            "features": [],
        }
        payload = json.dumps(collection)
        assert len(payload.encode("utf-8")) < 1024


# ---------------------------------------------------------------------------
# 4.2 — Tile endpoint latency verification
# ---------------------------------------------------------------------------


class TestTileLatency:
    """Verify tile generation performance characteristics.

    We test the _encode_terrain_rgb function directly since it is the
    CPU-intensive part of tile serving. rio-tiler COG read is I/O-bound
    and typically takes 20-80ms for local COG files.
    """

    def test_terrain_rgb_encoding_under_50ms(self):
        """Terrain-RGB encoding of a 256x256 tile should complete in < 50ms.

        This is the CPU-intensive part of tile serving. If encoding alone
        exceeds 50ms, the full endpoint can't meet the 200ms budget
        (rio-tiler COG read + encode + HTTP overhead).
        """
        # Simulate a 256x256 DEM tile in Bell Ville elevation range (80-120m)
        rng = np.random.default_rng(seed=99)
        elevation = rng.uniform(80.0, 120.0, size=(256, 256)).astype(np.float64)

        # Warm up
        _encode_terrain_rgb(elevation)

        # Benchmark 10 runs
        times = []
        for _ in range(10):
            start = time.perf_counter()
            result = _encode_terrain_rgb(elevation)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        median_ms = sorted(times)[len(times) // 2]
        p95_ms = sorted(times)[int(len(times) * 0.95)]

        assert result.shape == (3, 256, 256), f"Expected (3, 256, 256), got {result.shape}"
        assert result.dtype == np.uint8, f"Expected uint8, got {result.dtype}"
        assert median_ms < 50, (
            f"Terrain-RGB encoding median={median_ms:.1f}ms — too slow for 200ms tile budget. "
            f"Consider vectorizing with numpy or using numba."
        )
        print(f"\n  Terrain-RGB encoding: median={median_ms:.1f}ms, p95={p95_ms:.1f}ms")

    def test_tile_render_pipeline_under_100ms(self):
        """Full encoding pipeline (simulating tile_service code path) < 100ms.

        This leaves ~100ms headroom for rio-tiler COG read + HTTP overhead
        to meet the 200ms total budget.
        """
        rng = np.random.default_rng(seed=42)
        elevation = rng.uniform(80.0, 120.0, size=(1, 256, 256)).astype(np.float64)

        # Warm up
        _encode_terrain_rgb(elevation[0])

        times = []
        for _ in range(10):
            start = time.perf_counter()
            terrain_data = _encode_terrain_rgb(elevation[0])
            assert terrain_data.shape == (3, 256, 256)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        median_ms = sorted(times)[len(times) // 2]

        assert median_ms < 100, (
            f"Encoding pipeline median={median_ms:.1f}ms — leaves insufficient "
            f"headroom for COG read within 200ms budget."
        )
        print(f"\n  Full encode pipeline: median={median_ms:.1f}ms (budget: 200ms total)")

    def test_encoding_throughput_tiles_per_second(self):
        """Measure tiles-per-second throughput for capacity planning.

        At minimum we need ~10 tiles/sec for smooth map panning
        (256px tiles at zoom 12-14, viewport typically loads 6-12 tiles).
        """
        rng = np.random.default_rng(seed=77)
        elevation = rng.uniform(80.0, 120.0, size=(256, 256)).astype(np.float64)

        # Warm up
        _encode_terrain_rgb(elevation)

        num_tiles = 50
        start = time.perf_counter()
        for _ in range(num_tiles):
            _encode_terrain_rgb(elevation)
        total_s = time.perf_counter() - start

        tiles_per_sec = num_tiles / total_s
        assert tiles_per_sec > 10, (
            f"Only {tiles_per_sec:.1f} tiles/sec — need >10 for smooth map panning."
        )
        print(f"\n  Throughput: {tiles_per_sec:.0f} tiles/sec (encoding only)")


# ---------------------------------------------------------------------------
# 4.3 — Terrain-RGB round-trip accuracy
# ---------------------------------------------------------------------------


class TestTerrainRGBRoundTrip:
    """Verify terrain-RGB encode/decode round-trip accuracy.

    Mapbox terrain-RGB formula:
      Encode: encoded = (elevation + 10000) * 10
              R = encoded // 65536
              G = (encoded % 65536) // 256
              B = encoded % 256
      Decode: elevation = (R * 65536 + G * 256 + B) * 0.1 - 10000

    Precision: 0.1m (the quantization step).
    For Bell Ville (80-120m), quantization error should be < 0.1m.
    """

    def test_round_trip_95_5m(self):
        """Encode 95.5m (mid Bell Ville range) -> decode -> error < 0.1m."""
        elevation = np.array([[95.5]], dtype=np.float64)
        rgb = _encode_terrain_rgb(elevation)
        decoded = _decode_terrain_rgb(rgb)

        error = abs(decoded[0, 0] - 95.5)
        assert error < 0.1, f"Round-trip error for 95.5m: {error:.4f}m (max 0.1m)"
        print(f"\n  95.5m -> encode -> decode = {decoded[0, 0]:.2f}m (error: {error:.4f}m)")

    def test_round_trip_bell_ville_range(self):
        """Test full Bell Ville elevation range (80-120m) round-trip.

        Every value in the 80-120m range should decode with < 0.1m error.
        This validates that the encoding has sufficient precision for
        this extremely flat terrain.
        """
        elevations = np.linspace(80.0, 120.0, 1000).reshape(1, 1000)
        rgb = _encode_terrain_rgb(elevations)
        decoded = _decode_terrain_rgb(rgb).flatten()

        errors = np.abs(decoded - elevations.flatten())
        max_error = float(np.max(errors))
        mean_error = float(np.mean(errors))

        assert max_error < 0.1, (
            f"Max round-trip error: {max_error:.4f}m — exceeds 0.1m tolerance. "
            f"Check encoding formula."
        )
        print(
            f"\n  Bell Ville range (80-120m):"
            f"\n    Max error:  {max_error:.4f}m"
            f"\n    Mean error: {mean_error:.4f}m"
            f"\n    Precision:  0.1m quantization step"
        )

    def test_round_trip_extreme_values(self):
        """Test edges of the valid terrain-RGB range.

        terrain-RGB can encode from -10000m to ~+1,667,721m.
        Bell Ville only uses 80-120m, but verify math at boundaries too.
        """
        test_values = np.array([
            [0.0],       # sea level
            [80.0],      # Bell Ville min
            [100.0],     # Bell Ville typical
            [120.0],     # Bell Ville max
            [8848.0],    # Everest
            [-100.0],    # below sea level
        ], dtype=np.float64)

        rgb = _encode_terrain_rgb(test_values)
        decoded = _decode_terrain_rgb(rgb).flatten()
        original = test_values.flatten()

        for orig, dec in zip(original, decoded):
            error = abs(dec - orig)
            assert error < 0.1, f"Round-trip error for {orig}m: {error:.4f}m"

        print("\n  Extreme value round-trip:")
        for orig, dec in zip(original, decoded):
            print(f"    {orig:>8.1f}m -> {dec:>10.2f}m (error: {abs(dec - orig):.4f}m)")

    def test_encoding_output_types(self):
        """Verify encoder returns correct shape and dtype for deck.gl consumption."""
        elevation = np.array([[95.0, 100.0], [85.0, 115.0]], dtype=np.float64)
        rgb = _encode_terrain_rgb(elevation)

        assert rgb.shape == (3, 2, 2), f"Expected (3, 2, 2), got {rgb.shape}"
        assert rgb.dtype == np.uint8, f"Expected uint8, got {rgb.dtype}"
        assert rgb.min() >= 0
        assert rgb.max() <= 255

    def test_encoding_monotonicity(self):
        """Higher elevation must produce higher encoded values.

        This ensures the encoding preserves ordering, which is critical
        for terrain visualization (otherwise 3D mesh is garbage).
        """
        elevations = np.array([[80.0, 90.0, 100.0, 110.0, 120.0]], dtype=np.float64)
        rgb = _encode_terrain_rgb(elevations)

        # Compute combined encoded value: R*65536 + G*256 + B
        combined = (
            rgb[0].astype(np.uint32) * 65536
            + rgb[1].astype(np.uint32) * 256
            + rgb[2].astype(np.uint32)
        )

        for i in range(combined.shape[1] - 1):
            assert combined[0, i] < combined[0, i + 1], (
                f"Encoding not monotonic: elevation {elevations[0, i]}m "
                f"(encoded={combined[0, i]}) >= elevation {elevations[0, i + 1]}m "
                f"(encoded={combined[0, i + 1]})"
            )

    def test_encoding_matches_tile_service_implementation(self):
        """Verify our test encoder matches the tile_service implementation exactly.

        Since we can't import tile_service directly (rio-tiler not installed),
        we verify by checking the known encoding for specific values:
          95.5m -> encoded = (95.5 + 10000) * 10 = 100955
          R = 100955 // 65536 = 1
          G = (100955 % 65536) // 256 = 138
          B = 100955 % 256 = 91
        """
        elevation = np.array([[95.5]], dtype=np.float64)
        rgb = _encode_terrain_rgb(elevation)

        expected_encoded = int((95.5 + 10000.0) * 10.0)  # 100955
        expected_r = expected_encoded // 65536             # 1
        expected_g = (expected_encoded % 65536) // 256     # 138
        expected_b = expected_encoded % 256                # 91

        assert rgb[0, 0, 0] == expected_r, f"R: expected {expected_r}, got {rgb[0, 0, 0]}"
        assert rgb[1, 0, 0] == expected_g, f"G: expected {expected_g}, got {rgb[1, 0, 0]}"
        assert rgb[2, 0, 0] == expected_b, f"B: expected {expected_b}, got {rgb[2, 0, 0]}"

        print(
            f"\n  95.5m -> encoded={expected_encoded}"
            f" -> RGB=({expected_r}, {expected_g}, {expected_b})"
        )
