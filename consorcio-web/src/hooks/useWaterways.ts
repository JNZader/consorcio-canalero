/**
 * Hook for loading waterway GeoJSON layers from static files.
 * No auth required — files served from public/waterways/.
 */

import type { FeatureCollection } from 'geojson';
import type { PathOptions } from 'leaflet';
import { useQuery } from '@tanstack/react-query';
import { API_URL } from '../lib/api';
import { logger } from '../lib/logger';
import { queryKeys } from '../lib/query';

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
  {
    id: 'canales_existentes',
    file: 'canales_existentes.geojson',
    nombre: 'Canales existentes',
    style: { color: '#0B3D91', weight: 4, opacity: 0.95, dashArray: '6 4' } satisfies PathOptions,
  },
] as const;

export function useWaterways() {
  const query = useQuery({
    queryKey: queryKeys.waterways(),
    queryFn: async () => {
      let incorporatedSuggestions: FeatureCollection | null = null;
      try {
        const response = await fetch(
          `${API_URL}/api/v2/public/sugerencias/canales-existentes`,
        );
        if (response.ok) {
          incorporatedSuggestions = (await response.json()) as FeatureCollection;
        }
      } catch (err) {
        logger.warn('Error loading incorporated suggestion channels', err);
      }

      const results = await Promise.all(
        WATERWAY_DEFS.map(async (def) => {
          try {
            const response = await fetch(`/waterways/${def.file}`);
            if (!response.ok) {
              logger.warn(`Waterway '${def.id}' not available: ${response.status}`);
              return null;
            }
            const data = (await response.json()) as FeatureCollection;
            const mergedData =
              def.id === 'canales_existentes' && incorporatedSuggestions
                ? ({
                    type: 'FeatureCollection',
                    features: [
                      ...(data.features ?? []),
                      ...(incorporatedSuggestions.features ?? []),
                    ],
                  } satisfies FeatureCollection)
                : data;
            return {
              id: def.id,
              nombre: def.nombre,
              data: mergedData,
              style: def.style as PathOptions,
            } satisfies WaterwayLayer;
          } catch (err) {
            logger.warn(`Error loading waterway '${def.id}'`, err);
            return null;
          }
        }),
      );

      const loaded = results.filter((r): r is NonNullable<typeof r> => r !== null) as WaterwayLayer[];
      if (loaded.length === 0) {
        throw new Error('No se pudieron cargar las capas hidrográficas');
      }
      return loaded;
    },
    staleTime: Infinity,
  });

  return {
    waterways: query.data ?? [],
    loading: query.isLoading,
    error: query.error?.message ?? null,
    reload: query.refetch,
  };
}
