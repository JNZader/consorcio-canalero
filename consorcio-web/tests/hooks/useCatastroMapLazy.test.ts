/**
 * useCatastroMapLazy.test.ts
 *
 * R4-003 — `/data/catastro_rural_cu.geojson` is a multi-MB asset whose ONLY 2D
 * consumer is the KMZ export (`exportSources.catastro`); the 2D catastro render
 * uses Martin vector tiles. Catastro now defaults to VISIBLE, so gating the
 * fetch on layer visibility made every visitor pay a multi-MB download plus a
 * main-thread parse for a file the map never renders.
 *
 * `MapaMapLibre` now passes `enabled: exportIntent` (latched when the Export
 * dropdown opens). This pins the hook side of that contract:
 *   - disabled → ZERO network calls;
 *   - enabled  → exactly one fetch of the geojson, cached afterwards.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useCatastroMap } from '../../src/hooks/useCatastroMap';

const fetchSpy = vi.fn();

beforeEach(() => {
  fetchSpy.mockReset();
  fetchSpy.mockImplementation(
    async () =>
      ({
        ok: true,
        json: async () => ({ type: 'FeatureCollection', features: [] }),
      }) as Response
  );
  vi.stubGlobal('fetch', fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

describe('useCatastroMap — export-intent gating', () => {
  it('fetches NOTHING while disabled (a plain map visitor never pays for it)', async () => {
    const { result } = renderHook(() => useCatastroMap({ enabled: false }), { wrapper });

    // Give react-query a tick to do anything it might have wanted to do.
    await waitFor(() => expect(result.current.catastroMap).toBeNull());
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('fetches the geojson once when export intent enables it', async () => {
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useCatastroMap({ enabled }),
      { wrapper, initialProps: { enabled: false } }
    );

    expect(fetchSpy).not.toHaveBeenCalled();

    rerender({ enabled: true });

    await waitFor(() => expect(result.current.catastroMap).not.toBeNull());
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith('/data/catastro_rural_cu.geojson');
  });
});
