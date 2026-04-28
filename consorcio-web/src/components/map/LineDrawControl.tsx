/**
 * LineDrawControl — polyline draw control (MapLibre only).
 *
 * Uses @mapbox/mapbox-gl-draw. Requires a `map` prop (maplibregl.Map instance).
 *
 * External interface (DrawnLineFeatureCollection, LineDrawControlProps) is UNCHANGED.
 */

// ─── Public types ─────────────────────────────────────────────────────────────

export interface DrawnLineFeature {
  type: 'Feature';
  geometry: {
    type: 'LineString';
    coordinates: number[][];
  };
  properties: Record<string, never>;
}

export interface DrawnPointFeature {
  type: 'Feature';
  geometry: {
    type: 'Point';
    coordinates: number[];
  };
  properties: Record<string, never>;
}

export interface DrawnLineFeatureCollection {
  type: 'FeatureCollection';
  features: Array<DrawnLineFeature | DrawnPointFeature>;
}

interface LineDrawControlProps {
  /** MapLibre map instance (required). */
  readonly map: import('maplibre-gl').Map;
  readonly value: DrawnLineFeatureCollection | null;
  readonly onChange: (geometry: DrawnLineFeatureCollection | null) => void;
}

// ─── MapLibre implementation ──────────────────────────────────────────────────

import MapboxDraw from '@mapbox/mapbox-gl-draw';
import '@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css';
import { useEffect, useRef } from 'react';
import { useMapboxDrawSlot } from '../../stores/mapboxDrawSlot';
import { ensureMapboxDrawCompatibility } from './mapboxDrawCompatibility';
import { MAPBOX_DRAW_LINE_STYLES, removeMapboxDrawArtifacts } from './mapboxDrawShared';

export default function LineDrawControl({ map, value, onChange }: LineDrawControlProps) {
  const drawRef = useRef<MapboxDraw | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Slot mutex — measurement takes precedence. When `slotOwner === 'measurement'`
  // we skip the entire mount (no MapboxDraw, no event listeners). Once the
  // user finishes measuring and the slot returns to null, this effect re-runs
  // and we mount normally; the value-sync effect below restores the saved
  // features from props.
  const slotOwner = useMapboxDrawSlot((s) => s.owner);
  const acquire = useMapboxDrawSlot((s) => s.acquire);
  const release = useMapboxDrawSlot((s) => s.release);

  useEffect(() => {
    if (slotOwner === 'measurement') {
      // Measurement is active — yield the slot. We'll re-mount when it releases.
      return;
    }
    if (!acquire('line-draw')) {
      // Defensive: another non-measurement owner — should not happen today
      // but the API allows for it. Skip the mount cleanly.
      return;
    }

    ensureMapboxDrawCompatibility(map);

    const draw = new MapboxDraw({
      displayControlsDefault: false,
      controls: { point: true, line_string: true, trash: true },
      defaultMode: 'simple_select',
      styles: [...MAPBOX_DRAW_LINE_STYLES],
    });

    drawRef.current = draw;

    // Clean stale Draw sources/layers before adding — prevents "source already exists"
    // crash after WebGL context loss+restore (same fix as DrawControl.tsx).
    removeMapboxDrawArtifacts(map);

    // MapboxDraw targets the same GL API as maplibre-gl
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    map.addControl(draw as unknown as import('maplibre-gl').IControl);

    const emitCurrent = () => {
      const all = draw.getAll();
      const accepted = all.features.filter(
        (f) => f.geometry.type === 'LineString' || f.geometry.type === 'Point'
      );
      if (accepted.length === 0) {
        onChangeRef.current(null);
        return;
      }
      onChangeRef.current({
        type: 'FeatureCollection',
        features: accepted.map((f) => {
          if (f.geometry.type === 'Point') {
            return {
              type: 'Feature' as const,
              geometry: {
                type: 'Point' as const,
                coordinates: (f.geometry as GeoJSON.Point).coordinates as number[],
              },
              properties: {} as Record<string, never>,
            };
          }
          return {
            type: 'Feature' as const,
            geometry: {
              type: 'LineString' as const,
              coordinates: (f.geometry as GeoJSON.LineString).coordinates as number[][],
            },
            properties: {} as Record<string, never>,
          };
        }),
      });
    };

    const handleContextLost = () => {
      removeMapboxDrawArtifacts(map);
    };

    map.on('draw.create', emitCurrent);
    map.on('draw.update', emitCurrent);
    map.on('draw.delete', emitCurrent);
    map.on('webglcontextlost', handleContextLost);

    return () => {
      map.off('draw.create', emitCurrent);
      map.off('draw.update', emitCurrent);
      map.off('draw.delete', emitCurrent);
      map.off('webglcontextlost', handleContextLost);
      try {
        removeMapboxDrawArtifacts(map);
        if (map.hasControl(draw as unknown as import('maplibre-gl').IControl)) {
          map.removeControl(draw as unknown as import('maplibre-gl').IControl);
        }
      } catch {
        // ignore — removal can race with WebGL context restore / map teardown
      }
      removeMapboxDrawArtifacts(map);
      drawRef.current = null;
      release('line-draw');
    };
  }, [map, slotOwner, acquire, release]);

  // Sync external value → draw control (controlled component pattern)
  useEffect(() => {
    const draw = drawRef.current;
    if (!draw) return;
    draw.deleteAll();
    for (const feature of value?.features ?? []) {
      if (feature.geometry.type === 'LineString') {
        draw.add({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: feature.geometry.coordinates },
          properties: {},
        });
      } else if (feature.geometry.type === 'Point') {
        draw.add({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: feature.geometry.coordinates },
          properties: {},
        });
      }
    }
  }, [value]);

  return null;
}
