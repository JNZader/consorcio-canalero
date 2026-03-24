import { create } from 'zustand';
import { configApi, type SystemConfig } from '../lib/api';
import { logger } from '../lib/logger';
import { MAP_CENTER, MAP_DEFAULT_ZOOM, MAP_BOUNDS, CONSORCIO_AREA_HA, CONSORCIO_KM_CAMINOS, DEFAULT_MAX_CLOUD, DEFAULT_DAYS_BACK } from '../constants';

/**
 * Default system configuration used when the API is unavailable.
 * Bell Ville, Cordoba coordinates as map center.
 */
const DEFAULT_CONFIG: SystemConfig = {
  consorcio_area_ha: CONSORCIO_AREA_HA,
  consorcio_km_caminos: CONSORCIO_KM_CAMINOS,
  map: {
    center: { lat: MAP_CENTER[0], lng: MAP_CENTER[1] },
    zoom: MAP_DEFAULT_ZOOM,
    bounds: MAP_BOUNDS,
  },
  cuencas: [
    { id: 'candil', nombre: 'Candil', ha: 18800, color: '#3b82f6' },
    { id: 'ml', nombre: 'ML', ha: 18900, color: '#14b8a6' },
    { id: 'noroeste', nombre: 'Noroeste', ha: 18500, color: '#f97316' },
    { id: 'norte', nombre: 'Norte', ha: 18300, color: '#8b5cf6' },
  ],
  analysis: {
    default_max_cloud: DEFAULT_MAX_CLOUD,
    default_days_back: DEFAULT_DAYS_BACK,
  },
};

interface ConfigState {
  config: SystemConfig | null;
  loading: boolean;
  error: string | null;
  initialized: boolean;

  // Actions
  fetchConfig: () => Promise<void>;
}

/**
 * Store for global system configuration.
 * Fetched from backend on app initialization.
 * Falls back to DEFAULT_CONFIG when the API is unavailable.
 */
export const useConfigStore = create<ConfigState>((set, get) => ({
  config: DEFAULT_CONFIG,
  loading: false,
  error: null,
  initialized: false,

  fetchConfig: async () => {
    // Avoid multiple simultaneous fetches
    if (get().loading) return;

    set({ loading: true, error: null });

    try {
      const config = await configApi.getSystemConfig();
      set({ config, loading: false, initialized: true });
    } catch (err) {
      logger.error('Failed to fetch system configuration, using defaults:', err);
      set({
        config: DEFAULT_CONFIG,
        loading: false,
        initialized: true,
        error: err instanceof Error ? err.message : 'Error desconocido al cargar configuracion',
      });
    }
  },
}));

/**
 * Hook to access specific parts of the configuration with fallbacks.
 */
export function useSystemConfig() {
  return useConfigStore((state) => state.config);
}

/**
 * Hook to check if config is still loading.
 */
export function useIsConfigLoading() {
  return useConfigStore((state) => state.loading);
}
