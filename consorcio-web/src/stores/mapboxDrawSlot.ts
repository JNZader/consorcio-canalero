/**
 * mapboxDrawSlot — global mutex for the single MapboxDraw "slot" per map.
 *
 * Why this exists
 * ---------------
 * `@mapbox/mapbox-gl-draw` hard-codes its source IDs (`mapbox-gl-draw-cold` /
 * `mapbox-gl-draw-hot`) inside the library — there is NO way to namespace
 * them. So if two MapboxDraw instances try to coexist on the same MapLibre
 * map (`LineDrawControl` for canal drawing AND `useMeasurement` for distance
 * / area measuring), the second `addControl` crashes with
 * `Source "mapbox-gl-draw-cold" already exists`. On unmount the cleanup
 * races the same way: `Source ... cannot be removed while layer ... is using
 * it`, eventually forcing a WebGL context loss.
 *
 * Pragmatic fix: serialise. Only ONE owner at a time.
 *
 *   - `LineDrawControl` is the always-on default for operators. It tries to
 *     `acquire('line-draw')` on mount; succeeds when the slot is empty or
 *     already owned by `'line-draw'`.
 *   - `useMeasurement` is on-demand. When `startDistance` / `startArea` is
 *     called, it `acquire('measurement')` which is ALWAYS granted and forces
 *     `LineDrawControl` to release (its `useEffect` re-runs, removes the
 *     control, and stays unmounted while owner === 'measurement').
 *   - On `clear()` / `cancel()`, measurement releases. `LineDrawControl`
 *     re-runs and re-mounts with the same external `value`, so previously
 *     drawn canal lines reappear (the controlled-component pattern in
 *     LineDrawControl restores them via `draw.add(...)`).
 *
 * Note: this store is intentionally NOT scoped per-map. The app only ever
 * mounts ONE `MapaMapLibre` at a time, so a global slot is enough. If we
 * ever instantiate multiple maps, swap to a `WeakMap<Map, Owner>`.
 */

import { create } from 'zustand';

export type MapboxDrawOwner = 'line-draw' | 'measurement';

interface MapboxDrawSlotState {
  owner: MapboxDrawOwner | null;
  /**
   * Try to claim the slot.
   *
   * - `'measurement'` ALWAYS wins (kicks out `'line-draw'`).
   * - `'line-draw'` only succeeds when the slot is empty or already
   *   owned by `'line-draw'`. If `'measurement'` holds it, returns false
   *   and the caller MUST NOT mount its MapboxDraw.
   *
   * Returns whether the caller is allowed to proceed with mount.
   */
  acquire: (owner: MapboxDrawOwner) => boolean;
  /**
   * Release the slot. Only releases when the current owner matches —
   * a no-op otherwise (defensive against stale cleanup callbacks).
   */
  release: (owner: MapboxDrawOwner) => void;
}

export const useMapboxDrawSlot = create<MapboxDrawSlotState>((set, get) => ({
  owner: null,
  acquire: (owner) => {
    const current = get().owner;
    if (owner === 'measurement') {
      set({ owner });
      return true;
    }
    // owner === 'line-draw'
    if (current === null || current === 'line-draw') {
      set({ owner: 'line-draw' });
      return true;
    }
    return false;
  },
  release: (owner) => {
    if (get().owner === owner) {
      set({ owner: null });
    }
  },
}));
