/**
 * useMapLayerEffectsOpacityOrder.test.ts
 *
 * THE regression guard for the map-redesign Fase 3 opacity/order feature.
 *
 * The #1 rule of this whole redesign: with NO user override
 * (`opacityByLayer: {}`, `orderByLayer: []`) the imperative pipeline must make
 * ZERO opacity `setPaintProperty` calls and ZERO extra `moveLayer` calls — the
 * default rendering stays byte-identical to before the feature existed.
 *
 * Strategy: mock the sync-helper modules to no-ops so the ONLY imperative
 * `setPaintProperty` / `moveLayer` calls observable on the map mock come from
 * the two new effects under test. Then:
 *   - empty state  → assert the map mock received NONE of those calls.
 *   - override set  → assert the calls DO happen (proves the empty-state
 *     assertion is a real guard, not a vacuous "nothing ever calls it").
 */

import type { FeatureCollection } from 'geojson';
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// Neutralise persist middleware so `setState` doesn't hit happy-dom's
// incomplete `localStorage` (missing `setItem`) — same workaround the store
// unit tests use.
vi.mock('zustand/middleware', async () => {
  const actual = await vi.importActual<typeof import('zustand/middleware')>('zustand/middleware');
  return {
    ...actual,
    persist: (fn: unknown) => fn,
  };
});

vi.mock('../../src/components/map2d/mapLayerEffectHelpers', () => ({
  syncApprovedZoneLayers: vi.fn(),
  syncBaseTileVisibility: vi.fn(),
  syncBasinLayers: vi.fn(),
  syncCatastroLayers: vi.fn(),
  syncRoadLayers: vi.fn(),
  syncSoilLayers: vi.fn(),
  syncWaterwayLayers: vi.fn(),
  syncZonaLayer: vi.fn(),
  syncBpaHistoricoLayer: vi.fn(),
  syncAgroAceptadaLayer: vi.fn(),
  syncAgroPresentadaLayer: vi.fn(),
  syncAgroZonasLayer: vi.fn(),
  syncPorcentajeForestacionLayer: vi.fn(),
  syncCanalesLayers: vi.fn(),
  syncEscuelasLayer: vi.fn(),
  syncYpfEstacionBombeoLayer: vi.fn(),
}));

vi.mock('../../src/components/map2d/mapRasterOverlayHelpers', () => ({
  getVisibleRasterLayersForDem: vi.fn(() => []),
  moveDemAboveContextualVectors: vi.fn(),
  syncDemRasterLayer: vi.fn(),
  syncIgnLayer: vi.fn(),
  syncImageOverlays: vi.fn(),
  syncMartinSuggestionLayers: vi.fn(),
}));

import { useMapLayerEffects } from '../../src/components/map2d/useMapLayerEffects';
import { useMapLayerSyncStore } from '../../src/stores/mapLayerSyncStore';

function makeMapMock() {
  const setPaintProperty = vi.fn();
  const moveLayer = vi.fn();
  const map = {
    getLayer: vi.fn(() => ({})), // every layer "mounted"
    setPaintProperty,
    moveLayer,
    getStyle: vi.fn(() => ({ layers: [] })),
    getSource: vi.fn(() => ({})),
  };
  return { map, setPaintProperty, moveLayer };
}

type HookParams = Parameters<typeof useMapLayerEffects>[0];

function baseParams(
  map: ReturnType<typeof makeMapMock>['map'],
  overrides?: Partial<HookParams>
): HookParams {
  const mapRef = { current: map } as unknown as HookParams['mapRef'];
  return {
    mapRef,
    mapReady: true,
    baseLayer: 'osm',
    vectorVisibility: {},
    soilCollection: null as FeatureCollection | null,
    roadsCollection: null,
    basins: null,
    zonaCollection: null,
    approvedZonesCollection: null,
    hasApprovedZones: false,
    activeDemLayerId: null,
    showDemOverlay: false,
    demTileUrl: null,
    allGeoLayers: [],
    setVisibleRasterLayers: vi.fn(),
    showIGNOverlay: false,
    viewMode: 'base',
    selectedImage: null,
    comparison: null,
    waterwaysDefs: [],
    pilarVerde: null,
    canales: null,
    escuelas: null,
    ...overrides,
  };
}

function renderWithMap(
  map: ReturnType<typeof makeMapMock>['map'],
  overrides?: Partial<HookParams>
) {
  return renderHook(() => useMapLayerEffects(baseParams(map, overrides)));
}

describe('useMapLayerEffects · opacity/order regression guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset the map2d overrides to the untouched defaults.
    useMapLayerSyncStore.setState((s) => ({
      map2d: { ...s.map2d, opacityByLayer: {}, orderByLayer: [] },
    }));
  });

  it('DEFAULT (empty overrides): NO opacity setPaintProperty and NO extra moveLayer', () => {
    const { map, setPaintProperty, moveLayer } = makeMapMock();
    renderWithMap(map);
    expect(setPaintProperty).not.toHaveBeenCalled();
    expect(moveLayer).not.toHaveBeenCalled();
  });

  it('opacity override {soil:0.5} → setPaintProperty on soil ml layers at default*0.5', () => {
    useMapLayerSyncStore.setState((s) => ({
      map2d: { ...s.map2d, opacityByLayer: { soil: 0.5 } },
    }));
    const { map, setPaintProperty } = makeMapMock();
    renderWithMap(map);
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-soil-fill', 'fill-opacity', 0.15);
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-soil-line', 'line-opacity', 0.425);
  });

  it('order override [waterways,roads] → moveLayer reorders, roads hoisted last', () => {
    useMapLayerSyncStore.setState((s) => ({
      map2d: { ...s.map2d, orderByLayer: ['waterways', 'roads'] },
    }));
    const { map, moveLayer } = makeMapMock();
    renderWithMap(map);
    // waterways (5 line layers) + roads (1) = 6 hoists.
    expect(moveLayer).toHaveBeenCalledTimes(6);
    expect(moveLayer.mock.calls.at(-1)?.[0]).toBe('map2d-roads-line');
  });

  it('FF-A3 async mount: opacity override lands once the layer mounts on a later re-render', () => {
    useMapLayerSyncStore.setState((s) => ({
      map2d: { ...s.map2d, opacityByLayer: { soil: 0.5 } },
    }));
    const setPaintProperty = vi.fn();
    // Layer is NOT mounted yet on first render, mounts before the re-render.
    let mounted = false;
    const map = {
      getLayer: vi.fn(() => (mounted ? {} : undefined)),
      setPaintProperty,
      moveLayer: vi.fn(),
      getStyle: vi.fn(() => ({ layers: [] })),
      getSource: vi.fn(() => ({})),
    };
    // STABLE mapRef across rerenders (mirrors a real useRef). Without this the
    // changing ref identity alone would re-fire the effect and mask whether
    // `layerMountSignal` is what actually re-triggers it.
    const mapRef = { current: map } as unknown as HookParams['mapRef'];
    const { rerender } = renderHook((props: HookParams) => useMapLayerEffects(props), {
      initialProps: baseParams(map, { mapRef, vectorVisibility: { soil: false } }),
    });
    // First pass: getLayer undefined → override skipped.
    expect(setPaintProperty).not.toHaveBeenCalled();

    // Data/visibility arrives: layer mounts + the mount signal changes.
    mounted = true;
    rerender(baseParams(map, { mapRef, vectorVisibility: { soil: true } }));

    // The widened deps re-fire the effect → override now applies.
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-soil-fill', 'fill-opacity', 0.15);
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-soil-line', 'line-opacity', 0.425);
  });

  it('FF-A3 re-hoist: order override is re-asserted after a sibling re-render (raise*Stack)', () => {
    useMapLayerSyncStore.setState((s) => ({
      map2d: { ...s.map2d, orderByLayer: ['waterways', 'roads'] },
    }));
    const { map, moveLayer } = makeMapMock();
    // STABLE mapRef — see the async-mount test above.
    const mapRef = { current: map } as unknown as HookParams['mapRef'];
    const { rerender } = renderHook((props: HookParams) => useMapLayerEffects(props), {
      initialProps: baseParams(map, { mapRef, vectorVisibility: { roads: true } }),
    });
    expect(moveLayer).toHaveBeenCalledTimes(6);

    moveLayer.mockClear();
    // A canales/visibility change re-runs sibling sync effects (which call
    // raise*Stack); the mount signal changes so the order effect re-asserts.
    rerender(
      baseParams(map, { mapRef, vectorVisibility: { roads: true, canales_relevados: true } })
    );
    expect(moveLayer).toHaveBeenCalledTimes(6);
    expect(moveLayer.mock.calls.at(-1)?.[0]).toBe('map2d-roads-line');
  });
});
