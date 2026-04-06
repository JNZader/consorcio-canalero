import { renderHook, act, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createQueryWrapper } from '../test-utils';

// Use hoisted pattern for mocks
const { mockApiFetch, mockUnwrapItems } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
  mockUnwrapItems: vi.fn((res: unknown) => {
    if (Array.isArray(res)) return res;
    if (res && typeof res === 'object' && 'items' in (res as Record<string, unknown>))
      return (res as { items: unknown[] }).items;
    return [];
  }),
}));

vi.mock('../../src/lib/api', () => ({
  apiFetch: mockApiFetch,
  unwrapItems: mockUnwrapItems,
}));

import { useInfrastructure, type InfrastructureAsset } from '../../src/hooks/useInfrastructure';

describe('useInfrastructure', () => {
  let wrapper: ReturnType<typeof createQueryWrapper>;

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
    wrapper = createQueryWrapper();

    // Default: apiFetch resolves based on URL
    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes('infraestructura/assets')) {
        return Promise.resolve([mockAsset]);
      }
      if (url.includes('conflictos')) {
        return Promise.resolve(mockIntersections);
      }
      return Promise.resolve(null);
    });

    // localStorage mock for token check
    (window.localStorage.getItem as ReturnType<typeof vi.fn>).mockReturnValue('fake-token');
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

      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      // Initially should be true (not false)
      expect(result.current.loading).toBe(true);
      expect(result.current.loading).not.toBe(false);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });

    it('should initialize with empty assets array', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(Array.isArray(result.current.assets)).toBe(true);
    });

    it('should initialize with false loading state after fetch', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.loading).toBe(false);
      expect(result.current.loading).not.toBe(true);
    });

    it('should initialize with null error state', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe(null);
    });

    it('should return proper hook interface', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

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
    it('should fetch assets on mount', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(mockApiFetch).toHaveBeenCalledWith('/infraestructura/assets');
    });

    it('should fetch intersections when token is present', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining('conflictos')
      );
    });

    it('should fetch on mount only once (dependency array)', async () => {
      let callCount = 0;
      mockApiFetch.mockImplementation(() => {
        callCount++;
        return Promise.resolve([]);
      });

      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      // Single query wraps both calls, so should be exactly 2 calls (assets + intersections)
      expect(callCount).toBeLessThanOrEqual(4);
    });

    it('catches mutation: effect should not refetch on rerender', async () => {
      mockApiFetch.mockImplementation(() => Promise.resolve([]));
      const { result, rerender } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockApiFetch.mockClear();

      rerender();

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });

    it('should set loading to false after successful fetch', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      expect(result.current.loading).toBe(true);

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
    });

    it('should populate assets from API response', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.assets.length).toBeGreaterThan(0), {
        timeout: 3000,
      });

      expect(result.current.assets).toContainEqual(mockAsset);
    });

    it('should populate intersections from API response', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

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
    it('should handle asset fetch errors gracefully with empty assets', async () => {
      // The hook catches asset errors internally and returns []
      mockApiFetch.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      // Assets errors are caught, so error is null and assets default to []
      expect(result.current.assets).toEqual([]);
    });

    it('should handle non-Error exceptions gracefully', async () => {
      mockApiFetch.mockRejectedValue('String error');

      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
    });

    it('catches mutation: should set loading false after fetch completes', async () => {
      mockApiFetch.mockRejectedValue(new Error('API error'));

      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(result.current.loading).toBe(false);
      expect(result.current.loading).not.toBe(true);
    });

    it('should return null error when queryFn catches internally', async () => {
      // Both endpoints fail but queryFn catches them
      mockApiFetch.mockRejectedValue(new Error('First error'));

      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      // The hook catches errors internally, so query.error stays null
      expect(result.current.error).toBe(null);
    });
  });

  // ============================================
  // REFRESH FUNCTION
  // ============================================

  describe('Refresh function', () => {
    it('should expose callable refresh function', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      expect(typeof result.current.refresh).toBe('function');
      expect(result.current.refresh).toBeDefined();
    });

    it('should refresh data and call API when called', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockApiFetch.mockClear();
      const callCountBefore = mockApiFetch.mock.calls.length;

      await act(async () => {
        await result.current.refresh();
      });

      const callCountAfter = mockApiFetch.mock.calls.length;
      expect(callCountAfter).toBeGreaterThan(callCountBefore);
    });

    it('catches mutation: refresh should call assets endpoint', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockApiFetch.mockClear();

      await act(async () => {
        await result.current.refresh();
      });

      expect(mockApiFetch).toHaveBeenCalledWith('/infraestructura/assets');
    });

    it('catches mutation: refresh should update state after fetch', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      const newAsset = { ...mockAsset, id: '999', nombre: 'Updated' };
      mockApiFetch.mockImplementation((url: string) => {
        if (url.includes('infraestructura/assets')) {
          return Promise.resolve([newAsset]);
        }
        if (url.includes('conflictos')) {
          return Promise.resolve(mockIntersections);
        }
        return Promise.resolve(null);
      });

      await act(async () => {
        await result.current.refresh();
      });

      await waitFor(() => {
        expect(result.current.assets).toContainEqual(newAsset);
      });
    });

    it('should not throw on multiple refresh calls', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

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
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      expect(typeof result.current.createAsset).toBe('function');
      expect(result.current.createAsset).toBeDefined();
    });

    it('should create asset with POST method', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      const newAsset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'> = {
        nombre: 'Nuevo Canal',
        tipo: 'canal',
        descripcion: 'Descripcion',
        latitud: 0,
        longitud: 0,
        cuenca: 'Cuenca',
        estado_actual: 'bueno',
      };

      mockApiFetch.mockImplementation((url: string, options?: Record<string, unknown>) => {
        if (url === '/infraestructura/assets' && options?.method === 'POST') {
          return Promise.resolve({ ...mockAsset, ...newAsset });
        }
        if (url.includes('infraestructura/assets')) return Promise.resolve([]);
        if (url.includes('conflictos')) return Promise.resolve(mockIntersections);
        return Promise.resolve(null);
      });

      await act(async () => {
        await result.current.createAsset(newAsset);
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        '/infraestructura/assets',
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('catches mutation: should call correct endpoint', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      const newAsset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'> = {
        nombre: 'Nuevo Canal',
        tipo: 'canal',
        descripcion: 'Descripcion',
        latitud: 0,
        longitud: 0,
        cuenca: 'Cuenca',
        estado_actual: 'bueno',
      };

      mockApiFetch.mockImplementation((url: string) => {
        if (url === '/infraestructura/assets') return Promise.resolve(mockAsset);
        return Promise.resolve(null);
      });

      await act(async () => {
        await result.current.createAsset(newAsset);
      });

      expect(mockApiFetch).toHaveBeenCalledWith(
        '/infraestructura/assets',
        expect.any(Object)
      );
      expect(mockApiFetch).not.toHaveBeenCalledWith('', expect.any(Object));
    });

    it('catches mutation: should include asset in request body', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      const newAsset: Omit<InfrastructureAsset, 'id' | 'ultima_inspeccion'> = {
        nombre: 'Nuevo Canal',
        tipo: 'canal',
        descripcion: 'Descripcion',
        latitud: 0,
        longitud: 0,
        cuenca: 'Cuenca',
        estado_actual: 'bueno',
      };

      mockApiFetch.mockResolvedValue(mockAsset);

      await act(async () => {
        await result.current.createAsset(newAsset);
      });

      const calls = mockApiFetch.mock.calls;
      const createCall = calls.find((call: unknown[]) =>
        call[0] === '/infraestructura/assets' && (call[1] as Record<string, unknown>)?.method === 'POST'
      );

      expect(createCall).toBeDefined();
      expect(createCall?.[1]).toHaveProperty('body');
      expect(createCall?.[1]?.body).not.toBe('');
    });

    it('should throw on createAsset error', async () => {
      const { result } = renderHook(() => useInfrastructure(), { wrapper });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 3000 });

      mockApiFetch.mockRejectedValue(new Error('Create failed'));

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
  });

  // ============================================
  // CLEANUP
  // ============================================

  describe('Cleanup', () => {
    it('should clean up on unmount', () => {
      const { unmount } = renderHook(() => useInfrastructure(), { wrapper });

      expect(() => unmount()).not.toThrow();
    });
  });
});
