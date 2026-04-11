import type { FeatureCollection } from 'geojson';

interface UseSuggestedZonesOptions {
  cuenca?: string | null;
  enabled?: boolean;
}

// The /basins/suggested-zones endpoint and its grouped-zoning algorithm were
// removed as part of the admin cleanup. This hook is kept as a stable no-op so
// the consuming MapaMapLibre/SuggestedZonesPanel UI keeps working without the
// feature.
export function useSuggestedZones(_options: UseSuggestedZonesOptions = {}) {
  return {
    suggestedZones: null as FeatureCollection | null,
    loading: false,
    error: null as string | null,
    reload: () => Promise.resolve(),
  };
}
