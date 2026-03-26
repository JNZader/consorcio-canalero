/**
 * Hook for loading public vector layers from the backend.
 * Fetches from /api/v2/public/layers (no auth required).
 * These are admin-published layers (es_publica=True, visible=True).
 */

import type { FeatureCollection } from 'geojson';
import { useCallback, useEffect, useState } from 'react';
import { API_URL } from '../lib/api';
import { logger } from '../lib/logger';

export interface PublicLayer {
  id: string;
  nombre: string;
  descripcion: string | null;
  tipo: string;
  estilo: Record<string, unknown>;
  geojson_data: FeatureCollection | null;
  orden: number;
}

interface UsePublicLayersResult {
  layers: PublicLayer[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

/**
 * Fetches public layers from /api/v2/public/layers and loads their
 * GeoJSON detail from /api/v2/public/layers/{id}.
 */
export function usePublicLayers(): UsePublicLayersResult {
  const [layers, setLayers] = useState<PublicLayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Step 1: Get the list of public layers (lightweight, no geojson_data)
      const listResponse = await fetch(`${API_URL}/api/v2/public/layers`);
      if (!listResponse.ok) {
        throw new Error(`Error fetching public layers: ${listResponse.status}`);
      }

      const layerList: { id: string; nombre: string; tipo: string }[] =
        await listResponse.json();

      if (layerList.length === 0) {
        setLayers([]);
        setLoading(false);
        return;
      }

      // Step 2: Fetch detail (with geojson_data) for each layer in parallel
      const detailPromises = layerList.map(async (layer) => {
        try {
          const detailResponse = await fetch(
            `${API_URL}/api/v2/public/layers/${layer.id}`
          );
          if (detailResponse.ok) {
            return (await detailResponse.json()) as PublicLayer;
          }
          logger.warn(`Public layer detail not available: ${layer.nombre}`);
          return null;
        } catch (err) {
          logger.warn(`Error loading public layer detail: ${layer.nombre}`, err);
          return null;
        }
      });

      const details = await Promise.all(detailPromises);
      const validLayers = details.filter(
        (l): l is PublicLayer => l !== null && l.geojson_data !== null
      );

      setLayers(validLayers);
    } catch (err) {
      logger.error('Error loading public layers', err);
      setError('No se pudieron cargar las capas publicas');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { layers, loading, error, reload };
}
