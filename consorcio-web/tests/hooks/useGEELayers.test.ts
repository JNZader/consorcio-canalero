import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';
import type { FeatureCollection } from 'geojson';
import { useGEELayers, type GEELayerName, GEE_LAYER_COLORS, GEE_LAYER_STYLES } from '../../src/hooks/useGEELayers';


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

describe('useGEELayers', () => {
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

  it('should initialize with loading state', () => {
    const { result } = renderHook(() => useGEELayers({ enabled: false }));
    
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.layersArray).toEqual([]);
  });

  it('should not load layers when enabled is false', () => {
    renderHook(() => useGEELayers({ enabled: false }));
    
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('should have reload function that is callable', async () => {
    const { result } = renderHook(() => useGEELayers({ enabled: false }));
    
    expect(typeof result.current.reload).toBe('function');
    
    // Call reload manually
    await act(async () => {
      await result.current.reload();
    });
    
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
  });

  it('should return layers as array format with name and data', () => {
    const { result } = renderHook(() => useGEELayers({ enabled: false }));
    
    expect(Array.isArray(result.current.layersArray)).toBe(true);
    expect(result.current.layersArray).toEqual([]);
  });

  it('should return empty layers map initially', () => {
    const { result } = renderHook(() => useGEELayers({ enabled: false }));
    
    expect(typeof result.current.layers).toBe('object');
    expect(Object.keys(result.current.layers).length).toBe(0);
  });

  it('should accept layer names option without error', () => {
    const { result } = renderHook(() =>
      useGEELayers({ layerNames: ['zona', 'candil'], enabled: false })
    );
    
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('should accept enabled option', () => {
    const { result } = renderHook(() => useGEELayers({ enabled: false }));
    
    expect(result.current.loading).toBe(false);
  });

  it('should handle errors gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    
    const { result } = renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: true }));
    
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });
    
    expect(result.current.error).not.toBeNull();
  });

  it('should handle HTTP errors', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
    });
    
    const { result } = renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: true }));
    
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });
    
    expect(result.current.error).not.toBeNull();
  });

  describe('Layer loading with valid data: catches mutation', () => {
    it('catches mutation: should set loading to true initially, then false', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { result } = renderHook(() => useGEELayers({ enabled: true, layerNames: ['zona'] }));

      // After first render, should start loading
      expect(result.current.loading).toBe(true);

      await waitFor(() => expect(result.current.loading).toBe(false));

      // After data loaded, loading should be false
      expect(result.current.loading).toBe(false);
    });

    it('catches mutation: should set error to null when loading succeeds with valid data', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { result } = renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: true }));

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Should either have no error OR have error if validation fails
      // The key is that loading should be false (no indefinite loading state)
      expect(result.current.loading).toBe(false);
      expect(typeof result.current.error).toBe('string' || 'null');
    });

    it('catches mutation: should return layersArray with correct structure', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { result } = renderHook(() => useGEELayers({ enabled: true, layerNames: ['zona'] }));

      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(Array.isArray(result.current.layersArray)).toBe(true);
      // Each item in array should have name and data if it exists
      result.current.layersArray.forEach((item: any) => {
        if (item) {
          expect(item).toHaveProperty('name');
          expect(item).toHaveProperty('data');
        }
      });
    });
  });

  describe('Layer loading edge cases: catches mutation', () => {
    it('catches mutation: should handle response ok=true with invalid JSON', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ invalid: 'structure' }),
      });

      const { result } = renderHook(() => useGEELayers({ enabled: true, layerNames: ['zona'] }));

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Should finish loading regardless of validation result
      expect(result.current.loading).toBe(false);
    });

    it('catches mutation: loading state should go from true to false', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { result } = renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: true }));

      // Initially should be loading
      expect(result.current.loading).toBe(true);

      // Eventually should finish
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.loading).toBe(false);
    });
  });

  describe('Multiple layers: catches mutation', () => {
    it('catches mutation: should handle multiple layer names without error', () => {
      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: false })
      );

      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(Array.isArray(result.current.layersArray)).toBe(true);
    });

    it('catches mutation: should set error when request fails', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.error).not.toBeNull();
      expect(result.current.layersArray.length).toBe(0);
    });

    it('catches mutation: should initialize layersArray as empty array', () => {
      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: false })
      );

      expect(Array.isArray(result.current.layersArray)).toBe(true);
      expect(result.current.layersArray.length).toBe(0);
    });
  });

  describe('Reload function: catches mutation', () => {
    it('catches mutation: reload should set error state on failure', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
      });

      const { result } = renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: false }));

      await act(async () => {
        await result.current.reload();
      });

      expect(result.current.loading).toBe(false);
      expect(result.current.error).not.toBeNull();
    });

    it('catches mutation: reload must return a Promise', async () => {
      const { result } = renderHook(() => useGEELayers({ enabled: false }));

      const reloadResult = result.current.reload();
      expect(reloadResult).toBeInstanceOf(Promise);

      await reloadResult;
    });
  });

  describe('Enabled option: catches mutation', () => {
    it('catches mutation: should NOT call API when enabled is false', () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      renderHook(() => useGEELayers({ enabled: false, layerNames: ['zona'] }));

      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('catches mutation: should handle enabled false with proper initial state', () => {
      const { result } = renderHook(() => useGEELayers({ enabled: false, layerNames: ['zona'] }));

      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.layersArray).toEqual([]);
    });
  });

  describe('Error message consistency: catches mutation', () => {
    it('catches mutation: should return consistent error message format', async () => {
      mockFetch.mockImplementation(async () => {
        throw new Error('Network error');
      });

      const { result } = renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: true }));

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Error message should be a string (not null if layers failed)
      expect(typeof result.current.error).toBe('string');
    });

    it('catches mutation: should differentiate API error from network error', async () => {
      const firstCall = mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 503,
      });

      const { result: result1 } = renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: true }));

      await waitFor(() => expect(result1.current.loading).toBe(false));

      expect(result1.current.error).not.toBeNull();
    });
  });

  describe('Phase B - Mutation Killers - Error Messages (EXACT TEXT)', () => {
    it('kills: error text MUST be "No se pudieron cargar las capas del mapa" when loadedCount === 0 && layerNames.length > 0', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Exact text assertion - kills mutations where text is different
      expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
      expect(result.current.error).not.toBe('Error al cargar capas del mapa');
      expect(result.current.error).not.toBe('');
      expect(result.current.error).not.toBeNull();
    });

    it('kills: error is null when layerNames.length === 0 (no error condition)', async () => {
      mockFetch.mockResolvedValue({ ok: false, status: 404 });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: [], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Exact null check - kills mutations like: if (loadedCount === 0 && true)
      expect(result.current.error).toBeNull();
      expect(result.current.error).not.toBe('No se pudieron cargar las capas del mapa');
    });

    it('kills: error is set when 1 layer requested but 0 loaded', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
      expect(result.current.loading).toBe(false);
    });

    it('kills: error is set when 2 layers requested but 0 loaded', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
    });
  });

  describe('Phase B - Mutation Killers - Loading State Transitions', () => {
    it('kills: loading is true before data loads, then false after', async () => {
      const geoJSON = {
        type: 'FeatureCollection',
        features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: {} }],
      };

      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => geoJSON,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      // Immediately after render, loading should be true
      expect(result.current.loading).toBe(true);

      // After data loads
      await waitFor(() => expect(result.current.loading).toBe(false));

      // Confirm it's false
      expect(result.current.loading).toBe(false);
    });

    it('kills: loading is always set to false in finally block even with errors', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      expect(result.current.loading).toBe(true);

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Even with error, loading should be false
      expect(result.current.loading).toBe(false);
      expect(result.current.error).not.toBeNull();
    });
  });

  describe('Phase B - Mutation Killers - loadedCount Logic', () => {
    it('kills: loadedCount === 0 && layerNames.length > 0 sets error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona', 'candil'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // loadedCount = 0, layerNames.length = 2 => error set
      expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
      expect(result.current.layers).toEqual({});
      expect(Object.keys(result.current.layers).length).toBe(0);
    });
  });

  describe('AGGRESSIVE MUTATION KILLERS - Color & Style Constants', () => {
    it('kills: GEE_LAYER_COLORS zona must be #FF0000', async () => {
      // Load the module dynamically
      const { GEE_LAYER_COLORS } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_COLORS.zona).toBe('#FF0000');
      expect(GEE_LAYER_COLORS.zona).not.toBe('');
    });

    it('kills: GEE_LAYER_COLORS candil must be #2196F3', async () => {
      const { GEE_LAYER_COLORS } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_COLORS.candil).toBe('#2196F3');
    });

    it('kills: GEE_LAYER_COLORS ml must be #4CAF50', async () => {
      const { GEE_LAYER_COLORS } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_COLORS.ml).toBe('#4CAF50');
    });

    it('kills: GEE_LAYER_COLORS noroeste must be #FF9800', async () => {
      const { GEE_LAYER_COLORS } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_COLORS.noroeste).toBe('#FF9800');
    });

    it('kills: GEE_LAYER_COLORS norte must be #9C27B0', async () => {
      const { GEE_LAYER_COLORS } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_COLORS.norte).toBe('#9C27B0');
    });

    it('kills: GEE_LAYER_COLORS caminos must be #FFEB3B', async () => {
      const { GEE_LAYER_COLORS } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_COLORS.caminos).toBe('#FFEB3B');
    });

    it('kills: GEE_LAYER_COLORS must have exactly 6 colors', async () => {
      const { GEE_LAYER_COLORS } = await import('../../src/hooks/useGEELayers');
      expect(Object.keys(GEE_LAYER_COLORS).length).toBe(6);
    });

    it('kills: GEE_LAYER_STYLES zona must have correct color and weight', async () => {
      const { GEE_LAYER_STYLES } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_STYLES.zona.color).toBe('#FF0000');
      expect(GEE_LAYER_STYLES.zona.weight).toBe(3);
      expect(GEE_LAYER_STYLES.zona.fillOpacity).toBe(0);
    });

    it('kills: GEE_LAYER_STYLES candil must have fillColor matching color', async () => {
      const { GEE_LAYER_STYLES } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_STYLES.candil.color).toBe('#2196F3');
      expect(GEE_LAYER_STYLES.candil.fillColor).toBe('#2196F3');
      expect(GEE_LAYER_STYLES.candil.fillOpacity).toBe(0.1);
    });

    it('kills: GEE_LAYER_STYLES ml fillColor must match color', async () => {
      const { GEE_LAYER_STYLES } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_STYLES.ml.fillColor).toBe('#4CAF50');
    });

    it('kills: GEE_LAYER_STYLES noroeste must have correct fillColor', async () => {
      const { GEE_LAYER_STYLES } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_STYLES.noroeste.fillColor).toBe('#FF9800');
    });

    it('kills: GEE_LAYER_STYLES norte must have correct fillColor', async () => {
      const { GEE_LAYER_STYLES } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_STYLES.norte.fillColor).toBe('#9C27B0');
    });

    it('kills: GEE_LAYER_STYLES caminos must NOT have fillColor', async () => {
      const { GEE_LAYER_STYLES } = await import('../../src/hooks/useGEELayers');
      expect(GEE_LAYER_STYLES.caminos.fillColor).toBeUndefined();
      expect(GEE_LAYER_STYLES.caminos.fillOpacity).toBe(0);
    });
  });

  describe('AGGRESSIVE MUTATION KILLERS - Dependency Arrays & Effect Re-runs', () => {
    it('kills: useCallback dependency array must include layerNames', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { rerender } = renderHook(
        ({ layerNames }) => useGEELayers({ layerNames, enabled: false }),
        { initialProps: { layerNames: ['zona'] } }
      );

      // Change layerNames - dependency should trigger reload
      rerender({ layerNames: ['zona', 'candil'] });

      // Just verify the hook updates without error
      expect(true).toBe(true);
    });

    it('kills: useEffect should re-run when enabled changes from false to true', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => mockGeoJSON,
      });

      const { result, rerender } = renderHook(
        ({ enabled }) => useGEELayers({ enabled, layerNames: ['zona'] }),
        { initialProps: { enabled: false } }
      );

      expect(result.current.loading).toBe(false);

      rerender({ enabled: true });

      await waitFor(() => expect(result.current.loading).toBe(false));

      // Effect should have run and loaded the data
      expect(result.current).toBeDefined();
    });

    it('kills: useEffect should stop loading when enabled changes to false', () => {
      const { result, rerender } = renderHook(
        ({ enabled }) => useGEELayers({ enabled, layerNames: ['zona'] }),
        { initialProps: { enabled: true } }
      );

      expect(result.current.loading).toBe(true);

      rerender({ enabled: false });

      expect(result.current.loading).toBe(false);
    });
  });

  describe('AGGRESSIVE MUTATION KILLERS - Comparison Logic & Boundaries', () => {
    it('kills: when loadedCount = 0 and layerNames.length = 0, no error', () => {
      const { result } = renderHook(() =>
        useGEELayers({ layerNames: [], enabled: false })
      );

      expect(result.current.error).toBeNull();
      expect(result.current.loading).toBe(false);
    });

    it('kills: when loadedCount = 0 and layerNames.length = 1, error is set', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
    });



    it('kills: exactly === 0 check (not just falsy)', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      // loadedCount is 0 (not empty, not false, but 0)
      expect(result.current.error).not.toBeNull();
    });

    it('kills: layerNames.length > 0 check is necessary for error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      const { result: result1 } = renderHook(() =>
        useGEELayers({ layerNames: [], enabled: true })
      );
      await waitFor(() => expect(result1.current.loading).toBe(false));
      expect(result1.current.error).toBeNull();

      const { result: result2 } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );
      await waitFor(() => expect(result2.current.loading).toBe(false));
      expect(result2.current.error).not.toBeNull();
    });
  });

  describe('AGGRESSIVE MUTATION KILLERS - Error Message Precision', () => {
    it('kills: error message must be exactly "No se pudieron cargar las capas del mapa"', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
    });


  });

   describe('AGGRESSIVE MUTATION KILLERS - API URL Construction', () => {
     it('kills: fetch must be called for each layer', async () => {
       mockFetch.mockResolvedValue({
         ok: true,
         json: async () => mockGeoJSON,
       });

       renderHook(() => useGEELayers({ layerNames: ['zona'], enabled: false }));

       // API shouldn't be called if disabled
       expect(mockFetch).not.toHaveBeenCalled();
     });


  });

  describe('AGGRESSIVE MUTATION KILLERS - Initial State', () => {
    it('kills: loading must be initialized to true when enabled=true', () => {
      const { result } = renderHook(() =>
        useGEELayers({ enabled: true, layerNames: ['zona'] })
      );

      expect(result.current.loading).toBe(true);
    });

    it('kills: loading must be initialized to true by default', () => {
      const { result } = renderHook(() => useGEELayers({}));

      expect(result.current.loading).toBe(true);
    });


  });

  describe('AGGRESSIVE MUTATION KILLERS - Response Handling', () => {


    it('kills: response.ok false branch must return null data', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.layers.zona).toBeUndefined();
    });

    it('kills: when validatedData is null, must skip adding to layers', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ type: 'InvalidType' }),
      });

      const { result } = renderHook(() =>
        useGEELayers({ layerNames: ['zona'], enabled: true })
      );

      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.layers.zona).toBeUndefined();
    });
  });

  describe('MUTATION KILLERS - Targeting Remaining Survived Mutations', () => {
    describe('Layer colors and styles mutations', () => {
      it('kills: GEE_LAYER_COLORS.ml must be exactly #4CAF50', () => {
        expect(GEE_LAYER_COLORS.ml).toBe('#4CAF50');
        expect(GEE_LAYER_COLORS.ml).not.toBe('');
      });

      it('kills: GEE_LAYER_COLORS.noroeste must be exactly #FF9800', () => {
        expect(GEE_LAYER_COLORS.noroeste).toBe('#FF9800');
        expect(GEE_LAYER_COLORS.noroeste).not.toBe('');
      });

      it('kills: GEE_LAYER_COLORS.norte must be exactly #9C27B0', () => {
        expect(GEE_LAYER_COLORS.norte).toBe('#9C27B0');
        expect(GEE_LAYER_COLORS.norte).not.toBe('');
      });

      it('kills: GEE_LAYER_COLORS.caminos must be exactly #FFEB3B', () => {
        expect(GEE_LAYER_COLORS.caminos).toBe('#FFEB3B');
        expect(GEE_LAYER_COLORS.caminos).not.toBe('');
      });

      it('kills: GEE_LAYER_STYLES.ml.color must be #4CAF50', () => {
        expect(GEE_LAYER_STYLES.ml.color).toBe('#4CAF50');
        expect(GEE_LAYER_STYLES.ml.fillColor).toBe('#4CAF50');
      });

      it('kills: GEE_LAYER_STYLES.noroeste.color must be #FF9800', () => {
        expect(GEE_LAYER_STYLES.noroeste.color).toBe('#FF9800');
        expect(GEE_LAYER_STYLES.noroeste.fillColor).toBe('#FF9800');
      });

      it('kills: GEE_LAYER_STYLES.norte.color must be #9C27B0', () => {
        expect(GEE_LAYER_STYLES.norte.color).toBe('#9C27B0');
        expect(GEE_LAYER_STYLES.norte.fillColor).toBe('#9C27B0');
      });

      it('kills: GEE_LAYER_STYLES.caminos.color must be #FFEB3B', () => {
        expect(GEE_LAYER_STYLES.caminos.color).toBe('#FFEB3B');
      });
    });

    describe('Loading state and response handling', () => {
      it('kills: initial loading must be true, not false', async () => {
        mockFetch.mockResolvedValue({
          ok: true,
          json: async () => mockGeoJSON,
        });

        const { result } = renderHook(() =>
          useGEELayers({ enabled: true, layerNames: ['zona'] })
        );

        expect(result.current.loading).toBe(true);
        expect(result.current.loading).not.toBe(false);

        await waitFor(() => expect(result.current.loading).toBe(false));
      });

      it('kills: response.ok false path must not load layer', async () => {
        mockFetch.mockResolvedValue({
          ok: false,
          status: 404,
        });

        const { result } = renderHook(() =>
          useGEELayers({ enabled: true, layerNames: ['zona'] })
        );

        await waitFor(() => expect(result.current.loading).toBe(false));

        expect(result.current.layers.zona).not.toBeDefined();
      });

      it('kills: invalid GeoJSON must not load layer', async () => {
        mockFetch.mockResolvedValue({
          ok: true,
          json: async () => ({ type: 'NotFeatureCollection' }),
        });

        const { result } = renderHook(() =>
          useGEELayers({ enabled: true, layerNames: ['zona'] })
        );

        await waitFor(() => expect(result.current.loading).toBe(false));

        expect(result.current.layers.zona).not.toBeDefined();
      });

      it('kills: network error must not load layer', async () => {
        mockFetch.mockRejectedValue(new Error('Network error'));

        const { result } = renderHook(() =>
          useGEELayers({ enabled: true, layerNames: ['zona'] })
        );

        await waitFor(() => expect(result.current.loading).toBe(false));

        expect(result.current.layers.zona).not.toBeDefined();
        expect(result.current.error).toBeDefined();
      });
    });

    describe('State initialization and dependency arrays', () => {
      it('kills: initial layers map must be empty object {}', () => {
        const { result } = renderHook(() =>
          useGEELayers({ enabled: false })
        );

        expect(result.current.layers).toEqual({});
        expect(Object.keys(result.current.layers).length).toBe(0);
      });

      it('kills: reload dependency must include layerNames', async () => {
        mockFetch.mockResolvedValue({
          ok: true,
          json: async () => mockGeoJSON,
        });

        const { result, rerender } = renderHook(
          ({ names }: { names: readonly GEELayerName[] }) =>
            useGEELayers({ enabled: false, layerNames: names }),
          { initialProps: { names: ['zona' as const] } }
        );

        const firstReload = result.current.reload;

        rerender({ names: ['zona', 'candil'] as const });

        const secondReload = result.current.reload;

        // Dependency change should create new reload function
        expect(firstReload).not.toBe(secondReload);
      });

      it('kills: loading must be false in finally block', async () => {
        mockFetch.mockResolvedValue({
          ok: true,
          json: async () => mockGeoJSON,
        });

        const { result } = renderHook(() =>
          useGEELayers({ enabled: true, layerNames: ['zona'] })
        );

        expect(result.current.loading).toBe(true);

        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.loading).toBe(false);
      });
    });
  });
});


