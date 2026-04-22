import type maplibregl from 'maplibre-gl';

export function removeMapboxDrawArtifacts(map: maplibregl.Map): void {
  const style = map.getStyle();
  if (!style) return;

  for (const layer of style.layers ?? []) {
    if (layer.id.startsWith('gl-draw-') || layer.id.includes('mapbox-gl-draw')) {
      try {
        map.removeLayer(layer.id);
      } catch {
        // ignore cleanup races during WebGL context restore
      }
    }
  }

  for (const id of ['mapbox-gl-draw-cold', 'mapbox-gl-draw-hot']) {
    try {
      if (map.getSource(id)) map.removeSource(id);
    } catch {
      // ignore cleanup races during WebGL context restore
    }
  }
}

export const MAPBOX_DRAW_LINE_STYLES = [
  {
    id: 'gl-draw-lines',
    type: 'line',
    filter: ['all', ['==', '$type', 'LineString'], ['==', 'meta', 'feature']],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#0B3D91', 'line-width': 4, 'line-opacity': 0.95 },
  },
  {
    id: 'gl-draw-lines-active',
    type: 'line',
    filter: [
      'all',
      ['==', '$type', 'LineString'],
      ['==', 'meta', 'feature'],
      ['==', 'active', 'true'],
    ],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#2563eb', 'line-width': 5, 'line-opacity': 1 },
  },
  {
    id: 'gl-draw-points',
    type: 'circle',
    filter: ['all', ['==', '$type', 'Point'], ['==', 'meta', 'feature']],
    paint: {
      'circle-radius': 6,
      'circle-color': '#dc2626',
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
    },
  },
  {
    id: 'gl-draw-points-active',
    type: 'circle',
    filter: ['all', ['==', '$type', 'Point'], ['==', 'meta', 'feature'], ['==', 'active', 'true']],
    paint: {
      'circle-radius': 7,
      'circle-color': '#ef4444',
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
    },
  },
  {
    id: 'gl-draw-vertex-active',
    type: 'circle',
    filter: ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point']],
    paint: {
      'circle-radius': 5,
      'circle-color': '#2563eb',
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
    },
  },
] as const;
