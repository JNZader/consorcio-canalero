import { useQuery } from '@tanstack/react-query';
import { API_URL, getAuthToken } from '../lib/api';
import { queryKeys } from '../lib/query';
import { useAuthStore } from '../stores/authStore';

export interface CompositeStatItem {
  id: string;
  zona_id: string;
  zona_nombre?: string | null;
  cuenca?: string | null;
  superficie_ha?: number | null;
  tipo: 'flood_risk' | 'drainage_need';
  mean_score: number;
  max_score: number;
  p90_score: number;
  area_high_risk_ha: number;
  fecha_calculo: string;
}

export interface CompositeComparisonItem {
  zona_id: string;
  zona_nombre?: string | null;
  cuenca?: string | null;
  superficie_ha?: number | null;
  tipo: 'flood_risk' | 'drainage_need';
  current_mean_score: number;
  baseline_mean_score: number;
  delta_mean_score: number;
  current_area_high_risk_ha: number;
  baseline_area_high_risk_ha: number;
  delta_area_high_risk_ha: number;
}

export function useCompositeStats(
  areaId: string,
  tipo: 'flood_risk' | 'drainage_need',
) {
  const { loading: authLoading, initialized, user } = useAuthStore();
  const isAuthenticated = initialized && !authLoading && !!user;

  const query = useQuery({
    queryKey: queryKeys.compositeStats(areaId, tipo),
    enabled: isAuthenticated,
    staleTime: 1000 * 60,
    queryFn: async () => {
      const token = await getAuthToken();
      const response = await fetch(
        `${API_URL}/api/v2/geo/intelligence/composite/stats/${areaId}?tipo=${tipo}`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      );
      if (!response.ok) {
        throw new Error(`Error fetching composite stats: ${response.status}`);
      }
      const data = await response.json();
      return (data.items ?? []) as CompositeStatItem[];
    },
  });

  return {
    items: query.data ?? [],
    loading: authLoading || query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    reload: query.refetch,
  };
}

export function useCompositeComparison(
  areaId: string,
  tipo: 'flood_risk' | 'drainage_need' = 'drainage_need',
) {
  const { loading: authLoading, initialized, user } = useAuthStore();
  const isAuthenticated = initialized && !authLoading && !!user;

  const query = useQuery({
    queryKey: queryKeys.compositeComparison(areaId, tipo),
    enabled: isAuthenticated,
    staleTime: 1000 * 60,
    queryFn: async () => {
      const token = await getAuthToken();
      const response = await fetch(
        `${API_URL}/api/v2/geo/intelligence/composite/compare/${areaId}?tipo=${tipo}`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      );
      if (!response.ok) {
        throw new Error(`Error fetching composite comparison: ${response.status}`);
      }
      const data = await response.json();
      return (data.items ?? []) as CompositeComparisonItem[];
    },
  });

  return {
    items: query.data ?? [],
    loading: authLoading || query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    reload: query.refetch,
  };
}
