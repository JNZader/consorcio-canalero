/**
 * usePilarVerdeLazy.test.ts — T3c fix 1 (lazy-load the eager GeoJSON).
 *
 * Contract under test:
 *   - The 10 assets are partitioned into three independently gated groups
 *     (`meta` / `layers` / `bpa`) with NO slot lost or duplicated.
 *   - With `layers: false` + `bpa: false`, ONLY aggregates.json is fetched —
 *     ~1.6MB stays on the server on a fresh /mapa mount.
 *   - Flipping a group on fires exactly that group's fetches.
 *   - `bpaLoading` reports the BPA group's in-flight state so the ficha can show
 *     a pending state instead of a premature "Sin vinculación".
 */

import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  PILAR_VERDE_PUBLIC_PATHS,
  PILAR_VERDE_SLOT_GROUPS,
  PILAR_VERDE_UNFETCHED_SLOTS,
  usePilarVerde,
} from '../../src/hooks/usePilarVerde';
import { createQueryWrapper } from '../test-utils';

const minimalFC = { type: 'FeatureCollection', features: [] };
const aggregatesSample = { schema_version: '1.2' };
const bpaEnrichedSample = { schema_version: '1.2', parcels: [] };

let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch = vi.fn((url: string) => {
    if (url.endsWith('aggregates.json')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => aggregatesSample });
    }
    if (url.endsWith('bpa_enriched.json')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => bpaEnrichedSample });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => minimalFC });
  });
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function fetchedUrls(): string[] {
  return mockFetch.mock.calls.map((call) => call[0] as string);
}

describe('PILAR_VERDE_SLOT_GROUPS', () => {
  it('accounts for every public path exactly once (fetched group OR unfetched)', () => {
    const grouped = Object.values(PILAR_VERDE_SLOT_GROUPS).flat();
    const accounted = [...grouped, ...PILAR_VERDE_UNFETCHED_SLOTS];
    expect([...accounted].sort()).toEqual(Object.keys(PILAR_VERDE_PUBLIC_PATHS).sort());
    expect(new Set(accounted).size).toBe(accounted.length);
  });

  it('keeps the consumer-less slots OUT of every fetched group (R2-004)', () => {
    const grouped = Object.values(PILAR_VERDE_SLOT_GROUPS).flat() as string[];
    for (const slot of PILAR_VERDE_UNFETCHED_SLOTS) {
      expect(grouped).not.toContain(slot);
    }
  });
});

describe('usePilarVerde — group gating (T3c fix 1)', () => {
  it('fetches ONLY aggregates.json when both heavy groups are off', async () => {
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde({ layers: false, bpa: false }), { wrapper });

    await waitFor(() => expect(result.current.data?.aggregates).toBeTruthy());

    expect(fetchedUrls()).toEqual([PILAR_VERDE_PUBLIC_PATHS.aggregates]);
    expect(result.current.data?.bpaEnriched).toBeNull();
    expect(result.current.data?.porcentajeForestacion).toBeNull();
    expect(result.current.bpaLoading).toBe(false);
  });

  it('fires the 7 render GeoJSON only once the layers gate opens', async () => {
    const wrapper = createQueryWrapper();
    const { result, rerender } = renderHook(
      ({ layers }: { layers: boolean }) => usePilarVerde({ layers, bpa: false }),
      { wrapper, initialProps: { layers: false } }
    );
    await waitFor(() => expect(result.current.data?.aggregates).toBeTruthy());
    expect(fetchedUrls()).not.toContain(PILAR_VERDE_PUBLIC_PATHS.porcentajeForestacion);

    rerender({ layers: true });

    await waitFor(() =>
      expect(fetchedUrls()).toContain(PILAR_VERDE_PUBLIC_PATHS.porcentajeForestacion)
    );
    for (const slot of PILAR_VERDE_SLOT_GROUPS.layers) {
      expect(fetchedUrls()).toContain(PILAR_VERDE_PUBLIC_PATHS[slot]);
    }
    // The BPA pair stayed on the server.
    expect(fetchedUrls()).not.toContain(PILAR_VERDE_PUBLIC_PATHS.bpaEnriched);
  });

  it('feeds the BPA join once its gate opens (parcela ficha intent)', async () => {
    const wrapper = createQueryWrapper();
    const { result, rerender } = renderHook(
      ({ bpa }: { bpa: boolean }) => usePilarVerde({ layers: false, bpa }),
      { wrapper, initialProps: { bpa: false } }
    );
    await waitFor(() => expect(result.current.data?.aggregates).toBeTruthy());
    expect(result.current.data?.bpaEnriched).toBeNull();

    rerender({ bpa: true });

    await waitFor(() => expect(result.current.data?.bpaEnriched).not.toBeNull());
    expect(fetchedUrls()).toContain(PILAR_VERDE_PUBLIC_PATHS.bpaEnriched);
    expect(fetchedUrls()).toContain(PILAR_VERDE_PUBLIC_PATHS.bpaHistory);
    expect(result.current.bpaLoading).toBe(false);
  });

  it('reports bpaLoading TRUE while the BPA group is in flight (R3-002)', async () => {
    // A never-resolving BPA fetch pins the query in `pending + fetching`.
    const releaseBpa: Array<() => void> = [];
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('bpa_enriched.json') || url.endsWith('bpa_history.json')) {
        // BOTH slots need a resolver: the group only settles once every fetch
        // in it does, so one entry per pending fetch.
        return new Promise((resolve) => {
          releaseBpa.push(() =>
            resolve({ ok: true, status: 200, json: async () => bpaEnrichedSample })
          );
        });
      }
      if (url.endsWith('aggregates.json')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => aggregatesSample });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => minimalFC });
    });

    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde({ layers: false, bpa: true }), { wrapper });

    await waitFor(() => expect(result.current.bpaLoading).toBe(true));
    expect(result.current.data?.bpaEnriched ?? null).toBeNull();

    for (const release of releaseBpa) release();
    await waitFor(() => expect(result.current.bpaLoading).toBe(false));
  });

  it('RETRIES a failed group when its gate re-opens instead of caching nulls (R4-001)', async () => {
    let failLayers = true;
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('aggregates.json')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => aggregatesSample });
      }
      if (url.endsWith('agro_zonas.geojson') && failLayers) {
        return Promise.resolve({ ok: false, status: 503, json: async () => ({}) });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => minimalFC });
    });

    const wrapper = createQueryWrapper();
    const { result, rerender } = renderHook(
      ({ layers }: { layers: boolean }) => usePilarVerde({ layers, bpa: false }),
      { wrapper, initialProps: { layers: true } }
    );

    await waitFor(() => expect(result.current.layersError).not.toBeNull());
    expect(result.current.data?.agroZonas ?? null).toBeNull();

    // Toggle the family off and back on — the errored query has no cached data,
    // so `staleTime: Infinity` cannot shield it and the fetch runs again.
    rerender({ layers: false });
    failLayers = false;
    rerender({ layers: true });

    await waitFor(() => expect(result.current.data?.agroZonas).not.toBeNull());
    expect(result.current.layersError).toBeNull();
  });

  it('master `enabled: false` still fetches nothing at all', async () => {
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde({ enabled: false }), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.data).toBeNull();
  });
});
