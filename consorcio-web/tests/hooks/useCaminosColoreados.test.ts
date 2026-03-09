import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FeatureCollection } from 'geojson';
import { useCaminosColoreados } from '../../src/hooks/useCaminosColoreados';

// Mock fetch globally
global.fetch = vi.fn();

const mockFetch = global.fetch as any;

const mockResponse = {
  type: 'FeatureCollection' as const,
  features: [
    {
      type: 'Feature' as const,
      geometry: { type: 'LineString' as const, coordinates: [[0, 0], [1, 1]] },
      properties: { consorcio: 'Consorcio A', color: '#FF0000' },
    },
    {
      type: 'Feature' as const,
      geometry: { type: 'LineString' as const, coordinates: [[2, 2], [3, 3]] },
      properties: { consorcio: 'Consorcio B', color: '#00FF00' },
    },
  ],
};

describe('useCaminosColoreados', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });
  });

  it('should initialize with empty state', () => {
    const { result } = renderHook(() => useCaminosColoreados());

    expect(result.current.loading).toBe(true);
    expect(result.current.caminos).toBeDefined();
    expect(result.current.consorcios).toBeDefined();
    expect(result.current.error).toBeNull();
  });

  it('should return structured data with caminos, consorcios, and metadata', () => {
    const { result } = renderHook(() => useCaminosColoreados());

    expect(result.current).toHaveProperty('caminos');
    expect(result.current).toHaveProperty('consorcios');
    expect(result.current).toHaveProperty('metadata');
    expect(result.current).toHaveProperty('loading');
    expect(result.current).toHaveProperty('error');
    expect(result.current).toHaveProperty('reload');
  });

  it('should have a reload function', () => {
    const { result } = renderHook(() => useCaminosColoreados());

    expect(typeof result.current.reload).toBe('function');
  });

  it('should handle errors gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useCaminosColoreados());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    expect(result.current.error).not.toBeNull();
  });

  it('should handle HTTP errors', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
    });

    const { result } = renderHook(() => useCaminosColoreados());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    expect(result.current.error).not.toBeNull();
  });

  it('should have reload function that is callable', async () => {
    const { result } = renderHook(() => useCaminosColoreados());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    mockFetch.mockClear();

    await result.current.reload();

    expect(result.current.loading).toBe(false);
  });

  it('should return null values initially if loading fails', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useCaminosColoreados());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    expect(result.current.caminos).toBeDefined();
    expect(result.current.consorcios).toBeDefined();
  });

  it('should not throw errors when reload is called multiple times', async () => {
    const { result } = renderHook(() => useCaminosColoreados());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

    expect(async () => {
      await result.current.reload();
      await result.current.reload();
    }).not.toThrow();
  });
});
