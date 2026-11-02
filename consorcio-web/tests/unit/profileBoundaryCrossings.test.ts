import type { Feature, Polygon } from 'geojson';
import { describe, expect, it } from 'vitest';

import { crossingsOnProfile } from '../../src/components/map2d/canalProfile';
import {
  culvertMarks,
  culvertPoints,
  parcelBoundaryMarks,
} from '../../src/components/map2d/profileBoundaryCrossings';

const samples = [
  { distance_m: 0, lon: 0, lat: 0 },
  { distance_m: 100, lon: 0.001, lat: 0 },
];

describe('parcel and culvert crossings', () => {
  it('marks a parcel edge the profile crosses', () => {
    const parcel: Feature<Polygon> = {
      type: 'Feature',
      properties: { Nro_Cuenta: '9-1' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [0.0005, -0.001],
            [0.0005, 0.001],
            [0.002, 0.001],
            [0.002, -0.001],
            [0.0005, -0.001],
          ],
        ],
      },
    };
    const marks = parcelBoundaryMarks(samples, [parcel]);
    expect(marks.some((mark) => mark.label === 'Parcela 9-1')).toBe(true);
    const hits = crossingsOnProfile(samples, marks, 50_000);
    expect(hits.length).toBeGreaterThan(0);
  });

  it('returns nothing when no parcels are loaded', () => {
    expect(parcelBoundaryMarks(samples, null)).toEqual([]);
    expect(parcelBoundaryMarks(samples, [])).toEqual([]);
  });

  it('keeps only alcantarillas', () => {
    expect(
      culvertPoints({
        features: [
          {
            geometry: { type: 'Point', coordinates: [-64.2, -32.4] },
            properties: { tipo: 'alcantarilla', titulo: 'Sur' },
          },
          {
            geometry: { type: 'Point', coordinates: [-64.1, -32.4] },
            properties: { tipo: 'alteo', titulo: 'Norte' },
          },
        ],
      })
    ).toEqual([{ lon: -64.2, lat: -32.4, label: 'Alcantarilla Sur' }]);
    expect(culvertMarks(null)).toEqual([]);
  });
});
