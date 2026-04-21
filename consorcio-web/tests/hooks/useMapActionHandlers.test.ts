import type { FeatureCollection } from 'geojson';
import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  useAssetCreationHandler,
  useMapExportHandlers,
  useZoningHandlers,
} from '../../src/components/map2d/useMapActionHandlers';
import { MAP_FALLBACK_BOUNDS } from '../../src/components/map2d/map2dUtils';

const notificationsShow = vi.fn();
const getAuthTokenMock = vi.fn();
const buildKmzMock = vi.fn();
const triggerKmzDownloadMock = vi.fn();
const useMapLayerSyncStoreMock = vi.fn();

vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: (...args: unknown[]) => notificationsShow(...args),
  },
}));

vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
  getAuthToken: (...args: unknown[]) => getAuthTokenMock(...args),
}));

vi.mock('../../src/lib/kmzExport/kmzBuilder', () => ({
  buildKmz: (...args: unknown[]) => buildKmzMock(...args),
}));

vi.mock('../../src/lib/kmzExport/triggerKmzDownload', () => ({
  triggerKmzDownload: (...args: unknown[]) => triggerKmzDownloadMock(...args),
}));

vi.mock('../../src/stores/mapLayerSyncStore', () => ({
  useMapLayerSyncStore: (selector: (state: unknown) => unknown) =>
    useMapLayerSyncStoreMock(selector),
}));

describe('useMapActionHandlers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getAuthTokenMock.mockResolvedValue('token-123');
    // Default store state — tests override as needed.
    useMapLayerSyncStoreMock.mockImplementation((selector: (state: unknown) => unknown) =>
      selector({
        map2d: { visibleVectors: {}, activeRasterType: null },
        propuestasEtapasVisibility: {},
      }),
    );
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

  it('surfaces the FastAPI 422 detail when the backend rejects the payload', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const fastApiDetail = [
      {
        loc: ['body', 'mapImageDataUrl'],
        msg: 'field required',
        type: 'value_error.missing',
      },
    ];

    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: fastApiDetail }),
    } as unknown as Response);

    const approvedZones: FeatureCollection = {
      type: 'FeatureCollection',
      features: [],
    };

    const mapRef = {
      current: {
        getCanvas: () => ({ toDataURL: () => 'data:image/png;base64,MOCK' }),
      },
    } as const;

    try {
      const { result } = renderHook(() =>
        useMapExportHandlers({
          mapRef,
          exportTitle: 'Mapa',
          setExportPngModalOpen: vi.fn(),
          approvedZones,
        }),
      );

      await act(async () => {
        await result.current.handleExportApprovedZonesPdf();
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(consoleErrorSpy).toHaveBeenCalled();

      // At least one console.error call must include the FastAPI detail.
      const loggedMatches = consoleErrorSpy.mock.calls.some((call) =>
        call.some((arg) => {
          if (arg === fastApiDetail) return true;
          const text = typeof arg === 'string' ? arg : JSON.stringify(arg);
          return text.includes('mapImageDataUrl') || text.includes('field required');
        }),
      );
      expect(loggedMatches).toBe(true);
    } finally {
      consoleErrorSpy.mockRestore();
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

  describe('handleExportKmz', () => {
    function fc(features: unknown[] = []): FeatureCollection {
      return { type: 'FeatureCollection', features: features as never[] };
    }

    function renderExportHook(
      overrides: Partial<Parameters<typeof useMapExportHandlers>[0]> = {},
    ) {
      const canalesRelevados = fc([{ type: 'Feature', geometry: null, properties: {} }]);
      const canalesPropuestos = fc([{ type: 'Feature', geometry: null, properties: {} }]);
      const escuelas = fc([{ type: 'Feature', geometry: null, properties: {} }]);
      const bpaHistorico = fc([{ type: 'Feature', geometry: null, properties: {} }]);
      const ypf = fc([{ type: 'Feature', geometry: null, properties: {} }]);

      const exportSources = {
        canales_relevados: canalesRelevados,
        canales_propuestos: canalesPropuestos,
        escuelas,
        pilar_verde_bpa_historico: bpaHistorico,
        pilar_verde_agro_aceptada: null,
        pilar_verde_agro_presentada: null,
        pilar_verde_agro_zonas: null,
        pilar_verde_porcentaje_forestacion: null,
        waterways: null,
        roads: null,
        catastro: null,
        soil: null,
        'ypf-estacion-bombeo': ypf,
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
          approvedZones: null,
          exportSources,
          ...overrides,
        }),
      );
      return { result, sources: exportSources };
    }

    it('reads visibleVectors + propuestasEtapasVisibility from the store', async () => {
      const visibleVectors = { canales_relevados: true, escuelas: false };
      const propuestasEtapasVisibility = { '1': true, '2': false, '3': true, '4': true, '5': true };
      useMapLayerSyncStoreMock.mockImplementation((selector: (state: unknown) => unknown) =>
        selector({
          map2d: { visibleVectors, activeRasterType: null },
          propuestasEtapasVisibility,
        }),
      );
      buildKmzMock.mockResolvedValue(new Blob(['kmz']));

      const { result } = renderExportHook();

      await act(async () => {
        await result.current.handleExportKmz();
      });

      expect(buildKmzMock).toHaveBeenCalledTimes(1);
      const input = buildKmzMock.mock.calls[0][0] as {
        visibleLayers: Record<string, boolean>;
        propuestasEtapasVisibility: Record<string, boolean>;
        data: Record<string, unknown>;
        timestamp: Date;
      };
      expect(input.visibleLayers).toEqual(visibleVectors);
      expect(input.propuestasEtapasVisibility).toEqual(propuestasEtapasVisibility);
    });

    it('passes the data map to buildKmz keyed by layer keys', async () => {
      buildKmzMock.mockResolvedValue(new Blob(['kmz']));
      const { result, sources } = renderExportHook();

      await act(async () => {
        await result.current.handleExportKmz();
      });

      const input = buildKmzMock.mock.calls[0][0] as {
        data: Record<string, unknown>;
      };
      expect(input.data.canales_relevados).toBe(sources.canales_relevados);
      expect(input.data.canales_propuestos).toBe(sources.canales_propuestos);
      expect(input.data.escuelas).toBe(sources.escuelas);
      expect(input.data.pilar_verde_bpa_historico).toBe(sources.pilar_verde_bpa_historico);
      expect(input.data['ypf-estacion-bombeo']).toBe(sources['ypf-estacion-bombeo']);
    });

    it('triggers download with YYYY-MM-DD filename after buildKmz resolves', async () => {
      const blob = new Blob(['kmz'], { type: 'application/vnd.google-earth.kmz' });
      buildKmzMock.mockResolvedValue(blob);

      const { result } = renderExportHook();

      await act(async () => {
        await result.current.handleExportKmz();
      });

      expect(triggerKmzDownloadMock).toHaveBeenCalledTimes(1);
      const [downloadedBlob, filename] = triggerKmzDownloadMock.mock.calls[0];
      expect(downloadedBlob).toBe(blob);
      expect(filename).toMatch(/^consorcio_canalero_\d{4}-\d{2}-\d{2}\.kmz$/);
    });

    it('does NOT call triggerKmzDownload when buildKmz throws', async () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      buildKmzMock.mockRejectedValue(new Error('boom'));

      const { result } = renderExportHook();

      await act(async () => {
        await result.current.handleExportKmz();
      });

      expect(triggerKmzDownloadMock).not.toHaveBeenCalled();
      // Error path notifies the user (mirror handleExportApprovedZonesPdf).
      expect(notificationsShow).toHaveBeenCalledWith(
        expect.objectContaining({ color: 'red' }),
      );
      consoleErrorSpy.mockRestore();
    });

    it('shows a success notification when the export completes', async () => {
      buildKmzMock.mockResolvedValue(new Blob(['kmz']));

      const { result } = renderExportHook();

      await act(async () => {
        await result.current.handleExportKmz();
      });

      // At least one green-colored notification was dispatched.
      const greenCalls = notificationsShow.mock.calls.filter(([arg]) =>
        (arg as { color?: string })?.color === 'green',
      );
      expect(greenCalls.length).toBeGreaterThanOrEqual(1);
    });
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

  // ─────────────────────────────────────────────────────────────────────────
  // Auto-fit to consorcio — shared helpers
  // ─────────────────────────────────────────────────────────────────────────
  function buildZonaCollection(): FeatureCollection {
    return {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [
              [
                [-62.8, -32.7],
                [-62.4, -32.7],
                [-62.4, -32.5],
                [-62.8, -32.5],
                [-62.8, -32.7],
              ],
            ],
          },
          properties: {},
        },
      ],
    };
  }

  interface FakeMapOptions {
    currentZoom?: number;
    fitZoom?: number;
    /** If true, `cameraForBounds` returns undefined (older MapLibre / mocks). */
    cameraUndefined?: boolean;
  }

  function buildFakeMap(opts: FakeMapOptions = {}) {
    const fitBounds = vi.fn();
    const triggerRepaint = vi.fn();
    const once = vi.fn((event: string, cb: () => void) => {
      // Invoke 'idle' and 'render' callbacks synchronously so awaits resolve.
      if (event === 'idle' || event === 'render') {
        cb();
      }
    });
    const getZoom = vi.fn(() => opts.currentZoom ?? 10);
    const cameraForBounds = vi.fn(() =>
      opts.cameraUndefined ? undefined : { zoom: opts.fitZoom ?? 11 },
    );
    const map = {
      fitBounds,
      triggerRepaint,
      once,
      getZoom,
      cameraForBounds,
      getCanvas: () => ({ toDataURL: () => 'data:image/png;base64,MOCK' }),
    };
    return { map, fitBounds, triggerRepaint, once, getZoom, cameraForBounds };
  }

  describe('handleExportApprovedZonesPdf — auto-fit to consorcio', () => {
    it('calls fitBounds with the zonaCollection bbox BEFORE capturing the canvas', async () => {
      const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        blob: async () => new Blob(['pdf']),
      } as Response);
      const createObjectURL = vi
        .spyOn(window.URL, 'createObjectURL')
        .mockReturnValue('blob:test');
      const revokeObjectURL = vi
        .spyOn(window.URL, 'revokeObjectURL')
        .mockImplementation(() => {});

      const { map, fitBounds, once } = buildFakeMap();
      // Spy on toDataURL to assert ordering vs fitBounds.
      const toDataURLSpy = vi.fn(() => 'data:image/png;base64,MOCK');
      map.getCanvas = () => ({ toDataURL: toDataURLSpy }) as never;

      const zonaCollection = buildZonaCollection();
      const approvedZones: FeatureCollection = {
        type: 'FeatureCollection',
        features: [],
      };
      const mapRef = { current: map } as const;

      try {
        const { result } = renderHook(() =>
          useMapExportHandlers({
            mapRef,
            exportTitle: 'Mapa',
            setExportPngModalOpen: vi.fn(),
            approvedZones,
            zonaCollection,
          } as Parameters<typeof useMapExportHandlers>[0]),
        );

        await act(async () => {
          await result.current.handleExportApprovedZonesPdf();
        });

        // fitBounds MUST be called.
        expect(fitBounds).toHaveBeenCalledTimes(1);
        const [bounds, options] = fitBounds.mock.calls[0];
        // Bounds come from the zonaCollection's bbox.
        expect(bounds).toEqual([
          [-62.8, -32.7],
          [-62.4, -32.5],
        ]);
        // animate: false and duration: 0 for instant snap during capture.
        expect(options).toEqual(
          expect.objectContaining({ animate: false, duration: 0 }),
        );

        // After fitBounds, awaits 'idle' before capture.
        expect(once).toHaveBeenCalledWith('idle', expect.any(Function));

        // Ordering: fitBounds happens before toDataURL.
        const fitOrder = fitBounds.mock.invocationCallOrder[0];
        const captureOrder = toDataURLSpy.mock.invocationCallOrder[0];
        expect(fitOrder).toBeLessThan(captureOrder);
      } finally {
        fetchMock.mockRestore();
        createObjectURL.mockRestore();
        revokeObjectURL.mockRestore();
      }
    });

    it('falls back to MAP_FALLBACK_BOUNDS when zonaCollection is null', async () => {
      const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        blob: async () => new Blob(['pdf']),
      } as Response);
      const createObjectURL = vi
        .spyOn(window.URL, 'createObjectURL')
        .mockReturnValue('blob:test');
      const revokeObjectURL = vi
        .spyOn(window.URL, 'revokeObjectURL')
        .mockImplementation(() => {});

      const { map, fitBounds } = buildFakeMap();
      const approvedZones: FeatureCollection = {
        type: 'FeatureCollection',
        features: [],
      };
      const mapRef = { current: map } as const;

      try {
        const { result } = renderHook(() =>
          useMapExportHandlers({
            mapRef,
            exportTitle: 'Mapa',
            setExportPngModalOpen: vi.fn(),
            approvedZones,
            zonaCollection: null,
          } as Parameters<typeof useMapExportHandlers>[0]),
        );

        await act(async () => {
          await result.current.handleExportApprovedZonesPdf();
        });

        expect(fitBounds).toHaveBeenCalledTimes(1);
        const [bounds] = fitBounds.mock.calls[0];
        expect(bounds).toEqual(MAP_FALLBACK_BOUNDS);
      } finally {
        fetchMock.mockRestore();
        createObjectURL.mockRestore();
        revokeObjectURL.mockRestore();
      }
    });
  });

  describe('handleExportPng — fit-or-respect-zoom threshold', () => {
    // Reusable <a> stub so the link.click() inside handleExportPng doesn't
    // explode when the test env's default document.createElement('a') is used.
    function stubAnchor() {
      const click = vi.fn();
      const originalCreateElement = document.createElement.bind(document);
      const createElement = vi
        .spyOn(document, 'createElement')
        .mockImplementation(((tagName: string) => {
          if (tagName === 'a') {
            return { click, href: '', download: '' } as unknown as HTMLElement;
          }
          return originalCreateElement(tagName);
        }) as typeof document.createElement);
      return { click, createElement };
    }

    it('calls fitBounds when current zoom is BELOW the threshold (zoomed out)', async () => {
      const { createElement } = stubAnchor();
      try {
        const zonaCollection = buildZonaCollection();
        const { map, fitBounds, once } = buildFakeMap({
          currentZoom: 10.8,
          fitZoom: 11,
        });
        const mapRef = { current: map } as const;

        const { result } = renderHook(() =>
          useMapExportHandlers({
            mapRef,
            exportTitle: 'Mapa Test',
            setExportPngModalOpen: vi.fn(),
            approvedZones: null,
            zonaCollection,
          } as Parameters<typeof useMapExportHandlers>[0]),
        );

        await act(async () => {
          await result.current.handleExportPng();
        });

        expect(fitBounds).toHaveBeenCalledTimes(1);
        const [bounds] = fitBounds.mock.calls[0];
        expect(bounds).toEqual([
          [-62.8, -32.7],
          [-62.4, -32.5],
        ]);
        expect(once).toHaveBeenCalledWith('idle', expect.any(Function));
      } finally {
        createElement.mockRestore();
      }
    });

    it('calls fitBounds when current zoom is AT the threshold (≤ fitZoom + 0.25)', async () => {
      const { createElement } = stubAnchor();
      try {
        const zonaCollection = buildZonaCollection();
        // currentZoom 11.25, fitZoom 11 → 11.25 ≤ 11 + 0.25 → fit
        const { map, fitBounds } = buildFakeMap({
          currentZoom: 11.25,
          fitZoom: 11,
        });
        const mapRef = { current: map } as const;

        const { result } = renderHook(() =>
          useMapExportHandlers({
            mapRef,
            exportTitle: 'Mapa Test',
            setExportPngModalOpen: vi.fn(),
            approvedZones: null,
            zonaCollection,
          } as Parameters<typeof useMapExportHandlers>[0]),
        );

        await act(async () => {
          await result.current.handleExportPng();
        });

        expect(fitBounds).toHaveBeenCalledTimes(1);
      } finally {
        createElement.mockRestore();
      }
    });

    it('does NOT call fitBounds when current zoom is ABOVE the threshold (zoomed in)', async () => {
      const { createElement } = stubAnchor();
      try {
        const zonaCollection = buildZonaCollection();
        // currentZoom 12.5, fitZoom 11 → 12.5 > 11 + 0.25 → respect user zoom
        const { map, fitBounds, once } = buildFakeMap({
          currentZoom: 12.5,
          fitZoom: 11,
        });
        const mapRef = { current: map } as const;

        const { result } = renderHook(() =>
          useMapExportHandlers({
            mapRef,
            exportTitle: 'Mapa Test',
            setExportPngModalOpen: vi.fn(),
            approvedZones: null,
            zonaCollection,
          } as Parameters<typeof useMapExportHandlers>[0]),
        );

        await act(async () => {
          await result.current.handleExportPng();
        });

        expect(fitBounds).not.toHaveBeenCalled();
        // Still awaits a stable render before capture.
        expect(once).toHaveBeenCalledWith('idle', expect.any(Function));
      } finally {
        createElement.mockRestore();
      }
    });

    it('uses MAP_FALLBACK_BOUNDS for cameraForBounds and fitBounds when zonaCollection is null', async () => {
      const { createElement } = stubAnchor();
      try {
        const { map, fitBounds, cameraForBounds } = buildFakeMap({
          currentZoom: 9.0,
          fitZoom: 10,
        });
        const mapRef = { current: map } as const;

        const { result } = renderHook(() =>
          useMapExportHandlers({
            mapRef,
            exportTitle: 'Mapa Test',
            setExportPngModalOpen: vi.fn(),
            approvedZones: null,
            zonaCollection: null,
          } as Parameters<typeof useMapExportHandlers>[0]),
        );

        await act(async () => {
          await result.current.handleExportPng();
        });

        // cameraForBounds was computed against the fallback bounds.
        expect(cameraForBounds).toHaveBeenCalledTimes(1);
        const [cbBounds] = cameraForBounds.mock.calls[0];
        expect(cbBounds).toEqual(MAP_FALLBACK_BOUNDS);

        // And fitBounds was called with the fallback bounds
        // (currentZoom 9 ≤ fitZoom 10 + 0.25 → fit).
        expect(fitBounds).toHaveBeenCalledTimes(1);
        const [fbBounds] = fitBounds.mock.calls[0];
        expect(fbBounds).toEqual(MAP_FALLBACK_BOUNDS);
      } finally {
        createElement.mockRestore();
      }
    });

    it('skips fitBounds when cameraForBounds returns undefined (defensive default)', async () => {
      const { createElement } = stubAnchor();
      try {
        const zonaCollection = buildZonaCollection();
        const { map, fitBounds, once } = buildFakeMap({
          currentZoom: 10,
          cameraUndefined: true,
        });
        const mapRef = { current: map } as const;

        const { result } = renderHook(() =>
          useMapExportHandlers({
            mapRef,
            exportTitle: 'Mapa Test',
            setExportPngModalOpen: vi.fn(),
            approvedZones: null,
            zonaCollection,
          } as Parameters<typeof useMapExportHandlers>[0]),
        );

        await act(async () => {
          await result.current.handleExportPng();
        });

        expect(fitBounds).not.toHaveBeenCalled();
        expect(once).toHaveBeenCalledWith('idle', expect.any(Function));
      } finally {
        createElement.mockRestore();
      }
    });
  });
});
