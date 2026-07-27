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
  /**
   * true cuando la capa es de un ESCENARIO (relevados + propuestas quemadas),
   * no del drenaje operativo. Derivado del prefijo del nombre en el backend
   * (`escenario_flow_acc_*`): la capa comparte `tipo` con la operativa
   * (ambas FLOW_ACC), asi que el tipo NO alcanza para distinguirlas.
   */
  esEscenario: boolean;
  /** Etiqueta lista para el selector, ya con el sufijo de escenario si aplica. */
  label: string;
}

/** El backend nombra las capas de escenario con este prefijo. */
const ESCENARIO_PREFIX = 'escenario_';

/**
 * Deriva `esEscenario` y `label` de una capa cruda del backend.
 *
 * El backend distingue el escenario por el PREFIJO del nombre
 * (`escenario_flow_acc_zona_principal`), no por el tipo — la capa de escenario
 * comparte tipo con la operativa. Toda la logica de "esto es simulacion" cuelga
 * de ese prefijo, en un solo lugar.
 */
export function enrichLayer(layer: GeoLayerInfo): GeoLayerInfo {
  const esEscenario = layer.nombre.startsWith(ESCENARIO_PREFIX);
  const base = GEO_LAYER_LABELS[layer.tipo] ?? layer.tipo;
  return {
    ...layer,
    esEscenario,
    // El sufijo hace inconfundible que es una simulacion, para que nadie tome
    // el drenaje propuesto por el existente.
    label: esEscenario ? `${base} (escenario)` : base,
  };
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

const isTruthyFlag = (value: string | undefined): boolean =>
  ['1', 'true', 'yes', 'on'].includes((value ?? '').trim().toLowerCase());

// Review/evaluation flag only; it is not a production publication policy.
// Requires backend PUBLIC_MAP_LAYER_EVAL=true to return more than dem_raw.
const PUBLIC_MAP_LAYER_EVAL = isTruthyFlag(import.meta.env.VITE_PUBLIC_MAP_LAYER_EVAL);

export function useGeoLayers() {
  const { loading: authLoading, initialized } = useAuthStore();

  const query = useQuery({
    queryKey: queryKeys.geoLayers(),
    queryFn: async () => {
      const token = await getAuthToken();
      const publicEndpoint = PUBLIC_MAP_LAYER_EVAL
        ? `${API_URL}/api/v2/geo/layers/public?limit=100&fuente=dem_pipeline`
        : `${API_URL}/api/v2/geo/layers/public?limit=100&fuente=dem_pipeline&tipo=dem_raw`;
      const endpoint = token
        ? `${API_URL}/api/v2/geo/layers?limit=100&fuente=dem_pipeline`
        : publicEndpoint;

      const response = await fetch(endpoint, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        throw new Error(`Error fetching geo layers: ${response.status}`);
      }

      const data = await response.json();
      const items: GeoLayerInfo[] = (data.items ?? [])
        .filter((l: GeoLayerInfo) => TILE_CAPABLE_TYPES.has(l.tipo))
        .map((l: GeoLayerInfo) => enrichLayer(l));

      // Dedup por (esEscenario, tipo, area): sin el flag de escenario, una
      // capa `escenario_flow_acc` (tipo FLOW_ACC) pisaria a la operativa del
      // mismo tipo y area, y solo quedaria una en el selector. Con el flag,
      // conviven la operativa y la de escenario.
      const seen = new Map<string, GeoLayerInfo>();
      for (const layer of items) {
        const key = `${layer.esEscenario ? 'esc' : 'op'}::${layer.tipo}::${layer.area_id ?? ''}`;
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
  options?: { colormap?: string; hideClasses?: number[]; hideRanges?: number[] }
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
