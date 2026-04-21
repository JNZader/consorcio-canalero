import type { FeatureCollection } from 'geojson';
import { describe, expect, it } from 'vitest';

import {
  MAP_FALLBACK_BOUNDS,
  getFeatureCollectionBounds,
  resolveConsorcioBounds,
} from '../../src/components/map2d/map2dUtils';
import { MAP_BOUNDS } from '../../src/constants';

describe('map2dUtils — bounds helpers', () => {
  describe('getFeatureCollectionBounds', () => {
    it('returns null when the FeatureCollection is null', () => {
      expect(getFeatureCollectionBounds(null)).toBeNull();
    });

    it('returns null when there are no features', () => {
      const fc: FeatureCollection = { type: 'FeatureCollection', features: [] };
      expect(getFeatureCollectionBounds(fc)).toBeNull();
    });

    it('computes correct bbox for a single Polygon feature', () => {
      const fc: FeatureCollection = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: {
              type: 'Polygon',
              coordinates: [
                [
                  [-63.0, -33.0],
                  [-62.0, -33.0],
                  [-62.0, -32.0],
                  [-63.0, -32.0],
                  [-63.0, -33.0],
                ],
              ],
            },
            properties: {},
          },
        ],
      };

      expect(getFeatureCollectionBounds(fc)).toEqual([
        [-63.0, -33.0],
        [-62.0, -32.0],
      ]);
    });

    it('returns the UNION bbox for a MultiPolygon feature', () => {
      const fc: FeatureCollection = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: {
              type: 'MultiPolygon',
              coordinates: [
                [
                  [
                    [-63.5, -33.5],
                    [-63.0, -33.5],
                    [-63.0, -33.0],
                    [-63.5, -33.0],
                    [-63.5, -33.5],
                  ],
                ],
                [
                  [
                    [-62.5, -32.5],
                    [-62.0, -32.5],
                    [-62.0, -32.0],
                    [-62.5, -32.0],
                    [-62.5, -32.5],
                  ],
                ],
              ],
            },
            properties: {},
          },
        ],
      };

      expect(getFeatureCollectionBounds(fc)).toEqual([
        [-63.5, -33.5],
        [-62.0, -32.0],
      ]);
    });

    it('returns an encompassing bbox for mixed Point + LineString + Polygon', () => {
      const fc: FeatureCollection = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [-62.1, -32.1] },
            properties: {},
          },
          {
            type: 'Feature',
            geometry: {
              type: 'LineString',
              coordinates: [
                [-63.2, -32.9],
                [-62.8, -32.5],
              ],
            },
            properties: {},
          },
          {
            type: 'Feature',
            geometry: {
              type: 'Polygon',
              coordinates: [
                [
                  [-62.5, -32.6],
                  [-62.4, -32.6],
                  [-62.4, -32.4],
                  [-62.5, -32.4],
                  [-62.5, -32.6],
                ],
              ],
            },
            properties: {},
          },
        ],
      };

      // lng range: [-63.2, -62.1], lat range: [-32.9, -32.1]
      expect(getFeatureCollectionBounds(fc)).toEqual([
        [-63.2, -32.9],
        [-62.1, -32.1],
      ]);
    });

    it('ignores features without coordinates (e.g. null geometry)', () => {
      const fc: FeatureCollection = {
        type: 'FeatureCollection',
        features: [
          { type: 'Feature', geometry: null as never, properties: {} },
        ],
      };
      expect(getFeatureCollectionBounds(fc)).toBeNull();
    });
  });

  describe('MAP_FALLBACK_BOUNDS', () => {
    it('mirrors MAP_BOUNDS as [[west, south], [east, north]]', () => {
      expect(MAP_FALLBACK_BOUNDS).toEqual([
        [MAP_BOUNDS.west, MAP_BOUNDS.south],
        [MAP_BOUNDS.east, MAP_BOUNDS.north],
      ]);
    });
  });

  describe('resolveConsorcioBounds', () => {
    it('returns MAP_FALLBACK_BOUNDS when the zone collection is null', () => {
      expect(resolveConsorcioBounds(null)).toEqual(MAP_FALLBACK_BOUNDS);
    });

    it("returns the FeatureCollection's bbox when it has features", () => {
      const fc: FeatureCollection = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: {
              type: 'Polygon',
              coordinates: [
                [
                  [-62.8, -32.7],
                  [-62.4, -32.7],
                  [-62.4, -32.5],
                  [-62.8, -32.5],
                  [-62.8, -32.7],
                ],
              ],
            },
            properties: {},
          },
        ],
      };

      expect(resolveConsorcioBounds(fc)).toEqual([
        [-62.8, -32.7],
        [-62.4, -32.5],
      ]);
    });

    it('falls back to MAP_FALLBACK_BOUNDS when the collection is empty', () => {
      const emptyFc: FeatureCollection = { type: 'FeatureCollection', features: [] };
      expect(resolveConsorcioBounds(emptyFc)).toEqual(MAP_FALLBACK_BOUNDS);
    });
  });
});
