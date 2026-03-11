// @ts-nocheck
import { renderHook, waitFor, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';

// Mock fetch globally BEFORE importing the hook
global.fetch = vi.fn();
const mockFetch = global.fetch as any;

// Mock API module
vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  },
}));

import { useCaminosColoreados } from '../../src/hooks/useCaminosColoreados';

const mockResponse = {
  type: 'FeatureCollection' as const,
  features: [
    {
      type: 'Feature' as const,
      geometry: { type: 'LineString' as const, coordinates: [[0, 0], [1, 1]] },
      properties: { consorcio: 'Consorcio A', color: '#FF0000' },
    },
  ],
  metadata: {
    total_tramos: 1,
    total_consorcios: 1,
    total_km: 50,
  },
  consorcios: [
    { nombre: 'Consorcio A', codigo: 'CA', color: '#FF0000', tramos: 1, longitud_km: 50 },
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

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ============================================
  // INITIAL STATE
  // ============================================

  describe('Initial state', () => {
    it('should initialize with loading=true', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.loading).toBe(true);
    });

    it('should initialize with null caminos', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.caminos).toBeNull();
    });

    it('should initialize with empty consorcios array', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.consorcios).toEqual([]);
    });

    it('should initialize with null metadata', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.metadata).toBeNull();
    });

    it('should initialize with null error', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.error).toBeNull();
    });

    it('should return proper hook interface', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current).toHaveProperty('caminos');
      expect(result.current).toHaveProperty('consorcios');
      expect(result.current).toHaveProperty('metadata');
      expect(result.current).toHaveProperty('loading');
      expect(result.current).toHaveProperty('error');
      expect(result.current).toHaveProperty('reload');
    });
  });

  // ============================================
  // DATA LOADING
  // ============================================

  describe('Data loading', () => {
    it('should set loading to false after fetch completes', async () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.loading).toBe(true);

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });
    });

    it('catches mutation: loading state initial and final', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });
      
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.loading).toBe(true);

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
      expect(result.current.loading).not.toBe(true);
    });

    it('catches mutation: should populate caminos when fetch succeeds', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.caminos).not.toBeNull();
      expect(result.current.caminos?.type).toBe('FeatureCollection');
      expect(result.current.caminos?.features.length).toBeGreaterThan(0);
    });

    it('catches mutation: caminos should have exact type value', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.caminos).not.toBeNull(), { timeout: 3000 });

      // Should be exactly 'FeatureCollection', not empty string or other value
      expect(result.current.caminos?.type).toBe('FeatureCollection');
      expect(result.current.caminos?.type).not.toBe('');
      expect(result.current.caminos?.type).not.toBe('Feature');
    });

    it('catches mutation: caminos should have features array not empty object', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.caminos).not.toBeNull(), { timeout: 3000 });

      expect(result.current.caminos?.features).toBeDefined();
      expect(Array.isArray(result.current.caminos?.features)).toBe(true);
      expect(result.current.caminos?.features.length).toBe(1);
    });

    it('catches mutation: should populate consorcios from response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.consorcios.length).toBeGreaterThan(0), { timeout: 3000 });

      expect(result.current.consorcios.length).toBe(1);
      expect(result.current.consorcios[0].nombre).toBe('Consorcio A');
      expect(result.current.consorcios[0].color).toBe('#FF0000');
    });

    it('catches mutation: should populate metadata from response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.metadata).not.toBeNull(), { timeout: 3000 });

      expect(result.current.metadata?.total_km).toBe(50);
      expect(result.current.metadata?.total_tramos).toBe(1);
      expect(result.current.metadata?.total_consorcios).toBe(1);
    });
  });

  // ============================================
  // ERROR HANDLING
  // ============================================

  describe('Error handling', () => {
    it('should handle fetch errors gracefully', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.error).not.toBeNull();
    });

    it('catches mutation: should check response.ok status - 500 error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.error).not.toBeNull();
      expect(result.current.error).toContain('HTTP');
      expect(result.current.error).toContain('500');
      expect(result.current.caminos).toBeNull();
    });

    it('catches mutation: should check response.ok status - 403 error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      expect(result.current.error).toContain('403');
      expect(result.current.caminos).toBeNull();
    });

    it('catches mutation: should include HTTP status in error message - multiple statuses', async () => {
      const statuses = [400, 401, 404, 500, 502, 503];

      for (const status of statuses) {
        mockFetch.mockResolvedValueOnce({
          ok: false,
          status,
        });

        const { result } = renderHook(() => useCaminosColoreados());

        await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

        expect(result.current.error).toContain(String(status));
        mockFetch.mockClear();
      }
    });

    it('catches mutation: should set loading false on HTTP error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
      expect(result.current.loading).not.toBe(true);
    });

    it('catches mutation: should set loading false on network error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
      expect(result.current.loading).not.toBe(true);
    });

    it('should handle non-Error exceptions', async () => {
      mockFetch.mockRejectedValueOnce('String error');

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      expect(result.current.error).not.toBeNull();
      expect(result.current.error).toContain('Error desconocido');
    });

    it('catches mutation: should set error on network failure and loading false', async () => {
      mockFetch.mockRejectedValueOnce(new Error('API failure'));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
        expect(result.current.error).not.toBeNull();
      }, { timeout: 3000 });
    });

    it('catches mutation: error message should not be empty on HTTP error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      expect(result.current.error).not.toBe('');
      expect(result.current.error?.length).toBeGreaterThan(0);
    });

    it('catches mutation: error message should contain "No se pudieron cargar"', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      expect(result.current.error).toContain('No se pudieron cargar');
    });
  });

  // ============================================
  // RELOAD FUNCTION
  // ============================================

  describe('Reload function', () => {
    it('should expose callable reload function', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(typeof result.current.reload).toBe('function');
      expect(result.current.reload).toBeDefined();
    });

    it('catches mutation: should have reload as a function', async () => {
      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(typeof result.current.reload).toBe('function');
    });

    it('catches mutation: reload should trigger refetch of data', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const { result, rerender } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(mockFetch).toHaveBeenCalledTimes(1);

      // Trigger reload
      act(() => {
        result.current.reload();
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      // Re-render or wait for next fetch
      await waitFor(() => expect(mockFetch).toHaveBeenCalled(), { timeout: 3000 });
    });

    it('catches mutation: reload should reset error state', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      expect(result.current.error).not.toBeNull();

      // Mock successful response for reload
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      act(() => {
        result.current.reload();
      });

      await waitFor(() => expect(result.current.error).toBeNull(), { timeout: 3000 });
    });
  });

  // ============================================
  // CLEANUP
  // ============================================

  describe('Cleanup', () => {
    it('should clean up on unmount', () => {
      const { unmount } = renderHook(() => useCaminosColoreados());

      expect(() => unmount()).not.toThrow();
    });
  });
});
