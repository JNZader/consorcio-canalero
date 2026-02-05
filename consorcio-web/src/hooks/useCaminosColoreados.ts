/**
 * Hook para cargar caminos con colores por consorcio caminero.
 * Cada camino tiene un color asignado segun su consorcio para visualizacion diferenciada.
 */

import type { FeatureCollection } from 'geojson';
import { useCallback, useEffect, useState } from 'react';
import { API_URL } from '../lib/api';
import { logger } from '../lib/logger';

// Tipo para la informacion de un consorcio
export interface ConsorcioInfo {
  nombre: string;
  codigo: string;
  color: string;
  tramos: number;
  longitud_km: number;
}

// Tipo para la respuesta del endpoint
export interface CaminosColoreados {
  type: 'FeatureCollection';
  features: FeatureCollection['features'];
  metadata: {
    total_tramos: number;
    total_consorcios: number;
    total_km: number;
  };
  consorcios: ConsorcioInfo[];
}

interface UseCaminosColoreados {
  /** GeoJSON de caminos con propiedad 'color' */
  caminos: FeatureCollection | null;
  /** Lista de consorcios con colores y estadisticas */
  consorcios: ConsorcioInfo[];
  /** Metadata con totales */
  metadata: CaminosColoreados['metadata'] | null;
  /** Estado de carga */
  loading: boolean;
  /** Error si hubo alguno */
  error: string | null;
  /** Recargar datos */
  reload: () => Promise<void>;
}

/**
 * Hook para cargar la red vial con colores diferenciados por consorcio caminero.
 *
 * @example
 * ```tsx
 * const { caminos, consorcios, loading } = useCaminosColoreados();
 *
 * // Usar en GeoJSON con style dinamico
 * <GeoJSON
 *   data={caminos}
 *   style={(feature) => ({
 *     color: feature?.properties?.color || '#888',
 *     weight: 2,
 *   })}
 * />
 * ```
 */
export function useCaminosColoreados(): UseCaminosColoreados {
  const [caminos, setCaminos] = useState<FeatureCollection | null>(null);
  const [consorcios, setConsorcios] = useState<ConsorcioInfo[]>([]);
  const [metadata, setMetadata] = useState<CaminosColoreados['metadata'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/gee/layers/caminos/coloreados`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data: CaminosColoreados = await response.json();

      // Extraer el FeatureCollection
      const featureCollection: FeatureCollection = {
        type: 'FeatureCollection',
        features: data.features,
      };

      setCaminos(featureCollection);
      setConsorcios(data.consorcios);
      setMetadata(data.metadata);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Error desconocido';
      setError(`No se pudieron cargar los caminos: ${message}`);
      logger.error('Error loading colored roads', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return {
    caminos,
    consorcios,
    metadata,
    loading,
    error,
    reload,
  };
}

export default useCaminosColoreados;
