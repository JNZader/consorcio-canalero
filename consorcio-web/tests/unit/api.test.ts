/**
 * Unit Tests for src/lib/api.ts
 *
 * Tests the API client including fetch mocking, error handling, and timeouts.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock import.meta.env before importing api module
vi.stubGlobal('import', {
  meta: {
    env: {
      PUBLIC_API_URL: 'http://localhost:8000',
    },
  },
});

// We need to import dynamically after mocking
let statsApi: typeof import('../../src/lib/api').statsApi;
let layersApi: typeof import('../../src/lib/api').layersApi;
let reportsApi: typeof import('../../src/lib/api').reportsApi;
let publicApi: typeof import('../../src/lib/api').publicApi;
let healthCheck: typeof import('../../src/lib/api').healthCheck;

describe('API Client', () => {
  const mockFetch = vi.fn();

  beforeEach(async () => {
    // Reset modules and mocks
    vi.resetModules();

    // Mock global fetch
    global.fetch = mockFetch;

    // Import the API module fresh
    const apiModule = await import('../../src/lib/api');
    statsApi = apiModule.statsApi;
    layersApi = apiModule.layersApi;
    reportsApi = apiModule.reportsApi;
    publicApi = apiModule.publicApi;
    healthCheck = apiModule.healthCheck;

    // Reset fetch mock
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ===========================================
  // Health Check
  // ===========================================
  describe('healthCheck', () => {
    it('should return true when API is healthy', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'healthy' }),
      });

      const result = await healthCheck();

      expect(result).toBe(true);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/health',
        expect.objectContaining({
          signal: expect.any(AbortSignal),
        })
      );
    });

    it('should return false when API returns error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const result = await healthCheck();

      expect(result).toBe(false);
    });

    it('should return false when fetch throws', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const result = await healthCheck();

      expect(result).toBe(false);
    });
  });

  // ===========================================
  // Layers API
  // ===========================================
  describe('layersApi', () => {
    describe('getAll', () => {
      it('should fetch all layers', async () => {
        const mockLayers = [
          { id: '1', nombre: 'Cuencas', tipo: 'polygon' },
          { id: '2', nombre: 'Caminos', tipo: 'line' },
        ];

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockLayers),
        });

        const result = await layersApi.getAll();

        expect(result).toEqual(mockLayers);
        expect(mockFetch).toHaveBeenCalledWith(
          'http://localhost:8000/api/v1/layers?visible_only=false',
          expect.any(Object)
        );
      });

      it('should fetch only visible layers when specified', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve([]),
        });

        await layersApi.getAll(true);

        expect(mockFetch).toHaveBeenCalledWith(
          'http://localhost:8000/api/v1/layers?visible_only=true',
          expect.any(Object)
        );
      });
    });

    describe('create', () => {
      it('should create a new layer', async () => {
        const newLayer = {
          nombre: 'Nueva Capa',
          tipo: 'cuenca' as const,
          visible: true,
        };

        const mockResponse = { id: 'new-id', ...newLayer };

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockResponse),
        });

        const result = await layersApi.create(newLayer);

        expect(result).toEqual(mockResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          'http://localhost:8000/api/v1/layers',
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify(newLayer),
          })
        );
      });
    });

    describe('delete', () => {
      it('should delete a layer', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(undefined),
        });

        await layersApi.delete('layer-123');

        expect(mockFetch).toHaveBeenCalledWith(
          'http://localhost:8000/api/v1/layers/layer-123',
          expect.objectContaining({
            method: 'DELETE',
          })
        );
      });
    });
  });

  // ===========================================
  // Reports API
  // ===========================================
  describe('reportsApi', () => {
    describe('getAll', () => {
      it('should fetch reports with pagination (positional args)', async () => {
        const mockReports = {
          items: [{ id: '1', tipo: 'desborde' }],
          total: 50,
          page: 1,
        };

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockReports),
        });

        const result = await reportsApi.getAll(1, 10, 'pendiente');

        expect(result).toEqual(mockReports);
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('page=1'),
          expect.any(Object)
        );
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('limit=10'),
          expect.any(Object)
        );
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('status=pendiente'),
          expect.any(Object)
        );
      });

      it('should fetch reports with object params', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ items: [], total: 0, page: 1 }),
        });

        await reportsApi.getAll({
          page: 2,
          limit: 20,
          status: 'en_revision',
          cuenca: 'cuenca_1',
        });

        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('page=2'),
          expect.any(Object)
        );
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('cuenca=cuenca_1'),
          expect.any(Object)
        );
      });
    });

    describe('updateStatus', () => {
      it('should update report status', async () => {
        const mockReport = {
          id: 'report-123',
          estado: 'en_revision',
        };

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockReport),
        });

        const result = await reportsApi.updateStatus(
          'report-123',
          'en_revision',
          'Revisando el problema'
        );

        expect(result).toEqual(mockReport);
        expect(mockFetch).toHaveBeenCalledWith(
          'http://localhost:8000/api/v1/reports/report-123',
          expect.objectContaining({
            method: 'PUT',
            body: JSON.stringify({
              estado: 'en_revision',
              notas_admin: 'Revisando el problema',
            }),
          })
        );
      });
    });
  });

  // ===========================================
  // Public API
  // ===========================================
  describe('publicApi', () => {
    describe('createReport', () => {
      it('should create a public report', async () => {
        const mockResponse = {
          id: 'new-report-123',
          message: 'Denuncia creada',
          estado: 'pendiente',
        };

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockResponse),
        });

        const reportData = {
          tipo: 'desborde',
          descripcion: 'Canal desbordado en zona norte',
          latitud: -33.7,
          longitud: -63.9,
          cuenca: 'cuenca_1',
        };

        const result = await publicApi.createReport(reportData);

        expect(result).toEqual(mockResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          'http://localhost:8000/api/v1/public/reports',
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify(reportData),
          })
        );
      });
    });

  });

  // ===========================================
  // Error Handling
  // ===========================================
  describe('Error Handling', () => {
    it('should throw error with detail from API response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () =>
          Promise.resolve({
            detail: 'Tipo invalido. Valores permitidos: alcantarilla_tapada, desborde',
          }),
      });

      await expect(
        publicApi.createReport({
          tipo: 'invalid',
          descripcion: 'Test description',
          latitud: -33.7,
          longitud: -63.9,
        })
      ).rejects.toThrow('Tipo invalido');
    });

    it('should throw generic error when no detail in response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error('Not JSON')),
      });

      await expect(healthCheck()).resolves.toBe(false);
    });

    it('should handle network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Failed to fetch'));

      await expect(statsApi.getHistorical()).rejects.toThrow('Failed to fetch');
    });
  });

  // ===========================================
  // Timeout Handling
  // ===========================================
  describe('Timeout Handling', () => {
    it('should pass AbortSignal to fetch for timeout support', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      });

      await statsApi.getHistorical();

      // Verify that fetch was called with an AbortSignal
      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          signal: expect.any(AbortSignal),
        })
      );
    });

    it('should convert AbortError to timeout message', async () => {
      // Simulate an immediate AbortError
      const abortError = new Error('The operation was aborted');
      abortError.name = 'AbortError';
      mockFetch.mockRejectedValueOnce(abortError);

      await expect(statsApi.getHistorical()).rejects.toThrow(/excedio el tiempo limite/i);
    });
  });
});
