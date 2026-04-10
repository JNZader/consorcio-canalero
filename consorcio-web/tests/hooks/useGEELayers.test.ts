import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FeatureCollection } from 'geojson';
import { createQueryWrapper } from '../test-utils';
import {
  GEE_LAYER_COLORS,
  GEE_LAYER_STYLES,
  useGEELayers,
  type GEELayerName,
} from '../../src/hooks/useGEELayers';

const { loggerWarn } = vi.hoisted(() => ({
  loggerWarn: vi.fn(),
}));

vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    warn: loggerWarn,
    error: vi.fn(),
    info: vi.fn(),
  },
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

const candilGeoJson: FeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [1, 1] },
      properties: { name: 'Candil' },
    },
  ],
};

function getFetchMock() {
  return global.fetch as ReturnType<typeof vi.fn>;
}

function mockLayerResponse(data: FeatureCollection) {
  return {
    ok: true,
    json: async () => data,
  };
}

describe('useGEELayers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('starts idle when disabled', () => {
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useGEELayers({ enabled: false }), { wrapper });

    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.layers).toEqual({});
    expect(result.current.layersArray).toEqual([]);
    expect(getFetchMock()).not.toHaveBeenCalled();
  });

  it('loads the requested layers and exposes both map and array shapes', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock()
      .mockResolvedValueOnce(mockLayerResponse(zonaGeoJson) as Response)
      .mockResolvedValueOnce(mockLayerResponse(candilGeoJson) as Response);

    const { result } = renderHook(
      () => useGEELayers({ enabled: true, layerNames: ['zona', 'candil'] }),
      { wrapper }
    );

    expect(result.current.loading).toBe(true);

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getFetchMock()).toHaveBeenCalledTimes(2);
    expect(getFetchMock()).toHaveBeenNthCalledWith(1, 'http://localhost:8000/api/v2/geo/gee/layers/zona');
    expect(getFetchMock()).toHaveBeenNthCalledWith(2, 'http://localhost:8000/api/v2/geo/gee/layers/candil');
    expect(result.current.error).toBeNull();
    expect(result.current.layers).toEqual({
      zona: zonaGeoJson,
      candil: candilGeoJson,
    });
    expect(result.current.layersArray).toEqual([
      { name: 'zona', data: zonaGeoJson },
      { name: 'candil', data: candilGeoJson },
    ]);
  });

  it('returns the no-layers error when every requested layer fails', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock().mockResolvedValue({ ok: false, status: 404 } as Response);

    const { result } = renderHook(
      () => useGEELayers({ enabled: true, layerNames: ['zona'] }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.layers).toEqual({});
    expect(result.current.layersArray).toEqual([]);
    expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
    expect(loggerWarn).toHaveBeenCalled();
  });

  it('keeps successfully loaded layers when only some requests fail', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock()
      .mockResolvedValueOnce(mockLayerResponse(zonaGeoJson) as Response)
      .mockResolvedValueOnce({ ok: false, status: 500 } as Response);

    const { result } = renderHook(
      () => useGEELayers({ enabled: true, layerNames: ['zona', 'candil'] }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBeNull();
    expect(result.current.layers).toEqual({ zona: zonaGeoJson });
    expect(result.current.layersArray).toEqual([{ name: 'zona', data: zonaGeoJson }]);
  });

  it('treats invalid GeoJSON as an unloaded layer', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock().mockResolvedValue({
      ok: true,
      json: async () => ({ type: 'Feature', features: [] }),
    } as Response);

    const { result } = renderHook(
      () => useGEELayers({ enabled: true, layerNames: ['zona'] }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.layers).toEqual({});
    expect(result.current.error).toBe('No se pudieron cargar las capas del mapa');
    expect(loggerWarn).toHaveBeenCalledWith("GEE layer 'zona' returned invalid GeoJSON structure");
  });

  it('can be enabled later via rerender', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock().mockResolvedValue(mockLayerResponse(zonaGeoJson) as Response);

    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useGEELayers({ enabled, layerNames: ['zona'] }),
      { wrapper, initialProps: { enabled: false } }
    );

    expect(result.current.loading).toBe(false);
    expect(getFetchMock()).not.toHaveBeenCalled();

    rerender({ enabled: true });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getFetchMock()).toHaveBeenCalledTimes(1);
    expect(result.current.layers.zona).toEqual(zonaGeoJson);
  });

  it('reload refetches the current selection', async () => {
    const wrapper = createQueryWrapper();
    getFetchMock().mockResolvedValueOnce(mockLayerResponse(zonaGeoJson) as Response);

    const { result } = renderHook(
      () => useGEELayers({ enabled: false, layerNames: ['zona'] }),
      { wrapper }
    );

    await act(async () => {
      await result.current.reload();
    });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getFetchMock()).toHaveBeenCalledTimes(1);
    expect(result.current.layers.zona).toEqual(zonaGeoJson);
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

    expect(GEE_LAYER_STYLES.zona).toEqual({ color: '#FF0000', weight: 3, fillOpacity: 0 });
    expect(GEE_LAYER_STYLES.candil).toEqual({
      color: '#2196F3',
      weight: 2,
      fillOpacity: 0.1,
      fillColor: '#2196F3',
    });
    expect(GEE_LAYER_STYLES.caminos).toEqual({
      color: '#FFEB3B',
      weight: 2,
      fillOpacity: 0,
    });
  });
});
