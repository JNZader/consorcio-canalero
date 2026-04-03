/**
 * configStore.test.ts
 * Unit: Zustand store for global system configuration
 * Coverage Target: 100% for configStore
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useConfigStore, useSystemConfig, useIsConfigLoading } from '../../src/stores/configStore';
import * as configModule from '../../src/lib/api';
import * as loggerModule from '../../src/lib/logger';

// Mock the dependencies
vi.mock('../../src/lib/api', () => ({
  configApi: {
    getSystemConfig: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}));

const mockGetSystemConfig = configModule.configApi.getSystemConfig as ReturnType<typeof vi.fn>;
const mockLoggerError = loggerModule.logger.error as ReturnType<typeof vi.fn>;

describe('configStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset store state — keep config as default (store uses DEFAULT_CONFIG on init)
    useConfigStore.setState({
      loading: false,
      error: null,
      initialized: false,
    });
  });

  describe('useConfigStore', () => {
    it('should initialize with correct default state', () => {
      const state = useConfigStore.getState();
      // Store now initializes with DEFAULT_CONFIG (not null) for immediate usability
      expect(state.config).not.toBeNull();
      expect(state.config).toHaveProperty('consorcio_area_ha');
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.initialized).toBe(false);
    });

    it('should have a fetchConfig function', () => {
      const state = useConfigStore.getState();
      expect(typeof state.fetchConfig).toBe('function');
    });
  });

  describe('fetchConfig', () => {
    it('should fetch config successfully', async () => {
      const mockConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -63 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      mockGetSystemConfig.mockResolvedValue(mockConfig);

      const { fetchConfig } = useConfigStore.getState();
      await fetchConfig();

      const state = useConfigStore.getState();
      expect(state.config).toEqual(mockConfig);
      expect(state.loading).toBe(false);
      expect(state.initialized).toBe(true);
      expect(state.error).toBeNull();
    });

    it('should set loading to true while fetching', async () => {
      const mockConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -63 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      let resolveCallback: (value: any) => void;
      const fetchPromise = new Promise((resolve) => {
        resolveCallback = resolve;
      });

      mockGetSystemConfig.mockReturnValue(fetchPromise);

      const { fetchConfig } = useConfigStore.getState();
      const fetchPromise2 = fetchConfig();

      // Should be loading immediately
      let state = useConfigStore.getState();
      expect(state.loading).toBe(true);

      // Resolve the fetch
      resolveCallback!(mockConfig);
      await fetchPromise2;

      // Should no longer be loading
      state = useConfigStore.getState();
      expect(state.loading).toBe(false);
    });

    it('should prevent multiple simultaneous fetches', async () => {
      const mockConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -63 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      mockGetSystemConfig.mockResolvedValue(mockConfig);

      // Set loading to true manually
      useConfigStore.setState({ loading: true });

      const { fetchConfig } = useConfigStore.getState();
      await fetchConfig();

      // Should not have called getSystemConfig because loading was true
      expect(mockGetSystemConfig).not.toHaveBeenCalled();
    });

    it('should handle fetch errors gracefully', async () => {
      const error = new Error('Network error');
      mockGetSystemConfig.mockRejectedValue(error);

      const { fetchConfig } = useConfigStore.getState();
      await fetchConfig();

      const state = useConfigStore.getState();
      expect(state.loading).toBe(false);
      expect(state.initialized).toBe(true);
      expect(state.error).toBe('Network error');
      // On error, store falls back to DEFAULT_CONFIG (not null)
      expect(state.config).not.toBeNull();
      expect(state.config).toHaveProperty('consorcio_area_ha');
      expect(mockLoggerError).toHaveBeenCalledWith(
        'Failed to fetch system configuration, using defaults:',
        error
      );
    });

    it('should handle unknown errors with fallback message', async () => {
      const unknownError = 'Some error string';
      mockGetSystemConfig.mockRejectedValue(unknownError);

      const { fetchConfig } = useConfigStore.getState();
      await fetchConfig();

      const state = useConfigStore.getState();
      expect(state.error).toBe('Error desconocido al cargar configuracion');
    });

    it('should clear previous errors on new fetch', async () => {
      const mockConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -63 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      // Set initial error state
      useConfigStore.setState({ error: 'Previous error' });

      mockGetSystemConfig.mockResolvedValue(mockConfig);

      const { fetchConfig } = useConfigStore.getState();
      await fetchConfig();

      const state = useConfigStore.getState();
      expect(state.error).toBeNull();
    });
  });



  describe('Store state management', () => {
    it('should track initialized flag correctly', async () => {
      const mockConfig = {
        consorcio_area_ha: 10000,
        consorcio_km_caminos: 500,
        map: {
          center: { lat: -35, lng: -62 },
          zoom: 10,
          bounds: { north: -34, south: -36, east: -61, west: -63 },
        },
        cuencas: [],
        analysis: { default_max_cloud: 20, default_days_back: 30 },
      };

      expect(useConfigStore.getState().initialized).toBe(false);

      mockGetSystemConfig.mockResolvedValue(mockConfig);
      const { fetchConfig } = useConfigStore.getState();
      await fetchConfig();

      expect(useConfigStore.getState().initialized).toBe(true);
    });

    it('should track error state correctly', async () => {
      const error = new Error('Test error');
      mockGetSystemConfig.mockRejectedValue(error);

      const { fetchConfig } = useConfigStore.getState();
      await fetchConfig();

      expect(useConfigStore.getState().error).toBe('Test error');
    });
  });
});
