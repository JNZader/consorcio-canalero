/**
 * Hook for loading the narrow public-map GeoJSON projections.
 *
 * The complete GEE layer family is operator-only. Public callers may request
 * only the fixed zona and caminos projections; legacy sub-basin identifiers are
 * reported as unavailable and are never interpolated into a URL.
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

export const GEE_LAYER_NAMES = ['zona', 'candil', 'ml', 'noroeste', 'norte', 'caminos'] as const;
export type GEELayerName = (typeof GEE_LAYER_NAMES)[number];

export const PUBLIC_GEE_LAYER_NAMES = ['zona', 'caminos'] as const;
export type PublicGEELayerName = (typeof PUBLIC_GEE_LAYER_NAMES)[number];
export const PUBLIC_GEE_LAYER_UNAVAILABLE_MESSAGE =
  'Las capas GEE solicitadas no estan disponibles en el mapa publico';

const PUBLIC_GEE_LAYER_ENDPOINTS: Record<PublicGEELayerName, string> = {
  zona: '/api/v2/public/map/gee/zona',
  caminos: '/api/v2/public/map/gee/caminos',
};

interface PublicMapProjectionResponse {
  status: 'available' | 'unavailable';
  projection: PublicGEELayerName;
  data: unknown;
  reason: 'not_configured' | 'configuration_not_approved' | 'temporarily_unavailable' | null;
}

function isPublicGEELayerName(name: GEELayerName): name is PublicGEELayerName {
  return (PUBLIC_GEE_LAYER_NAMES as readonly string[]).includes(name);
}

// Layer colors for styling and legends
export const GEE_LAYER_COLORS: Record<GEELayerName, string> = {
  zona: '#FF0000',
  candil: '#2196F3',
  ml: '#4CAF50',
  noroeste: '#FF9800',
  norte: '#9C27B0',
  caminos: '#FFEB3B',
};

/** GEE layer paint properties for MapLibre GL rendering. */
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

export interface GEELayerData {
  name: GEELayerName;
  data: FeatureCollection;
}

export type GEELayersMap = Partial<Record<GEELayerName, FeatureCollection>>;

interface UseGEELayersOptions {
  /** Layer names to load. Publicly allowlisted names are zona and caminos. */
  layerNames?: readonly GEELayerName[];
  /** Whether to load layers immediately. Defaults to true. */
  enabled?: boolean;
}

async function loadPublicLayer(
  name: PublicGEELayerName
): Promise<[GEELayerName, FeatureCollection | null]> {
  try {
    const response = await fetch(`${API_URL}${PUBLIC_GEE_LAYER_ENDPOINTS[name]}`);
    if (!response.ok) {
      logger.warn(`Public GEE projection '${name}' not available: ${response.status}`);
      return [name, null];
    }

    const envelope = (await response.json()) as PublicMapProjectionResponse;
    if (envelope.status !== 'available') {
      logger.warn(
        `Public GEE projection '${name}' is unavailable: ${envelope.reason ?? 'unknown'}`
      );
      return [name, null];
    }
    const validatedData = parseFeatureCollection(envelope.data);
    if (!validatedData) {
      logger.warn(`Public GEE projection '${name}' returned invalid GeoJSON structure`);
      return [name, null];
    }
    return [name, validatedData];
  } catch (err) {
    logger.warn(`Error loading public GEE projection '${name}'`, err);
    return [name, null];
  }
}

export function useGEELayers(options: UseGEELayersOptions = {}) {
  const { layerNames = PUBLIC_GEE_LAYER_NAMES, enabled = true } = options;
  const publicLayerNames = layerNames.filter(isPublicGEELayerName);
  const unavailableLayers = layerNames.filter((name) => !isPublicGEELayerName(name));

  const query = useQuery({
    queryKey: queryKeys.geeLayers(layerNames),
    queryFn: async () => {
      if (publicLayerNames.length === 0 && unavailableLayers.length > 0) {
        throw new Error(PUBLIC_GEE_LAYER_UNAVAILABLE_MESSAGE);
      }

      const results = await Promise.all(publicLayerNames.map(loadPublicLayer));
      const { layers: newLayers, loadedCount } = processLoadResults(results);
      if (shouldSetError(loadedCount, publicLayerNames.length)) {
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
    unavailableLayers,
    loading: query.isLoading,
    error: query.error?.message ?? null,
    reload: query.refetch,
  };
}

export default useGEELayers;
