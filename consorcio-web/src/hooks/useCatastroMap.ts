import { useQuery } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { queryKeys } from '../lib/query';

export interface CatastroFeatureProperties {
  Nomenclatura?: string | null;
  Tipo_Parcela?: string | null;
  desig_oficial?: string | null;
  departamento?: string | null;
  pedania?: string | null;
  Superficie_Tierra_Rural?: number | null;
  Valuacion_Tierra_Rural?: number | null;
  Nro_Cuenta?: string | null;
}

export interface UseCatastroMapOptions {
  /**
   * Defer the (multi-MB) GeoJSON fetch until the user actually toggles the
   * catastro layer on. Default ``true`` keeps existing callers eager.
   */
  enabled?: boolean;
}

export function useCatastroMap(options: UseCatastroMapOptions = {}) {
  const query = useQuery({
    queryKey: [...queryKeys.publicLayers(), 'catastro-rural-map'],
    queryFn: async () => {
      const response = await fetch('/data/catastro_rural_cu.geojson');
      if (!response.ok) {
        throw new Error(`Error fetching catastro map: ${response.status}`);
      }
      return (await response.json()) as FeatureCollection;
    },
    staleTime: Number.POSITIVE_INFINITY,
    // Static bundled asset: a 404/error won't fix itself on retry, and the
    // KMZ export degrades gracefully without the slot. Overrides the global
    // `retry: 3` (exponential backoff) from lib/query.ts.
    retry: 0,
    enabled: options.enabled ?? true,
  });

  return {
    catastroMap: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    // `retry: 0` above means a failure is terminal for the session — an explicit
    // reload is the ONLY recovery path. Note `refetch()` ignores `enabled`, so
    // callers must not offer it before export intent latched (see
    // `layerHealth.ts` gates).
    reload: query.refetch,
  };
}
