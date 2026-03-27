/**
 * Hook for loading basin polygons from PostGIS via /api/v2/geo/basins.
 * Public endpoint — no auth required.
 * Returns a GeoJSON FeatureCollection with simplified basin geometries.
 */

import type { FeatureCollection } from 'geojson';
import { useCallback, useEffect, useState } from 'react';
import { API_URL } from '../lib/api';
import { logger } from '../lib/logger';

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

interface UseBasinsResult {
  /** Basin polygons as GeoJSON FeatureCollection */
  basins: FeatureCollection | null;
  /** Loading state */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** Reload basins */
  reload: () => Promise<void>;
}

export function useBasins(options: UseBasinsOptions = {}): UseBasinsResult {
  const {
    bbox = null,
    tolerance = 0.001,
    limit = 500,
    cuenca = null,
    enabled = true,
  } = options;

  const [basins, setBasins] = useState<FeatureCollection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      params.set('tolerance', String(tolerance));
      params.set('limit', String(limit));

      if (bbox) {
        params.set('bbox', bbox.join(','));
      }
      if (cuenca) {
        params.set('cuenca', cuenca);
      }

      const response = await fetch(
        `${API_URL}/api/v2/geo/basins?${params.toString()}`
      );

      if (!response.ok) {
        throw new Error(`Error fetching basins: ${response.status}`);
      }

      const data = await response.json();
      setBasins(data as FeatureCollection);
    } catch (err) {
      logger.error('Error loading basins', err);
      setError('No se pudieron cargar las cuencas operativas');
    } finally {
      setLoading(false);
    }
  }, [bbox?.join(','), tolerance, limit, cuenca]);

  useEffect(() => {
    if (enabled) {
      reload();
    } else {
      setLoading(false);
    }
  }, [enabled, reload]);

  return { basins, loading, error, reload };
}
