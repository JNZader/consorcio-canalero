/**
 * Hook for consuming Martin vector tile sources in Leaflet maps.
 *
 * Martin serves MVT (Mapbox Vector Tiles) from PostGIS views.
 * This hook provides utilities to add vector tile layers to a Leaflet map
 * using the maplibre-gl-leaflet bridge or protomaps-leaflet.
 *
 * For now, we use a simpler approach: fetch GeoJSON from Martin's
 * built-in GeoJSON endpoint for lower zoom levels, and switch to
 * vector tiles at higher zooms. This avoids adding a new dependency
 * while still getting the benefit of Martin serving data directly
 * from PostGIS.
 */

import { useQuery } from '@tanstack/react-query';

const MARTIN_URL = import.meta.env.VITE_MARTIN_URL || 'http://localhost:3000';

/** Available vector tile sources served by Martin */
export const VT_SOURCES = {
  zonas_operativas: {
    id: 'vt_zonas_operativas',
    label: 'Zonas Operativas',
    tileUrl: `${MARTIN_URL}/vt_zonas_operativas/{z}/{x}/{y}`,
    type: 'polygon' as const,
    color: '#3b82f6',
    fillOpacity: 0.15,
  },
  puntos_conflicto: {
    id: 'vt_puntos_conflicto',
    label: 'Puntos de Conflicto',
    tileUrl: `${MARTIN_URL}/vt_puntos_conflicto/{z}/{x}/{y}`,
    type: 'point' as const,
    color: '#ef4444',
    fillOpacity: 0.8,
  },
  denuncias: {
    id: 'vt_denuncias',
    label: 'Denuncias',
    tileUrl: `${MARTIN_URL}/vt_denuncias/{z}/{x}/{y}`,
    type: 'point' as const,
    color: '#f59e0b',
    fillOpacity: 0.8,
  },
  assets: {
    id: 'vt_assets',
    label: 'Infraestructura',
    tileUrl: `${MARTIN_URL}/vt_assets/{z}/{x}/{y}`,
    type: 'point' as const,
    color: '#10b981',
    fillOpacity: 0.8,
  },
} as const;

export type VTSourceKey = keyof typeof VT_SOURCES;

/**
 * Fetch GeoJSON from Martin for a specific source.
 * Martin supports GeoJSON output at: GET /{source}/{z}/{x}/{y}
 * For overview/low-zoom usage, we can also query the catalog.
 */
export function useVectorTileCatalog() {
  return useQuery({
    queryKey: ['martin', 'catalog'],
    queryFn: async () => {
      const res = await fetch(`${MARTIN_URL}/catalog`);
      if (!res.ok) throw new Error('Martin catalog unavailable');
      return res.json();
    },
    staleTime: 60_000,
    retry: 2,
  });
}

/**
 * Build the tile URL template for a Martin source.
 * Use this with Leaflet's L.vectorGrid.protobuf() or similar.
 */
export function getMartinTileUrl(sourceId: string): string {
  return `${MARTIN_URL}/${sourceId}/{z}/{x}/{y}`;
}

/**
 * Get all available source IDs for Martin.
 */
export function getVTSourceIds(): string[] {
  return Object.values(VT_SOURCES).map((s) => s.id);
}

/** Style mapping for conflict severity */
export const SEVERIDAD_COLORS: Record<string, string> = {
  baja: '#22c55e',
  media: '#f59e0b',
  alta: '#ef4444',
};

/** Style mapping for denuncia estado */
export const ESTADO_COLORS: Record<string, string> = {
  pendiente: '#f59e0b',
  en_revision: '#3b82f6',
  resuelto: '#22c55e',
  descartado: '#6b7280',
};

/** Style mapping for asset estado */
export const ASSET_ESTADO_COLORS: Record<string, string> = {
  bueno: '#22c55e',
  regular: '#f59e0b',
  malo: '#ef4444',
  critico: '#991b1b',
};
