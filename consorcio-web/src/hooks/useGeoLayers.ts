/**
 * Hook for loading DEM pipeline GeoLayer records from the backend.
 * Authenticated endpoint — requires login.
 * Returns layer metadata (id, name, type) for building tile overlay URLs.
 */

import { useQuery } from '@tanstack/react-query';
import { API_URL, getAuthToken } from '../lib/api';
import { queryKeys } from '../lib/query';
import { useAuthStore } from '../stores/authStore';

export interface GeoLayerInfo {
  id: string;
  nombre: string;
  tipo: string;
  fuente: string;
  formato: string;
  area_id: string | null;
  created_at: string;
}

/** Human-readable labels for layer types */
export const GEO_LAYER_LABELS: Record<string, string> = {
  dem_raw: 'Elevacion (DEM)',
  slope: 'Pendiente',
  aspect: 'Orientacion',
  twi: 'Indice Humedad (TWI)',
  hand: 'Altura sobre Drenaje (HAND)',
  flow_acc: 'Acumulacion de Flujo',
  flow_dir: 'Direccion de Flujo',
  terrain_class: 'Clasificacion Terreno',
  flood_risk: 'Riesgo de Inundacion',
  drainage_need: 'Necesidad de Drenaje',
  profile_curvature: 'Curvatura de Perfil',
  tpi: 'Posicion Topografica (TPI)',
};

/** Layer types that support raster tile visualization */
const TILE_CAPABLE_TYPES = new Set([
  'dem_raw',
  'slope',
  'aspect',
  'twi',
  'hand',
  'flow_acc',
  'flow_dir',
  'terrain_class',
  'flood_risk',
  'drainage_need',
]);

export function useGeoLayers() {
  const { loading: authLoading, initialized } = useAuthStore();

  const query = useQuery({
    queryKey: queryKeys.geoLayers(),
    queryFn: async () => {
      const token = await getAuthToken();
      const endpoint = token
        ? `${API_URL}/api/v2/geo/layers?limit=100&fuente=dem_pipeline`
        : `${API_URL}/api/v2/geo/layers/public?limit=100&fuente=dem_pipeline&tipo=dem_raw`;

      const response = await fetch(endpoint, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        throw new Error(`Error fetching geo layers: ${response.status}`);
      }

      const data = await response.json();
      const items: GeoLayerInfo[] = (data.items || []).filter(
        (l: GeoLayerInfo) => TILE_CAPABLE_TYPES.has(l.tipo),
      );

      const seen = new Map<string, GeoLayerInfo>();
      for (const layer of items) {
        const key = `${layer.tipo}::${layer.area_id ?? ''}`;
        const existing = seen.get(key);
        if (!existing || layer.created_at > existing.created_at) {
          seen.set(key, layer);
        }
      }
      return Array.from(seen.values());
    },
    enabled: initialized && !authLoading,
    staleTime: 1000 * 60 * 5,
  });

  return {
    layers: query.data ?? [],
    loading: authLoading || query.isLoading,
    error: query.error ? 'No se pudieron cargar las capas DEM' : null,
    reload: query.refetch,
  };
}

/**
 * Build the tile URL template for a given layer.
 * Uses the backend proxy endpoint so the frontend only needs one API URL.
 */
export function buildTileUrl(
  layerId: string,
  options?: { colormap?: string; hideClasses?: number[]; hideRanges?: number[] },
): string {
  const base = `${API_URL}/api/v2/geo/layers/${layerId}/tiles/{z}/{x}/{y}.png`;
  const params = new URLSearchParams();
  if (options?.colormap) {
    params.set('colormap', options.colormap);
  }
  if (options?.hideClasses && options.hideClasses.length > 0) {
    params.set('hide_classes', options.hideClasses.join(','));
  }
  if (options?.hideRanges && options.hideRanges.length > 0) {
    params.set('hide_ranges', options.hideRanges.join(','));
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}
