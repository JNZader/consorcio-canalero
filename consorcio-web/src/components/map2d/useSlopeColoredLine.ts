import type { Feature } from 'geojson';
import type * as maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';
import { ensureGeoJsonSource } from './map2dUtils';
import type { ProfileChartRow } from './profileChartRows';
import { slopeLineFeatures } from './slopeColor';

const SOURCE = 'map2d-profile-slope';
const LAYER = 'map2d-profile-slope-line';

export function useSlopeColoredLine({
  mapRef,
  mapReady,
  samples,
}: {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  readonly samples: readonly ProfileChartRow[];
}): void {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const features: Feature[] = slopeLineFeatures(samples);
    ensureGeoJsonSource(map, SOURCE, { type: 'FeatureCollection', features });
    if (!map.getLayer(LAYER)) {
      map.addLayer({
        id: LAYER,
        type: 'line',
        source: SOURCE,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 4,
        },
      });
    }
  }, [mapReady, mapRef, samples]);
}
