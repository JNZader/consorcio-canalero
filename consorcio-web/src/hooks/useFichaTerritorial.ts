/**
 * useFichaTerritorial
 *
 * TanStack Query hook that owns the `POST /api/v2/geo/analisis-zona` request for
 * the ficha territorial. The container (`MapaMapLibre`) calls it and threads the
 * resulting state down to `<FichaTerritorialPanel>` as props — `InfoPanel` stays
 * pure and never fetches (design §6, spec "Ficha data is fetched by a container").
 *
 * Staleness contract (design §6.5, spec "Switching modes discards previous
 * result"): the query key includes the area reference and the hook deliberately
 * does NOT use `placeholderData: keepPreviousData`. Clicking a different parcel
 * or switching modes changes `refKey`, so the card falls back to its loading
 * state instead of presenting the previous area's numbers.
 */

import { useQuery } from '@tanstack/react-query';

import {
  type FichaRequest,
  type FichaResponse,
  FichaApiError,
  fetchAnalisisZona,
} from '../lib/api/ficha';

/** Stable reference key per area of interest, used in the query key. */
function refKeyFor(request: FichaRequest): string {
  switch (request.tipo) {
    case 'parcela':
      return request.nomenclatura;
    case 'poligono':
      // A stable hash of the rounded polygon coordinates (phase A5). Until then
      // the raw stringified geometry is a correct — if verbose — reference.
      return JSON.stringify(request.geometry);
    case 'canal_buffer':
      return `${request.canal_ref}:${request.buffer_m}`;
    case 'canal_cuenca':
      return `${request.canal_ref}:${request.variante ?? 'relevado'}`;
  }
}

export interface UseFichaTerritorialResult {
  data: FichaResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  /** Present only on failure. `FichaApiError` carries the HTTP status + codigo. */
  error: FichaApiError | Error | null;
}

/**
 * @param request the area of interest, or `null` to keep the query idle (no
 *   selection → no fetch).
 */
export function useFichaTerritorial(request: FichaRequest | null): UseFichaTerritorialResult {
  const query = useQuery({
    queryKey: request
      ? (['ficha-territorial', request.tipo, refKeyFor(request)] as const)
      : (['ficha-territorial', 'idle'] as const),
    queryFn: ({ signal }) => fetchAnalisisZona(request as FichaRequest, signal),
    enabled: request !== null,
    staleTime: 5 * 60 * 1000, // 5 min — the ficha of a parcel does not change mid-session.
    gcTime: 30 * 60 * 1000,
    // Client errors (bad geometry, caps, rate limit) never fix themselves on a
    // blind retry — only transient server/network faults are worth one retry.
    // `cuenca_no_computada` is a 503 but a DELIBERATE not-yet-computed state (the
    // batch has not produced this canal's catchment), so a blind retry would just
    // hit the same 503 — exclude it too so it never retry-storms.
    retry: (failureCount, error) =>
      failureCount < 1 &&
      !(
        error instanceof FichaApiError &&
        ([413, 422, 429].includes(error.status) || error.codigo === 'cuenca_no_computada')
      ),
    // No `placeholderData: keepPreviousData` — see the staleness contract above.
  });

  return {
    data: query.data,
    isLoading: query.isLoading && query.fetchStatus !== 'idle',
    isError: query.isError,
    error: (query.error as FichaApiError | Error | null) ?? null,
  };
}
