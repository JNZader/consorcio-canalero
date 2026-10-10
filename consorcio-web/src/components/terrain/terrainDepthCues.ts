import type { Map as MapLibreMap } from 'maplibre-gl';

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
  if (map.getSource('terrain-rgb') && !map.getLayer(TERRAIN_HILLSHADE_LAYER_ID)) {
    const layer = {
      id: TERRAIN_HILLSHADE_LAYER_ID,
      type: 'hillshade' as const,
      source: 'terrain-rgb',
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
}
