import type { Feature, LineString } from 'geojson';
import { describe, expect, it } from 'vitest';

import { groupSelectionSummary } from '../../src/components/map2d/InfoPanel';
import {
  dedupedLineStringLengthM,
  mergeLineStringTramos,
} from '../../src/components/map2d/mergeLineStringTramos';

function line(coordinates: LineString['coordinates']): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates },
    properties: {},
  };
}

describe('mergeLineStringTramos', () => {
  it('returns null when there is no LineString', () => {
    expect(
      mergeLineStringTramos([
        { type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: {} },
      ]),
    ).toBeNull();
  });

  it('returns the single line unchanged', () => {
    const feature = line([
      [0, 0],
      [1, 0],
    ]);
    expect(mergeLineStringTramos([feature])).toEqual(feature.geometry);
  });

  it('concatenates two tramos in selection order and drops a shared vertex', () => {
    const merged = mergeLineStringTramos([
      line([
        [0, 0],
        [1, 0],
      ]),
      line([
        [1, 0],
        [2, 0],
      ]),
    ]);
    expect(merged?.coordinates).toEqual([
      [0, 0],
      [1, 0],
      [2, 0],
    ]);
  });

  it('reverses the next tramo when it meets at the far end', () => {
    const merged = mergeLineStringTramos([
      line([
        [0, 0],
        [1, 0],
      ]),
      line([
        [2, 0],
        [1, 0],
      ]),
    ]);
    expect(merged?.coordinates).toEqual([
      [0, 0],
      [1, 0],
      [2, 0],
    ]);
  });

  it('does not jump a catalog-order gap (T269-03 25 km false positive)', () => {
    const merged = mergeLineStringTramos([
      line([
        [0, 0],
        [1, 0],
      ]),
      line([
        [10, 10],
        [11, 10],
      ]),
      line([
        [1, 0],
        [2, 0],
      ]),
    ]);
    expect(merged?.coordinates).toEqual([
      [0, 0],
      [1, 0],
      [2, 0],
    ]);
  });

  it('does not traverse a duplicated piece with the same endpoints twice', () => {
    const piece = line([
      [0, 0],
      [0.01, 0],
    ]);
    const merged = mergeLineStringTramos([piece, piece]);
    expect(merged?.coordinates).toEqual([
      [0, 0],
      [0.01, 0],
    ]);
  });

  it('follows the stem through a T, not both branches', () => {
    const stemA = line([
      [0, 0],
      [0.02, 0],
    ]);
    const stemB = line([
      [0.02, 0],
      [0.04, 0],
    ]);
    const branch = line([
      [0.02, 0],
      [0.02, 0.005],
    ]);
    const merged = mergeLineStringTramos([stemA, stemB, branch]);
    const lons = merged?.coordinates.map((c) => c[0]);
    expect(lons?.[0]).toBe(0);
    expect(lons?.[lons.length - 1]).toBe(0.04);
    expect(merged?.coordinates.every((c) => c[1] === 0)).toBe(true);
  });

  it('drops an out-and-back so the map cursor cannot reverse while chainage increases', () => {
    const merged = mergeLineStringTramos([
      line([
        [0, 0],
        [0.01, 0],
        [0.02, 0],
        [0.01, 0],
        [0, 0],
      ]),
    ]);
    const lons = merged?.coordinates.map((c) => c[0]);
    expect(lons).toEqual([0, 0.01, 0.02]);
  });

  it('keeps a right-angle bend (not a retrace)', () => {
    const merged = mergeLineStringTramos([
      line([
        [0, 0],
        [0.01, 0],
        [0.01, 0.01],
      ]),
    ]);
    expect(merged?.coordinates).toEqual([
      [0, 0],
      [0.01, 0],
      [0.01, 0.01],
    ]);
  });

  it('never walks the same stretch twice around a loop (A581/T028-19 inflation)', () => {
    // A four-tramo ring: the longest extension from one end and from the other
    // both reach for the same edge, so the axis used to walk it out and back.
    const ring = [
      line([
        [0, 0],
        [0.01, 0],
      ]),
      line([
        [0.01, 0],
        [0.01, 0.01],
      ]),
      line([
        [0.01, 0.01],
        [0, 0.01],
      ]),
      line([
        [0, 0.01],
        [0, 0],
      ]),
    ];
    const merged = mergeLineStringTramos(ring);
    const coords = merged?.coordinates ?? [];
    const distinct = new Set(coords.map((c) => `${c[0]},${c[1]}`));
    expect(coords.length).toBeGreaterThan(1);
    expect(distinct.size).toBe(coords.length);
  });

  it('follows the road body when the first selected tramo is a stray piece (T027-01)', () => {
    const stray = line([
      [-0.02, -0.02],
      [-0.0195, -0.0195],
    ]);
    const bodyA = line([
      [0, 0],
      [0.02, 0],
    ]);
    const bodyB = line([
      [0.02, 0],
      [0.04, 0],
    ]);
    const merged = mergeLineStringTramos([stray, bodyA, bodyB]);
    const lons = merged?.coordinates.map((c) => c[0]) ?? [];
    expect(lons[0]).toBe(0);
    expect(lons[lons.length - 1]).toBe(0.04);
  });
});

describe('dedupedLineStringLengthM', () => {
  it('counts a duplicated piece once', () => {
    const piece = line([
      [0, 0],
      [0.01, 0],
    ]);
    const once = dedupedLineStringLengthM([piece]);
    const twice = dedupedLineStringLengthM([piece, piece]);
    expect(twice).toBeCloseTo(once, 5);
    expect(once).toBeGreaterThan(1000);
  });

  it('keeps a T-branch in the unique total', () => {
    const stemA = line([
      [0, 0],
      [0.02, 0],
    ]);
    const stemB = line([
      [0.02, 0],
      [0.04, 0],
    ]);
    const branch = line([
      [0.02, 0],
      [0.02, 0.005],
    ]);
    const unique = dedupedLineStringLengthM([stemA, stemB, branch]);
    const stemOnly = dedupedLineStringLengthM([stemA, stemB]);
    expect(unique).toBeGreaterThan(stemOnly);
  });
});

describe('groupSelectionSummary', () => {
  it('reports the profile axis km, not T-branches', () => {
    const stemA = line([
      [0, 0],
      [0.02, 0],
    ]);
    const stemB = line([
      [0.02, 0],
      [0.04, 0],
    ]);
    const branch = line([
      [0.02, 0],
      [0.02, 0.005],
    ]);
    const features = [stemA, stemB, branch];
    const axis = mergeLineStringTramos(features);
    expect(axis).not.toBeNull();
    const summary = groupSelectionSummary(features);
    expect(summary).toContain('3 tramos');
    const uniqueKm = (dedupedLineStringLengthM(features) / 1000).toFixed(2);
    const axisKm = summary.match(/([0-9.]+) km sin superposición/);
    expect(axisKm?.[1]).not.toBe(uniqueKm);
  });
});
