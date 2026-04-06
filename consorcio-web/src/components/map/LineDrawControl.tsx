/**
 * LineDrawControl — polyline draw control (MapLibre only).
 *
 * Uses @mapbox/mapbox-gl-draw. Requires a `map` prop (maplibregl.Map instance).
 *
 * External interface (DrawnLineFeatureCollection, LineDrawControlProps) is UNCHANGED.
 */

// ─── Public types ─────────────────────────────────────────────────────────────

export interface DrawnLineFeatureCollection {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: {
      type: 'LineString';
      coordinates: number[][];
    };
    properties: Record<string, never>;
  }>;
}

interface LineDrawControlProps {
  /** MapLibre map instance (required). */
  readonly map: import('maplibre-gl').Map;
  readonly value: DrawnLineFeatureCollection | null;
  readonly onChange: (geometry: DrawnLineFeatureCollection | null) => void;
}

// ─── MapLibre implementation ──────────────────────────────────────────────────

import MapboxDraw from '@mapbox/mapbox-gl-draw';
import { useEffect, useRef } from 'react';

export default function LineDrawControl({ map, value, onChange }: LineDrawControlProps) {
  const drawRef = useRef<MapboxDraw | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const draw = new MapboxDraw({
      displayControlsDefault: false,
      controls: { line_string: true, trash: true },
      defaultMode: 'simple_select',
      styles: [
        {
          id: 'gl-draw-line-active',
          type: 'line',
          filter: ['all', ['==', '$type', 'LineString'], ['!=', 'mode', 'static']],
          paint: { 'line-color': '#0B3D91', 'line-width': 4, 'line-opacity': 0.95 },
        },
        {
          id: 'gl-draw-line-vertex',
          type: 'circle',
          filter: ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point']],
          paint: { 'circle-radius': 4, 'circle-color': '#0B3D91' },
        },
      ],
    });

    drawRef.current = draw;

    // Clean stale Draw sources/layers before adding — prevents "source already exists"
    // crash after WebGL context loss+restore (same fix as DrawControl.tsx).
    const existingStyle = map.getStyle();
    if (existingStyle && map.getSource('mapbox-gl-draw-cold')) {
      for (const layer of existingStyle.layers ?? []) {
        if (layer.id.startsWith('gl-draw-') || layer.id.includes('mapbox-gl-draw')) {
          try { map.removeLayer(layer.id); } catch { /* ignore */ }
        }
      }
      for (const id of ['mapbox-gl-draw-cold', 'mapbox-gl-draw-hot']) {
        try { map.removeSource(id); } catch { /* ignore */ }
      }
    }

    // MapboxDraw targets the same GL API as maplibre-gl
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    map.addControl(draw as unknown as import('maplibre-gl').IControl);

    const emitCurrent = () => {
      const all = draw.getAll();
      const lines = all.features.filter((f) => f.geometry.type === 'LineString');
      if (lines.length === 0) {
        onChangeRef.current(null);
        return;
      }
      onChangeRef.current({
        type: 'FeatureCollection',
        features: lines.map((f) => ({
          type: 'Feature' as const,
          geometry: {
            type: 'LineString' as const,
            coordinates: (f.geometry as GeoJSON.LineString).coordinates as number[][],
          },
          properties: {} as Record<string, never>,
        })),
      });
    };

    map.on('draw.create', emitCurrent);
    map.on('draw.update', emitCurrent);
    map.on('draw.delete', emitCurrent);

    return () => {
      map.off('draw.create', emitCurrent);
      map.off('draw.update', emitCurrent);
      map.off('draw.delete', emitCurrent);
      if (map.hasControl(draw as unknown as import('maplibre-gl').IControl)) {
        map.removeControl(draw as unknown as import('maplibre-gl').IControl);
      }
      drawRef.current = null;
    };
  }, [map]);

  // Sync external value → draw control (controlled component pattern)
  useEffect(() => {
    const draw = drawRef.current;
    if (!draw) return;
    draw.deleteAll();
    for (const feature of value?.features ?? []) {
      if (feature.geometry.type !== 'LineString') continue;
      draw.add({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: feature.geometry.coordinates },
        properties: {},
      });
    }
  }, [value]);

  return null;
}
