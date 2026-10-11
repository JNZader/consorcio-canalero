import { describe, expect, it } from 'vitest';

import { profileSliceStats, sliceProfile } from '../../src/components/map2d/profileRange';

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
});
