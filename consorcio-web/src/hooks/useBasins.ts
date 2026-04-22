/**
 * Hook for loading basin polygons from PostGIS via /api/v2/geo/basins.
 * Public endpoint — no auth required.
 * Returns a GeoJSON FeatureCollection with simplified basin geometries.
 */

import { useQuery } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { API_URL } from '../lib/api';
import { queryKeys } from '../lib/query';

interface UseBasinsOptions {
  /** Bounding box filter: [minx, miny, maxx, maxy] */
  bbox?: [number, number, number, number] | null;
  /** ST_Simplify tolerance in degrees (default 0.001 ~ 100m) */
  tolerance?: number;
  /** Max features (default 500) */
  limit?: number;
  /** Filter by cuenca name */
  cuenca?: string | null;
  /** Whether to fetch immediately (default true) */
  enabled?: boolean;
}

export function useBasins(options: UseBasinsOptions = {}) {
  const { bbox = null, tolerance = 0.001, limit = 500, cuenca = null, enabled = true } = options;

  const bboxKey = bbox?.join(',') ?? null;

  const query = useQuery({
    queryKey: queryKeys.basins({ tolerance, limit, cuenca, bbox: bboxKey }),
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set('tolerance', String(tolerance));
      params.set('limit', String(limit));

      if (bbox) {
        params.set('bbox', bbox.join(','));
      }
      if (cuenca) {
        params.set('cuenca', cuenca);
      }
      params.set('adjusted', 'true');

      const response = await fetch(`${API_URL}/api/v2/geo/basins?${params.toString()}`);

      if (!response.ok) {
        throw new Error(`Error fetching basins: ${response.status}`);
      }

      return (await response.json()) as FeatureCollection;
    },
    enabled,
    staleTime: 1000 * 60 * 5,
  });

  return {
    basins: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? 'No se pudieron cargar las cuencas operativas' : null,
    reload: query.refetch,
  };
}
