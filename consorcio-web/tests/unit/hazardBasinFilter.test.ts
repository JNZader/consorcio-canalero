/**
 * hazardBasinFilter.test.ts
 *
 * Locks the basin → catastro filter helper used by Multi-Hazard mode.
 */

import { describe, it, expect } from 'vitest';
import {
  buildBasinCatastroFilter,
  findBasinById,
  basinToFeatureCollection,
} from '../../src/components/map2d/hazardBasinFilter';
import type { Feature, FeatureCollection, Polygon } from 'geojson';

const basinPolygon: Feature<Polygon> = {
  type: 'Feature',
  id: 'cuenca-rio-tercero',
  properties: { id: 'cuenca-rio-tercero', nombre: 'Río Tercero' },
  geometry: {
    type: 'Polygon',
    coordinates: [
      [
        [-63, -32],
        [-62, -32],
        [-62, -33],
        [-63, -33],
        [-63, -32],
      ],
    ],
  },
};

const basins: FeatureCollection = {
  type: 'FeatureCollection',
  features: [basinPolygon],
};

describe('buildBasinCatastroFilter', () => {
  it('returns null for null/undefined basin', () => {
    expect(buildBasinCatastroFilter(null)).toBeNull();
    expect(buildBasinCatastroFilter(undefined)).toBeNull();
  });

  it('returns null for a basin with no geometry', () => {
    const noGeometry = { type: 'Feature', properties: {}, geometry: null } as unknown as Feature;
    expect(buildBasinCatastroFilter(noGeometry)).toBeNull();
  });

  it('returns a MapLibre `within` filter for a valid basin', () => {
    const filter = buildBasinCatastroFilter(basinPolygon);

    expect(filter).toBeDefined();
    expect(Array.isArray(filter)).toBe(true);
    expect(filter![0]).toBe('within');
    expect((filter![1] as Feature).geometry).toEqual(basinPolygon.geometry);
  });
});

describe('findBasinById', () => {
  it('finds a basin by its id property', () => {
    expect(findBasinById(basins, 'cuenca-rio-tercero')).toEqual(basinPolygon);
  });

  it('finds a basin by its feature id when property id is absent', () => {
    const byFeatureId: FeatureCollection = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          id: 'cuenca-x',
          properties: { nombre: 'Cuenca X' },
          geometry: basinPolygon.geometry,
        },
      ],
    };
    expect(findBasinById(byFeatureId, 'cuenca-x')).toBeDefined();
  });

  it('returns undefined for missing id', () => {
    expect(findBasinById(basins, 'missing')).toBeUndefined();
    expect(findBasinById(basins, null)).toBeUndefined();
    expect(findBasinById(null, 'cuenca-rio-tercero')).toBeUndefined();
  });
});

describe('basinToFeatureCollection', () => {
  it('wraps a single basin in a FeatureCollection', () => {
    const fc = basinToFeatureCollection(basinPolygon);
    expect(fc.type).toBe('FeatureCollection');
    expect(fc.features).toHaveLength(1);
    expect(fc.features[0]).toBe(basinPolygon);
  });
});
