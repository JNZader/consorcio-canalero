/**
 * useEscuelas
 *
 * Loads the single static Escuelas rurales geojson in a TanStack Query.
 *
 * Design mirror of `useCanales.ts` narrowed to ONE slot (escuelas is a
 * single FeatureCollection, not the 3-slot fan-out that canales uses):
 *   - queryKey: `["public", "escuelas"]`
 *   - staleTime: `Number.POSITIVE_INFINITY` (static public asset,
 *     forever cacheable for this session)
 *   - One fetch against `/capas/escuelas/escuelas_rurales.geojson`
 *   - Graceful degradation — any failure leaves `collection: null` and
 *     flips `isError: true`, but the Query itself still resolves so
 *     `isLoading` flips to `false` instead of hanging. The surrounding
 *     map continues to render without the layer.
 *
 * The hook does NOT transform the data — it returns the raw
 * FeatureCollection exactly as produced by the ETL. Any render-time
 * humanization (e.g., `Esc. → Escuela`) happens in the presentational
 * layer (`EscuelaCard.tsx`, Batch E), keeping data flow explicit.
 *
 * @see design `sdd/escuelas-rurales/design` §3.5 Frontend CREATE
 */

import { useQuery } from '@tanstack/react-query';

import type { EscuelaFeatureCollection } from '../types/escuelas';

/** Canonical public asset path — kept as an export so tests can assert it. */
export const ESCUELAS_GEOJSON_URL =
  '/capas/escuelas/escuelas_rurales.geojson' as const;

interface LoadResult {
  collection: EscuelaFeatureCollection | null;
  failed: boolean;
}

/**
 * Fetch + parse, wrapping every failure mode into a single resolved
 * envelope. The QueryFn NEVER rejects — this is load-bearing for the
 * `isLoading → false` transition on the error path.
 */
async function loadEscuelas(): Promise<LoadResult> {
  try {
    const res = await fetch(ESCUELAS_GEOJSON_URL);
    if (!res.ok) {
      // eslint-disable-next-line no-console
      console.warn(
        `[escuelas:fetch] failed to load (${res.status}): ${ESCUELAS_GEOJSON_URL}`,
      );
      return { collection: null, failed: true };
    }
    const json = (await res.json()) as EscuelaFeatureCollection;
    return { collection: json, failed: false };
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(`[escuelas:fetch] network error:`, err);
    return { collection: null, failed: true };
  }
}

export interface UseEscuelasResult {
  collection: EscuelaFeatureCollection | null;
  isLoading: boolean;
  /** True iff the fetch failed (4xx / 5xx / network). */
  isError: boolean;
}

export function useEscuelas(): UseEscuelasResult {
  const query = useQuery({
    queryKey: ['public', 'escuelas'] as const,
    queryFn: loadEscuelas,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const payload = query.data;
  return {
    collection: payload?.collection ?? null,
    isLoading: query.isLoading,
    isError: payload?.failed ?? false,
  };
}
