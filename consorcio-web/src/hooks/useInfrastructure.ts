import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { apiFetch, getAuthToken, unwrapItems } from '../lib/api';
import { queryKeys } from '../lib/query';

export interface InfrastructureAsset {
  id: string;
  nombre: string;
  tipo: 'canal' | 'alcantarilla' | 'puente' | 'otro';
  descripcion: string;
  latitud: number;
  longitud: number;
  cuenca: string;
  estado_actual: 'bueno' | 'regular' | 'malo' | 'critico';
  ultima_inspeccion: string;
}

export function useInfrastructure() {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: queryKeys.infrastructure(),
    queryFn: async () => {
      const assetsData = await apiFetch('/infraestructura/assets')
        .then((res) => unwrapItems<InfrastructureAsset>(res))
        .catch(() => [] as InfrastructureAsset[]);

      let intersectionsData: FeatureCollection | null = null;
      const token = await getAuthToken();
      if (token) {
        try {
          const data = await apiFetch<FeatureCollection>('/geo/intelligence/conflictos');
          if (data && data.type === 'FeatureCollection') {
            intersectionsData = data;
          }
        } catch {
          // Silently skip — user may lack permissions
        }
      }

      return { assets: assetsData, intersections: intersectionsData };
    },
    staleTime: 1000 * 60 * 5,
  });

  const createMutation = useMutation({
    mutationFn: (asset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'>) =>
      apiFetch<InfrastructureAsset>('/infraestructura/assets', {
        method: 'POST',
        body: JSON.stringify(asset),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.infrastructure() });
    },
  });

  return {
    assets: query.data?.assets ?? [],
    intersections: query.data?.intersections ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    refresh: query.refetch,
    createAsset: createMutation.mutateAsync,
  };
}
