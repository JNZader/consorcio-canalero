import type { FeatureCollection } from 'geojson';
import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  useAssetCreationHandler,
  useMapExportHandlers,
  useZoningHandlers,
} from '../../src/components/map2d/useMapActionHandlers';

const notificationsShow = vi.fn();
const getAuthTokenMock = vi.fn();

vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: (...args: unknown[]) => notificationsShow(...args),
  },
}));

vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
  getAuthToken: (...args: unknown[]) => getAuthTokenMock(...args),
}));

describe('useMapActionHandlers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getAuthTokenMock.mockResolvedValue('token-123');
  });

  it('exports PNG and closes the modal', () => {
    const click = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElement = vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      if (tagName === 'a') {
        return {
          click,
          href: '',
          download: '',
        } as unknown as HTMLElement;
      }
      return originalCreateElement(tagName);
    }) as typeof document.createElement);

    const setExportPngModalOpen = vi.fn();
    const mapRef = {
      current: {
        getCanvas: () => ({ toDataURL: () => 'data:image/png;base64,mock' }),
      },
    } as const;

    const { result } = renderHook(() =>
      useMapExportHandlers({
        mapRef,
        exportTitle: 'Mapa Test',
        setExportPngModalOpen,
        approvedZones: null,
      }),
    );

    act(() => {
      result.current.handleExportPng();
    });

    expect(click).toHaveBeenCalledTimes(1);
    expect(setExportPngModalOpen).toHaveBeenCalledWith(false);
    expect(notificationsShow).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Exportación completada', color: 'green' }),
    );

    createElement.mockRestore();
  });

  it('sends the ApprovedZonesMapPdfRequest payload shape expected by the backend', async () => {
    const click = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElement = vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      if (tagName === 'a') {
        return { click, href: '', download: '' } as unknown as HTMLElement;
      }
      return originalCreateElement(tagName);
    }) as typeof document.createElement);
    const createObjectURL = vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:test');
    const revokeObjectURL = vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {});

    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['pdf']),
    } as Response);

    try {
      const approvedZones: FeatureCollection = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
            properties: {
              nombre: 'Zona Norte',
              basin_count: 3,
              superficie_ha: 1234.56,
              __color: '#9C27B0',
            },
          },
        ],
      };

      const mapRef = {
        current: {
          getCanvas: () => ({ toDataURL: () => 'data:image/png;base64,REALBASE64==' }),
        },
      } as const;

      const { result } = renderHook(() =>
        useMapExportHandlers({
          mapRef,
          exportTitle: 'Mapa Aprobado',
          approvalName: 'Zonificación v3',
          setExportPngModalOpen: vi.fn(),
          approvedZones,
          activeLegendItems: [
            { color: '#9C27B0', label: 'Zona Norte', type: 'fill' },
            { color: '#FF0000', label: 'Zona Consorcio', type: 'border' },
          ],
          consorcios: [
            { codigo: 'C1', nombre: 'Caminero Uno', color: '#111111', longitud_km: 12.34 },
          ],
          visibleRasterLayers: [{ tipo: 'terrain_class' }, { tipo: 'flood_risk' }],
          hiddenClasses: {},
          hiddenRanges: {},
        }),
      );

      await act(async () => {
        await result.current.handleExportApprovedZonesPdf();
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toMatch(/\/api\/v2\/geo\/basins\/approved-zones\/current\/export-map-pdf$/);
      expect(init?.method).toBe('POST');
      const body = JSON.parse(init?.body as string) as Record<string, unknown>;

      // Must send the camelCase contract the backend expects.
      expect(typeof body.title).toBe('string');
      expect((body.title as string).length).toBeGreaterThan(0);
      expect(typeof body.mapImageDataUrl).toBe('string');
      expect(body.mapImageDataUrl as string).toMatch(/^data:image\/png;base64,/);
      expect(Array.isArray(body.zoneLegend)).toBe(true);
      expect(Array.isArray(body.roadLegend)).toBe(true);
      expect(Array.isArray(body.rasterLegends)).toBe(true);
      expect(Array.isArray(body.infoRows)).toBe(true);
      expect(Array.isArray(body.zoneSummary)).toBe(true);

      // Must NOT send the legacy buggy keys.
      expect(body).not.toHaveProperty('features');
      expect(body).not.toHaveProperty('map_snapshot');

      // Content spot-checks.
      expect(body.zoneLegend).toContainEqual(
        expect.objectContaining({ label: 'Zona Norte', color: '#9C27B0' }),
      );
      expect(body.roadLegend).toContainEqual(
        expect.objectContaining({ label: expect.stringContaining('Caminero Uno') }),
      );
      expect(body.zoneSummary).toContainEqual(
        expect.objectContaining({ name: 'Zona Norte', subcuencas: 3 }),
      );
    } finally {
      createElement.mockRestore();
      createObjectURL.mockRestore();
      revokeObjectURL.mockRestore();
      fetchMock.mockRestore();
    }
  });

  it('exports approved zones as PDF and GeoJSON', async () => {
    const click = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElement = vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      if (tagName === 'a') {
        return {
          click,
          href: '',
          download: '',
        } as unknown as HTMLElement;
      }
      return originalCreateElement(tagName);
    }) as typeof document.createElement);
    const createObjectURL = vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:test');
    const revokeObjectURL = vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {});
    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['pdf']),
    } as Response);

    const approvedZones: FeatureCollection = {
      type: 'FeatureCollection',
      features: [],
    };

    const mapRef = {
      current: {
        getCanvas: () => ({ toDataURL: () => 'data:image/png;base64,mock' }),
      },
    } as const;

    const { result } = renderHook(() =>
      useMapExportHandlers({
        mapRef,
        exportTitle: 'Mapa Test',
        setExportPngModalOpen: vi.fn(),
        approvedZones,
      }),
    );

    await act(async () => {
      await result.current.handleExportApprovedZonesPdf();
    });

    expect(fetchMock).toHaveBeenCalled();
    expect(click).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.handleExportApprovedZonesGeoJSON();
    });

    expect(click).toHaveBeenCalledTimes(2);
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();

    createElement.mockRestore();
    createObjectURL.mockRestore();
    revokeObjectURL.mockRestore();
    fetchMock.mockRestore();
  });

  it('creates infrastructure assets and resets state on success', async () => {
    const createAsset = vi.fn().mockResolvedValue({});
    const setIsSubmitting = vi.fn();
    const setNewPoint = vi.fn();
    const setMarkingMode = vi.fn();
    const resetForm = vi.fn();

    const { result } = renderHook(() =>
      useAssetCreationHandler({
        newPoint: { lat: -32.6, lng: -62.6 },
        createAsset,
        setIsSubmitting,
        setNewPoint,
        setMarkingMode,
        resetForm,
      }),
    );

    await act(async () => {
      await result.current({ nombre: 'Puente 1', tipo: 'puente', descripcion: '' });
    });

    expect(createAsset).toHaveBeenCalledWith(
      expect.objectContaining({
        nombre: 'Puente 1',
        tipo: 'puente',
        latitud: -32.6,
        longitud: -62.6,
        estado_actual: 'bueno',
      }),
    );
    expect(setNewPoint).toHaveBeenCalledWith(null);
    expect(setMarkingMode).toHaveBeenCalledWith(false);
    expect(resetForm).toHaveBeenCalled();
  });

  it('approves, clears and reapplies zoning assignments', async () => {
    const saveApprovedZones = vi.fn().mockResolvedValue({});
    const clearApprovedZones = vi.fn().mockResolvedValue({});
    const setDraftBasinAssignments = vi.fn();
    const setSelectedDraftBasinId = vi.fn();
    const setDraftDestinationZoneId = vi.fn();

    const suggestedZonesDisplay: FeatureCollection = {
      type: 'FeatureCollection',
      features: [],
    };

    const { result } = renderHook(() =>
      useZoningHandlers({
        suggestedZonesDisplay,
        effectiveBasinAssignments: { b1: 'z1' },
        suggestedZoneNames: { z1: 'Zona 1' },
        approvalName: 'Versión A',
        approvalNotes: 'Notas',
        saveApprovedZones,
        clearApprovedZones,
        selectedDraftBasinId: 'b1',
        draftDestinationZoneId: 'z2',
        setDraftBasinAssignments,
        setSelectedDraftBasinId,
        setDraftDestinationZoneId,
      }),
    );

    await act(async () => {
      await result.current.handleApproveZones();
    });
    expect(saveApprovedZones).toHaveBeenCalledWith(
      suggestedZonesDisplay,
      expect.objectContaining({ nombre: 'Versión A', notes: 'Notas' }),
    );

    await act(async () => {
      await result.current.handleClearApprovedZones();
    });
    expect(clearApprovedZones).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.handleApplyBasinMove();
    });
    expect(setDraftBasinAssignments).toHaveBeenCalled();
    expect(setSelectedDraftBasinId).toHaveBeenCalledWith(null);
    expect(setDraftDestinationZoneId).toHaveBeenCalledWith(null);
  });
});
