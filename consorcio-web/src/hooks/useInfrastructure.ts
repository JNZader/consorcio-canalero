import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../lib/api';
import type { FeatureCollection } from 'geojson';

export interface InfrastructureAsset {
  id: string;
  nombre: string;
  tipo: 'canal' | 'alcantarilla' | 'puente' | 'otro';
  descripcion: string;
  latitud: number;
  longitud: number;
  cuenca: string;
  estado_actual: 'bueno' | 'regular' | 'malo' | 'critico';
  ultima_inspeccion: string;
}

export function useInfrastructure() {
  const [assets, setAssets] = useState<InfrastructureAsset[]>([]);
  const [intersections, setIntersections] = useState<FeatureCollection | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchInfrastructure = useCallback(async () => {
    setLoading(true);
    try {
      const [assetsData, intersectionsData] = await Promise.all([
        apiFetch<InfrastructureAsset[]>('/infrastructure/assets'),
        apiFetch<FeatureCollection>('/infrastructure/potential-intersections')
      ]);
      setAssets(assetsData);
      setIntersections(intersectionsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error cargando infraestructura');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInfrastructure();
  }, [fetchInfrastructure]);

  const createAsset = async (asset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'>) => {
    try {
      const newAsset = await apiFetch<InfrastructureAsset>('/infrastructure/assets', {
        method: 'POST',
        body: JSON.stringify(asset)
      });
      setAssets(prev => [...prev, newAsset]);
      return newAsset;
    } catch (err) {
      throw err instanceof Error ? err : new Error('Error al crear activo');
    }
  };

  return { assets, intersections, loading, error, refresh: fetchInfrastructure, createAsset };
}
