/**
 * Hook for loading the Martin tile catalog from the backend.
 * Fetches from GET /api/v2/public/layers/catalog (no auth required).
 * Returns public-facing tile URL templates for each PostGIS view
 * published by Martin.
 */

import { useQuery } from '@tanstack/react-query';
import { API_URL } from '../lib/api';
import { queryKeys } from '../lib/query';

export interface MartinCatalogItem {
  id: string;
  tile_url: string;
  description: string;
  geometry_type: string;
  source_layer: string;
}

interface MartinCatalogResponse {
  layers: MartinCatalogItem[];
  count: number;
}

export function useMartinCatalog() {
  const query = useQuery({
    queryKey: queryKeys.martinCatalog(),
    queryFn: async () => {
      const response = await fetch(`${API_URL}/api/v2/public/layers/catalog`);
      if (!response.ok) {
        throw new Error(`Error fetching Martin catalog: ${response.status}`);
      }
      return (await response.json()) as MartinCatalogResponse;
    },
    staleTime: 1000 * 60 * 5, // 5 minutes — catalog metadata is stable
  });

  return {
    layers: query.data?.layers ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error ? 'No se pudo cargar el catalogo de capas Martin' : null,
    reload: query.refetch,
  };
}
