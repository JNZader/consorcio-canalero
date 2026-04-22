/**
 * Helper functions for GEE layers management.
 * Extracted from useGEELayers for better testability and reusability.
 */

import type { FeatureCollection } from 'geojson';
import type { GEELayerData, GEELayerName, GEELayersMap } from './useGEELayers';

/**
 * Generic error message for GEE layer loading failures.
 */
export const GENERIC_ERROR_MESSAGE = 'Error cargando capas del servidor de maps';

/**
 * Error message when no layers could be loaded.
 */
export const NO_LAYERS_ERROR_MESSAGE = 'No se pudieron cargar las capas del mapa';

/**
 * Process results from loading multiple layers.
 * @param results Array of [layerName, layerData] tuples
 * @returns Object with processed layers map and count of successfully loaded layers
 */
export function processLoadResults(results: Array<[GEELayerName, FeatureCollection | null]>): {
  layers: GEELayersMap;
  loadedCount: number;
} {
  const layers: GEELayersMap = {};
  let loadedCount = 0;

  for (const [name, data] of results) {
    if (data !== null) {
      layers[name] = data;
      loadedCount++;
    }
  }

  return { layers, loadedCount };
}

/**
 * Determine if an error should be set based on load results.
 * @param loadedCount Number of successfully loaded layers
 * @param requestedCount Total number of layers requested
 * @returns true if error should be set (no layers loaded)
 */
export function shouldSetError(loadedCount: number, requestedCount: number): boolean {
  return loadedCount === 0 && requestedCount > 0;
}

/**
 * Convert a layers map to an array of GEELayerData with color info.
 * @param layers Map of layer names to FeatureCollections
 * @returns Array of layer data with names
 */
export function layersMapToArray(layers: GEELayersMap): GEELayerData[] {
  return Object.entries(layers)
    .filter(([, data]) => data !== undefined)
    .map(([name, data]) => ({
      name: name as GEELayerName,
      data: data as FeatureCollection,
    }));
}
