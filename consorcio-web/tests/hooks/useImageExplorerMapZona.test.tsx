/**
 * Regression (audit 2026-10 finding C4): commit 84c0a9c4 moved `new
 * maplibregl.Map()` behind `await bootMapLibreWorker()` inside an async IIFE,
 * so `mapInstanceRef.current` is only assigned in a microtask AFTER the
 * passive-effects flush. The zona effect (deps `[]`) ran synchronously in that
 * same flush, read the ref as null, early-returned, and was never retried —
 * the red consorcio boundary never rendered on /admin/images, and
 * `zonaLayerIdRef` stayed null so GEE rasters lost their `beforeId` z-order
 * slot (they stopped slotting under the boundary line).
 *
 * The fix folds the zona fetch/add into the map-init IIFE itself; these tests
 * pin that contract from the outside: the zona boundary must appear once the
 * map exists, and raster layers must be inserted below it.
 */

import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const fakeMap = {
  isStyleLoaded: vi.fn(() => true),
  getLayer: vi.fn(() => undefined),
  getSource: vi.fn(() => undefined),
  addSource: vi.fn(),
  addLayer: vi.fn(),
  removeLayer: vi.fn(),
  removeSource: vi.fn(),
  once: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
  remove: vi.fn(),
  fitBounds: vi.fn(),
  addControl: vi.fn(),
  resize: vi.fn(),
};

vi.mock('maplibre-gl', () => {
  const Map = vi.fn(function FakeMap() {
    return fakeMap;
  });
  const NavigationControl = vi.fn(function FakeNav() {
    return {};
  });
  const FullscreenControl = vi.fn(function FakeFullscreen() {
    return {};
  });
  return {
    Map,
    NavigationControl,
    FullscreenControl,
    setWorkerUrl: () => {},
    default: { Map, NavigationControl, FullscreenControl },
  };
});
vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}));

const zonaGeojson = { type: 'FeatureCollection', features: [] };

// Unlike the tiles harness, the zona endpoint must RESOLVE — that is the code
// path under test. Anything else stays pending, as in the tiles harness.
vi.mock('../../src/lib/api', () => ({
  apiFetch: vi.fn((url: string) =>
    url === '/geo/gee/layers/zona' ? Promise.resolve(zonaGeojson) : new Promise(() => undefined),
  ),
  GEE_TIMEOUT: 1000,
}));
vi.mock('../../src/lib/logger', () => ({
  logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import { useImageExplorerMap } from '../../src/components/admin/images/useImageExplorerMap';

type Api = ReturnType<typeof useImageExplorerMap>;

/** Mounts the hook with a real container so the init effect creates the map. */
function mount(): Api {
  let api!: Api;
  function Probe() {
    api = useImageExplorerMap();
    return <div ref={api.mapRef} />;
  }
  render(<Probe />);
  return api;
}

const TILE_A = 'https://earthengine.googleapis.com/map-A/{z}/{x}/{y}';

/** The addLayer call for the given layer id, if any: [layerSpec, beforeId?]. */
function layerCall(id: string): Parameters<typeof fakeMap.addLayer> | undefined {
  return fakeMap.addLayer.mock.calls.find(([layer]) => layer?.id === id) as
    | Parameters<typeof fakeMap.addLayer>
    | undefined;
}

describe('zona boundary layer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fakeMap.isStyleLoaded.mockReturnValue(true);
  });

  it('adds the zona boundary once the map exists (regression 84c0a9c4)', async () => {
    mount();
    await waitFor(() => expect(fakeMap.addControl).toHaveBeenCalled());

    await waitFor(() => {
      expect(fakeMap.addSource).toHaveBeenCalledWith(
        'zona-boundary',
        expect.objectContaining({ type: 'geojson', data: zonaGeojson }),
      );
    });
    const zonaLine = layerCall('zona-boundary-line');
    expect(zonaLine).toBeDefined();
    expect(zonaLine?.[0]).toMatchObject({ type: 'line', source: 'zona-boundary' });
  });

  it('slots GEE raster layers UNDER the zona line (beforeId restored)', async () => {
    const api = mount();
    await waitFor(() => expect(fakeMap.addControl).toHaveBeenCalled());
    // Wait until the zona layer actually exists before switching imagery.
    await waitFor(() => expect(layerCall('zona-boundary-line')).toBeDefined());

    api.updateTileLayer(TILE_A);

    // `beforeId` = zona line: the raster renders below the red boundary
    // instead of covering it. Pre-fix this arrived as null/undefined forever.
    const raster = layerCall('gee-image-layer');
    expect(raster).toBeDefined();
    expect(raster?.[0]).toMatchObject({ source: 'gee-image' });
    expect(raster?.[1]).toBe('zona-boundary-line');
  });
});
