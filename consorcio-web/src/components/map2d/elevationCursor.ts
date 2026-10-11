import type { Feature, FeatureCollection } from 'geojson';

import type { ProfileExtremaPoint, ProfileRangeStats } from './profileRange';

export type ElevationProfileHover = {
  readonly lon: number;
  readonly lat: number;
} | null;

function extremaFeature(kind: 'min' | 'max', point: ProfileExtremaPoint): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [point.lon, point.lat] },
    properties: {
      kind,
      elevation_m: point.elevation_m,
    },
  };
}

export function rangeCollection(range: ProfileRangeStats | null): FeatureCollection {
  if (!range || range.coordinates.length < 2) {
    return { type: 'FeatureCollection', features: [] };
  }
  const features: Feature[] = [
    {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: range.coordinates.map((pair) => [...pair]),
      },
      properties: { kind: 'span' },
    },
  ];
  if (range.min_point) {
    features.push(extremaFeature('min', range.min_point));
  }
  if (range.max_point) {
    features.push(extremaFeature('max', range.max_point));
  }
  return { type: 'FeatureCollection', features };
}

export function cursorCollection(hover: ElevationProfileHover): FeatureCollection {
  if (!hover) {
    return { type: 'FeatureCollection', features: [] };
  }
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [hover.lon, hover.lat] },
        properties: {},
      },
    ],
  };
}
