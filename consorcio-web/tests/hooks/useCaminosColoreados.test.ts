import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';

// Mock API module
vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
}));

// Mock logger
vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
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

let mockFetch: ReturnType<typeof vi.fn>;

describe('useCaminosColoreados', () => {
  beforeEach(() => {
    mockFetch = vi.fn();
    vi.stubGlobal('fetch', mockFetch);
    
    // Set default mock response
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  // ============================================
  // INITIAL STATE
  // ============================================

  describe('Initial state', () => {
    it('should initialize with loading=true (not false)', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      // Catch mutation: useState(true) -> useState(false)
      expect(result.current.loading).toBe(true);
      expect(result.current.loading).not.toBe(false);
    });

    it('should initialize with null caminos', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.caminos).toBeNull();
    });

    it('should initialize with empty consorcios array', () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.consorcios).toEqual([]);
      expect(result.current.consorcios.length).toBe(0);
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

    it('catches mutation: should set loading to false (not true)', async () => {
      const { result } = renderHook(() => useCaminosColoreados());

      expect(result.current.loading).toBe(true);

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      // After load, must be false
      expect(result.current.loading).toBe(false);
      expect(result.current.loading).not.toBe(true);
    });
  });

  // ============================================
  // API URL AND FETCH
  // ============================================

  describe('API URL and fetch', () => {
    it('catches StringLiteral mutation: should use exact API endpoint URL', async () => {
      // Default mock already set in beforeEach
      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      // Verify the exact URL was called (check the first call)
      const calls = mockFetch.mock.calls;
      expect(calls.length).toBeGreaterThan(0);
      expect(calls[0][0]).toBe('http://localhost:8000/api/v1/gee/layers/caminos/coloreados');
    });

    it('catches StringLiteral mutation: should not call with empty URL', async () => {
      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      // Should NOT have empty URL
      expect(mockFetch).not.toHaveBeenCalledWith('');
    });
  });

  // ============================================
  // RESPONSE VALIDATION
  // ============================================

  describe('Response validation', () => {
    it('catches BooleanLiteral mutation: should check response.ok', async () => {
      mockFetch.mockImplementationOnce(() => Promise.resolve({
        ok: false,
        status: 400,
        json: async () => mockResponse,
      }));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      // If response.ok mutation (false -> true) is made, error won't be set
      expect(result.current.error).not.toBeNull();
      expect(result.current.error).toContain('HTTP 400');
    });

    it('catches ConditionalExpression mutation: should error on HTTP 500', async () => {
      mockFetch.mockImplementationOnce(() => Promise.resolve({
        ok: false,
        status: 500,
        json: async () => mockResponse,
      }));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.error).not.toBeNull();
      expect(result.current.error).toContain('HTTP 500');
    });

    it('catches ConditionalExpression mutation: should NOT error on response.ok = true', async () => {
      mockFetch.mockImplementationOnce(() => Promise.resolve({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      }));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.error).toBeNull();
    });

    it('catches StringLiteral mutation: should include status in error message', async () => {
      mockFetch.mockImplementationOnce(() => Promise.resolve({
        ok: false,
        status: 403,
        json: async () => mockResponse,
      }));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      // Must include "HTTP 403"
      expect(result.current.error).toContain('HTTP 403');
    });
  });

  // ============================================
  // FEATURE COLLECTION
  // ============================================

  describe('FeatureCollection structure', () => {
    it('catches StringLiteral mutation: type must be FeatureCollection not empty string', async () => {
      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      if (result.current.caminos) {
        expect(result.current.caminos.type).toBe('FeatureCollection');
        expect(result.current.caminos.type).not.toBe('');
      }
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

    it('catches StringLiteral mutation: should use exact error message prefix', async () => {
      mockFetch.mockRejectedValueOnce(new Error('API Error'));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      // Must start with exact message
      expect(result.current.error).toContain('No se pudieron cargar los caminos:');
    });

    it('catches StringLiteral mutation: should not use empty error prefix', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Test error'));

      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      expect(result.current.error).not.toBe('');
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

    it('should be callable and return a promise', async () => {
      const { result } = renderHook(() => useCaminosColoreados());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockFetch.mockImplementationOnce(() => Promise.resolve({
        ok: true,
        json: async () => mockResponse,
      }));

      const reloadResult = result.current.reload();
      expect(reloadResult instanceof Promise).toBe(true);

      await reloadResult;
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
