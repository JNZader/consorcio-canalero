import type { FeatureCollection } from 'geojson';

export type ElevationProfileHover = {
  readonly lon: number;
  readonly lat: number;
} | null;

export function rangeCollection(
  coordinates: ReadonlyArray<readonly [number, number]> | null,
): FeatureCollection {
  if (!coordinates || coordinates.length < 2) {
    return { type: 'FeatureCollection', features: [] };
  }
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: coordinates.map((pair) => [...pair]) },
        properties: {},
      },
    ],
  };
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
