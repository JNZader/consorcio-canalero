/**
 * useEscuelas.test.ts
 *
 * Hook contract (mirror of `useCanales` adapted to a SINGLE static asset):
 *   - TanStack Query, queryKey = ["public", "escuelas"]
 *   - staleTime = Number.POSITIVE_INFINITY (public geojson, forever cacheable)
 *   - ONE fetch against `/capas/escuelas/escuelas_rurales.geojson` — on 2xx
 *     the hook returns `{ collection, isLoading, isError }` with the parsed
 *     FeatureCollection<Point, EscuelaFeatureProperties>.
 *   - On 404 / network reject / 500: `collection` is `null`, `isError` is
 *     `true`. The Query still resolves (no throw-through).
 *   - No per-school visibility slots (unlike canales) — one collection, one
 *     master toggle, handled at the sync-helper layer.
 *
 * Batch C scope: hook + types only. Sync helper wiring lives in Batch D.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ESCUELAS_GEOJSON_URL,
  useEscuelas,
} from '../../src/hooks/useEscuelas';

import escuelasSample from '../fixtures/escuelas/escuelasSample.json';
import { createQueryWrapper } from '../test-utils';

function mockOk(json: unknown) {
  return { ok: true, status: 200, json: async () => json };
}

function mockNotOk(status = 404) {
  return { ok: false, status, json: async () => ({}) };
}

let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch = vi.fn();
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('useEscuelas · path', () => {
  it('exposes the single canonical public asset path', () => {
    expect(ESCUELAS_GEOJSON_URL).toBe('/capas/escuelas/escuelas_rurales.geojson');
  });
});

describe('useEscuelas · happy path', () => {
  it('initializes with isLoading=true and null collection', () => {
    mockFetch.mockImplementation(() => Promise.resolve(mockOk(escuelasSample)));
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useEscuelas(), { wrapper });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.collection).toBeNull();
    expect(result.current.isError).toBe(false);
  });

  it('fires ONE fetch against the canonical geojson path', async () => {
    mockFetch.mockImplementation(() => Promise.resolve(mockOk(escuelasSample)));
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useEscuelas(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(ESCUELAS_GEOJSON_URL);
  });

  it('returns the populated FeatureCollection on happy path', async () => {
    mockFetch.mockImplementation(() => Promise.resolve(mockOk(escuelasSample)));
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useEscuelas(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.collection).not.toBeNull();
    expect(result.current.collection?.type).toBe('FeatureCollection');
    expect(result.current.collection?.features).toHaveLength(3);
    expect(result.current.isError).toBe(false);
  });

  it('preserves top-level feature.id (GeoJSON-spec idiomatic) — not properties.id', async () => {
    mockFetch.mockImplementation(() => Promise.resolve(mockOk(escuelasSample)));
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useEscuelas(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const first = result.current.collection?.features[0];
    expect(first?.id).toBe('esc-joaquin-victor-gonzalez');
    // properties must NOT duplicate the id — the 4-prop whitelist is locked.
    expect(first?.properties).toEqual({
      nombre: 'Esc. Joaquín Víctor González',
      localidad: 'Monte Leña',
      ambito: 'Rural Aglomerado',
      nivel: 'Inicial · Primario',
    });
  });
});

describe('useEscuelas · graceful degradation', () => {
  it('404 on geojson resolves with collection=null and isError=true', async () => {
    mockFetch.mockImplementation(() => Promise.resolve(mockNotOk(404)));
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useEscuelas(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.collection).toBeNull();
    expect(result.current.isError).toBe(true);
  });

  it('500 on geojson resolves with collection=null and isError=true', async () => {
    mockFetch.mockImplementation(() => Promise.resolve(mockNotOk(500)));
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useEscuelas(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.collection).toBeNull();
    expect(result.current.isError).toBe(true);
  });

  it('network reject resolves with collection=null and isError=true (no throw)', async () => {
    mockFetch.mockImplementation(() =>
      Promise.reject(new Error('network down')),
    );
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useEscuelas(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.collection).toBeNull();
    expect(result.current.isError).toBe(true);
  });
});
