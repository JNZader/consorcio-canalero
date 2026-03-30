/**
 * Hook for loading waterway GeoJSON layers from static files.
 * No auth required — files served from public/waterways/.
 */

import type { FeatureCollection } from 'geojson';
import type { PathOptions } from 'leaflet';
import { useCallback, useEffect, useState } from 'react';
import { logger } from '../lib/logger';

export interface WaterwayLayer {
  id: string;
  nombre: string;
  data: FeatureCollection;
  style: PathOptions;
}

/** Waterway definitions with display name and styling */
const WATERWAY_DEFS = [
  {
    id: 'rio_tercero',
    file: 'rio_tercero.geojson',
    nombre: 'Río Tercero',
    style: { color: '#1565C0', weight: 4, opacity: 0.9 } satisfies PathOptions,
  },
  {
    id: 'canal_desviador',
    file: 'canal_desviador.geojson',
    nombre: 'Canal Desviador a Río Tercero',
    style: { color: '#00897B', weight: 3, opacity: 0.9 } satisfies PathOptions,
  },
  {
    id: 'canal_litin_tortugas',
    file: 'canal_litin_tortugas.geojson',
    nombre: 'Canal Litín Tortugas',
    style: { color: '#00ACC1', weight: 3, opacity: 0.9 } satisfies PathOptions,
  },
  {
    id: 'arroyo_algodon',
    file: 'arroyo_algodon.geojson',
    nombre: 'Arroyo Algodón',
    style: { color: '#42A5F5', weight: 2, opacity: 0.85 } satisfies PathOptions,
  },
  {
    id: 'arroyo_las_mojarras',
    file: 'arroyo_las_mojarras.geojson',
    nombre: 'A. Las Saladas / de las Mojarras',
    style: { color: '#64B5F6', weight: 2, opacity: 0.85 } satisfies PathOptions,
  },
] as const;

interface UseWaterwaysResult {
  waterways: WaterwayLayer[];
  loading: boolean;
  error: string | null;
}

export function useWaterways(): UseWaterwaysResult {
  const [waterways, setWaterways] = useState<WaterwayLayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const results = await Promise.all(
        WATERWAY_DEFS.map(async (def) => {
          try {
            const response = await fetch(`/waterways/${def.file}`);
            if (!response.ok) {
              logger.warn(`Waterway '${def.id}' not available: ${response.status}`);
              return null;
            }
            const data = (await response.json()) as FeatureCollection;
            return {
              id: def.id,
              nombre: def.nombre,
              data,
              style: def.style as PathOptions,
            } satisfies WaterwayLayer;
          } catch (err) {
            logger.warn(`Error loading waterway '${def.id}'`, err);
            return null;
          }
        }),
      );

      const loaded = results.filter((r): r is NonNullable<typeof r> => r !== null) as WaterwayLayer[];
      setWaterways(loaded);

      if (loaded.length === 0) {
        setError('No se pudieron cargar las capas hidrográficas');
      }
    } catch (err) {
      logger.error('Error loading waterways', err);
      setError('Error cargando hidrografía');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { waterways, loading, error };
}
