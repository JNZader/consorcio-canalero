/**
 * Hook para cargar la proyeccion publica fija de caminos coloreados.
 * Cada camino tiene un color asignado segun su consorcio caminero.
 */

import { useQuery } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { useMemo } from 'react';
import { API_URL } from '../lib/api';
import { queryKeys } from '../lib/query';

export interface ConsorcioInfo {
  nombre: string;
  codigo: string;
  color: string;
  tramos: number;
  longitud_km: number;
}

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

interface PublicCaminosProjectionResponse {
  status: 'available' | 'unavailable';
  projection: 'caminos';
  data: CaminosColoreados | null;
  reason: 'temporarily_unavailable' | null;
}

const PUBLIC_CAMINOS_URL = `${API_URL}/api/v2/public/map/gee/caminos`;

export function useCaminosColoreados() {
  const query = useQuery({
    queryKey: queryKeys.caminosColoreados(),
    queryFn: async () => {
      const response = await fetch(PUBLIC_CAMINOS_URL);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const envelope = (await response.json()) as PublicCaminosProjectionResponse;
      if (envelope.status !== 'available' || !envelope.data) {
        throw new Error(`Proyeccion no disponible: ${envelope.reason ?? 'unknown'}`);
      }
      return envelope.data;
    },
    staleTime: 1000 * 60 * 10,
    // Public geo layer that degrades gracefully: the map renders without it and
    // the failure surfaces as an inline row + "Reintentar" in the layer panel
    // (`layerHealth.ts` → `LayerControlsPanel`), wired to the `reload` below.
    retry: 1,
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
