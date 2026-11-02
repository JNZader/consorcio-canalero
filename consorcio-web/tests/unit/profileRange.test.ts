import { describe, expect, it } from 'vitest';

import {
  localSlopePct,
  medianElevation,
  profileGrade,
  profileSliceStats,
  sliceProfile,
} from '../../src/components/map2d/profileRange';

const samples = [
  { distance_m: 0, elevation_m: 120, lon: -62.7, lat: -32.6 },
  { distance_m: 10, elevation_m: 118, lon: -62.71, lat: -32.6 },
  { distance_m: 20, elevation_m: 119, lon: -62.72, lat: -32.6 },
  { distance_m: 30, elevation_m: 121, lon: -62.73, lat: -32.6 },
];

describe('sliceProfile', () => {
  it('keeps samples inside the dragged window, order independent', () => {
    expect(sliceProfile(samples, 20, 10).map((s) => s.distance_m)).toEqual([10, 20]);
  });
});

describe('profileSliceStats', () => {
  it('returns length, extrema and end-minus-start', () => {
    const stats = profileSliceStats(sliceProfile(samples, 10, 30));
    expect(stats?.length_m).toBe(20);
    expect(stats?.min_elevation_m).toBe(118);
    expect(stats?.max_elevation_m).toBe(121);
    expect(stats?.delta_m).toBe(3);
    expect(stats?.coordinates).toHaveLength(3);
    expect(stats?.min_point).toEqual({
      lon: -62.71,
      lat: -32.6,
      elevation_m: 118,
      distance_m: 10,
    });
    expect(stats?.max_point).toEqual({
      lon: -62.73,
      lat: -32.6,
      elevation_m: 121,
      distance_m: 30,
    });
  });

  it('returns null for a single sample', () => {
    expect(profileSliceStats(samples.slice(0, 1))).toBeNull();
  });

  it('reports mean, median, relief and net slope', () => {
    const stats = profileSliceStats(sliceProfile(samples, 0, 30));
    expect(stats?.mean_elevation_m).toBe(119.5);
    expect(stats?.median_elevation_m).toBe(119.5);
    expect(stats?.ascent_m).toBe(3);
    expect(stats?.descent_m).toBe(2);
    expect(stats?.mean_slope_pct).toBeCloseTo((1 / 30) * 100);
    expect(stats?.max_down_slope_pct).toBeLessThan(0);
    expect(stats?.max_up_slope_pct).toBeGreaterThan(0);
  });
});

describe('profileGrade', () => {
  it('does not invent a slope across a null gap', () => {
    const grade = profileGrade([
      { distance_m: 0, elevation_m: 100 },
      { distance_m: 10, elevation_m: null },
      { distance_m: 20, elevation_m: 90 },
    ]);
    expect(grade.ascent_m).toBe(0);
    expect(grade.descent_m).toBe(0);
    expect(grade.mean_slope_pct).toBeCloseTo(-50);
    expect(grade.median_elevation_m).toBe(95);
  });
});

describe('medianElevation', () => {
  it('averages the two central values when the count is even', () => {
    expect(medianElevation([4, 1, 3, 2])).toBe(2.5);
  });

  it('picks the central value when the count is odd', () => {
    expect(medianElevation([9, 1, 4])).toBe(4);
  });
});

describe('localSlopePct', () => {
  it('uses the neighbours around the sample', () => {
    expect(localSlopePct(samples, 1)).toBeCloseTo(((119 - 120) / 20) * 100);
  });

  it('is null on a sample without elevation', () => {
    expect(localSlopePct([{ distance_m: 0, elevation_m: null }], 0)).toBeNull();
  });
});
