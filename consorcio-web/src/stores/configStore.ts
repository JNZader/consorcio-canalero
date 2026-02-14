import { create } from 'zustand';
import { configApi, type SystemConfig } from '../lib/api';
import { logger } from '../lib/logger';

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
 */
export const useConfigStore = create<ConfigState>((set, get) => ({
  config: null,
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
      logger.error('Failed to fetch system configuration:', err);
      set({
        loading: false,
        initialized: true,
        error: err instanceof Error ? err.message : 'Error desconocido al cargar configuracion'
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
