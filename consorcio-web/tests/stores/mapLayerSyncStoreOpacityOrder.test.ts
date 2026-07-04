/**
 * mapLayerSyncStoreOpacityOrder.test.ts
 *
 * Covers the map-redesign Fase 3 additions to the layer-sync store:
 *   - `opacityByLayer` / `orderByLayer` slots default to `{}` / `[]`.
 *   - `setLayerOpacity` clamps 0..1 and writes to the right view.
 *   - `setLayerOrder` replaces the order list on the right view.
 *   - `migrateMapLayerState` (v3 → v4) preserves ALL persisted visibility and
 *     seeds the new slots without touching anything else.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// Neutralise persist middleware — same workaround as the sibling store tests
// (happy-dom `localStorage` is missing `setItem` when `createJSONStorage` runs).
vi.mock('zustand/middleware', async () => {
  const actual = await vi.importActual<typeof import('zustand/middleware')>('zustand/middleware');
  return {
    ...actual,
    persist: (fn: unknown) => fn,
  };
});

import {
  useMapLayerSyncStore,
  migrateMapLayerState,
} from '../../src/stores/mapLayerSyncStore';

describe('mapLayerSyncStore — opacity/order defaults', () => {
  it('both views start with empty opacityByLayer {} and orderByLayer []', () => {
    const state = useMapLayerSyncStore.getState();
    expect(state.map2d.opacityByLayer).toEqual({});
    expect(state.map2d.orderByLayer).toEqual([]);
    expect(state.map3d.opacityByLayer).toEqual({});
    expect(state.map3d.orderByLayer).toEqual([]);
  });
});

describe('mapLayerSyncStore — setLayerOpacity', () => {
  beforeEach(() => {
    useMapLayerSyncStore.setState((s) => ({
      map2d: { ...s.map2d, opacityByLayer: {} },
      map3d: { ...s.map3d, opacityByLayer: {} },
    }));
  });

  it('writes a value to the targeted view only', () => {
    useMapLayerSyncStore.getState().setLayerOpacity('map2d', 'soil', 0.5);
    const state = useMapLayerSyncStore.getState();
    expect(state.map2d.opacityByLayer.soil).toBe(0.5);
    expect(state.map3d.opacityByLayer.soil).toBeUndefined();
  });

  it('clamps values above 1 down to 1', () => {
    useMapLayerSyncStore.getState().setLayerOpacity('map2d', 'roads', 5);
    expect(useMapLayerSyncStore.getState().map2d.opacityByLayer.roads).toBe(1);
  });

  it('clamps negative values up to 0', () => {
    useMapLayerSyncStore.getState().setLayerOpacity('map2d', 'roads', -3);
    expect(useMapLayerSyncStore.getState().map2d.opacityByLayer.roads).toBe(0);
  });

  it('writes to map3d independently', () => {
    useMapLayerSyncStore.getState().setLayerOpacity('map3d', 'catastro', 0.2);
    const state = useMapLayerSyncStore.getState();
    expect(state.map3d.opacityByLayer.catastro).toBe(0.2);
    expect(state.map2d.opacityByLayer.catastro).toBeUndefined();
  });
});

describe('mapLayerSyncStore — setLayerOrder', () => {
  beforeEach(() => {
    useMapLayerSyncStore.setState((s) => ({
      map2d: { ...s.map2d, orderByLayer: [] },
      map3d: { ...s.map3d, orderByLayer: [] },
    }));
  });

  it('replaces the order list on the targeted view', () => {
    useMapLayerSyncStore.getState().setLayerOrder('map2d', ['waterways', 'roads']);
    const state = useMapLayerSyncStore.getState();
    expect(state.map2d.orderByLayer).toEqual(['waterways', 'roads']);
    expect(state.map3d.orderByLayer).toEqual([]);
  });

  it('stores a copy (mutating the input array does not leak into the store)', () => {
    const input = ['soil'];
    useMapLayerSyncStore.getState().setLayerOrder('map2d', input);
    input.push('roads');
    expect(useMapLayerSyncStore.getState().map2d.orderByLayer).toEqual(['soil']);
  });
});

describe('migrateMapLayerState — v3 → v4', () => {
  it('preserves ALL persisted visibility and seeds new slots as {} / []', () => {
    const v3State = {
      map2d: {
        activeRasterType: 'dem',
        visibleVectors: { roads: true, soil: false, catastro: true, escuelas: false },
      },
      map3d: {
        activeRasterType: null,
        visibleVectors: { roads: true, waterways: true, canales_relevados: true },
      },
      propuestasEtapasVisibility: { Alta: false, Media: true },
      terrainSmoothingEnabled: false,
      terrainSmoothingThreshold: 'high',
    };

    const migrated = migrateMapLayerState(v3State, 3);

    // Visibility preserved verbatim.
    expect(migrated.map2d?.visibleVectors).toEqual({
      roads: true,
      soil: false,
      catastro: true,
      escuelas: false,
    });
    expect(migrated.map3d?.visibleVectors).toEqual({
      roads: true,
      waterways: true,
      canales_relevados: true,
    });
    // Other persisted fields untouched.
    expect(migrated.map2d?.activeRasterType).toBe('dem');
    expect(migrated.terrainSmoothingEnabled).toBe(false);
    expect(migrated.terrainSmoothingThreshold).toBe('high');
    expect(migrated.propuestasEtapasVisibility).toEqual({ Alta: false, Media: true });

    // New slots seeded empty on BOTH views.
    expect(migrated.map2d?.opacityByLayer).toEqual({});
    expect(migrated.map2d?.orderByLayer).toEqual([]);
    expect(migrated.map3d?.opacityByLayer).toEqual({});
    expect(migrated.map3d?.orderByLayer).toEqual([]);
  });

  it('does NOT clobber opacity/order values already present (idempotent)', () => {
    const partialV4 = {
      map2d: {
        activeRasterType: null,
        visibleVectors: { roads: true },
        opacityByLayer: { soil: 0.5 },
        orderByLayer: ['soil'],
      },
      map3d: { activeRasterType: null, visibleVectors: {} },
    };

    const migrated = migrateMapLayerState(partialV4, 3);
    expect(migrated.map2d?.opacityByLayer).toEqual({ soil: 0.5 });
    expect(migrated.map2d?.orderByLayer).toEqual(['soil']);
    // map3d had neither → seeded empty.
    expect(migrated.map3d?.opacityByLayer).toEqual({});
    expect(migrated.map3d?.orderByLayer).toEqual([]);
  });

  it('v3 migration still runs its own step when coming from v2', () => {
    const v2State = {
      map3d: { activeRasterType: null, visibleVectors: { roads: false } },
    };
    const migrated = migrateMapLayerState(v2State, 2);
    // v2→v3 step forces roads/waterways/canales on map3d ...
    expect(migrated.map3d?.visibleVectors?.roads).toBe(true);
    expect(migrated.map3d?.visibleVectors?.canales_relevados).toBe(true);
    // ... and v3→v4 seeds the new slots.
    expect(migrated.map3d?.opacityByLayer).toEqual({});
    expect(migrated.map3d?.orderByLayer).toEqual([]);
  });
});
