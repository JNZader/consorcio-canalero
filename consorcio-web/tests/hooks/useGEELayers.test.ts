import { act, renderHook, waitFor } from '@testing-library/react';
import type { FeatureCollection } from 'geojson';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  GEE_LAYER_COLORS,
  GEE_LAYER_STYLES,
  PUBLIC_GEE_LAYER_UNAVAILABLE_MESSAGE,
  type GEELayerName,
  useGEELayers,
} from '../../src/hooks/useGEELayers';
import { createQueryWrapper } from '../test-utils';

const { loggerWarn } = vi.hoisted(() => ({ loggerWarn: vi.fn() }));

vi.mock('../../src/lib/api', () => ({ API_URL: 'http://localhost:8000' }));
vi.mock('../../src/lib/logger', () => ({
  logger: { warn: loggerWarn, error: vi.fn(), info: vi.fn() },
}));
vi.mock('../../src/lib/typeGuards', () => ({
  parseFeatureCollection: (data: unknown) => {
    if (
      data &&
      typeof data === 'object' &&
      (data as { type?: string }).type === 'FeatureCollection' &&
      Array.isArray((data as { features?: unknown[] }).features)
    ) {
      return data;
    }
    return null;
  },
}));

const zonaGeoJson: FeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [0, 0] },
      properties: { name: 'Zona' },
    },
  ],
};
const caminosGeoJson: FeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
      properties: { name: 'Camino' },
    },
  ],
};

function getFetchMock() {
  return global.fetch as ReturnType<typeof vi.fn>;
}

function mockProjection(name: 'zona' | 'caminos', data: FeatureCollection) {
  return {
    ok: true,
    json: async () => ({ status: 'available', projection: name, data, reason: null }),
  } as Response;
}

describe('useGEELayers public allowlist', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  afterEach(() => vi.clearAllMocks());

  it('starts idle when disabled', () => {
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useGEELayers({ enabled: false }), { wrapper });

    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.layers).toEqual({});
    expect(result.current.layersArray).toEqual([]);
    expect(result.current.unavailableLayers).toEqual([]);
    expect(getFetchMock()).not.toHaveBeenCalled();
  });

  it('loads only fixed zona and caminos public URLs', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock()
      .mockResolvedValueOnce(mockProjection('zona', zonaGeoJson))
      .mockResolvedValueOnce(mockProjection('caminos', caminosGeoJson));

    const { result } = renderHook(
      () => useGEELayers({ layerNames: ['zona', 'caminos'] }),
      { wrapper }
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getFetchMock()).toHaveBeenCalledTimes(2);
    expect(getFetchMock()).toHaveBeenNthCalledWith(
      1,
      'http://localhost:8000/api/v2/public/map/gee/zona'
    );
    expect(getFetchMock()).toHaveBeenNthCalledWith(
      2,
      'http://localhost:8000/api/v2/public/map/gee/caminos'
    );
    expect(result.current.layers).toEqual({ zona: zonaGeoJson, caminos: caminosGeoJson });
    expect(result.current.unavailableLayers).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('rejects legacy and runtime-injected identifiers without making a request', async () => {
    const wrapper = createQueryWrapper();
    const arbitrary = 'users/private/asset' as GEELayerName;
    const { result } = renderHook(
      () => useGEELayers({ layerNames: ['candil', arbitrary] }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getFetchMock()).not.toHaveBeenCalled();
    expect(result.current.layers).toEqual({});
    expect(result.current.unavailableLayers).toEqual(['candil', arbitrary]);
    expect(result.current.error).toBe(PUBLIC_GEE_LAYER_UNAVAILABLE_MESSAGE);
  });

  it('keeps a safe projection while explicitly reporting unsupported layers', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock().mockResolvedValueOnce(mockProjection('zona', zonaGeoJson));

    const { result } = renderHook(
      () => useGEELayers({ layerNames: ['zona', 'noroeste'] }),
      { wrapper }
    );
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getFetchMock()).toHaveBeenCalledTimes(1);
    expect(result.current.layers).toEqual({ zona: zonaGeoJson });
    expect(result.current.unavailableLayers).toEqual(['noroeste']);
    expect(result.current.error).toBeNull();
  });

  it('maps unavailable and invalid projection envelopes to the no-layers error', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          status: 'unavailable',
          projection: 'zona',
          data: null,
          reason: 'temporarily_unavailable',
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          status: 'available',
          projection: 'zona',
          data: { type: 'Feature', features: [] },
          reason: null,
        }),
      } as Response);

    const first = renderHook(() => useGEELayers({ layerNames: ['zona'] }), { wrapper });
    await waitFor(() => expect(first.result.current.loading).toBe(false));
    expect(first.result.current.error).toBe('No se pudieron cargar las capas del mapa');
    first.unmount();

    const secondWrapper = createQueryWrapper();
    const second = renderHook(() => useGEELayers({ layerNames: ['zona'] }), {
      wrapper: secondWrapper,
    });
    await waitFor(() => expect(second.result.current.loading).toBe(false));
    expect(second.result.current.error).toBe('No se pudieron cargar las capas del mapa');
    expect(loggerWarn).toHaveBeenCalled();
  });

  it('can be enabled later and reloaded explicitly', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock().mockResolvedValue(mockProjection('zona', zonaGeoJson));
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useGEELayers({ enabled, layerNames: ['zona'] }),
      { wrapper, initialProps: { enabled: false } }
    );

    expect(getFetchMock()).not.toHaveBeenCalled();
    rerender({ enabled: true });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.layers.zona).toEqual(zonaGeoJson);

    await act(async () => {
      await result.current.reload();
    });
    expect(getFetchMock()).toHaveBeenCalledTimes(2);
  });
});

describe('useGEELayers constants', () => {
  it('keeps color and style definitions aligned', () => {
    const expectedNames: GEELayerName[] = ['zona', 'candil', 'ml', 'noroeste', 'norte', 'caminos'];

    expect(Object.keys(GEE_LAYER_COLORS)).toEqual(expectedNames);
    expect(Object.keys(GEE_LAYER_STYLES)).toEqual(expectedNames);
    expectedNames.forEach((name) => {
      expect(GEE_LAYER_STYLES[name].color).toBe(GEE_LAYER_COLORS[name]);
    });
  });
});
