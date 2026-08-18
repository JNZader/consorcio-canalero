/**
 * useHazardMapState.test.ts
 *
 * Integration-level tests for the Multi-Hazard map state hook.
 * Verifies that enabling hazard mode applies the canonical layer stack,
 * that non-operator users are gated out, and that the map-side basin filter
 * is built/removed as the basin selection changes.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { Feature } from 'geojson';
import type { MutableRefObject } from 'react';
import type maplibregl from 'maplibre-gl';
import { useHazardMapState } from '../../src/components/map2d/useHazardMapState';
import type { HazardUrlState } from '../../src/hooks/useHazardUrlState';
import {
  HAZARD_VISIBILITY_SNAPSHOT_KEY,
  readHazardVisibilitySnapshot,
  clearHazardVisibilitySnapshot,
} from '../../src/components/map2d/hazardVisibilitySnapshot';

/** Documented normal defaults used by the fresh-shared-link fallback. */
const { NORMAL_DEFAULT_VECTORS } = vi.hoisted(() => ({
  NORMAL_DEFAULT_VECTORS: {
    roads: true,
    waterways: true,
    catastro: true,
    soil: false,
    approved_zones: false,
    zona: false,
    cuencas: false,
    basins: false,
    hydraulic_risk: false,
    puntos_conflicto: false,
    ign_historico: false,
    canales_relevados: true,
    canales_propuestos: false,
    escuelas: false,
    pilar_verde_bpa_historico: false,
    pilar_verde_agro_aceptada: false,
    pilar_verde_agro_presentada: false,
    pilar_verde_agro_zonas: false,
    pilar_verde_porcentaje_forestacion: false,
  } as Record<string, boolean>,
}));

const CANONICAL_STACK = [
  'flood_risk',
  'drainage_need',
  'soil',
  'canales_relevados',
  'basins',
  'precip_normal',
];

const mocks = vi.hoisted(() => ({
  gateOpen: true,
  url: {
    hazard: false,
    isHazardActive: false,
    basin: null,
    riskClasses: [],
    precipMonth: 'anual',
    setHazard: vi.fn(),
    setBasin: vi.fn(),
    setRiskClasses: vi.fn(),
    setPrecipMonth: vi.fn(),
    resetToDefaults: vi.fn(),
  } as HazardUrlState,
  store: {
    panelOpen: true,
    mobileExpanded: false,
    pendingBasinZoom: false,
    setPanelOpen: vi.fn(),
    setMobileExpanded: vi.fn(),
    setPendingBasinZoom: vi.fn(),
    minimizeForFicha: vi.fn(),
    reset: vi.fn(),
  },
  shared: {
    map2d: {
      visibleVectors: {
        roads: true,
        waterways: true,
        catastro: true,
        soil: false,
      } as Record<string, boolean>,
    },
    setVectorVisibility: vi.fn(),
  },
}));

function createFakeMap() {
  const layers = new Map<string, unknown>();
  const sources = new Map<string, unknown>();
  const handlers = new Map<string, Array<() => void>>();
  return {
    getLayer: (id: string) => layers.get(id) ?? undefined,
    getSource: (id: string) => sources.get(id) ?? undefined,
    addSource: vi.fn((id: string, source: unknown) => sources.set(id, source)),
    removeSource: vi.fn((id: string) => sources.delete(id)),
    addLayer: vi.fn((layer: { id: string }) => layers.set(layer.id, layer)),
    removeLayer: vi.fn((id: string) => layers.delete(id)),
    setFilter: vi.fn(),
    setLayoutProperty: vi.fn(),
    setPaintProperty: vi.fn(),
    moveLayer: vi.fn(),
    fitBounds: vi.fn(),
    once: vi.fn((event: string, fn: () => void) => {
      const list = handlers.get(event) ?? [];
      list.push(fn);
      handlers.set(event, list);
    }),
    off: vi.fn(),
    getCanvas: () => ({ style: { cursor: '' } }),
    getStyle: () => ({ layers: [] }),
  };
}

vi.mock('../../src/hooks/useMultiHazardGate', () => ({
  useMultiHazardGate: () => mocks.gateOpen,
}));

vi.mock('../../src/hooks/useHazardUrlState', () => ({
  useHazardUrlState: () => mocks.url,
  HAZARD_DEFAULT_LAYERS: [
    'flood_risk',
    'drainage_need',
    'soil',
    'canales_relevados',
    'basins',
    'precip_normal',
  ],
  HAZARD_DEFAULT_RISK_CLASSES: ['Bajo', 'Medio', 'Alto', 'Crítico'],
  HAZARD_DEFAULT_PRECIP_MONTH: 'anual',
  RISK_CLASS_LABELS: ['Bajo', 'Medio', 'Alto', 'Crítico'],
}));

vi.mock('../../src/stores/hazardMapStore', () => ({
  useHazardMapStore: () => mocks.store,
}));

vi.mock('../../src/stores/mapLayerSyncStore', () => ({
  useMapLayerSyncStore: (selector: (state: typeof mocks.shared) => unknown) =>
    selector(mocks.shared),
  defaultVisibleVectors: NORMAL_DEFAULT_VECTORS,
}));

// Auth initialization flag. Default `loading: false` (auth resolved) so the
// existing scenarios run the snapshot lifecycle exactly as before; the
// C6-R3-001 regression test flips it to `true` to simulate a pending reload.
const authState = vi.hoisted(() => ({ loading: false }));
vi.mock('../../src/stores/authStore', () => ({
  useAuthLoading: () => authState.loading,
}));

describe('useHazardMapState', () => {
  beforeEach(() => {
    mocks.gateOpen = true;
    mocks.url.hazard = false;
    mocks.url.isHazardActive = false;
    mocks.url.basin = null;
    mocks.url.riskClasses = [];
    mocks.url.precipMonth = 'anual';
    authState.loading = false;
    mocks.shared.map2d.visibleVectors = {
      roads: true,
      waterways: true,
      catastro: true,
      soil: false,
    };
    // Start every test with a clean per-tab snapshot store.
    try {
      sessionStorage.clear();
    } catch {
      // ignore (some environments disable storage)
    }
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('applies the canonical layer stack when hazard mode turns on', () => {
    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    const { rerender } = renderHook(
      ({ active }) => {
        mocks.url.hazard = active;
        mocks.url.isHazardActive = active && mocks.gateOpen;
        return useHazardMapState({
          mapRef,
          mapReady: true,
          basins: { type: 'FeatureCollection', features: [] },
          allGeoLayers: [],
          fichaActive: false,
        });
      },
      { initialProps: { active: false } }
    );

    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalledWith(
      'map2d',
      'flood_risk',
      true
    );

    act(() => rerender({ active: true }));

    for (const layerId of CANONICAL_STACK) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', layerId, true);
    }
  });

  it('does not force the canonical stack when hazard mode is off', () => {
    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    renderHook(() =>
      useHazardMapState({
        mapRef,
        mapReady: true,
        basins: { type: 'FeatureCollection', features: [] },
        allGeoLayers: [],
        fichaActive: false,
      })
    );

    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalledWith(
      'map2d',
      'flood_risk',
      true
    );
    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalledWith(
      'map2d',
      'precip_normal',
      true
    );
  });

  it('ignores hazard=1 when the user lacks the admin/operador role', () => {
    mocks.gateOpen = false;
    mocks.url.hazard = true;
    mocks.url.isHazardActive = false;

    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    renderHook(() =>
      useHazardMapState({
        mapRef,
        mapReady: true,
        basins: { type: 'FeatureCollection', features: [] },
        allGeoLayers: [],
        fichaActive: false,
      })
    );

    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalledWith(
      'map2d',
      'flood_risk',
      true
    );
    expect(mocks.url.setRiskClasses).not.toHaveBeenCalled();
  });

  it('sets a basin filter on the catastro layer when a basin is selected', () => {
    const basin = {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [-62.5, -32.5],
            [-62.4, -32.5],
            [-62.4, -32.6],
            [-62.5, -32.6],
            [-62.5, -32.5],
          ],
        ],
      },
      properties: { id: 'cuenca-1', nombre: 'Cuenca Test' },
    };

    const map = createFakeMap();
    map.getLayer = (id: string) => (id === 'map2d-catastro-fill' || id === 'map2d-catastro-line' ? {} : undefined);
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    const { rerender } = renderHook(
      ({ basinId }: { basinId: string | null }) => {
        mocks.url.hazard = true;
        mocks.url.isHazardActive = true;
        mocks.url.basin = basinId;
        return useHazardMapState({
          mapRef,
          mapReady: true,
          basins: { type: 'FeatureCollection', features: [basin as Feature] },
          allGeoLayers: [],
          fichaActive: false,
        });
      },
      { initialProps: { basinId: null } }
    );

    // Initial mount with no basin clears any existing filter by writing
    // `undefined` to both catastro layers.
    expect(map.setFilter).toHaveBeenCalledWith('map2d-catastro-fill', undefined);
    expect(map.setFilter).toHaveBeenCalledWith('map2d-catastro-line', undefined);

    act(() => rerender({ basinId: 'cuenca-1' }));

    const fillCalls = map.setFilter.mock.calls.filter(
      ([layerId]) => layerId === 'map2d-catastro-fill'
    );
    const lastFillCall = fillCalls[fillCalls.length - 1];
    expect(lastFillCall[1]).toEqual(
      expect.arrayContaining(['within', expect.objectContaining({ type: 'Feature' })])
    );
  });

  it('zooms to the basin exactly once when the async basin catalog loads after a shared URL (JD-A-1)', () => {
    const basin = {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [-62.5, -32.5],
            [-62.4, -32.5],
            [-62.4, -32.6],
            [-62.5, -32.6],
            [-62.5, -32.5],
          ],
        ],
      },
      properties: { id: 'cuenca-1', nombre: 'Cuenca Test' },
    };

    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    const { rerender } = renderHook(
      ({ ready, basinId }: { ready: boolean; basinId: string | null }) => {
        mocks.url.hazard = true;
        mocks.url.isHazardActive = true;
        mocks.url.basin = basinId;
        return useHazardMapState({
          mapRef,
          mapReady: true,
          basins: ready
            ? { type: 'FeatureCollection', features: [basin as Feature] }
            : { type: 'FeatureCollection', features: [] },
          allGeoLayers: [],
          fichaActive: false,
        });
      },
      { initialProps: { ready: false, basinId: 'cuenca-1' } }
    );

    // Before the catalog arrives, `selectedBasin` is undefined → no zoom yet.
    expect(map.fitBounds).not.toHaveBeenCalled();

    // Catalog loads → the delayed basin resolves and fitBounds fires once.
    act(() => rerender({ ready: true, basinId: 'cuenca-1' }));
    expect(map.fitBounds).toHaveBeenCalledTimes(1);

    // Further re-renders with the same selection must NOT zoom again.
    act(() => rerender({ ready: true, basinId: 'cuenca-1' }));
    expect(map.fitBounds).toHaveBeenCalledTimes(1);
  });
});

describe('useHazardMapState — H4 pre-hazard visibility snapshot', () => {
  /** A non-canonical, clearly-custom pre-hazard visibility the user chose. */
  const CUSTOM_PRE_HAZARD: Record<string, boolean> = {
    roads: false,
    waterways: true,
    catastro: false,
    soil: true,
    canales_relevados: true,
    basins: false,
  };

  /** The canonical hazard stack as it would appear persisted in the store. */
  const CANONICAL_AS_PERSISTED: Record<string, boolean> = {
    ...CUSTOM_PRE_HAZARD,
    flood_risk: true,
    drainage_need: true,
    soil: true,
    canales_relevados: true,
    basins: true,
    precip_normal: true,
  };

  function mountHazard(active: boolean, visibleVectors: Record<string, boolean>) {
    mocks.shared.map2d.visibleVectors = visibleVectors;
    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;
    mocks.url.hazard = active;
    mocks.url.isHazardActive = active && mocks.gateOpen;
    return renderHook(
      (_props: { active: boolean }) =>
        useHazardMapState({
          mapRef,
          mapReady: true,
          basins: { type: 'FeatureCollection', features: [] },
          allGeoLayers: [],
          fichaActive: false,
        }),
      { initialProps: { active } }
    );
  }

  it('normal enable → disable restores original values and clears the snapshot', () => {
    // Genuine enable: store still holds the user's pre-hazard state.
    const { rerender } = mountHazard(false, CUSTOM_PRE_HAZARD);
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();

    // Enable.
    mocks.url.hazard = true;
    mocks.url.isHazardActive = true;
    act(() => rerender({ active: true }));

    // Snapshot captured the pre-hazard (custom) state.
    const captured = readHazardVisibilitySnapshot();
    expect(captured).not.toBeNull();
    expect(captured?.values).toEqual(CUSTOM_PRE_HAZARD);

    // Disable.
    mocks.url.hazard = false;
    mocks.url.isHazardActive = false;
    act(() => rerender({ active: false }));

    // Every custom key was restored to its pre-hazard value.
    for (const [key, value] of Object.entries(CUSTOM_PRE_HAZARD)) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', key, value);
    }
    // Canonical hazard layers not in the snapshot are explicitly turned OFF.
    for (const layerId of ['flood_risk', 'drainage_need', 'precip_normal']) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', layerId, false);
    }
    // Snapshot cleared.
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('reload/remount while active preserves the snapshot and restores it exactly once', () => {
    // Simulate a prior session that wrote a valid snapshot.
    sessionStorage.setItem(
      HAZARD_VISIBILITY_SNAPSHOT_KEY,
      JSON.stringify({ version: 1, values: CUSTOM_PRE_HAZARD })
    );
    const seedRaw = sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY);

    // Reload while hazard stays active (store shows canonical stack).
    const { rerender } = mountHazard(true, CANONICAL_AS_PERSISTED);

    // Snapshot was NOT overwritten by the now-canonical store state.
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBe(seedRaw);
    const loaded = readHazardVisibilitySnapshot();
    expect(loaded?.values).toEqual(CUSTOM_PRE_HAZARD);

    // Disable once → restore + clear.
    mocks.url.hazard = false;
    mocks.url.isHazardActive = false;
    act(() => rerender({ active: false }));

    for (const [key, value] of Object.entries(CUSTOM_PRE_HAZARD)) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', key, value);
    }
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('fresh shared `hazard=1` link with no snapshot restores normal defaults', () => {
    // No snapshot, store already shows the canonical stack (fresh link in a
    // new tab that inherited the persisted hazard state).
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
    const { rerender } = mountHazard(true, CANONICAL_AS_PERSISTED);

    // Snapshot fell back to documented normal defaults, not the canonical stack.
    const captured = readHazardVisibilitySnapshot();
    expect(captured?.values).toEqual(NORMAL_DEFAULT_VECTORS);
    // The canonical stack is never written back as the restore source.
    expect(captured?.values.flood_risk).toBeUndefined();
    expect(captured?.values.precip_normal).toBeUndefined();

    // Disable → restore normal defaults + turn canonical layers OFF.
    mocks.url.hazard = false;
    mocks.url.isHazardActive = false;
    act(() => rerender({ active: false }));

    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'soil', false);
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'flood_risk', false);
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'precip_normal', false);
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'canales_relevados', true);
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('malformed snapshot is cleared and safely falls back to normal defaults', () => {
    sessionStorage.setItem(HAZARD_VISIBILITY_SNAPSHOT_KEY, '{not valid json');

    const { rerender } = mountHazard(true, CANONICAL_AS_PERSISTED);

    // Malformed blob was replaced by a fresh normal-defaults fallback snapshot.
    const captured = readHazardVisibilitySnapshot();
    expect(captured?.values).toEqual(NORMAL_DEFAULT_VECTORS);

    // Disable → normal defaults restored, no crash, snapshot cleared.
    mocks.url.hazard = false;
    mocks.url.isHazardActive = false;
    act(() => rerender({ active: false }));
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'flood_risk', false);
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('wrong-version snapshot is cleared and safely falls back to normal defaults', () => {
    sessionStorage.setItem(
      HAZARD_VISIBILITY_SNAPSHOT_KEY,
      JSON.stringify({ version: 999, values: { roads: true } })
    );

    const { rerender } = mountHazard(true, CANONICAL_AS_PERSISTED);

    // Wrong-version blob was replaced by a fresh normal-defaults fallback snapshot.
    const captured = readHazardVisibilitySnapshot();
    expect(captured?.values).toEqual(NORMAL_DEFAULT_VECTORS);

    mocks.url.hazard = false;
    mocks.url.isHazardActive = false;
    act(() => rerender({ active: false }));
    expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', 'flood_risk', false);
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('snapshot is not overwritten by an active-mode remount', () => {
    // Seed a valid snapshot from a prior session.
    sessionStorage.setItem(
      HAZARD_VISIBILITY_SNAPSHOT_KEY,
      JSON.stringify({ version: 1, values: CUSTOM_PRE_HAZARD })
    );
    const seedRaw = sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY);
    expect(seedRaw).not.toBeNull();

    // Mount while active.
    const first = mountHazard(true, CANONICAL_AS_PERSISTED);
    // Snapshot preserved exactly (not overwritten with canonical/normal).
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBe(seedRaw);

    // Remount (unmount + mount) while still active.
    first.unmount();
    mountHazard(true, CANONICAL_AS_PERSISTED);
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBe(seedRaw);
    expect(readHazardVisibilitySnapshot()?.values).toEqual(CUSTOM_PRE_HAZARD);
  });

  it('sessionStorage unavailable does not crash and falls back gracefully', () => {
    // Force the snapshot module's storage access to throw.
    const original = globalThis.sessionStorage;
    const throwing = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
      removeItem: () => {
        throw new Error('blocked');
      },
    };
    Object.defineProperty(globalThis, 'sessionStorage', {
      value: throwing,
      configurable: true,
    });

    try {
      // Genuine enable with storage unavailable: must not throw.
      const { rerender } = mountHazard(false, CUSTOM_PRE_HAZARD);
      mocks.url.hazard = true;
      mocks.url.isHazardActive = true;
      expect(() => act(() => rerender({ active: true }))).not.toThrow();

      // Disable must also not throw.
      mocks.url.hazard = false;
      mocks.url.isHazardActive = false;
      expect(() => act(() => rerender({ active: false }))).not.toThrow();

      // Restore still happened from the in-memory ref (exactly once per key).
      for (const [key, value] of Object.entries(CUSTOM_PRE_HAZARD)) {
        expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', key, value);
      }
    } finally {
      Object.defineProperty(globalThis, 'sessionStorage', {
        value: original,
        configurable: true,
      });
    }
  });

  it('C6-R3-001: reload with ?hazard=1 while auth loads preserves snapshot, then restores exactly once', () => {
    // Simulate a prior hazard session in this tab that captured the user's
    // pre-hazard layer visibility.
    sessionStorage.setItem(
      HAZARD_VISIBILITY_SNAPSHOT_KEY,
      JSON.stringify({ version: 1, values: CUSTOM_PRE_HAZARD })
    );
    const seedRaw = sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY);
    expect(seedRaw).not.toBeNull();

    // Auth is still initializing → the gate is closed and `isHazardActive` is
    // momentarily false even though `?hazard=1` was requested.
    authState.loading = true;
    mocks.url.hazard = true;
    mocks.url.isHazardActive = false;

    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    const { rerender } = renderHook(
      (_props: { active: boolean }) =>
        useHazardMapState({
          mapRef,
          mapReady: true,
          basins: { type: 'FeatureCollection', features: [] },
          allGeoLayers: [],
          fichaActive: false,
        }),
      { initialProps: { active: false } }
    );

    // Reset call history so the assertions below reflect ONLY this test's
    // pending mount (the shared mock carries residue from earlier tests).
    mocks.shared.setVectorVisibility.mockClear();

    // While auth is pending the mount effect must NOT clear the snapshot.
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBe(seedRaw);
    // No visibility writes happened during the pending mount (auth gate still
    // closed); the lifecycle must wait until auth resolves.
    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalled();

    // Auth resolves and the operator is authorized → hazard becomes active.
    authState.loading = false;
    mocks.url.isHazardActive = true;
    act(() => rerender({ active: true }));

    // Snapshot was hydrated WITHOUT being overwritten by the canonical stack.
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBe(seedRaw);
    expect(readHazardVisibilitySnapshot()?.values).toEqual(CUSTOM_PRE_HAZARD);
    // Canonical hazard layers are forced ON.
    for (const layerId of ['flood_risk', 'drainage_need', 'precip_normal']) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', layerId, true);
    }

    // Now the user disables hazard → genuine active→inactive transition must
    // restore the original visibility exactly once and clear the snapshot.
    mocks.url.hazard = false;
    mocks.url.isHazardActive = false;
    act(() => rerender({ active: false }));

    // Every original pre-hazard key was restored to its exact value.
    for (const [key, value] of Object.entries(CUSTOM_PRE_HAZARD)) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', key, value);
    }
    // Canonical hazard layers not in the snapshot are explicitly turned OFF.
    for (const layerId of ['flood_risk', 'drainage_need', 'precip_normal']) {
      expect(mocks.shared.setVectorVisibility).toHaveBeenCalledWith('map2d', layerId, false);
    }
    // Snapshot cleared exactly once.
    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
  });

  it('clears a stale snapshot on an initial resolved non-hazard mount without restoring layers', () => {
    sessionStorage.setItem(
      HAZARD_VISIBILITY_SNAPSHOT_KEY,
      JSON.stringify({ version: 1, values: CUSTOM_PRE_HAZARD })
    );
    authState.loading = false;
    mocks.url.hazard = false;
    mocks.url.isHazardActive = false;
    mocks.shared.setVectorVisibility.mockClear();

    const map = createFakeMap();
    const mapRef = { current: map as unknown as maplibregl.Map } as MutableRefObject<maplibregl.Map>;

    renderHook(() =>
      useHazardMapState({
        mapRef,
        mapReady: true,
        basins: { type: 'FeatureCollection', features: [] },
        allGeoLayers: [],
        fichaActive: false,
      })
    );

    expect(sessionStorage.getItem(HAZARD_VISIBILITY_SNAPSHOT_KEY)).toBeNull();
    expect(mocks.shared.setVectorVisibility).not.toHaveBeenCalled();
  });
});
