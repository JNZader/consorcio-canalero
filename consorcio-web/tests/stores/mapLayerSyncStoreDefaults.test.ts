/**
 * mapLayerSyncStoreDefaults.test.ts
 *
 * Locks in the startup-default layer visibility contract for the 2D map.
 *
 * Contract (see feat(ui): startup defaults + map-fluidity T1):
 *   - Hidrografía (`waterways`), Red Vial (`roads`) and Catastro rural
 *     (`catastro`) start visible.
 *   - Every other registered vector layer (approved zones, Pilar Verde, IGN
 *     histórico, DEM overlays, hydraulic risk, soil, etc.) starts hidden.
 *
 * `catastro` was flipped OFF → ON in the map-fluidity pass: its fill is the only
 * clickable surface that opens the ficha territorial, so while it was hidden a
 * citizen could click a parcel and get no response whatsoever.
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

import { useMapLayerSyncStore, PILAR_VERDE_LAYER_IDS } from '../../src/stores/mapLayerSyncStore';
import { DEFAULT_BASE_LAYER } from '../../src/components/map2d/map2dConfig';

/**
 * The ONLY top-level vector layer ids that should start visible on first load.
 * Sub-layers of Hidrografía (`waterways_*`) are not user-visible toggles —
 * they are implicit filters activated alongside the parent `waterways` layer.
 */
const INITIAL_ON_VECTORS = [
  'roads',
  'waterways',
  // map-fluidity T1: Catastro rural flipped OFF → ON. The parcel fill is the
  // only clickable surface that opens the ficha territorial, so with the layer
  // hidden a citizen clicking a parcel got no response at all.
  'catastro',
] as const;

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
  // `catastro` MOVED to INITIAL_ON_VECTORS (map-fluidity T1) — see above.
  'hydraulic_risk',
  'puntos_conflicto',
  // Pilar Azul — Escuelas rurales (v1 master toggle, opt-in per design §7).
  'escuelas',
] as const;

/**
 * map3d startup lists. They mirror map2d EXCEPT for `catastro`: the flip to ON
 * exists to make the ficha territorial discoverable, and the 3D terrain viewer
 * has no ficha — mirroring it there would only load a heavy vector-tile fill for
 * no user benefit. See MAP3D_DEFAULT_VISIBLE_VECTORS.
 */
const MAP3D_ON_VECTORS = INITIAL_ON_VECTORS.filter((id) => id !== 'catastro');
const MAP3D_OFF_VECTORS = [...INITIAL_OFF_VECTORS, 'catastro'] as const;

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

  describe('map3d initial visibleVectors (mirrors map2d defaults)', () => {
    // Since `unify 2D and 3D viewer layer behaviour` (acb1d23), map3d
    // defaults intentionally mirror map2d: roads/waterways/canales
    // relevados start VISIBLE so switching 2D→3D shows a consistent map.
    const initial = useMapLayerSyncStore.getState().map3d.visibleVectors;

    it.each(MAP3D_ON_VECTORS)('%s starts visible on map3d', (id) => {
      expect(initial[id]).toBe(true);
    });

    it.each(MAP3D_OFF_VECTORS)('%s starts hidden on map3d', (id) => {
      expect(initial[id]).toBe(false);
    });

    it('starts Canales relevados visible (propuestos hidden) on map3d', () => {
      expect(initial.canales_relevados).toBe(true);
      expect(initial.canales_propuestos).toBe(false);
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
