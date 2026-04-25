/**
 * Unit tests for computeLineLabelAnchor helper.
 *
 * Covers:
 * - Empty coordinate list → fallback [0, 0]
 * - Single coordinate → returns that point
 * - Two coordinates → midpoint behaviour (backwards compatible)
 * - Three+ coordinates with zig-zag → midpoint by accumulated distance,
 *   which must fall ON the actual polyline, not on the geographic midpoint
 *   between first and last vertex.
 */

import { describe, expect, it } from 'vitest';

import { computeLineLabelAnchor } from '@/components/map2d/measurement/useMeasurement';
import type { Feature, LineString } from 'geojson';

function makeLineString(coords: [number, number][]): Feature<LineString> {
  return {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: coords },
    properties: {},
  };
}

describe('computeLineLabelAnchor', () => {
  it('returns [0, 0] for empty coordinate list', () => {
    const line = makeLineString([]);
    expect(computeLineLabelAnchor(line)).toEqual([0, 0]);
  });

  it('returns the single coordinate for a one-point line', () => {
    const line = makeLineString([[-62.68, -32.63]]);
    expect(computeLineLabelAnchor(line)).toEqual([-62.68, -32.63]);
  });

  it('returns geographic midpoint for two coordinates', () => {
    // Simple east-west line at constant latitude for predictable midpoint
    const line = makeLineString([
      [-62.7, -32.6],
      [-62.5, -32.6],
    ]);
    const [lng, lat] = computeLineLabelAnchor(line);
    expect(lng).toBeCloseTo(-62.6, 4);
    expect(lat).toBeCloseTo(-32.6, 4);
  });

  it('returns geographic midpoint for two coordinates (north-south)', () => {
    const line = makeLineString([
      [-62.6, -32.8],
      [-62.6, -32.4],
    ]);
    const [lng, lat] = computeLineLabelAnchor(line);
    expect(lng).toBeCloseTo(-62.6, 4);
    expect(lat).toBeCloseTo(-32.6, 4);
  });

  it('places midpoint on the polyline for zig-zag with 3+ vertices', () => {
    // A "V" shape: start at A, go deep to B, come back near start at C.
    // Geographic midpoint(A, C) is close to A/C, but the true distance
    // midpoint should be at B (the tip of the V), because B is roughly
    // at 50 % of total travelled distance.
    const a: [number, number] = [-62.7, -32.6];
    const b: [number, number] = [-62.65, -32.55]; // tip
    const c: [number, number] = [-62.7, -32.5]; // back near A vertically

    const line = makeLineString([a, b, c]);
    const [lng, lat] = computeLineLabelAnchor(line);

    // The old midpoint(a, c) would be ~[-62.7, -32.55].
    // The true distance midpoint should be much closer to b.
    const distToB = Math.hypot(lng - b[0], lat - b[1]);
    const distToOldMid = Math.hypot(lng - a[0], lat - (-32.55));

    // Anchor must be closer to B than to the naive midpoint between A and C
    expect(distToB).toBeLessThan(distToOldMid);
  });

  it('interpolates along the correct segment for a 4-vertex polyline', () => {
    // Segment 1: 100 m (approx at this latitude for small offsets)
    // Segment 2: 100 m
    // Segment 3: 100 m
    // Total ~300 m, midpoint at ~150 m → should land in segment 2.
    // Using small offsets to keep linear approximation valid.
    const dLngPer100m = 0.00102; // rough at mid-latitudes
    const dLatPer100m = 0.0009;

    const p0: [number, number] = [-62.7, -32.6];
    const p1: [number, number] = [p0[0] + dLngPer100m, p0[1]];
    const p2: [number, number] = [p1[0] + dLngPer100m, p1[1]];
    const p3: [number, number] = [p2[0] + dLngPer100m, p2[1]];

    const line = makeLineString([p0, p1, p2, p3]);
    const [lng] = computeLineLabelAnchor(line);

    // Should be somewhere inside segment 2 (between p1 and p2)
    expect(lng).toBeGreaterThan(p1[0]);
    expect(lng).toBeLessThan(p2[0]);
  });

  it('handles zero-length segments gracefully', () => {
    const line = makeLineString([
      [-62.7, -32.6],
      [-62.7, -32.6], // duplicate vertex
      [-62.5, -32.6],
    ]);
    const [lng, lat] = computeLineLabelAnchor(line);
    // Should still return a valid point on the line (last point as fallback
    // or somewhere in the non-zero segment)
    expect(typeof lng).toBe('number');
    expect(typeof lat).toBe('number');
    expect(Number.isFinite(lng)).toBe(true);
    expect(Number.isFinite(lat)).toBe(true);
  });
});
