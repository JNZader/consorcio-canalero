/**
 * usePilarVerde.test.ts
 *
 * Hook contract:
 *   - TanStack Query, queryKey = [...queryKeys.publicLayers(), 'pilar-verde']
 *   - staleTime = Number.POSITIVE_INFINITY (static public asset)
 *   - 9 parallel fetches via Promise.allSettled — one failed slot must NOT
 *     tank the others (graceful degradation per spec).
 *   - Returned shape: { data, loading, error } where data carries the 9 typed slots.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createQueryWrapper } from '../test-utils';
import { usePilarVerde, PILAR_VERDE_PUBLIC_PATHS } from '../../src/hooks/usePilarVerde';

const minimalFC = { type: 'FeatureCollection', features: [] };
const aggregatesSample = {
  schema_version: '1.1',
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
    evolucion_anual: { '2019': 0, '2020': 0, '2021': 0, '2022': 0, '2023': 0, '2024': 0, '2025': 0 },
    practica_top_adoptada: { nombre: 'rotacion_gramineas', adopcion_pct: 0 },
    practica_top_no_adoptada: { nombre: 'sistema_terraza', adopcion_pct: 0 },
    practicas_ranking: [],
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
  schema_version: '1.0',
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
    if (url.endsWith('/data/pilar-verde/aggregates.json')) return Promise.resolve(mockOk(aggregatesSample));
    if (url.endsWith('/data/pilar-verde/bpa_enriched.json')) return Promise.resolve(mockOk(bpaEnrichedSample));
    if (url.endsWith('/data/pilar-verde/bpa_history.json')) return Promise.resolve(mockOk(bpaHistorySample));
    return Promise.resolve(mockOk(minimalFC));
  });
}

describe('usePilarVerde', () => {
  it('exposes the 9 expected public asset paths in PILAR_VERDE_PUBLIC_PATHS', () => {
    expect(Object.keys(PILAR_VERDE_PUBLIC_PATHS)).toEqual(
      expect.arrayContaining([
        'zonaAmpliada',
        'bpa2025',
        'agroAceptada',
        'agroPresentada',
        'agroZonas',
        'porcentajeForestacion',
        'bpaEnriched',
        'bpaHistory',
        'aggregates',
      ]),
    );
    expect(Object.keys(PILAR_VERDE_PUBLIC_PATHS)).toHaveLength(9);
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

  it('fires 9 parallel fetches against the expected paths', async () => {
    setHappyPath();
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockFetch).toHaveBeenCalledTimes(9);
    const calledUrls = mockFetch.mock.calls.map((c) => c[0]);
    for (const expected of Object.values(PILAR_VERDE_PUBLIC_PATHS)) {
      expect(calledUrls).toContain(expected);
    }
  });

  it('returns typed data slots on happy path', async () => {
    setHappyPath();
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).not.toBeNull();
    expect(result.current.data?.aggregates?.schema_version).toBe('1.1');
    expect(result.current.data?.bpaEnriched?.schema_version).toBe('1.0');
    expect(result.current.data?.bpaHistory?.schema_version).toBe('1.0');
    expect(result.current.data?.bpa2025).toEqual(minimalFC);
    expect(result.current.error).toBeNull();
  });

  it('gracefully degrades: a 404 on bpaHistory leaves the slot null but other slots succeed', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/data/pilar-verde/bpa_history.json')) return Promise.resolve(mockNotOk(404));
      if (url.endsWith('/data/pilar-verde/aggregates.json')) return Promise.resolve(mockOk(aggregatesSample));
      if (url.endsWith('/data/pilar-verde/bpa_enriched.json')) return Promise.resolve(mockOk(bpaEnrichedSample));
      return Promise.resolve(mockOk(minimalFC));
    });
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).not.toBeNull();
    expect(result.current.data?.bpaHistory).toBeNull();
    expect(result.current.data?.aggregates).not.toBeNull();
    expect(result.current.data?.bpaEnriched).not.toBeNull();
    expect(result.current.error).toBeNull(); // partial failure does NOT set error
  });

  it('gracefully degrades: a network throw leaves the slot null but does not throw', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.endsWith('/capas/pilar-verde/agro_zonas.geojson')) {
        return Promise.reject(new Error('network down'));
      }
      if (url.endsWith('/data/pilar-verde/aggregates.json')) return Promise.resolve(mockOk(aggregatesSample));
      if (url.endsWith('/data/pilar-verde/bpa_enriched.json')) return Promise.resolve(mockOk(bpaEnrichedSample));
      if (url.endsWith('/data/pilar-verde/bpa_history.json')) return Promise.resolve(mockOk(bpaHistorySample));
      return Promise.resolve(mockOk(minimalFC));
    });
    const wrapper = createQueryWrapper();
    const { result } = renderHook(() => usePilarVerde(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).not.toBeNull();
    expect(result.current.data?.agroZonas).toBeNull();
    expect(result.current.data?.aggregates).not.toBeNull();
    expect(result.current.error).toBeNull();
  });
});
