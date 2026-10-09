import type { FeatureCollection, LineString } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';

import { ensureGeoJsonSource } from './map2dUtils';
import { pointAlongLineString } from './pointAlongLine';

export const ELEVATION_CURSOR_SOURCE = 'elevation-profile-cursor';
export const ELEVATION_CURSOR_LAYER = 'elevation-profile-cursor-point';

export type ElevationProfileHover = {
  readonly geometry: LineString;
  readonly distanceM: number;
} | null;

function cursorCollection(hover: ElevationProfileHover): FeatureCollection {
  if (!hover) {
    return { type: 'FeatureCollection', features: [] };
  }
  const coordinates = pointAlongLineString(hover.geometry.coordinates, hover.distanceM);
  if (!coordinates) {
    return { type: 'FeatureCollection', features: [] };
  }
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates },
        properties: {},
      },
    ],
  };
}

export function useElevationProfileCursor({
  mapRef,
  mapReady,
  hover,
}: {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  readonly hover: ElevationProfileHover;
}): void {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) {
      return;
    }
    ensureGeoJsonSource(map, ELEVATION_CURSOR_SOURCE, cursorCollection(hover));
    if (!map.getLayer(ELEVATION_CURSOR_LAYER)) {
      map.addLayer({
        id: ELEVATION_CURSOR_LAYER,
        type: 'circle',
        source: ELEVATION_CURSOR_SOURCE,
        paint: {
          'circle-radius': 7,
          'circle-color': '#f97316',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff',
        },
      });
    }
  }, [hover, mapReady, mapRef]);

  useEffect(() => {
    return () => {
      const map = mapRef.current;
      if (!map) {
        return;
      }
      if (map.getLayer(ELEVATION_CURSOR_LAYER)) {
        map.removeLayer(ELEVATION_CURSOR_LAYER);
      }
      if (map.getSource(ELEVATION_CURSOR_SOURCE)) {
        map.removeSource(ELEVATION_CURSOR_SOURCE);
      }
    };
  }, [mapRef]);
}
