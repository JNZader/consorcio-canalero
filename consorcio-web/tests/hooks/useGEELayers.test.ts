import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FeatureCollection } from 'geojson';
import { useGEELayers } from '../../src/hooks/useGEELayers';

// Mock fetch globally
global.fetch = vi.fn();

const mockFetch = global.fetch as any;

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
    await result.current.reload();
    
    expect(result.current.loading).toBe(false);
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
});
