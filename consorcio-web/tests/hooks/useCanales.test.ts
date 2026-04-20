/**
 * useCanales.test.ts
 *
 * Hook contract:
 *   - TanStack Query, queryKey = ["public", "canales"]
 *   - staleTime = Number.POSITIVE_INFINITY (static assets, forever cacheable)
 *   - 3 parallel fetches via `Promise.allSettled` — a failed slot stays `null`
 *     without crashing the hook or the peers (spec "Missing file graceful
 *     degradation").
 *   - Returned shape: `{ relevados, propuestas, index, isLoading, isError }`.
 *     `isError` is `true` iff ANY slot failed (per-slot warnings surface via
 *     console but don't reject the Query).
 */

import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  CANALES_PATHS,
  useCanales,
} from '../../src/hooks/useCanales';

import indexSample from '../fixtures/canales/indexSample.json';
import propuestasSample from '../fixtures/canales/propuestasSample.json';
import relevadosSample from '../fixtures/canales/relevadosSample.json';
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

function setHappyPath() {
  mockFetch.mockImplementation((url: string) => {
    if (url.endsWith('/capas/canales/relevados.geojson'))
      return Promise.resolve(mockOk(relevadosSample));
    if (url.endsWith('/capas/canales/propuestas.geojson'))
      return Promise.resolve(mockOk(propuestasSample));
    if (url.endsWith('/capas/canales/index.json'))
      return Promise.resolve(mockOk(indexSample));
    return Promise.resolve(mockNotOk(404));
  });
}

describe('useCanales · paths', () => {
  it('exposes the 3 expected public asset paths', () => {
    expect(CANALES_PATHS).toEqual({
      relevados: '/capas/canales/relevados.geojson',
      propuestas: '/capas/canales/propuestas.geojson',
      index: '/capas/canales/index.json',
    });
  });
});

describe('useCanales · happy path', () => {
  it('initializes with isLoading=true and null data', () => {
    setHappyPath();
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useCanales(), { wrapper });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.relevados).toBeNull();
    expect(result.current.propuestas).toBeNull();
    expect(result.current.index).toBeNull();
    expect(result.current.isError).toBe(false);
  });

  it('fires 3 parallel fetches against the expected paths', async () => {
    setHappyPath();
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useCanales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockFetch).toHaveBeenCalledTimes(3);
    const calledUrls = mockFetch.mock.calls.map((c) => c[0]);
    for (const expected of Object.values(CANALES_PATHS)) {
      expect(calledUrls).toContain(expected);
    }
  });

  it('returns the 3 populated slots on happy path with correct shapes', async () => {
    setHappyPath();
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useCanales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.relevados?.features).toHaveLength(2);
    expect(result.current.propuestas?.features).toHaveLength(3);
    expect(result.current.index?.schema_version).toBe('1.0');
    expect(result.current.index?.counts.total).toBe(5);
    expect(result.current.isError).toBe(false);
  });
});

describe('useCanales · graceful degradation', () => {
  it('index.json 404 leaves index null, other slots succeed, isError=true', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/capas/canales/relevados.geojson'))
        return Promise.resolve(mockOk(relevadosSample));
      if (url.endsWith('/capas/canales/propuestas.geojson'))
        return Promise.resolve(mockOk(propuestasSample));
      if (url.endsWith('/capas/canales/index.json'))
        return Promise.resolve(mockNotOk(404));
      return Promise.resolve(mockNotOk(404));
    });
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useCanales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.relevados).not.toBeNull();
    expect(result.current.propuestas).not.toBeNull();
    expect(result.current.index).toBeNull();
    expect(result.current.isError).toBe(true);
  });

  it('network reject on relevados leaves that slot null without rejecting the Query', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/capas/canales/relevados.geojson'))
        return Promise.reject(new Error('network down'));
      if (url.endsWith('/capas/canales/propuestas.geojson'))
        return Promise.resolve(mockOk(propuestasSample));
      if (url.endsWith('/capas/canales/index.json'))
        return Promise.resolve(mockOk(indexSample));
      return Promise.resolve(mockNotOk(404));
    });
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useCanales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.relevados).toBeNull();
    expect(result.current.propuestas).not.toBeNull();
    expect(result.current.index).not.toBeNull();
    expect(result.current.isError).toBe(true);
  });

  it('all three failing still resolves with isError=true and all-null slots', async () => {
    mockFetch.mockImplementation(() => Promise.resolve(mockNotOk(404)));
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => useCanales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.relevados).toBeNull();
    expect(result.current.propuestas).toBeNull();
    expect(result.current.index).toBeNull();
    expect(result.current.isError).toBe(true);
  });
});
