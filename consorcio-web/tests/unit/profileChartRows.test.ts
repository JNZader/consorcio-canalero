import { describe, expect, it } from 'vitest';

import { buildProfileChartRows } from '../../src/components/map2d/profileChartRows';

describe('buildProfileChartRows', () => {
  it('inserts a null break row where the trace jumps to another part', () => {
    const rows = buildProfileChartRows([
      { distance_m: 0, elevation_m: 10, lon: -62.7, lat: -32.6 },
      { distance_m: 100, elevation_m: 11, lon: -62.701, lat: -32.6, parte: 0 },
      { distance_m: 100, elevation_m: 30, lon: -62.8, lat: -32.7, parte: 1 },
    ]);

    expect(rows).toHaveLength(4);
    expect(rows[2]?.elevation_m).toBeNull();
    expect(rows[2]?.distance_m).toBe(100);
    expect(rows[2]?.lon).toBe(-62.701);
    expect(rows[3]?.elevation_m).toBe(30);
  });

  it('leaves a single-part payload untouched', () => {
    const rows = buildProfileChartRows([
      { distance_m: 0, elevation_m: 10 },
      { distance_m: 10, elevation_m: 11 },
    ]);

    expect(rows).toHaveLength(2);
    expect(rows.every((row) => row.elevation_m != null)).toBe(true);
  });

  it('does not break inside one part', () => {
    const rows = buildProfileChartRows([
      { distance_m: 0, elevation_m: 10, parte: 0 },
      { distance_m: 10, elevation_m: 11, parte: 0 },
      { distance_m: 20, elevation_m: 12, parte: 0 },
    ]);

    expect(rows).toHaveLength(3);
  });
});
