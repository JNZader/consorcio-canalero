import { useQuery } from '@tanstack/react-query';

import {
  HAZARD_BASIN_FILTER_ALL,
  type HazardBasinMembership,
} from '../components/map2d/hazardBasinFilter';
import { apiFetch } from '../lib/api/core';
import { useAuthStore } from '../stores/authStore';

interface HazardBasinMembershipWireResponse {
  basin_id: string;
  feature_id_property: 'nomenclatura';
  intersecting_feature_ids: string[];
}

function mapMembership(response: HazardBasinMembershipWireResponse): HazardBasinMembership {
  return {
    featureIdProperty: response.feature_id_property,
    intersectingFeatureIds: response.intersecting_feature_ids,
  };
}

export function useHazardBasinMembership(basinId: string | null | typeof HAZARD_BASIN_FILTER_ALL) {
  const userId = useAuthStore((state) => state.user?.id ?? null);
  const authReady = useAuthStore((state) => state.initialized && !state.loading);
  const hasSelectedBasin = basinId !== null && basinId !== HAZARD_BASIN_FILTER_ALL;
  const enabled = authReady && userId !== null && hasSelectedBasin;
  const query = useQuery({
    queryKey: ['hazard-basin-membership', userId, basinId],
    queryFn: () =>
      apiFetch<HazardBasinMembershipWireResponse>(
        `/geo/basins/${encodeURIComponent(basinId!)}/catastro-membership`
      ),
    enabled,
    retry: 0,
    select: mapMembership,
  });
  const membership =
    query.isLoading || query.isFetching || query.isError ? null : (query.data ?? null);

  return {
    membership,
    isLoading: query.isLoading,
    isSuccess: query.isSuccess,
    isError: query.isError,
    error: query.error,
  };
}
