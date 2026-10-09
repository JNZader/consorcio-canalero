import type { Position } from 'geojson';
import { describe, expect, it } from 'vitest';

import { pointAlongLineString } from '../../src/components/map2d/pointAlongLine';

describe('pointAlongLineString', () => {
  const east: Position[] = [
    [0, 0],
    [1, 0],
  ];

  it('returns the start at distance 0', () => {
    expect(pointAlongLineString(east, 0)).toEqual([0, 0]);
  });

  it('interpolates along the first segment', () => {
    const mid = pointAlongLineString(east, 55_000);
    expect(mid).not.toBeNull();
    expect(mid![0]).toBeGreaterThan(0.4);
    expect(mid![0]).toBeLessThan(0.6);
    expect(mid![1]).toBeCloseTo(0, 5);
  });

  it('clamps past the end', () => {
    expect(pointAlongLineString(east, 1_000_000)).toEqual([1, 0]);
  });

  it('returns null for an empty line', () => {
    expect(pointAlongLineString([], 10)).toBeNull();
  });
});
