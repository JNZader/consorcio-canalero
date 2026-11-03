import type { Feature } from 'geojson';
import type * as maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';
import { ensureGeoJsonSource } from '../map2dUtils';
import { readPersonalMeasurements } from './personalMeasurements';

const SOURCE = 'map2d-personal-measurements';
const FILL_LAYER = 'map2d-personal-measurements-fill';
const LAYER = 'map2d-personal-measurements-line';

export function usePersonalMeasurementsLayer(
  mapRef: RefObject<maplibregl.Map | null>,
  mapReady: boolean,
  revision: number,
  visible = true
): void {
  useEffect(() => {
    return () => {
      const map = mapRef.current;
      if (!map) return;
      try {
        if (map.getLayer(LAYER)) map.removeLayer(LAYER);
        if (map.getLayer(FILL_LAYER)) map.removeLayer(FILL_LAYER);
        if (map.getSource(SOURCE)) map.removeSource(SOURCE);
      } catch {
        // Map might have already been destroyed or removed
      }
    };
  }, [mapRef]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const features: Feature[] = visible
      ? readPersonalMeasurements().map((item) => ({
          type: 'Feature',
          id: item.id,
          properties: { kind: item.kind },
          geometry: item.geometry,
        }))
      : [];
    ensureGeoJsonSource(map, SOURCE, { type: 'FeatureCollection', features });
    if (!map.getLayer(FILL_LAYER)) {
      map.addLayer({
        id: FILL_LAYER,
        type: 'fill',
        source: SOURCE,
        filter: ['==', ['geometry-type'], 'Polygon'],
        paint: { 'fill-color': '#7c3aed', 'fill-opacity': 0.18 },
      });
    }
    if (!map.getLayer(LAYER)) {
      map.addLayer({
        id: LAYER,
        type: 'line',
        source: SOURCE,
        paint: { 'line-color': '#7c3aed', 'line-width': 3 },
      });
    }
  }, [mapReady, mapRef, revision, visible]);
}
