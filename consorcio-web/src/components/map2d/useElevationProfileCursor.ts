import type maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';

import {
  cursorCollection,
  rangeCollection,
  type ElevationProfileHover,
} from './elevationCursor';
import { ensureGeoJsonSource } from './map2dUtils';

export const ELEVATION_CURSOR_SOURCE = 'elevation-profile-cursor';
export const ELEVATION_CURSOR_LAYER = 'elevation-profile-cursor-point';
export const ELEVATION_RANGE_SOURCE = 'elevation-profile-range';
export const ELEVATION_RANGE_LAYER = 'elevation-profile-range-line';
export type { ElevationProfileHover };
export { cursorCollection };

export function useElevationProfileCursor({
  mapRef,
  mapReady,
  hover,
  rangeCoordinates = null,
}: {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  readonly hover: ElevationProfileHover;
  readonly rangeCoordinates?: ReadonlyArray<readonly [number, number]> | null;
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
    const map = mapRef.current;
    if (!map || !mapReady) {
      return;
    }
    ensureGeoJsonSource(map, ELEVATION_RANGE_SOURCE, rangeCollection(rangeCoordinates ?? null));
    if (!map.getLayer(ELEVATION_RANGE_LAYER)) {
      map.addLayer({
        id: ELEVATION_RANGE_LAYER,
        type: 'line',
        source: ELEVATION_RANGE_SOURCE,
        paint: {
          'line-color': '#f97316',
          'line-width': 6,
          'line-opacity': 0.85,
        },
      });
    }
  }, [mapReady, mapRef, rangeCoordinates]);

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
      if (map.getLayer(ELEVATION_RANGE_LAYER)) {
        map.removeLayer(ELEVATION_RANGE_LAYER);
      }
      if (map.getSource(ELEVATION_RANGE_SOURCE)) {
        map.removeSource(ELEVATION_RANGE_SOURCE);
      }
    };
  }, [mapRef]);
}
