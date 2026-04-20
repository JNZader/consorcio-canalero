/**
 * mapLayerSyncStorePilarVerde.test.ts
 *
 * Verifies the Pilar Verde additions to the existing visible-vectors slice:
 *   - 5 new layer IDs declared with default visibility = false
 *   - Toggle flow works for each (setVectorVisibility on map2d/map3d)
 *   - Existing layers are unaffected
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// `tests/setup.ts` installs a `vi.fn()`-only localStorage mock, but happy-dom
// initialises `window.localStorage` as an object WITHOUT `setItem` before
// setup runs — zustand's `createJSONStorage` captures that broken object
// eagerly at module-import time, so subsequent `setState` calls blow up
// with "storage.setItem is not a function".
//
// Neutralise the persist middleware for this test — we only care about the
// in-memory store shape, not about localStorage round-tripping.
vi.mock('zustand/middleware', async () => {
  const actual = await vi.importActual<typeof import('zustand/middleware')>('zustand/middleware');
  return {
    ...actual,
    persist: (fn: unknown) => fn,
  };
});

import {
  useMapLayerSyncStore,
  PILAR_VERDE_LAYER_IDS,
  PILAR_VERDE_DEFAULT_VISIBILITY,
} from '../../src/stores/mapLayerSyncStore';

describe('mapLayerSyncStore — Pilar Verde slots', () => {
  beforeEach(() => {
    // Reset both views to a known default so toggles are isolated.
    useMapLayerSyncStore.setState((s) => ({
      ...s,
      map2d: {
        activeRasterType: null,
        visibleVectors: { ...s.map2d.visibleVectors, ...PILAR_VERDE_DEFAULT_VISIBILITY },
      },
      map3d: {
        activeRasterType: null,
        visibleVectors: { ...s.map3d.visibleVectors, ...PILAR_VERDE_DEFAULT_VISIBILITY },
      },
    }));
  });

  it('exposes the 5 expected Pilar Verde layer IDs', () => {
    expect(PILAR_VERDE_LAYER_IDS).toEqual([
      'pilar_verde_bpa',
      'pilar_verde_agro_aceptada',
      'pilar_verde_agro_presentada',
      'pilar_verde_agro_zonas',
      'pilar_verde_porcentaje_forestacion',
    ]);
  });

  it('default visibility for every Pilar Verde layer is false', () => {
    for (const id of PILAR_VERDE_LAYER_IDS) {
      expect(PILAR_VERDE_DEFAULT_VISIBILITY[id]).toBe(false);
    }
  });

  it('initial map2d state has all Pilar Verde layers OFF', () => {
    const state = useMapLayerSyncStore.getState();
    for (const id of PILAR_VERDE_LAYER_IDS) {
      expect(state.map2d.visibleVectors[id]).toBe(false);
    }
  });

  it('setVectorVisibility flips a Pilar Verde layer ON for map2d', () => {
    const { setVectorVisibility } = useMapLayerSyncStore.getState();
    setVectorVisibility('map2d', 'pilar_verde_bpa', true);
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.pilar_verde_bpa).toBe(true);
    // Other Pilar Verde layers unchanged.
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.pilar_verde_agro_aceptada).toBe(false);
  });

  it('setVectorVisibility on map3d does not touch map2d', () => {
    const { setVectorVisibility } = useMapLayerSyncStore.getState();
    setVectorVisibility('map3d', 'pilar_verde_agro_zonas', true);
    expect(useMapLayerSyncStore.getState().map3d.visibleVectors.pilar_verde_agro_zonas).toBe(true);
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.pilar_verde_agro_zonas).toBe(false);
  });

  it('toggling Pilar Verde layers does not affect existing layer slots', () => {
    const { setVectorVisibility } = useMapLayerSyncStore.getState();
    const beforeRoads = useMapLayerSyncStore.getState().map2d.visibleVectors.roads;
    setVectorVisibility('map2d', 'pilar_verde_porcentaje_forestacion', true);
    expect(useMapLayerSyncStore.getState().map2d.visibleVectors.roads).toBe(beforeRoads);
  });
});
