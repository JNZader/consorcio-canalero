import type { Map as MapLibreMap } from 'maplibre-gl';

import {
  TERRAIN_HILLSHADE_SOURCE_ID,
  buildHillshadeDemSource,
} from './terrainHillshadeSource';

export const TERRAIN_HILLSHADE_LAYER_ID = 'terrain-hillshade';

export const TERRAIN_SKY = {
  'sky-color': '#87CEEB',
  'sky-horizon-blend': 0.5,
  'horizon-color': '#c8d6e5',
  'horizon-fog-blend': 0.5,
  'fog-color': '#d8e1ea',
  'fog-ground-blend': 0.45,
} as const;

const HILLSHADE_BEFORE_ID = 'puntos_conflicto-circle';

/** UX PDF T4 — hillshade under vectors + soft sky/fog. */
export function applyTerrainDepthCues(map: MapLibreMap): void {
  const terrainRgb = map.getSource('terrain-rgb') as
    | { tiles?: string[]; url?: string; tileSize?: number; maxzoom?: number; minzoom?: number }
    | undefined;
  if (terrainRgb && !map.getSource(TERRAIN_HILLSHADE_SOURCE_ID)) {
    const spec = buildHillshadeDemSource(terrainRgb);
    if (spec) map.addSource(TERRAIN_HILLSHADE_SOURCE_ID, spec);
  }
  const hillshadeSource = map.getSource(TERRAIN_HILLSHADE_SOURCE_ID)
    ? TERRAIN_HILLSHADE_SOURCE_ID
    : 'terrain-rgb';
  if (map.getSource(hillshadeSource) && !map.getLayer(TERRAIN_HILLSHADE_LAYER_ID)) {
    const layer = {
      id: TERRAIN_HILLSHADE_LAYER_ID,
      type: 'hillshade' as const,
      source: hillshadeSource,
      paint: {
        'hillshade-exaggeration': 0.35,
        'hillshade-illumination-direction': 315,
        'hillshade-illumination-anchor': 'viewport' as const,
      },
    };
    if (map.getLayer(HILLSHADE_BEFORE_ID)) {
      map.addLayer(layer, HILLSHADE_BEFORE_ID);
    } else {
      map.addLayer(layer);
    }
  }
  if (typeof map.setSky === 'function') {
    map.setSky({ ...TERRAIN_SKY });
  }
}

export function removeTerrainHillshade(map: MapLibreMap): void {
  if (map.getLayer(TERRAIN_HILLSHADE_LAYER_ID)) {
    map.removeLayer(TERRAIN_HILLSHADE_LAYER_ID);
  }
  if (map.getSource(TERRAIN_HILLSHADE_SOURCE_ID)) {
    map.removeSource(TERRAIN_HILLSHADE_SOURCE_ID);
  }
}
