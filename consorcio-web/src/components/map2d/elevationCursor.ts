import type { FeatureCollection } from 'geojson';

export type ElevationProfileHover = {
  readonly lon: number;
  readonly lat: number;
} | null;

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
