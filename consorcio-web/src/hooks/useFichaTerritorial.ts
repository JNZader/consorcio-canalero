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

/**
 * Stable reference key per area of interest, used in the query key.
 *
 * Exported because it is the ONLY honest identity of a selection: display
 * fields (nro_cuenta, canal name) are optional and repeat across different
 * targets. Anything that needs to answer "is this a different selection?" —
 * the query key here, the panels' reset trigger via `fichaSelectionKey` —
 * must derive it from the request, never from what the card happens to show.
 */
export function refKeyFor(request: FichaRequest): string {
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
      return `${request.canal_ref}:${request.variante ?? 'natural'}`;
  }
}

/** Selection key while nothing is selected. A constant: idle never "changes". */
export const FICHA_IDLE_SELECTION_KEY = 'ficha:idle';

/**
 * Identity of the CURRENT ficha selection, as a single comparable string.
 *
 * Same derivation as the query key above (`tipo` + `refKeyFor`), so "the UI
 * considers this a new selection" and "the query refetches" can never disagree.
 * Consumers use it as an opaque reset TRIGGER — only its identity matters.
 */
export function fichaSelectionKey(request: FichaRequest | null): string {
  if (!request) return FICHA_IDLE_SELECTION_KEY;
  return `${request.tipo}|${refKeyFor(request)}`;
}

export interface UseFichaTerritorialResult {
  data: FichaResponse | undefined;
  isLoading: boolean;
  /**
   * True while ANY fetch is in flight — including a retry over CACHED data,
   * where TanStack keeps `status: 'error'` (it only resets to pending when
   * `data === undefined`), so `isLoading` stays false for the whole refetch.
   * The error alert uses this to disable "Reintentar" and show in-flight
   * feedback on that path.
   */
  isFetching: boolean;
  isError: boolean;
  /** Present only on failure. `FichaApiError` carries the HTTP status + codigo. */
  error: FichaApiError | Error | null;
  /**
   * Re-run the query on demand (map-fluidity T2, fix 4). TanStack never retries
   * a client error (429 included), so the panel's error state needs an explicit
   * user-triggered path back — without it the only recovery was re-clicking the
   * parcel on the map.
   */
  refetch: () => void;
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
    isFetching: query.isFetching,
    isError: query.isError,
    error: (query.error as FichaApiError | Error | null) ?? null,
    // Discard the returned promise: the panel only needs the side effect, and
    // an unhandled rejection would surface as a console error on a failed retry.
    refetch: () => {
      void query.refetch();
    },
  };
}
