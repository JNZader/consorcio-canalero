import type { FeatureCollection } from 'geojson';
import { useQuery } from '@tanstack/react-query';
import { API_URL } from '../lib/api';
import { queryKeys } from '../lib/query';

interface UseSuggestedZonesOptions {
  cuenca?: string | null;
  enabled?: boolean;
}

export function useSuggestedZones(options: UseSuggestedZonesOptions = {}) {
  const { cuenca = null, enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.suggestedZones({ cuenca }),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (cuenca) params.set('cuenca', cuenca);

      const response = await fetch(
        `${API_URL}/api/v2/geo/basins/suggested-zones?${params.toString()}`,
      );
      if (!response.ok) {
        throw new Error(`Error fetching suggested zones: ${response.status}`);
      }
      return (await response.json()) as FeatureCollection;
    },
    enabled,
    staleTime: 1000 * 60 * 5,
  });

  return {
    suggestedZones: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? 'No se pudieron cargar las zonas sugeridas' : null,
    reload: query.refetch,
  };
}
