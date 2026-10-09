import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';

import { ensureGeoJsonSource } from './map2dUtils';

export const SELECTED_LINE_SOURCE = 'map2d-selected-lines';
export const SELECTED_LINE_CASING = 'map2d-selected-lines-casing';
export const SELECTED_LINE_LAYER = 'map2d-selected-lines-line';

function isLineGeometry(geometry: Geometry | null | undefined): boolean {
  return geometry?.type === 'LineString' || geometry?.type === 'MultiLineString';
}

function lineCollection(features: readonly Feature[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: features
      .filter((feature) => isLineGeometry(feature.geometry))
      .map((feature) => ({
        type: 'Feature' as const,
        id: feature.id,
        geometry: feature.geometry,
        properties: feature.properties ?? {},
      })),
  };
}

export function useSelectedLineHighlight({
  mapRef,
  mapReady,
  features,
}: {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  readonly features: readonly Feature[];
}): void {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) {
      return;
    }
    ensureGeoJsonSource(map, SELECTED_LINE_SOURCE, lineCollection(features));
    if (!map.getLayer(SELECTED_LINE_CASING)) {
      map.addLayer({
        id: SELECTED_LINE_CASING,
        type: 'line',
        source: SELECTED_LINE_SOURCE,
        paint: {
          'line-color': '#111827',
          'line-width': 8,
          'line-opacity': 0.9,
        },
      });
    }
    if (!map.getLayer(SELECTED_LINE_LAYER)) {
      map.addLayer({
        id: SELECTED_LINE_LAYER,
        type: 'line',
        source: SELECTED_LINE_SOURCE,
        paint: {
          'line-color': '#f97316',
          'line-width': 4,
          'line-opacity': 1,
        },
      });
    }
  }, [features, mapReady, mapRef]);

  useEffect(() => {
    return () => {
      const map = mapRef.current;
      if (!map) {
        return;
      }
      if (map.getLayer(SELECTED_LINE_LAYER)) {
        map.removeLayer(SELECTED_LINE_LAYER);
      }
      if (map.getLayer(SELECTED_LINE_CASING)) {
        map.removeLayer(SELECTED_LINE_CASING);
      }
      if (map.getSource(SELECTED_LINE_SOURCE)) {
        map.removeSource(SELECTED_LINE_SOURCE);
      }
    };
  }, [mapRef]);
}
