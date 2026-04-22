import { useQuery } from '@tanstack/react-query';
import type { FeatureCollection } from 'geojson';
import { queryKeys } from '../lib/query';

export interface SoilFeatureProperties {
  simbolo?: string | null;
  ip?: number | null;
  cap?: string | null;
}

export const SOIL_CAPABILITY_COLORS: Record<string, string> = {
  I: '#1b5e20',
  II: '#2e7d32',
  III: '#689f38',
  IV: '#c0ca33',
  V: '#f9a825',
  VI: '#fb8c00',
  VII: '#ef6c00',
  VIII: '#c62828',
};

/**
 * Spanish labels for soil capability classes (IDECOR soil-capability conventions).
 * Keys match those of SOIL_CAPABILITY_COLORS and are ordered I → VIII.
 */
export const SOIL_CAPABILITY_LABELS: Record<string, string> = {
  I: 'Excelente',
  II: 'Muy Buena',
  III: 'Buena',
  IV: 'Moderada',
  V: 'Baja',
  VI: 'Muy Baja',
  VII: 'Sumamente Baja',
  VIII: 'No Arable',
};

/** Ordered list of soil capability keys (I → VIII) for rendering legends. */
export const SOIL_CAPABILITY_ORDER: readonly string[] = [
  'I',
  'II',
  'III',
  'IV',
  'V',
  'VI',
  'VII',
  'VIII',
];

export function getSoilColor(capability?: string | null): string {
  if (!capability) return '#8d6e63';
  const normalized = capability.trim().toUpperCase();
  const match = normalized.match(/^(VIII|VII|VI|IV|III|II|I)/);
  return SOIL_CAPABILITY_COLORS[match?.[1] ?? ''] ?? '#8d6e63';
}

export function useSoilMap() {
  const query = useQuery({
    queryKey: [...queryKeys.publicLayers(), 'soil-map'],
    queryFn: async () => {
      const response = await fetch('/data/suelos_cu.geojson');
      if (!response.ok) {
        throw new Error(`Error fetching soil map: ${response.status}`);
      }
      return (await response.json()) as FeatureCollection;
    },
    staleTime: Number.POSITIVE_INFINITY,
  });

  return {
    soilMap: query.data ?? null,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
