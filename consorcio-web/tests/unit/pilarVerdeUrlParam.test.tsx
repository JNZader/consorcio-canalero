/**
 * pilarVerdeUrlParam.test.tsx
 *
 * Verifies the one-shot mount-time URL param handler that Phase 4 adds to
 * `MapaMapLibre.tsx`. The handler reads `?pilarVerde=1` from `location.search`
 * and calls `setVectorVisibility('map2d', layerId, true)` for each of the 5
 * Pilar Verde layer IDs.
 *
 * Design rules (per Phase 2 risk #3):
 *   - Flip happens ONCE at mount — no per-render override
 *   - Without the param, the handler MUST be a no-op (does not touch store)
 *   - With `?pilarVerde=0` / any other value, it MUST be a no-op too
 *
 * The handler lives in its own hook `useApplyPilarVerdeUrlParam` so this test
 * does not need to mount the entire MapaMapLibre tree.
 */

import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// `tests/setup.ts` leaves `window.localStorage` in a state that zustand's
// `persist` middleware can't write to — neutralise persist for this test so
// the in-memory store shape is all we exercise. (Same pattern as
// `tests/stores/mapLayerSyncStorePilarVerde.test.ts`.)
vi.mock('zustand/middleware', async () => {
  const actual = await vi.importActual<typeof import('zustand/middleware')>('zustand/middleware');
  return {
    ...actual,
    persist: (fn: unknown) => fn,
  };
});

import { useApplyPilarVerdeUrlParam } from '../../src/components/map2d/useApplyPilarVerdeUrlParam';
import {
  PILAR_VERDE_LAYER_IDS,
  useMapLayerSyncStore,
} from '../../src/stores/mapLayerSyncStore';

const originalSearch = window.location.search;

function setSearch(search: string) {
  // jsdom: mutate only the `search` slot to avoid blowing up window.localStorage
  // bindings used by the persist() middleware in the mapLayerSync store.
  Object.defineProperty(window.location, 'search', {
    configurable: true,
    value: search,
    writable: true,
  });
}

function resetStore() {
  // Hard-reset each of the 5 Pilar Verde layers to false so each test starts clean.
  const setVis = useMapLayerSyncStore.getState().setVectorVisibility;
  for (const id of PILAR_VERDE_LAYER_IDS) {
    setVis('map2d', id, false);
  }
}

describe('useApplyPilarVerdeUrlParam()', () => {
  beforeEach(() => {
    resetStore();
  });

  afterEach(() => {
    Object.defineProperty(window.location, 'search', {
      configurable: true,
      value: originalSearch,
      writable: true,
    });
  });

  it('flips all 5 Pilar Verde layers visible when ?pilarVerde=1', () => {
    setSearch('?pilarVerde=1');
    renderHook(() => useApplyPilarVerdeUrlParam());
    const vectors = useMapLayerSyncStore.getState().map2d.visibleVectors;
    for (const id of PILAR_VERDE_LAYER_IDS) {
      expect(vectors[id]).toBe(true);
    }
  });

  it('is a no-op when the URL does not carry pilarVerde=1', () => {
    setSearch('');
    renderHook(() => useApplyPilarVerdeUrlParam());
    const vectors = useMapLayerSyncStore.getState().map2d.visibleVectors;
    for (const id of PILAR_VERDE_LAYER_IDS) {
      expect(vectors[id]).toBe(false);
    }
  });

  it('is a no-op when pilarVerde=0', () => {
    setSearch('?pilarVerde=0');
    renderHook(() => useApplyPilarVerdeUrlParam());
    const vectors = useMapLayerSyncStore.getState().map2d.visibleVectors;
    for (const id of PILAR_VERDE_LAYER_IDS) {
      expect(vectors[id]).toBe(false);
    }
  });

  it('only fires at mount — subsequent re-renders do not re-apply', () => {
    setSearch('?pilarVerde=1');
    const { rerender } = renderHook(() => useApplyPilarVerdeUrlParam());
    // After mount, manually flip one layer OFF, then force a re-render. If the
    // hook were not one-shot, it would flip it back to true.
    useMapLayerSyncStore.getState().setVectorVisibility('map2d', 'pilar_verde_bpa', false);
    rerender();
    const vectors = useMapLayerSyncStore.getState().map2d.visibleVectors;
    expect(vectors.pilar_verde_bpa).toBe(false);
  });
});
