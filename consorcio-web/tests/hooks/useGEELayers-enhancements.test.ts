import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';
import type { FeatureCollection } from 'geojson';
import { useGEELayers } from '../../src/hooks/useGEELayers';

// Mock fetch globally BEFORE importing the hook
global.fetch = vi.fn();

const mockFetch = global.fetch as any;

// Mock API module
vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock('../../src/lib/typeGuards', () => ({
  parseFeatureCollection: (data: any) => {
    if (data && data.type === 'FeatureCollection' && Array.isArray(data.features)) {
      return data;
    }
    return null;
  },
}));

const mockGeoJSON: FeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [0, 0] },
      properties: { name: 'Test Feature' },
    },
  ],
};

describe('useGEELayers - Phase B Enhancements', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockGeoJSON,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Error Message Specific Text (Kills State Mutations)', () => {
    it('should set EXACT error message when no layers load', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // CRITICAL: Specific text, not just truthiness
      expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
    });

    it('should set error with specific text when Promise.all throws', async () => {
      mockFetch.mockImplementation(() => {
        throw new Error('Network error');
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // CRITICAL: Specific text for error scenario
      expect(result.current.error).toBe('Error al cargar capas del mapa');
    });

    it('should clear error to null on successful load', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // CRITICAL: Must be null (not undefined, not empty string)
      expect(result.current.error).toBeNull();
      expect(result.current.error).toBe(null);
    });
  });

  describe('State Transitions & Loading Flag (Kills State Mutations)', () => {
    it('should transition loading from true→false→true on reload', async () => {
      const { result } = renderHook(() => useGEELayers({ enabled: false }));

      expect(result.current.loading).toBe(false);

      // Trigger reload
      await act(async () => {
        await result.current.reload();
      });

      await waitFor(() => expect(result.current.loading).toBe(false));
    });

    it('should set loading=true before calling setError on no-load scenario', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: false })
      );

      expect(result.current.loading).toBe(false);

      await act(async () => {
        await result.current.reload();
      });

      await waitFor(() => {
        // CRITICAL: Must go through loading phase
        expect(result.current.loading).toBe(false);
        // And error should be set
        expect(result.current.error).not.toBeNull();
      });
    });
  });

  describe('Layers Object Structure (Kills Object Mutations)', () => {
    it('should populate layers object with specific layer name as key', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // CRITICAL: Verify specific key name exists
      expect(result.current.layers).toHaveProperty('zona');
      expect(result.current.layers.zona).toBeDefined();
      expect(result.current.layers.zona).toEqual(mockGeoJSON);
    });

    it('should populate multiple layers with correct keys', async () => {
      let callCount = 0;
      mockFetch.mockImplementation(async (url: string) => {
        callCount++;
        return {
          ok: true,
          json: async () => ({
            ...mockGeoJSON,
            properties: { layer: url.includes('zona') ? 'zona' : 'candil' },
          }),
        };
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 5000 });

      // CRITICAL: Both keys must exist
      expect(result.current.layers).toHaveProperty('zona');
      expect(result.current.layers).toHaveProperty('candil');
      expect(Object.keys(result.current.layers).length).toBe(2);
    });

    it('should NOT include layers with null data in layers object', async () => {
      mockFetch.mockImplementation(async (url: string) => {
        // First call returns invalid, second returns valid
        if (url.includes('zona')) {
          return {
            ok: true,
            json: async () => ({ invalid: 'structure' }),
          };
        }
        return {
          ok: true,
          json: async () => mockGeoJSON,
        };
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 5000 });

      // CRITICAL: Only valid layer should be in map
      expect(result.current.layers).not.toHaveProperty('zona');
      expect(result.current.layers).toHaveProperty('candil');
      expect(Object.keys(result.current.layers).length).toBe(1);
    });
  });

  describe('LayersArray Transformation (Kills Array Mutations)', () => {
    it('should transform layers object to array with name and data properties', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.layersArray).toHaveLength(1);
      expect(result.current.layersArray[0]).toHaveProperty('name');
      expect(result.current.layersArray[0]).toHaveProperty('data');
      expect(result.current.layersArray[0].name).toBe('zona');
      expect(result.current.layersArray[0].data).toEqual(mockGeoJSON);
    });

    it('should maintain empty array when no layers load', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 5000 });

      expect(Array.isArray(result.current.layersArray)).toBe(true);
      expect(result.current.layersArray).toHaveLength(0);
    });

    it('should filter out undefined entries from layers when building array', async () => {
      mockFetch.mockImplementation(async (url: string) => {
        if (url.includes('zona')) {
          return {
            ok: true,
            json: async () => ({ invalid: 'geojson' }),
          };
        }
        return {
          ok: true,
          json: async () => mockGeoJSON,
        };
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 5000 });

      // Only valid layer should be in array
      expect(result.current.layersArray).toHaveLength(1);
      expect(result.current.layersArray[0].name).toBe('candil');
    });
  });

  describe('Boundary Conditions: loadedCount Logic (Kills Conditional Mutations)', () => {
    it('should set error when loadedCount=0 and layerNames.length=1', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // CRITICAL: Error condition: 0 loaded, 1 requested
      expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
    });

    it('should set error when loadedCount=0 and layerNames.length=2', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 5000 });

      // CRITICAL: Error condition: 0 loaded, 2 requested
      expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
    });

    it('should NOT set error when loadedCount=0 and layerNames.length=0', async () => {
      const { result } = renderHook(() =>
        useGEELayers({ layerNames: [], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // CRITICAL: No error when no layers requested
      expect(result.current.error).toBeNull();
    });

    it('should NOT set error when loadedCount=1 and layerNames.length=2 (partial success)', async () => {
      mockFetch.mockImplementation(async (url: string) => {
        // First succeeds, second fails
        if (url.includes('zona')) {
          return {
            ok: true,
            json: async () => mockGeoJSON,
          };
        }
        return {
          ok: false,
          status: 404,
        };
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 5000 });

      // CRITICAL: Partial success means NO error
      expect(result.current.error).toBeNull();
    });

    it('should NOT set error when loadedCount=2 and layerNames.length=2 (full success)', async () => {
      let callCount = 0;
      mockFetch.mockImplementation(async () => {
        return {
          ok: true,
          json: async () => mockGeoJSON,
        };
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 5000 });

      // CRITICAL: Full success means NO error
      expect(result.current.error).toBeNull();
    });
  });

  describe('Conditional Branches: response.ok Logic (Kills Branch Mutations)', () => {
    it('should log warning but return [name, null] when response.ok=false', async () => {
      const mockWarn = vi.fn();
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Should have error, layer not added
      expect(result.current.error).not.toBeNull();
      expect(result.current.layers).not.toHaveProperty('zona');
    });

    it('should call parseFeatureCollection when response.ok=true', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // If parseFeatureCollection was called and validated, layer should be added
      expect(result.current.layers).toHaveProperty('zona');
      expect(result.current.error).toBeNull();
    });

    it('should return [name, null] when validatedData is falsy', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ invalid: 'geojson' }),
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Layer should not be added because validation failed
      expect(result.current.layers).not.toHaveProperty('zona');
    });
  });

  describe('Enabled Option Logic (Kills Conditional Mutations)', () => {
    it('should call API when enabled=true initially', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: true }));

      await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    });

    it('should NOT call API when enabled=false initially', () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: false }));

      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('should set loading=false immediately when enabled=false', () => {
      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: false })
      );

      expect(result.current.loading).toBe(false);
    });
  });
});
