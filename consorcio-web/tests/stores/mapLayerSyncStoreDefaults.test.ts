/**
 * mapLayerSyncStoreDefaults.test.ts
 *
 * Locks in the startup-default layer visibility contract for the 2D map.
 *
 * Contract (see feat(ui): startup defaults):
 *   - Only Hidrografía (`waterways`) + Red Vial (`roads`) start visible.
 *   - Every other registered vector layer (Catastro rural, approved zones,
 *     Pilar Verde, IGN histórico, DEM overlays, hydraulic risk, soil, etc.)
 *     starts hidden.
 *
 * The base layer default lives in `MapaMapLibre.tsx` (component-local state),
 * not in this store — but the 4 canonical layers are: Satélite, Imagen,
 * Hidrografía, Red Vial. This file covers the vector slice only.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// Neutralise persist middleware — see mapLayerSyncStorePilarVerde.test.ts for
// the same workaround (happy-dom `localStorage` is missing `setItem` at the
// moment `createJSONStorage` runs).
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
} from '../../src/stores/mapLayerSyncStore';
import { DEFAULT_BASE_LAYER } from '../../src/components/map2d/map2dConfig';

/**
 * The ONLY top-level vector layer ids that should start visible on first load.
 * Sub-layers of Hidrografía (`waterways_*`) are not user-visible toggles —
 * they are implicit filters activated alongside the parent `waterways` layer.
 */
const INITIAL_ON_VECTORS = ['roads', 'waterways'] as const;

/**
 * Top-level user-facing vector ids that MUST start hidden.
 * (Does not list waterways_* sub-filters, which are internal.)
 */
const INITIAL_OFF_VECTORS = [
  'approved_zones',
  'zona',
  'cuencas',
  'basins',
  'ign_historico',
  'soil',
  'catastro',
  'hydraulic_risk',
  'puntos_conflicto',
] as const;

describe('mapLayerSyncStore — startup defaults', () => {
  beforeEach(() => {
    // Nothing to reset for the defaults assertions — we only read initial state
    // as constructed by `create(...)`.
  });

  describe('map2d initial visibleVectors', () => {
    const initial = useMapLayerSyncStore.getState().map2d.visibleVectors;

    it.each(INITIAL_ON_VECTORS)('%s starts visible (true)', (id) => {
      expect(initial[id]).toBe(true);
    });

    it.each(INITIAL_OFF_VECTORS)('%s starts hidden (false)', (id) => {
      expect(initial[id]).toBe(false);
    });

    it('all Pilar Verde layers start hidden', () => {
      for (const id of PILAR_VERDE_LAYER_IDS) {
        expect(initial[id]).toBe(false);
      }
    });

    it('arbitrary unregistered id is undefined (i.e. not forced on)', () => {
      // Smoke: any random non-registered id is falsy by default — users must
      // register layers explicitly, and unknown ids do NOT start visible.
      expect(initial['some_random_unregistered_layer']).toBeUndefined();
    });
  });

  describe('map3d initial visibleVectors (mirrors map2d)', () => {
    const initial = useMapLayerSyncStore.getState().map3d.visibleVectors;

    it.each(INITIAL_ON_VECTORS)('%s starts visible on map3d', (id) => {
      expect(initial[id]).toBe(true);
    });

    it.each(INITIAL_OFF_VECTORS)('%s starts hidden on map3d', (id) => {
      expect(initial[id]).toBe(false);
    });
  });

  describe('activeRasterType defaults', () => {
    it('starts null on both views (no DEM overlay active)', () => {
      const state = useMapLayerSyncStore.getState();
      expect(state.map2d.activeRasterType).toBeNull();
      expect(state.map3d.activeRasterType).toBeNull();
    });
  });

  describe('base layer default', () => {
    it('defaults to satellite (imagery) so startup shows the 4 canonical layers', () => {
      expect(DEFAULT_BASE_LAYER).toBe('satellite');
    });
  });
});
