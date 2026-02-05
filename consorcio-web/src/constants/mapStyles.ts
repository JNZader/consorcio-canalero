/**
 * Centralized map styles and configurations.
 * Used across MapaLeaflet, MapaAnalisis, TrainingMap, etc.
 */

import type { PathOptions } from 'leaflet';

// ===========================================
// LAYER COLORS (hex codes)
// ===========================================

/**
 * Color palette for map layers.
 * Matches backend config.py CUENCA_COLORS.
 */
export const MAP_LAYER_COLORS = {
  zona: '#FF0000',
  candil: '#2196F3',
  ml: '#4CAF50',
  noroeste: '#FF9800',
  norte: '#9C27B0',
  caminos: '#FFEB3B',
  // Analysis-specific
  analysisArea: '#3b82f6',
  flood: '#0EA5E9',
  floodOptical: '#22C55E',
  floodFusion: '#A855F7',
} as const;

// ===========================================
// LAYER STYLES (Leaflet PathOptions)
// ===========================================

/**
 * Style for the consorcio zone boundary.
 */
export const ZONA_STYLE: PathOptions = {
  color: MAP_LAYER_COLORS.zona,
  weight: 3,
  fillOpacity: 0,
};

/**
 * Base style for cuenca (watershed) layers.
 */
const createCuencaStyle = (color: string): PathOptions => ({
  color,
  weight: 2,
  fillOpacity: 0.1,
  fillColor: color,
});

/**
 * Styles for each cuenca layer.
 */
export const CUENCA_STYLES: Record<string, PathOptions> = {
  candil: createCuencaStyle(MAP_LAYER_COLORS.candil),
  ml: createCuencaStyle(MAP_LAYER_COLORS.ml),
  noroeste: createCuencaStyle(MAP_LAYER_COLORS.noroeste),
  norte: createCuencaStyle(MAP_LAYER_COLORS.norte),
};

/**
 * Style for road network layer.
 */
export const CAMINOS_STYLE: PathOptions = {
  color: MAP_LAYER_COLORS.caminos,
  weight: 2,
};

/**
 * Complete map of all layer styles.
 */
export const LAYER_STYLES: Record<string, PathOptions> = {
  zona: ZONA_STYLE,
  candil: CUENCA_STYLES.candil,
  ml: CUENCA_STYLES.ml,
  noroeste: CUENCA_STYLES.noroeste,
  norte: CUENCA_STYLES.norte,
  caminos: CAMINOS_STYLE,
};

/**
 * Get style for a layer by name.
 * Returns a default style if layer not found.
 */
export function getLayerStyle(layerName: string): PathOptions {
  return (
    LAYER_STYLES[layerName] || {
      color: '#3388ff',
      weight: 2,
      fillOpacity: 0.1,
    }
  );
}

// ===========================================
// LEGEND CONFIGURATION
// ===========================================

export type LegendItemType = 'border' | 'line' | 'fill';

export interface LegendItem {
  color: string;
  label: string;
  type: LegendItemType;
}

/**
 * Default legend items for the main map.
 */
export const DEFAULT_LEGEND_ITEMS: LegendItem[] = [
  { color: MAP_LAYER_COLORS.zona, label: 'Zona Consorcio', type: 'border' },
  { color: MAP_LAYER_COLORS.candil, label: 'Cuenca Candil', type: 'fill' },
  { color: MAP_LAYER_COLORS.ml, label: 'Cuenca ML', type: 'fill' },
  { color: MAP_LAYER_COLORS.noroeste, label: 'Cuenca Noroeste', type: 'fill' },
  { color: MAP_LAYER_COLORS.norte, label: 'Cuenca Norte', type: 'fill' },
  { color: MAP_LAYER_COLORS.caminos, label: 'Red Vial', type: 'line' },
];

/**
 * Legend items for analysis map (includes analysis area).
 */
export const ANALYSIS_LEGEND_ITEMS: LegendItem[] = [
  ...DEFAULT_LEGEND_ITEMS,
  { color: MAP_LAYER_COLORS.analysisArea, label: 'Area de analisis', type: 'fill' },
];

// ===========================================
// TILE LAYER CONFIGURATIONS
// ===========================================

export const TILE_LAYERS = {
  osm: {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri',
  },
  terrain: {
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenTopoMap',
  },
} as const;

export type TileLayerName = keyof typeof TILE_LAYERS;
