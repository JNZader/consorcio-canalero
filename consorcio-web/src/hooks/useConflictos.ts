import { useQuery } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';

import { apiFetch, getAuthToken } from '../lib/api';
import { queryKeys } from '../lib/query';

/**
 * Fetches the geo intelligence "conflictos" FeatureCollection — points where
 * canales cross roads (canal/road intersections) computed by the backend in
 * `/api/v2/geo/intelligence/conflictos`. The endpoint is auth-only; we skip
 * the request entirely when there is no token to avoid a noisy 401 in the
 * console for anonymous viewers of the public map.
 *
 * Until 2026-04-28 this fetch lived inside `useInfrastructure`, alongside
 * the asset-management feature that was retired in the same cleanup pass.
 * The map's "Puntos conflicto" toggle still wants the layer, so the fetch
 * was extracted to its own hook with no coupling to the deleted domain.
 */
export function useConflictos() {
  const query = useQuery({
    queryKey: queryKeys.conflictos(),
    queryFn: async () => {
      const token = await getAuthToken();
      if (!token) return null;
      try {
        const data = await apiFetch<FeatureCollection>('/geo/intelligence/conflictos');
        return data && data.type === 'FeatureCollection' ? data : null;
      } catch {
        return null;
      }
    },
    staleTime: 1000 * 60 * 5,
  });

  return {
    conflictos: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
