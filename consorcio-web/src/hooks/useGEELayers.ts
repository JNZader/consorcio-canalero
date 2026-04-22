/**
 * Hook for loading GeoJSON layers from GEE backend.
 * Centralizes layer loading logic used across multiple map components.
 */

import { useQuery } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { API_URL } from '../lib/api';
import { logger } from '../lib/logger';
import { queryKeys } from '../lib/query';
import { parseFeatureCollection } from '../lib/typeGuards';
import {
  NO_LAYERS_ERROR_MESSAGE,
  layersMapToArray,
  processLoadResults,
  shouldSetError,
} from './geeLayerHelpers';

// Default layer names available from GEE
export const GEE_LAYER_NAMES = ['zona', 'candil', 'ml', 'noroeste', 'norte', 'caminos'] as const;
export type GEELayerName = (typeof GEE_LAYER_NAMES)[number];

// Layer colors for styling and legends
export const GEE_LAYER_COLORS: Record<GEELayerName, string> = {
  zona: '#FF0000',
  candil: '#2196F3',
  ml: '#4CAF50',
  noroeste: '#FF9800',
  norte: '#9C27B0',
  caminos: '#FFEB3B',
};

/** GEE layer paint properties for MapLibre GL rendering.
 *  Previously named GEE_LAYER_STYLES and typed as Leaflet PathOptions — now
 *  typed as plain MapLibre-compatible paint descriptors. */
export interface GEELayerPaint {
  color: string;
  weight: number;
  fillOpacity: number;
  fillColor?: string;
}

export const GEE_LAYER_STYLES: Record<GEELayerName, GEELayerPaint> = {
  zona: { color: '#FF0000', weight: 3, fillOpacity: 0 },
  candil: { color: '#2196F3', weight: 2, fillOpacity: 0.1, fillColor: '#2196F3' },
  ml: { color: '#4CAF50', weight: 2, fillOpacity: 0.1, fillColor: '#4CAF50' },
  noroeste: { color: '#FF9800', weight: 2, fillOpacity: 0.1, fillColor: '#FF9800' },
  norte: { color: '#9C27B0', weight: 2, fillOpacity: 0.1, fillColor: '#9C27B0' },
  caminos: { color: '#FFEB3B', weight: 2, fillOpacity: 0 },
};

// Layer data structure
export interface GEELayerData {
  name: GEELayerName;
  data: FeatureCollection;
}

// Layers map type
export type GEELayersMap = Partial<Record<GEELayerName, FeatureCollection>>;

interface UseGEELayersOptions {
  /** Layer names to load. Defaults to all layers. */
  layerNames?: readonly GEELayerName[];
  /** Whether to load layers immediately. Defaults to true. */
  enabled?: boolean;
}

async function loadLayer(name: GEELayerName): Promise<[GEELayerName, FeatureCollection | null]> {
  try {
    const response = await fetch(`${API_URL}/api/v2/geo/gee/layers/${name}`);
    if (response.ok) {
      const rawData = await response.json();
      const validatedData = parseFeatureCollection(rawData);
      if (!validatedData) {
        logger.warn(`GEE layer '${name}' returned invalid GeoJSON structure`);
        return [name, null];
      }
      return [name, validatedData];
    }
    logger.warn(`GEE layer '${name}' not available: ${response.status}`);
    return [name, null];
  } catch (err) {
    logger.warn(`Error loading GEE layer '${name}'`, err);
    return [name, null];
  }
}

export function useGEELayers(options: UseGEELayersOptions = {}) {
  const { layerNames = GEE_LAYER_NAMES, enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.geeLayers(layerNames),
    queryFn: async () => {
      const results = await Promise.all(layerNames.map(loadLayer));
      const { layers: newLayers, loadedCount } = processLoadResults(results);

      if (shouldSetError(loadedCount, layerNames.length)) {
        throw new Error(NO_LAYERS_ERROR_MESSAGE);
      }
      return newLayers;
    },
    enabled,
    staleTime: 1000 * 60 * 10,
  });

  const layers = query.data ?? {};
  const layersArray: GEELayerData[] = layersMapToArray(layers);

  return {
    layers,
    layersArray,
    loading: query.isLoading,
    error: query.error?.message ?? null,
    reload: query.refetch,
  };
}

export default useGEELayers;
