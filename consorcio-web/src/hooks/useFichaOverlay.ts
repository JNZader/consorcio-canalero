/**
 * useFichaOverlay
 *
 * TanStack Query hook for the opt-in `POST /api/v2/geo/analisis-zona/overlay`
 * request that returns the analysis CLIPPED to the analyzed zone (A(b) slice 1,
 * soils only). Mirrors `useFichaTerritorial`: the container owns the fetch and
 * threads the result to the map paint effect.
 *
 * It is ENABLED only when the "ver recortado en el mapa" toggle is ON AND there
 * is an active ficha request — so it never fetches unless the user opts in. The
 * query key includes the same per-area reference as the ficha, so switching the
 * selection changes the key and the previous overlay geometry is dropped (no
 * `keepPreviousData`), which is what lets a stale overlay never linger.
 */

import { useQuery } from '@tanstack/react-query';

import {
  type FichaOverlayDataset,
  type FichaOverlayResponse,
  type FichaRequest,
  FichaApiError,
  fetchFichaOverlay,
} from '../lib/api/ficha';

/** Stable reference key per area of interest (same shape as the ficha hook). */
function refKeyFor(request: FichaRequest): string {
  switch (request.tipo) {
    case 'parcela':
      return request.nomenclatura;
    case 'poligono':
      return JSON.stringify(request.geometry);
    case 'canal_buffer':
      return `${request.canal_ref}:${request.buffer_m}`;
    case 'canal_cuenca':
      return `${request.canal_ref}:${request.variante ?? 'natural'}`;
  }
}

export interface UseFichaOverlayResult {
  data: FichaOverlayResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: FichaApiError | Error | null;
}

/**
 * @param request the active area of interest, or `null` when nothing is selected.
 * @param dataset which overlay to paint (slice 1: only `"suelos"`).
 * @param enabled the toggle state — the query stays idle unless this is true.
 */
export function useFichaOverlay(
  request: FichaRequest | null,
  dataset: FichaOverlayDataset,
  enabled: boolean
): UseFichaOverlayResult {
  const active = enabled && request !== null;
  const query = useQuery({
    queryKey: active
      ? (['ficha-overlay', dataset, request.tipo, refKeyFor(request)] as const)
      : (['ficha-overlay', 'idle'] as const),
    queryFn: ({ signal }) => fetchFichaOverlay(request as FichaRequest, dataset, signal),
    enabled: active,
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    retry: (failureCount, error) =>
      failureCount < 1 &&
      !(error instanceof FichaApiError && [413, 422, 429].includes(error.status)),
  });

  return {
    data: query.data,
    isLoading: query.isLoading && query.fetchStatus !== 'idle',
    isError: query.isError,
    error: (query.error as FichaApiError | Error | null) ?? null,
  };
}
