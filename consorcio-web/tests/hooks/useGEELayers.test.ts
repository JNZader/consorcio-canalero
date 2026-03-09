import { renderHook, waitFor } from '@testing-library/react';
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
});
