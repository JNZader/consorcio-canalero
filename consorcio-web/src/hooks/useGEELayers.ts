/**
 * Hook for loading GeoJSON layers from GEE backend.
 * Centralizes layer loading logic used across multiple map components.
 */

import type { FeatureCollection } from 'geojson';
import { useCallback, useEffect, useState } from 'react';
import { API_URL } from '../lib/api';
import { logger } from '../lib/logger';
import { parseFeatureCollection } from '../lib/typeGuards';

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

// Default styles for GeoJSON layers (Leaflet PathOptions)
export const GEE_LAYER_STYLES: Record<GEELayerName, { color: string; weight: number; fillOpacity: number; fillColor?: string }> = {
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

interface UseGEELayersResult {
  /** Layers data as a map (name -> FeatureCollection) */
  layers: GEELayersMap;
  /** Layers data as array with name and color info */
  layersArray: GEELayerData[];
  /** Loading state */
  loading: boolean;
  /** Error message if any layer failed to load */
  error: string | null;
  /** Reload layers */
  reload: () => Promise<void>;
}

interface UseGEELayersOptions {
  /** Layer names to load. Defaults to all layers. */
  layerNames?: readonly GEELayerName[];
  /** Whether to load layers immediately. Defaults to true. */
  enabled?: boolean;
}

/**
 * Hook for loading GeoJSON layers from the GEE backend.
 *
 * @example
 * ```tsx
 * const { layers, loading, error } = useGEELayers();
 *
 * // Or load specific layers only
 * const { layers } = useGEELayers({ layerNames: ['zona', 'candil'] });
 * ```
 */
export function useGEELayers(options: UseGEELayersOptions = {}): UseGEELayersResult {
  const { layerNames = GEE_LAYER_NAMES, enabled = true } = options;

  const [layers, setLayers] = useState<GEELayersMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLayer = useCallback(
    async (name: GEELayerName): Promise<[GEELayerName, FeatureCollection | null]> => {
      try {
        const response = await fetch(`${API_URL}/api/v1/gee/layers/${name}`);
        if (response.ok) {
          const rawData = await response.json();

          // Validate the GeoJSON structure at runtime
          const validatedData = parseFeatureCollection(rawData);
          if (!validatedData) {
            logger.warn(`GEE layer '${name}' returned invalid GeoJSON structure`);
            return [name, null];
          }

          return [name, validatedData];
        }
        // Log warning but don't throw - layer might not be available
        logger.warn(`GEE layer '${name}' not available: ${response.status}`);
        return [name, null];
      } catch (err) {
        logger.warn(`Error loading GEE layer '${name}'`, err);
        return [name, null];
      }
    },
    []
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const results = await Promise.all(layerNames.map(loadLayer));

      const newLayers: GEELayersMap = {};
      let loadedCount = 0;

      for (const [name, data] of results) {
        if (data) {
          newLayers[name] = data;
          loadedCount++;
        }
      }

      setLayers(newLayers);

      // Set error if no layers loaded
      if (loadedCount === 0 && layerNames.length > 0) {
        setError('No se pudieron cargar las capas del mapa');
      }
    } catch (err) {
      setError('Error al cargar capas del mapa');
      logger.error('Error loading GEE layers', err);
    } finally {
      setLoading(false);
    }
  }, [layerNames, loadLayer]);

  useEffect(() => {
    if (enabled) {
      reload();
    } else {
      setLoading(false);
    }
  }, [enabled, reload]);

  // Convert layers map to array format
  const layersArray: GEELayerData[] = Object.entries(layers)
    .filter(([, data]) => data !== undefined)
    .map(([name, data]) => ({
      name: name as GEELayerName,
      data: data as FeatureCollection,
    }));

  return {
    layers,
    layersArray,
    loading,
    error,
    reload,
  };
}

export default useGEELayers;
