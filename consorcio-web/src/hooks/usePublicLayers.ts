/**
 * Hook for loading public vector layers from the backend.
 * Fetches from /api/v2/public/layers (no auth required).
 * These are admin-published layers (es_publica=True, visible=True).
 */

import type { FeatureCollection } from 'geojson';
import { useQuery } from '@tanstack/react-query';
import { API_URL } from '../lib/api';
import { logger } from '../lib/logger';
import { queryKeys } from '../lib/query';

export interface PublicLayer {
  id: string;
  nombre: string;
  descripcion: string | null;
  tipo: string;
  estilo: Record<string, unknown>;
  geojson_data: FeatureCollection | null;
  orden: number;
}

export function usePublicLayers() {
  const query = useQuery({
    queryKey: queryKeys.publicLayers(),
    queryFn: async () => {
      const listResponse = await fetch(`${API_URL}/api/v2/public/layers`);
      if (!listResponse.ok) {
        throw new Error(`Error fetching public layers: ${listResponse.status}`);
      }

      const layerList: { id: string; nombre: string; tipo: string }[] =
        await listResponse.json();

      if (layerList.length === 0) return [];

      const detailPromises = layerList.map(async (layer) => {
        try {
          const detailResponse = await fetch(
            `${API_URL}/api/v2/public/layers/${layer.id}`,
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
      return details.filter(
        (l): l is PublicLayer => l !== null && l.geojson_data !== null,
      );
    },
    staleTime: 1000 * 60 * 5,
  });

  return {
    layers: query.data ?? [],
    loading: query.isLoading,
    error: query.error ? 'No se pudieron cargar las capas publicas' : null,
    reload: query.refetch,
  };
}
