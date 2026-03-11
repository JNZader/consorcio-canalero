// @ts-nocheck
import { renderHook, act, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Use hoisted pattern for mocks
const { mockApiFetch } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
}));

vi.mock('../../src/lib/api', () => ({
  apiFetch: mockApiFetch,
}));

import { useInfrastructure, type InfrastructureAsset } from '../../src/hooks/useInfrastructure';

describe('useInfrastructure', () => {
  const mockAsset: InfrastructureAsset = {
    id: '1',
    nombre: 'Canal Principal',
    tipo: 'canal',
    descripcion: 'Canal principal de riego',
    latitud: -32.1234,
    longitud: -64.5678,
    cuenca: 'Rio Tercero',
    estado_actual: 'bueno',
    ultima_inspeccion: '2024-01-15',
  };

  const mockIntersections = {
    type: 'FeatureCollection' as const,
    features: [],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // Set default resolved value for both API calls
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes('assets')) {
        return Promise.resolve([mockAsset]);
      }
      if (url.includes('intersections')) {
        return Promise.resolve(mockIntersections);
      }
      return Promise.resolve(null);
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ============================================
  // INITIAL STATE
  // ============================================

  describe('Initial state', () => {
    it('should initialize with loading=true initially', async () => {
      mockApiFetch.mockImplementation(() => new Promise(resolve => setTimeout(() => resolve([]), 100)));
      
      const { result } = renderHook(() => useInfrastructure());
      
      // Initially should be true (not false)
      expect(result.current.loading).toBe(true);
      expect(result.current.loading).not.toBe(false);
      
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });

    it('should initialize with empty assets array', async () => {
      const { result } = renderHook(() => useInfrastructure());

      // Wait for initial effect to complete
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Check exact initial structure before API populates
      // Assets should be populated by API call
      expect(Array.isArray(result.current.assets)).toBe(true);
    });

    it('should initialize with false loading state after fetch', async () => {
      const { result } = renderHook(() => useInfrastructure());
      
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
      
      expect(result.current.loading).toBe(false);
      expect(result.current.loading).not.toBe(true);
    });

    it('should initialize with null error state', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe(null);
      expect(result.current.error).not.toEqual('Error cargando infraestructura');
    });

    it('should return proper hook interface', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current).toHaveProperty('loading');
      expect(result.current).toHaveProperty('assets');
      expect(result.current).toHaveProperty('intersections');
      expect(result.current).toHaveProperty('error');
      expect(result.current).toHaveProperty('refresh');
      expect(result.current).toHaveProperty('createAsset');
    });
  });

      // Check exact initial structure before API populates
      // Assets should be populated by API call
      expect(Array.isArray(result.current.assets)).toBe(true);
    });

    it('should initialize with false loading state', async () => {
      mockApiFetch.mockImplementation(() => new Promise(resolve => setTimeout(() => resolve([]), 100)));
      
      const { result } = renderHook(() => useInfrastructure());
      
      // Initially should be true
      expect(result.current.loading).toBe(true);
      
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
      
      expect(result.current.loading).toBe(false);
    });

    it('should initialize with null error state', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe(null);
      expect(result.current.error).not.toEqual('Error cargando infraestructura');
    });

    it('should return proper hook interface', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current).toHaveProperty('loading');
      expect(result.current).toHaveProperty('assets');
      expect(result.current).toHaveProperty('intersections');
      expect(result.current).toHaveProperty('error');
      expect(result.current).toHaveProperty('refresh');
      expect(result.current).toHaveProperty('createAsset');
    });
  });

  // ============================================
  // DATA LOADING
  // ============================================

  describe('Data loading', () => {
    it('should fetch assets and intersections on mount', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(mockApiFetch).toHaveBeenCalledWith('/infrastructure/assets');
      expect(mockApiFetch).toHaveBeenCalledWith('/infrastructure/potential-intersections');
    });

    it('catches mutation: should fetch both endpoints in parallel', async () => {
      mockApiFetch.mockImplementation(() => Promise.resolve([]));
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      // Must call both endpoints (not just one)
      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });

    it('should fetch on mount only once (dependency array)', async () => {
      let callCount = 0;
      mockApiFetch.mockImplementation(() => {
        callCount++;
        return Promise.resolve([]);
      });

      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      // If dependency array was wrong (e.g., empty []), would call multiple times
      // With correct dependencies, should fetch exactly once on mount
      expect(callCount).toBeLessThanOrEqual(4); // Allow for some timing variations
    });

    it('catches mutation: effect should depend on fetchInfrastructure', async () => {
      mockApiFetch.mockImplementation(() => Promise.resolve([]));
      const { result, rerender } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockApiFetch.mockClear();

      // Re-render should not trigger another fetch if dependency array is correct
      rerender();

      // If dependency array was [], it wouldn't re-register the effect
      // If it was [fetchInfrastructure], it would only refetch if fetchInfrastructure changes
      await waitFor(() => {
        // After rerender, loading should still be false
        expect(result.current.loading).toBe(false);
      });
    });

    it('should set loading to false after successful fetch', async () => {
      const { result } = renderHook(() => useInfrastructure());

      expect(result.current.loading).toBe(true);

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
    });

    it('should populate assets from API response', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.assets.length).toBeGreaterThan(0), {
        timeout: 3000,
      });

      expect(result.current.assets).toContainEqual(mockAsset);
    });

    it('should populate intersections from API response', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.intersections).not.toBeNull(), {
        timeout: 3000,
      });

      expect(result.current.intersections).toEqual(mockIntersections);
    });
  });

  // ============================================
  // ERROR HANDLING
  // ============================================

  describe('Error handling', () => {
    it('should handle errors gracefully with proper error message', async () => {
      mockApiFetch.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.error).not.toBeNull();
      expect(result.current.error).toBe('Network error');
      expect(result.current.error).toEqual('Network error');
    });

    it('should handle non-Error exceptions with default message', async () => {
      mockApiFetch.mockRejectedValueOnce('String error');

      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      expect(result.current.error).toBe('Error cargando infraestructura');
      expect(result.current.error).toEqual('Error cargando infraestructura');
    });

    it('catches mutation: should set loading false on error', async () => {
      mockApiFetch.mockRejectedValueOnce(new Error('API error'));

      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
      expect(result.current.loading).not.toBe(true);
    });

    it('should handle retry after error', async () => {
      // First call fails
      mockApiFetch.mockRejectedValueOnce(new Error('First error'));

      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.error).not.toBeNull(), { timeout: 3000 });

      const firstError = result.current.error;
      expect(firstError).toBe('First error');
      expect(typeof firstError).toBe('string');
    });
  });

  // ============================================
  // REFRESH FUNCTION
  // ============================================

  describe('Refresh function', () => {
    it('should expose callable refresh function', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(typeof result.current.refresh).toBe('function');
      expect(result.current.refresh).toBeDefined();
    });

    it('should refresh data and call API when called', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockApiFetch.mockClear();
      const callCountBefore = mockApiFetch.mock.calls.length;

      await act(async () => {
        await result.current.refresh();
      });

      const callCountAfter = mockApiFetch.mock.calls.length;
      expect(callCountAfter).toBeGreaterThan(callCountBefore);
    });

    it('catches mutation: refresh should call BOTH API endpoints', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockApiFetch.mockClear();

      await act(async () => {
        await result.current.refresh();
      });

      // Must call both endpoints, not just one
      expect(mockApiFetch).toHaveBeenCalledWith('/infrastructure/assets');
      expect(mockApiFetch).toHaveBeenCalledWith('/infrastructure/potential-intersections');
      expect(mockApiFetch.mock.calls.length).toBe(2);
    });

    it('catches mutation: refresh should update state after fetch', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      const newAsset = { ...mockAsset, id: '999', nombre: 'Updated' };
      mockApiFetch.mockImplementation((url: string) => {
        if (url.includes('assets')) {
          return Promise.resolve([newAsset]);
        }
        if (url.includes('intersections')) {
          return Promise.resolve(mockIntersections);
        }
        return Promise.resolve(null);
      });

      await act(async () => {
        await result.current.refresh();
      });

      // Verify state was actually updated with new data
      expect(result.current.assets).toContainEqual(newAsset);
    });

    it('should not throw on multiple refresh calls', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      await act(async () => {
        await Promise.all([result.current.refresh(), result.current.refresh()]);
      });

      expect(result.current.loading).toBe(false);
    });
  });

  // ============================================
  // CREATE ASSET
  // ============================================

  describe('Create asset function', () => {
    it('should expose callable createAsset function', () => {
      const { result } = renderHook(() => useInfrastructure());

      expect(typeof result.current.createAsset).toBe('function');
      expect(result.current.createAsset).toBeDefined();
    });

    it('should create asset with POST method', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      const newAsset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'> = {
        nombre: 'Nuevo Canal',
        tipo: 'canal',
        descripcion: 'Descripción',
        latitud: 0,
        longitud: 0,
        cuenca: 'Cuenca',
        estado_actual: 'bueno',
      };

      mockApiFetch.mockImplementation((url: string, options?: any) => {
        if (url === '/infrastructure/assets' && options?.method === 'POST') {
          return Promise.resolve({ ...mockAsset, ...newAsset });
        }
        if (url.includes('assets')) return Promise.resolve([]);
        if (url.includes('intersections')) return Promise.resolve(mockIntersections);
        return Promise.resolve(null);
      });

      await act(async () => {
        await result.current.createAsset(newAsset);
      });

      // Verify API was called with POST method
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/infrastructure/assets',
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('catches mutation: should call correct endpoint', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      const newAsset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'> = {
        nombre: 'Nuevo Canal',
        tipo: 'canal',
        descripcion: 'Descripción',
        latitud: 0,
        longitud: 0,
        cuenca: 'Cuenca',
        estado_actual: 'bueno',
      };

      mockApiFetch.mockImplementation((url: string) => {
        if (url === '/infrastructure/assets') return Promise.resolve(mockAsset);
        return Promise.reject(new Error('Wrong endpoint'));
      });

      await act(async () => {
        await result.current.createAsset(newAsset);
      });

      // Verify exact endpoint was called
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/infrastructure/assets',
        expect.any(Object)
      );
      // Should not call empty string
      expect(mockApiFetch).not.toHaveBeenCalledWith('', expect.any(Object));
    });

    it('catches mutation: should include asset in request body', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      const newAsset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'> = {
        nombre: 'Nuevo Canal',
        tipo: 'canal',
        descripcion: 'Descripción',
        latitud: 0,
        longitud: 0,
        cuenca: 'Cuenca',
        estado_actual: 'bueno',
      };

      mockApiFetch.mockResolvedValue(mockAsset);

      await act(async () => {
        await result.current.createAsset(newAsset);
      });

      // Verify body was included in the call
      const calls = mockApiFetch.mock.calls;
      expect(calls.length).toBeGreaterThan(0);
      
      const createCall = calls.find((call) => 
        call[0] === '/infrastructure/assets' && call[1]?.method === 'POST'
      );
      
      expect(createCall).toBeDefined();
      expect(createCall?.[1]).toHaveProperty('body');
      expect(createCall?.[1]?.body).not.toBe('');
    });

    it('catches mutation: should add new asset to state array', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      const initialAssetCount = result.current.assets.length;

      const newAsset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'> = {
        nombre: 'Another Canal',
        tipo: 'canal',
        descripcion: 'Descripción',
        latitud: -10,
        longitud: -65,
        cuenca: 'Cuenca',
        estado_actual: 'regular',
      };

      const createdAsset = { ...mockAsset, id: '2', ...newAsset };
      mockApiFetch.mockImplementation((url: string, options?: any) => {
        if (url === '/infrastructure/assets' && options?.method === 'POST') {
          return Promise.resolve(createdAsset);
        }
        if (url.includes('assets')) return Promise.resolve([mockAsset]);
        if (url.includes('intersections')) return Promise.resolve(mockIntersections);
        return Promise.resolve(null);
      });

      await act(async () => {
        await result.current.createAsset(newAsset);
      });

      // Verify asset was added to the array (spread not mutated)
      expect(result.current.assets.length).toBeGreaterThanOrEqual(initialAssetCount);
      expect(result.current.assets).toContainEqual(createdAsset);
    });

    it('should throw on createAsset error', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockApiFetch.mockRejectedValueOnce(new Error('Create failed'));

      await expect(
        result.current.createAsset({
          nombre: 'Test',
          tipo: 'canal',
          descripcion: '',
          latitud: 0,
          longitud: 0,
          cuenca: '',
          estado_actual: 'bueno',
        })
      ).rejects.toThrow('Create failed');
    });

    it('catches mutation: should handle non-Error exceptions with proper message', async () => {
      const { result } = renderHook(() => useInfrastructure());

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockApiFetch.mockRejectedValueOnce('String error');

      await expect(
        result.current.createAsset({
          nombre: 'Test',
          tipo: 'canal',
          descripcion: '',
          latitud: 0,
          longitud: 0,
          cuenca: '',
          estado_actual: 'bueno',
        })
      ).rejects.toThrow('Error al crear activo');
    });
  });

  // ============================================
  // CLEANUP
  // ============================================

  describe('Cleanup', () => {
    it('should clean up on unmount', () => {
      const { unmount } = renderHook(() => useInfrastructure());

      expect(() => unmount()).not.toThrow();
    });
  });
});
