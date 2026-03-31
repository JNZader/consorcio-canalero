import type { FeatureCollection } from 'geojson';
import { useQuery } from '@tanstack/react-query';
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

export function useCatastroMap() {
  const query = useQuery({
    queryKey: [...queryKeys.publicLayers(), 'catastro-rural-map'],
    queryFn: async () => {
      const response = await fetch('/data/catastro_rural_cu.geojson');
      if (!response.ok) {
        throw new Error(`Error fetching catastro map: ${response.status}`);
      }
      return (await response.json()) as FeatureCollection;
    },
    staleTime: Infinity,
  });

  return {
    catastroMap: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
