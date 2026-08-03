/**
 * usePilarVerde.test.ts
 *
 * Hook contract:
 *   - TanStack Query, queryKey = [...queryKeys.publicLayers(), 'pilar-verde', <group>]
 *   - staleTime = Number.POSITIVE_INFINITY (static public asset)
 *   - 8 fetches: the 10 typed slots minus `PILAR_VERDE_UNFETCHED_SLOTS`
 *     (`zonaAmpliada` / `bpa2025`, zero consumers — R2-004).
 *   - A group is ATOMIC (R4-001): one failed slot rejects the whole group's
 *     queryFn, so TanStack retries and `error` is real. It must NOT resolve
 *     with a null slot — `staleTime: Infinity` would cache that forever.
 *   - Groups are INDEPENDENT: a failing group must not tank the other two.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createQueryWrapper } from '../test-utils';
import {
  PILAR_VERDE_PUBLIC_PATHS,
  PILAR_VERDE_SLOT_GROUPS,
  PILAR_VERDE_UNFETCHED_SLOTS,
  usePilarVerde,
} from '../../src/hooks/usePilarVerde';

const minimalFC = { type: 'FeatureCollection', features: [] };
const aggregatesSample = {
  schema_version: '1.2',
  generated_at: '2026-04-20T05:37:59Z',
  zona: { nombre: 'Z', superficie_ha: 1 },
  ley_forestal: {
    aceptada_count: 0,
    presentada_count: 0,
    no_inscripta_count: 0,
    aceptada_superficie_ha: 0,
    presentada_superficie_ha: 0,
    cumplimiento_pct_parcelas: 0,
    cumplimiento_pct_superficie: 0,
  },
  bpa: {
    explotaciones_activas: 0,
    superficie_total_ha: 0,
    cobertura_pct_zona: 0,
    cobertura_historica_count: 0,
    cobertura_historica_pct: 0,
    abandonaron_count: 0,
    abandonaron_pct: 0,
    nunca_count: 0,
    nunca_pct: 0,
    evolucion_anual: {
      '2019': 0,
      '2020': 0,
      '2021': 0,
      '2022': 0,
      '2023': 0,
      '2024': 0,
      '2025': 0,
    },
    ejes_distribucion: { persona: 0, planeta: 0, prosperidad: 0, alianza: 0 },
  },
  grilla_aggregates: {
    altura_med_mean: 0,
    pend_media_mean: 0,
    forest_mean_pct: 0,
    categoria_distribution: {},
    drenaje_distribution: {},
  },
  zonas_agroforestales: [],
};
const bpaEnrichedSample = {
  schema_version: '1.2',
  generated_at: '2026-04-20T05:37:59Z',
  source: 's',
  parcels: [],
};
const bpaHistorySample = {
  schema_version: '1.0',
  generated_at: '2026-04-20T05:37:59Z',
  history: {},
};

let mockFetch: ReturnType<typeof vi.fn>;

function mockOk(json: unknown) {
  return { ok: true, status: 200, json: async () => json };
}
function mockNotOk(status = 404) {
  return { ok: false, status, json: async () => ({}) };
}

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
    if (url.endsWith('/data/pilar-verde/aggregates.json'))
      return Promise.resolve(mockOk(aggregatesSample));
    if (url.endsWith('/data/pilar-verde/bpa_enriched.json'))
      return Promise.resolve(mockOk(bpaEnrichedSample));
    if (url.endsWith('/data/pilar-verde/bpa_history.json'))
      return Promise.resolve(mockOk(bpaHistorySample));
    return Promise.resolve(mockOk(minimalFC));
  });
}

describe('usePilarVerde', () => {
  it('exposes the 10 expected public asset paths in PILAR_VERDE_PUBLIC_PATHS (incl. bpa_historico)', () => {
    expect(Object.keys(PILAR_VERDE_PUBLIC_PATHS)).toEqual(
      expect.arrayContaining([
        'zonaAmpliada',
        'bpa2025',
        'bpaHistorico',
        'agroAceptada',
        'agroPresentada',
        'agroZonas',
        'porcentajeForestacion',
        'bpaEnriched',
        'bpaHistory',
        'aggregates',
      ])
    );
    expect(Object.keys(PILAR_VERDE_PUBLIC_PATHS)).toHaveLength(10);
    // All paths point under the static public folder
    for (const p of Object.values(PILAR_VERDE_PUBLIC_PATHS)) {
      expect(p.startsWith('/capas/pilar-verde/') || p.startsWith('/data/pilar-verde/')).toBe(true);
    }
  });

  it('initializes with loading=true', () => {
    setHappyPath();
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde(), { wrapper });
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('fires 8 parallel fetches — the consumed slots only', async () => {
    setHappyPath();
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockFetch).toHaveBeenCalledTimes(8);
    const calledUrls = mockFetch.mock.calls.map((c) => c[0]);
    for (const slot of Object.values(PILAR_VERDE_SLOT_GROUPS).flat()) {
      expect(calledUrls).toContain(PILAR_VERDE_PUBLIC_PATHS[slot]);
    }
    // R2-004: the two consumer-less assets cost 0 bytes.
    for (const slot of PILAR_VERDE_UNFETCHED_SLOTS) {
      expect(calledUrls).not.toContain(PILAR_VERDE_PUBLIC_PATHS[slot]);
    }
  });

  it('returns typed data slots on happy path', async () => {
    setHappyPath();
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).not.toBeNull();
    expect(result.current.data?.aggregates?.schema_version).toBe('1.2');
    expect(result.current.data?.bpaEnriched?.schema_version).toBe('1.2');
    expect(result.current.data?.bpaHistory?.schema_version).toBe('1.0');
    expect(result.current.data?.bpaHistorico).toEqual(minimalFC);
    // Never fetched → stays null (R2-004).
    expect(result.current.data?.bpa2025).toBeNull();
    expect(result.current.data?.zonaAmpliada).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.layersError).toBeNull();
    expect(result.current.bpaError).toBeNull();
  });

  it('FAILS the bpa group on a 404 instead of caching a null slot (R4-001)', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/data/pilar-verde/bpa_history.json'))
        return Promise.resolve(mockNotOk(404));
      if (url.endsWith('/data/pilar-verde/aggregates.json'))
        return Promise.resolve(mockOk(aggregatesSample));
      if (url.endsWith('/data/pilar-verde/bpa_enriched.json'))
        return Promise.resolve(mockOk(bpaEnrichedSample));
      return Promise.resolve(mockOk(minimalFC));
    });
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde(), { wrapper });
    await waitFor(() => expect(result.current.bpaError).not.toBeNull());

    // The failing group reports WHICH slot died...
    expect(result.current.bpaError).toContain('bpaHistory');
    // ...and does not resolve with a poisoned null pair.
    expect(result.current.data?.bpaHistory).toBeNull();
    expect(result.current.data?.bpaEnriched).toBeNull();
    // The other groups are untouched.
    expect(result.current.data?.aggregates).not.toBeNull();
    expect(result.current.layersError).toBeNull();
  });

  it('FAILS the layers group on a network throw, leaving the other groups healthy', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/capas/pilar-verde/agro_zonas.geojson')) {
        return Promise.reject(new Error('network down'));
      }
      if (url.endsWith('/data/pilar-verde/aggregates.json'))
        return Promise.resolve(mockOk(aggregatesSample));
      if (url.endsWith('/data/pilar-verde/bpa_enriched.json'))
        return Promise.resolve(mockOk(bpaEnrichedSample));
      if (url.endsWith('/data/pilar-verde/bpa_history.json'))
        return Promise.resolve(mockOk(bpaHistorySample));
      return Promise.resolve(mockOk(minimalFC));
    });
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde(), { wrapper });
    await waitFor(() => expect(result.current.layersError).not.toBeNull());

    expect(result.current.layersError).toContain('agroZonas');
    expect(result.current.data?.agroZonas).toBeNull();
    expect(result.current.data?.aggregates).not.toBeNull();
    expect(result.current.data?.bpaEnriched).not.toBeNull();
    expect(result.current.bpaError).toBeNull();
    // The aggregate `error` surfaces the first failing group.
    expect(result.current.error).toContain('agroZonas');
  });
});
