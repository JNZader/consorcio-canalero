/**
 * TerrainViewer3DPilarVerdeSync.test.tsx
 *
 * Phase 1 (Batch B) of `pilar-verde-y-canales-3d` — wires the 5 Pilar Verde
 * sync helpers (`syncBpaHistoricoLayer`, `syncAgroAceptadaLayer`,
 * `syncAgroPresentadaLayer`, `syncAgroZonasLayer`,
 * `syncPorcentajeForestacionLayer`) into the 3D viewer as 1 `useEffect` per
 * layer, mirroring the 2D blueprint (`useMapLayerEffects.ts` — Phase 2).
 *
 * Contract asserted by these tests:
 *   1. When a Pilar Verde FeatureCollection resolves AND the map is mounted,
 *      the corresponding `sync*Layer` helper is called with the tuple
 *      `(mapInstance, featureCollection, visibilityBool)`.
 *   2. Flipping the visibility flag in `mapLayerSyncStore.map3d.visibleVectors`
 *      re-invokes the helper with the new flag.
 *   3. The map instance passed to the helper is the SAME instance created by
 *      MapLibre inside `TerrainViewer3D` (proven via ref equality over the
 *      shared `MapStub` singleton).
 *
 * The z-order hoist is NOT asserted in this file: each `sync*Layer` helper
 * already calls the PRIVATE `raisePilarVerdeStack` at its tail (see
 * `mapLayerEffectHelpers.ts` lines 392/423/454/485/507). Asserting twice would
 * couple the 3D wiring to the sync-helper internals.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, act } from '@testing-library/react';
import type { FeatureCollection } from 'geojson';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// ---------------------------------------------------------------------------
// Hook mocks — controlled per-test via the *Mock handles below.
// ---------------------------------------------------------------------------

const useCanalesMock = vi.fn();
const usePilarVerdeMock = vi.fn();

vi.mock('../../src/hooks/useCanales', () => ({
  useCanales: (...args: unknown[]) => useCanalesMock(...args),
  CANALES_PATHS: {},
}));

vi.mock('../../src/hooks/usePilarVerde', () => ({
  usePilarVerde: (...args: unknown[]) => usePilarVerdeMock(...args),
  PILAR_VERDE_PUBLIC_PATHS: {},
}));

vi.mock('../../src/hooks/useGeoLayers', () => ({
  useGeoLayers: () => ({ layers: [] }),
  buildTileUrl: () => 'https://tiles.test/{z}/{x}/{y}.png',
}));
vi.mock('../../src/hooks/useGEELayers', () => ({
  useGEELayers: () => ({ layers: {} }),
  GEE_LAYER_COLORS: { candil: '#000', ml: '#000', noroeste: '#000', norte: '#000' },
}));
vi.mock('../../src/hooks/useBasins', () => ({ useBasins: () => ({ basins: null }) }));
vi.mock('../../src/hooks/useApprovedZones', () => ({
  useApprovedZones: () => ({ approvedZones: null }),
}));
vi.mock('../../src/hooks/useCaminosColoreados', () => ({
  useCaminosColoreados: () => ({ caminos: null }),
}));
vi.mock('../../src/hooks/useCatastroMap', () => ({
  useCatastroMap: () => ({ catastroMap: null }),
}));
vi.mock('../../src/hooks/useSoilMap', () => ({
  useSoilMap: () => ({ soilMap: null }),
  getSoilColor: () => '#888',
}));
vi.mock('../../src/hooks/useSelectedImage', () => ({
  useSelectedImageListener: () => null,
}));
vi.mock('../../src/hooks/useWaterways', () => ({
  useWaterways: () => ({ waterways: [] }),
  WATERWAY_DEFS: [],
}));

// ---------------------------------------------------------------------------
// Sync helper mocks — spy on each helper so the test can assert call args.
// The real helpers mutate a MapLibre instance; under the stub they would
// no-op anyway, but replacing them with spies makes the assertions crisp.
// ---------------------------------------------------------------------------

const syncBpaHistoricoLayerMock = vi.fn();
const syncAgroAceptadaLayerMock = vi.fn();
const syncAgroPresentadaLayerMock = vi.fn();
const syncAgroZonasLayerMock = vi.fn();
const syncPorcentajeForestacionLayerMock = vi.fn();

vi.mock('../../src/components/map2d/mapLayerEffectHelpers', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    syncBpaHistoricoLayer: (...args: unknown[]) => syncBpaHistoricoLayerMock(...args),
    syncAgroAceptadaLayer: (...args: unknown[]) => syncAgroAceptadaLayerMock(...args),
    syncAgroPresentadaLayer: (...args: unknown[]) => syncAgroPresentadaLayerMock(...args),
    syncAgroZonasLayer: (...args: unknown[]) => syncAgroZonasLayerMock(...args),
    syncPorcentajeForestacionLayer: (...args: unknown[]) =>
      syncPorcentajeForestacionLayerMock(...args),
  };
});

// ---------------------------------------------------------------------------
// MapLibre stub — records the created instance so tests can assert
// ref-equality of the `map` argument passed to each sync helper. `on('load',
// cb)` fires `cb()` synchronously so the viewer's `ready` state flips to true
// and the vector-layer effects execute within the same render pass.
// ---------------------------------------------------------------------------

interface MapStubInstance {
  on: (event: string, cb: (e?: unknown) => void) => void;
  off: () => void;
  once: () => void;
  addControl: () => void;
  remove: () => void;
  isStyleLoaded: () => boolean;
  getLayer: () => undefined;
  getSource: () => undefined;
  addLayer: () => void;
  addSource: () => void;
  removeLayer: () => void;
  removeSource: () => void;
  setLayoutProperty: () => void;
  setPaintProperty: () => void;
  setTerrain: () => void;
  moveLayer: () => void;
  setFilter: () => void;
}

let lastMapInstance: MapStubInstance | null = null;

vi.mock('maplibre-gl', () => {
  class MapStub {
    constructor() {
      lastMapInstance = this as unknown as MapStubInstance;
    }
    on(event: string, cb: (e?: unknown) => void) {
      if (event === 'load') {
        // Fire synchronously so `setReady(true)` runs before the vector
        // effects check the `ready` flag.
        cb();
      }
    }
    off() {}
    once() {}
    addControl() {}
    remove() {
      lastMapInstance = null;
    }
    isStyleLoaded() {
      return true;
    }
    getLayer() {
      return undefined;
    }
    getSource() {
      return undefined;
    }
    addLayer() {}
    addSource() {}
    removeLayer() {}
    removeSource() {}
    setLayoutProperty() {}
    setPaintProperty() {}
    setTerrain() {}
    moveLayer() {}
    setFilter() {}
  }
  return {
    default: {
      Map: MapStub,
      NavigationControl: class {},
      addProtocol: () => {},
      removeProtocol: () => {},
    },
    Map: MapStub,
    NavigationControl: class {},
    addProtocol: () => {},
    removeProtocol: () => {},
  };
});

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeFeatureCollection(label: string): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [0, 0] },
        properties: { __testLabel: label },
      },
    ],
  };
}

function renderViewer(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>{ui}</MantineProvider>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

describe('TerrainViewer3D — Pilar Verde layer sync (Phase 1)', () => {
  beforeEach(() => {
    useCanalesMock.mockReset();
    usePilarVerdeMock.mockReset();
    syncBpaHistoricoLayerMock.mockReset();
    syncAgroAceptadaLayerMock.mockReset();
    syncAgroPresentadaLayerMock.mockReset();
    syncAgroZonasLayerMock.mockReset();
    syncPorcentajeForestacionLayerMock.mockReset();
    lastMapInstance = null;

    // No canales payload needed — Batch B only exercises PV wiring.
    useCanalesMock.mockReturnValue({
      relevados: null,
      propuestas: null,
      index: null,
      isLoading: false,
      isError: false,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('calls syncBpaHistoricoLayer with (map, bpaHistorico, visible=true) when the master toggle is ON', async () => {
    const bpaHistorico = makeFeatureCollection('bpa');
    usePilarVerdeMock.mockReturnValue({
      data: { bpaHistorico },
      loading: false,
      error: null,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    storeModule.useMapLayerSyncStore
      .getState()
      .setVectorVisibility('map3d', 'pilar_verde_bpa_historico', true);

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    expect(lastMapInstance).not.toBeNull();
    expect(syncBpaHistoricoLayerMock).toHaveBeenCalled();
    const [mapArg, dataArg, visibleArg] =
      syncBpaHistoricoLayerMock.mock.calls[
        syncBpaHistoricoLayerMock.mock.calls.length - 1
      ];
    expect(mapArg).toBe(lastMapInstance);
    expect(dataArg).toBe(bpaHistorico);
    expect(visibleArg).toBe(true);
  });

  it('re-invokes syncBpaHistoricoLayer with visible=false when the master toggle flips OFF', async () => {
    const bpaHistorico = makeFeatureCollection('bpa-flip');
    usePilarVerdeMock.mockReturnValue({
      data: { bpaHistorico },
      loading: false,
      error: null,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    // Start visible ON.
    storeModule.useMapLayerSyncStore
      .getState()
      .setVectorVisibility('map3d', 'pilar_verde_bpa_historico', true);

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    const initialCalls = syncBpaHistoricoLayerMock.mock.calls.length;
    expect(initialCalls).toBeGreaterThan(0);

    // Flip OFF — the shared store sync effect should propagate the new
    // value into the viewer's local `vectorLayerVisibility` state, which
    // re-fires the BPA effect with `visible=false`.
    await act(async () => {
      storeModule.useMapLayerSyncStore
        .getState()
        .setVectorVisibility('map3d', 'pilar_verde_bpa_historico', false);
    });

    const lastCall =
      syncBpaHistoricoLayerMock.mock.calls[
        syncBpaHistoricoLayerMock.mock.calls.length - 1
      ];
    expect(lastCall[2]).toBe(false);
  });

  it('calls syncAgroAceptadaLayer + syncAgroPresentadaLayer with their matching feature collections', async () => {
    const agroAceptada = makeFeatureCollection('agro-aceptada');
    const agroPresentada = makeFeatureCollection('agro-presentada');
    usePilarVerdeMock.mockReturnValue({
      data: { agroAceptada, agroPresentada },
      loading: false,
      error: null,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    storeModule.useMapLayerSyncStore
      .getState()
      .setVectorVisibility('map3d', 'pilar_verde_agro_aceptada', true);
    storeModule.useMapLayerSyncStore
      .getState()
      .setVectorVisibility('map3d', 'pilar_verde_agro_presentada', true);

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    expect(syncAgroAceptadaLayerMock).toHaveBeenCalled();
    const lastAceptada =
      syncAgroAceptadaLayerMock.mock.calls[
        syncAgroAceptadaLayerMock.mock.calls.length - 1
      ];
    expect(lastAceptada[1]).toBe(agroAceptada);
    expect(lastAceptada[2]).toBe(true);

    expect(syncAgroPresentadaLayerMock).toHaveBeenCalled();
    const lastPresentada =
      syncAgroPresentadaLayerMock.mock.calls[
        syncAgroPresentadaLayerMock.mock.calls.length - 1
      ];
    expect(lastPresentada[1]).toBe(agroPresentada);
    expect(lastPresentada[2]).toBe(true);
  });

  it('calls syncAgroZonasLayer + syncPorcentajeForestacionLayer with their matching feature collections', async () => {
    const agroZonas = makeFeatureCollection('agro-zonas');
    const porcentajeForestacion = makeFeatureCollection('forestacion');
    usePilarVerdeMock.mockReturnValue({
      data: { agroZonas, porcentajeForestacion },
      loading: false,
      error: null,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    storeModule.useMapLayerSyncStore
      .getState()
      .setVectorVisibility('map3d', 'pilar_verde_agro_zonas', true);
    storeModule.useMapLayerSyncStore
      .getState()
      .setVectorVisibility('map3d', 'pilar_verde_porcentaje_forestacion', true);

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    expect(syncAgroZonasLayerMock).toHaveBeenCalled();
    const lastZonas =
      syncAgroZonasLayerMock.mock.calls[
        syncAgroZonasLayerMock.mock.calls.length - 1
      ];
    expect(lastZonas[1]).toBe(agroZonas);
    expect(lastZonas[2]).toBe(true);

    expect(syncPorcentajeForestacionLayerMock).toHaveBeenCalled();
    const lastForestacion =
      syncPorcentajeForestacionLayerMock.mock.calls[
        syncPorcentajeForestacionLayerMock.mock.calls.length - 1
      ];
    expect(lastForestacion[1]).toBe(porcentajeForestacion);
    expect(lastForestacion[2]).toBe(true);
  });

  it('skips a sync helper when its FeatureCollection slot is still null (graceful degradation)', async () => {
    // Only bpaHistorico resolves; the other 4 slots stay null until fetch.
    const bpaHistorico = makeFeatureCollection('bpa-only');
    usePilarVerdeMock.mockReturnValue({
      data: { bpaHistorico },
      loading: false,
      error: null,
    });

    const storeModule = await import('../../src/stores/mapLayerSyncStore');
    // Turn ALL five on so the only thing gating the helper is the null data.
    for (const key of [
      'pilar_verde_bpa_historico',
      'pilar_verde_agro_aceptada',
      'pilar_verde_agro_presentada',
      'pilar_verde_agro_zonas',
      'pilar_verde_porcentaje_forestacion',
    ]) {
      storeModule.useMapLayerSyncStore.getState().setVectorVisibility('map3d', key, true);
    }

    const { default: TerrainViewer3D } = await import(
      '../../src/components/terrain/TerrainViewer3D'
    );

    renderViewer(<TerrainViewer3D demLayerId="dem-uuid" />);

    // BPA ran (slot present). Others did NOT run (slot null).
    expect(syncBpaHistoricoLayerMock).toHaveBeenCalled();
    expect(syncAgroAceptadaLayerMock).not.toHaveBeenCalled();
    expect(syncAgroPresentadaLayerMock).not.toHaveBeenCalled();
    expect(syncAgroZonasLayerMock).not.toHaveBeenCalled();
    expect(syncPorcentajeForestacionLayerMock).not.toHaveBeenCalled();
  });
});
