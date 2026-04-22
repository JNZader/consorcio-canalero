/**
 * Hook para cargar caminos con colores por consorcio caminero.
 * Cada camino tiene un color asignado segun su consorcio para visualizacion diferenciada.
 */

import { useQuery } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { useMemo } from 'react';
import { API_URL } from '../lib/api';
import { queryKeys } from '../lib/query';

// Tipo para la informacion de un consorcio
export interface ConsorcioInfo {
  nombre: string;
  codigo: string;
  color: string;
  tramos: number;
  longitud_km: number;
}

// Tipo para la respuesta del endpoint
export interface CaminosColoreados {
  type: 'FeatureCollection';
  features: FeatureCollection['features'];
  metadata: {
    total_tramos: number;
    total_consorcios: number;
    total_km: number;
  };
  consorcios: ConsorcioInfo[];
}

export function useCaminosColoreados() {
  const query = useQuery({
    queryKey: queryKeys.caminosColoreados(),
    queryFn: async () => {
      const response = await fetch(`${API_URL}/api/v2/geo/gee/layers/caminos/coloreados`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return (await response.json()) as CaminosColoreados;
    },
    staleTime: 1000 * 60 * 10,
  });

  const caminos = useMemo<FeatureCollection | null>(() => {
    if (!query.data) return null;
    return { type: 'FeatureCollection', features: query.data.features };
  }, [query.data]);

  return {
    caminos,
    consorcios: query.data?.consorcios ?? [],
    metadata: query.data?.metadata ?? null,
    loading: query.isLoading,
    error: query.error ? `No se pudieron cargar los caminos: ${query.error.message}` : null,
    reload: query.refetch,
  };
}

export default useCaminosColoreados;
