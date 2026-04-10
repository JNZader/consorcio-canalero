import { describe, expect, it } from 'vitest';

import {
  buildCorridorAnchorCollection,
  buildCorridorMapCollections,
  buildCorridorSummary,
  collectCorridorBounds,
  formatCorridorDistance,
  ROUTING_MODE_PRESETS,
  ROUTING_PROFILE_PRESETS,
} from '../../src/components/admin/canal-suggestions/corridorRoutingUtils';

const sampleResponse = {
  source: { id: 1 },
  target: { id: 2 },
  summary: {
    mode: 'raster' as const,
    profile: 'balanceado' as const,
    total_distance_m: 1530,
    edges: 6,
    corridor_width_m: 75,
    penalty_factor: 3,
    cost_breakdown: {
      profile: 'balanceado' as const,
      edge_count_with_profile_factor: 2,
      avg_profile_factor: 1.15,
      max_profile_factor: 1.3,
      min_profile_factor: 1,
      parcel_intersections: 1,
      near_parcels: 2,
      avg_hydric_index: 63.5,
      hydraulic_edge_count: 2,
      profile_edge_count: 2,
    },
  },
  centerline: {
    type: 'FeatureCollection' as const,
    features: [
      {
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: [
            [-60.1, -31.1],
            [-60.2, -31.2],
          ],
        },
        properties: { name: 'central' },
      },
    ],
  },
  corridor: {
    type: 'Feature' as const,
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [-60.11, -31.11],
          [-60.19, -31.11],
          [-60.19, -31.19],
          [-60.11, -31.19],
          [-60.11, -31.11],
        ],
      ],
    },
    properties: { label: 'buffer' },
  },
  alternatives: [
    {
      rank: 1,
      total_distance_m: 1700,
      edges: 7,
      edge_ids: [1, 2],
      geojson: {
        type: 'FeatureCollection' as const,
        features: [
          {
            type: 'Feature',
            geometry: {
              type: 'LineString',
              coordinates: [
                [-60.05, -31.05],
                [-60.15, -31.15],
              ],
            },
            properties: {},
          },
        ],
      },
    },
  ],
};

describe('corridorRoutingUtils', () => {
  it('formats distances in meters and kilometers', () => {
    expect(formatCorridorDistance(250)).toBe('250 m');
    expect(formatCorridorDistance(1234)).toBe('1.23 km');
  });

  it('defines named routing profile presets', () => {
    expect(ROUTING_PROFILE_PRESETS.hidraulico).toMatchObject({
      corridorWidthM: 80,
      alternativeCount: 1,
    });
    expect(ROUTING_PROFILE_PRESETS.evitar_propiedad).toMatchObject({
      corridorWidthM: 40,
      alternativeCount: 3,
    });
  });

  it('defines routing mode presets', () => {
    expect(ROUTING_MODE_PRESETS.raster.label).toBe('Raster multi-criterio');
  });

  it('builds summary from corridor response', () => {
    const summary = buildCorridorSummary(sampleResponse);

    expect(summary).toEqual({
      mode: 'Raster multi-criterio',
      profile: 'Balanceado',
      totalDistance: '1.53 km',
      edges: 6,
      width: '75 m',
      alternativeCount: 1,
      penaltyFactor: 3,
      costBreakdown: sampleResponse.summary.cost_breakdown,
    });
  });

  it('normalizes map collections with corridor roles', () => {
    const collections = buildCorridorMapCollections(sampleResponse);

    expect(collections.centerline?.features[0]?.properties).toMatchObject({
      name: 'central',
      role: 'centerline',
    });
    expect(collections.corridor?.features[0]?.properties).toMatchObject({
      label: 'buffer',
      role: 'corridor',
    });
    expect(collections.alternatives?.features[0]?.properties).toMatchObject({
      role: 'alternative',
      rank: 1,
      total_distance_m: 1700,
    });
  });

  it('collects bounds coordinates from centerline corridor and alternatives', () => {
    expect(collectCorridorBounds(sampleResponse)).toEqual(
      expect.arrayContaining([
        [-60.1, -31.1],
        [-60.2, -31.2],
        [-60.11, -31.11],
        [-60.15, -31.15],
      ]),
    );
  });

  it('builds origin and destination anchor features from form coordinates', () => {
    expect(
      buildCorridorAnchorCollection({
        fromLon: -60.1,
        fromLat: -31.1,
        toLon: -60.2,
        toLat: -31.2,
      }),
    ).toEqual({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [-60.1, -31.1] },
          properties: { role: 'from', label: 'Origen', color: '#2f9e44' },
        },
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [-60.2, -31.2] },
          properties: { role: 'to', label: 'Destino', color: '#e03131' },
        },
      ],
    });
  });
});
