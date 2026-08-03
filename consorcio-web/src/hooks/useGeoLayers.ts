/**
 * Hook for loading DEM pipeline GeoLayer records from the backend.
 * Authenticated endpoint — requires login.
 * Returns layer metadata (id, name, type) for building tile overlay URLs.
 */

import { useQuery } from '@tanstack/react-query';
import { API_URL, getAuthToken } from '../lib/api';
import { queryKeys } from '../lib/query';
import { useAuthStore } from '../stores/authStore';

/**
 * Variante de drenaje de una capa hidrologica:
 *   - `natural`   : sin canales (referencia)
 *   - `relevado`  : con la red de canales actual (operativo, el default)
 *   - `escenario` : relevados + propuestas quemadas (simulacion)
 *
 * HAND, TWI, flow_acc y flow_dir se generan en las tres variantes, que
 * comparten `tipo` y area — se distinguen SOLO por el prefijo del nombre.
 */
export type VarianteCapa = 'natural' | 'relevado' | 'escenario';

export interface GeoLayerInfo {
  id: string;
  nombre: string;
  tipo: string;
  fuente: string;
  formato: string;
  area_id: string | null;
  created_at: string;
  /** Variante derivada del prefijo del nombre. `relevado` es el default. */
  variante: VarianteCapa;
  /** Etiqueta lista para el selector, ya con el sufijo de variante si aplica. */
  label: string;
}

/** Prefijos de nombre con que el backend marca cada variante NO-operativa. */
const PREFIJO_VARIANTE: ReadonlyArray<readonly [string, VarianteCapa]> = [
  ['natural_', 'natural'],
  ['escenario_', 'escenario'],
];

/** Sufijo de etiqueta por variante. `relevado` no lleva sufijo: es la realidad actual. */
const SUFIJO_VARIANTE: Record<VarianteCapa, string> = {
  natural: ' (natural)',
  relevado: '',
  escenario: ' (escenario)',
};

/**
 * Deriva `variante` y `label` de una capa cruda del backend.
 *
 * La distincion cuelga del PREFIJO del nombre, no del tipo: las tres variantes
 * comparten tipo (p. ej. FLOW_ACC). Toda la logica vive aca, en un solo lugar.
 */
export function enrichLayer(layer: GeoLayerInfo): GeoLayerInfo {
  const encontrado = PREFIJO_VARIANTE.find(([prefijo]) => layer.nombre.startsWith(prefijo));
  const variante: VarianteCapa = encontrado ? encontrado[1] : 'relevado';
  const base = GEO_LAYER_LABELS[layer.tipo] ?? layer.tipo;
  return {
    ...layer,
    variante,
    // El sufijo hace inconfundible que la capa es natural o simulacion, para
    // que nadie tome el drenaje propuesto (o el sin-canales) por el existente.
    label: `${base}${SUFIJO_VARIANTE[variante]}`,
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

export function useGeoLayers() {
  const { loading: authLoading, initialized } = useAuthStore();
  /** ONE definition of the auth gate — consumed by `enabled` and re-exported. */
  const authGateOpen = initialized && !authLoading;

  const query = useQuery({
    queryKey: queryKeys.geoLayers(),
    queryFn: async () => {
      const token = await getAuthToken();
      // Anonymous visitors hit the public catalog WITHOUT a `tipo` filter:
      // the backend is the single authority over which layer types are
      // published (see PUBLIC_PRODUCTION_LAYER_TYPES in router_core.py).
      const endpoint = token
        ? `${API_URL}/api/v2/geo/layers?limit=100&fuente=dem_pipeline`
        : `${API_URL}/api/v2/geo/layers/public?limit=100&fuente=dem_pipeline`;

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

      const seen = new Map<string, GeoLayerInfo>();
      for (const layer of items) {
        // Dedup por (variante, tipo, area): las tres variantes comparten tipo
        // y area, asi que sin la variante en la clave se pisarian entre si y
        // solo sobreviviria una en el selector.
        const key = `${layer.variante}::${layer.tipo}::${layer.area_id ?? ''}`;
        const existing = seen.get(key);
        if (!existing || layer.created_at > existing.created_at) {
          seen.set(key, layer);
        }
      }
      return Array.from(seen.values());
    },
    enabled: authGateOpen,
    staleTime: 1000 * 60 * 5,
  });

  return {
    layers: query.data ?? [],
    loading: authLoading || query.isLoading,
    error: query.error ? 'No se pudieron cargar las capas DEM' : null,
    reload: query.refetch,
    /**
     * Whether the query's auth gate is OPEN. Exposed so consumers report this
     * family's health from ONE source of truth instead of re-deriving the gate
     * from the auth store (see `map2d/layerHealth.ts`).
     */
    enabled: authGateOpen,
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
