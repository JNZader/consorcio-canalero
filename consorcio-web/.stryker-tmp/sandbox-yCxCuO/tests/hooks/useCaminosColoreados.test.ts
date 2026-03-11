// @ts-nocheck
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';

// Mock fetch globally BEFORE importing the hook
global.fetch = vi.fn();
const mockFetch = global.fetch as any;

// Mock API module
vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
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

    it('catches mutation: should set loading when initialization complete', async () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.loading).toBe(true);

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
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

    it('should handle HTTP response errors', async () => {
      mockFetch.mockImplementationOnce(() => Promise.resolve({
        ok: false,
        status: 500,
      }));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.error).not.toBeNull();
    });

    it('catches mutation: should set loading false on error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
    });

    it('should handle non-Error exceptions', async () => {
      mockFetch.mockRejectedValueOnce('String error');

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      expect(result.current.error).not.toBeNull();
    });
  });

  // ============================================
  // RELOAD FUNCTION
  // ============================================

  describe('Reload function', () => {
    it('should expose callable reload function', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(typeof result.current.reload).toBe('function');
    });

    it('catches mutation: should have reload as a function', async () => {
      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(typeof result.current.reload).toBe('function');
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
