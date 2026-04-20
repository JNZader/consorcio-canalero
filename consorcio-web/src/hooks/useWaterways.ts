/**
 * Hook for loading waterway GeoJSON layers from static files.
 * No auth required — files served from public/waterways/.
 *
 * Batch 5 (2026-04-20): legacy `canales_existentes` layer retired — the 43
 * canals (23 relevados + 20 propuestas) now live in the Pilar Azul slice
 * (`useCanales`). Accordingly, this hook no longer fetches the old geojson
 * file, and the `/api/v2/public/sugerencias/canales-existentes` merge was
 * removed. The 5 remaining waterways (Río Tercero + arroyos + canal
 * desviador + canal Litín-Tortugas) continue to load from this hook.
 */

import type { FeatureCollection } from 'geojson';
import { useQuery } from '@tanstack/react-query';
import { logger } from '../lib/logger';
import { queryKeys } from '../lib/query';

/** Paint properties for a waterway layer — used by both MapLibre GL and Leaflet renderers. */
export interface WaterwayStyle {
  color: string;
  weight: number;
  opacity: number;
  dashArray?: string;
}

export interface WaterwayLayer {
  id: string;
  nombre: string;
  data: FeatureCollection;
  style: WaterwayStyle;
}

/** Waterway definitions with display name and styling */
export const WATERWAY_DEFS = [
  {
    id: 'rio_tercero',
    file: 'rio_tercero.geojson',
    nombre: 'Río Tercero',
    style: { color: '#1565C0', weight: 4, opacity: 0.9 } satisfies WaterwayStyle,
  },
  {
    id: 'canal_desviador',
    file: 'canal_desviador.geojson',
    nombre: 'Canal Desviador a Río Tercero',
    style: { color: '#00897B', weight: 3, opacity: 0.9 } satisfies WaterwayStyle,
  },
  {
    id: 'canal_litin_tortugas',
    file: 'canal_litin_tortugas.geojson',
    nombre: 'Canal Litín Tortugas',
    style: { color: '#00ACC1', weight: 3, opacity: 0.9 } satisfies WaterwayStyle,
  },
  {
    id: 'arroyo_algodon',
    file: 'arroyo_algodon.geojson',
    nombre: 'Arroyo Algodón',
    style: { color: '#42A5F5', weight: 2, opacity: 0.85 } satisfies WaterwayStyle,
  },
  {
    id: 'arroyo_las_mojarras',
    file: 'arroyo_las_mojarras.geojson',
    nombre: 'A. Las Saladas / de las Mojarras',
    style: { color: '#64B5F6', weight: 2, opacity: 0.85 } satisfies WaterwayStyle,
  },
] as const;

export function useWaterways() {
  const query = useQuery({
    queryKey: queryKeys.waterways(),
    queryFn: async () => {
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
              style: def.style as WaterwayStyle,
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
    staleTime: Number.POSITIVE_INFINITY,
  });

  return {
    waterways: query.data ?? [],
    loading: query.isLoading,
    error: query.error?.message ?? null,
    reload: query.refetch,
  };
}
