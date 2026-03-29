/**
 * Hook for loading DEM pipeline GeoLayer records from the backend.
 * Authenticated endpoint — requires login.
 * Returns layer metadata (id, name, type) for building tile overlay URLs.
 */

import { useCallback, useEffect, useState } from 'react';
import { API_URL, getAuthToken } from '../lib/api';
import { logger } from '../lib/logger';

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

interface UseGeoLayersResult {
  /** All raster layers available for tile overlay */
  layers: GeoLayerInfo[];
  /** Loading state */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** Reload layers */
  reload: () => Promise<void>;
}

export function useGeoLayers(): UseGeoLayersResult {
  const [layers, setLayers] = useState<GeoLayerInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const token = await getAuthToken();
      if (!token) {
        setLayers([]);
        setLoading(false);
        return;
      }

      const response = await fetch(
        `${API_URL}/api/v2/geo/layers?limit=100&fuente=dem_pipeline`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!response.ok) {
        throw new Error(`Error fetching geo layers: ${response.status}`);
      }

      const data = await response.json();
      const items: GeoLayerInfo[] = (data.items || []).filter(
        (l: GeoLayerInfo) => TILE_CAPABLE_TYPES.has(l.tipo)
      );

      // Dedup safety net: keep only the latest record per tipo+area_id
      // in case the backend returns duplicates from older runs.
      const seen = new Map<string, GeoLayerInfo>();
      for (const layer of items) {
        const key = `${layer.tipo}::${layer.area_id ?? ''}`;
        const existing = seen.get(key);
        if (!existing || layer.created_at > existing.created_at) {
          seen.set(key, layer);
        }
      }
      const dedupedItems = Array.from(seen.values());

      setLayers(dedupedItems);
    } catch (err) {
      logger.error('Error loading geo layers', err);
      setError('No se pudieron cargar las capas DEM');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { layers, loading, error, reload };
}

/**
 * Build the tile URL template for a given layer.
 * Uses the backend proxy endpoint so the frontend only needs one API URL.
 */
export function buildTileUrl(layerId: string, colormap?: string): string {
  const base = `${API_URL}/api/v2/geo/layers/${layerId}/tiles/{z}/{x}/{y}.png`;
  if (colormap) {
    return `${base}?colormap=${encodeURIComponent(colormap)}`;
  }
  return base;
}
