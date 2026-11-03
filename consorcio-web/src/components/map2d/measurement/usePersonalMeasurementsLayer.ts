import type { Feature } from 'geojson';
import type * as maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';
import { ensureGeoJsonSource } from '../map2dUtils';
import { readPersonalMeasurements } from './personalMeasurements';

const SOURCE = 'map2d-personal-measurements';
const LAYER = 'map2d-personal-measurements-line';

export function usePersonalMeasurementsLayer(
  mapRef: RefObject<maplibregl.Map | null>,
  mapReady: boolean,
  revision: number
): void {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const features: Feature[] = readPersonalMeasurements().map((item) => ({
      type: 'Feature',
      id: item.id,
      properties: { kind: item.kind },
      geometry: item.geometry,
    }));
    ensureGeoJsonSource(map, SOURCE, { type: 'FeatureCollection', features });
    if (!map.getLayer(LAYER)) {
      map.addLayer({
        id: LAYER,
        type: 'line',
        source: SOURCE,
        paint: { 'line-color': '#7c3aed', 'line-width': 3 },
      });
    }
  }, [mapReady, mapRef, revision]);
}
