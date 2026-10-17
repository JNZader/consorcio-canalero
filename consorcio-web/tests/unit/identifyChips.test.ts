import type { Feature, LineString } from 'geojson';
import { describe, expect, it } from 'vitest';

import {
  groupIdentifyChips,
  identifyTramoRows,
  shouldHideDuplicateChips,
} from '../../src/components/map2d/identifyChips';

function road(rtn: string, coords: LineString['coordinates']): Feature<LineString> {
  return {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: coords },
    properties: { rtn },
  };
}

const SEGMENT_A: LineString['coordinates'] = [
  [-62.5, -32.5],
  [-62.4, -32.5],
];
const SEGMENT_B: LineString['coordinates'] = [
  [-62.4, -32.5],
  [-62.3, -32.5],
];

describe('groupIdentifyChips', () => {
  it('collapses 18 identical road names into one counted chip', () => {
    const features = Array.from({ length: 18 }, () => road('CRN9', SEGMENT_A));
    const chips = groupIdentifyChips(features);
    expect(chips).toHaveLength(1);
    expect(chips[0].label).toBe('CRN9 ×18');
    expect(chips[0].indices).toHaveLength(18);
    expect(shouldHideDuplicateChips(chips, 18)).toBe(true);
  });

  it('keeps distinct names as separate chips', () => {
    const chips = groupIdentifyChips([
      road('CRN9', SEGMENT_A),
      road('T135-07', SEGMENT_B),
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [-62.5, -32.5] },
        properties: { nombre: 'Escuela rural' },
      },
    ]);
    expect(chips.map((chip) => chip.label)).toEqual(['CRN9', 'T135-07', 'Escuela rural']);
    expect(shouldHideDuplicateChips(chips, 3)).toBe(false);
  });

  it('does not hide chips for a single feature', () => {
    const chips = groupIdentifyChips([road('CRN9', SEGMENT_A)]);
    expect(shouldHideDuplicateChips(chips, 1)).toBe(false);
  });
});

describe('identifyTramoRows', () => {
  it('numbers each tramo and appends length in km', () => {
    const rows = identifyTramoRows([road('CRN9', SEGMENT_A), road('CRN9', SEGMENT_B)]);
    expect(rows).toHaveLength(2);
    expect(rows[0].label).toMatch(/^Tramo 1 · \d+\.\d{2} km$/);
    expect(rows[1].label).toMatch(/^Tramo 2 · \d+\.\d{2} km$/);
    expect(rows[0].index).toBe(0);
    expect(rows[1].index).toBe(1);
  });

  it('measures a unified MultiLineString route', () => {
    const route: Feature = {
      type: 'Feature',
      geometry: {
        type: 'MultiLineString',
        coordinates: [SEGMENT_A, SEGMENT_B],
      },
      properties: { rtn: 'T269-03' },
    };
    const rows = identifyTramoRows([route]);
    expect(rows[0].label).toMatch(/^Tramo 1 · \d+\.\d{2} km$/);
  });
});
