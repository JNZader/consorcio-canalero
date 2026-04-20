/**
 * useWaterways.test.ts — Batch 5 (Phase 6 removals)
 *
 * Locks in the contract AFTER removing the legacy `canales_existentes` layer:
 *   1. `WATERWAY_DEFS` no longer contains `canales_existentes`.
 *   2. The hook does NOT fetch `/api/v2/public/sugerencias/canales-existentes`
 *      (that endpoint is being retired in this batch).
 *   3. The hook does NOT fetch `/waterways/canales_existentes.geojson`.
 *   4. The 5 remaining waterways (rio_tercero, canal_desviador,
 *      canal_litin_tortugas, arroyo_algodon, arroyo_las_mojarras) still load.
 *
 * These tests are RED at the time of writing — the hook still references
 * `canales_existentes`. They turn GREEN once `useWaterways.ts` drops the
 * branch + sugerencias merge logic (task 6.3).
 */

import { describe, expect, it, beforeEach, vi, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';

import { useWaterways, WATERWAY_DEFS } from '../../src/hooks/useWaterways';

// ── fetch stub ────────────────────────────────────────────────────────────────
// Track every URL we hit so the test can assert the hook never dials the
// retired endpoints.
const fetchSpy = vi.fn();

beforeEach(() => {
  fetchSpy.mockReset();
  fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    // Any waterway fetch returns a tiny empty FeatureCollection so the hook
    // resolves without errors for the 5 kept entries.
    if (url.includes('/waterways/')) {
      return {
        ok: true,
        json: async () => ({ type: 'FeatureCollection', features: [] }),
      } as Response;
    }
    // Anything else (should NOT happen in this test) → 404 the request.
    return { ok: false, status: 404, json: async () => ({}) } as Response;
  });
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

// ──────────────────────────────────────────────────────────────────────────────
describe('useWaterways — canales_existentes removal (Batch 5)', () => {
  it('WATERWAY_DEFS no longer contains canales_existentes', () => {
    const ids = WATERWAY_DEFS.map((def) => def.id);
    expect(ids).not.toContain('canales_existentes');
  });

  it('WATERWAY_DEFS contains the 5 kept waterways (rio_tercero, canal_desviador, canal_litin_tortugas, arroyo_algodon, arroyo_las_mojarras)', () => {
    const ids = WATERWAY_DEFS.map((def) => def.id);
    expect(ids).toEqual([
      'rio_tercero',
      'canal_desviador',
      'canal_litin_tortugas',
      'arroyo_algodon',
      'arroyo_las_mojarras',
    ]);
  });

  it('does NOT fetch the retired /api/v2/public/sugerencias/canales-existentes endpoint', async () => {
    const { result } = renderHook(() => useWaterways(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    const urls = fetchSpy.mock.calls.map(([input]) =>
      typeof input === 'string' ? input : (input as URL).toString(),
    );
    expect(urls.some((u) => u.includes('/sugerencias/canales-existentes'))).toBe(false);
  });

  it('does NOT fetch /waterways/canales_existentes.geojson', async () => {
    const { result } = renderHook(() => useWaterways(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    const urls = fetchSpy.mock.calls.map(([input]) =>
      typeof input === 'string' ? input : (input as URL).toString(),
    );
    expect(urls.some((u) => u.includes('canales_existentes'))).toBe(false);
  });
});
