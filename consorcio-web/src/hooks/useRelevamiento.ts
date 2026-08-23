/**
 * useRelevamiento — the query/mutation surface of the segment survey
 * (flujo-caminos, Fase B).
 *
 * Three small hooks instead of one big one, because the three pieces have
 * different lifetimes: the coverage split belongs to the panel (it is on screen
 * as long as the layer is), the segment detail belongs to the sheet (it exists
 * only while one segment is selected), and the submission belongs to the save
 * button.
 *
 * ⚠️ NO CLIENT-SIDE DERIVATION OF ANYTHING THE SERVER PUBLISHES. ⚠️
 * `nivel_sugerido`, `nivel_desde_candidata` and the three coverage counters are
 * server facts. These hooks move them, they never recompute them — see the
 * header of `lib/api/relevamiento.ts`.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type CoberturaResponse,
  type RelevamientoTramoCreate,
  type RelevamientoTramoResponse,
  type TramoRelevamientoDetalle,
  fetchCobertura,
  fetchTramoRelevamiento,
  registrarRelevamiento,
} from '../lib/api/relevamiento';

/** Root of every query key in this module, so one invalidation reaches them all. */
export const RELEVAMIENTO_QUERY_ROOT = 'relevamiento';

export interface UseTramoRelevamientoResult {
  readonly data: TramoRelevamientoDetalle | undefined;
  readonly isLoading: boolean;
  readonly isError: boolean;
  readonly error: Error | null;
}

/**
 * Read `{vigente, historial[], candidata}` for ONE segment.
 *
 * Idle while `tramoRef` is null: no segment selected, no request. There is no
 * `keepPreviousData` — showing the previous segment's survey under the new
 * segment's name is exactly the failure this form cannot afford.
 */
export function useTramoRelevamiento(tramoRef: string | null): UseTramoRelevamientoResult {
  const query = useQuery({
    queryKey: [RELEVAMIENTO_QUERY_ROOT, 'tramo', tramoRef ?? 'idle'] as const,
    queryFn: ({ signal }) => fetchTramoRelevamiento(tramoRef as string, signal),
    enabled: tramoRef !== null,
    retry: false,
  });

  return {
    data: query.data,
    isLoading: query.isLoading && query.fetchStatus !== 'idle',
    isError: query.isError,
    error: (query.error as Error | null) ?? null,
  };
}

export interface UseRelevamientoCoberturaResult {
  readonly data: CoberturaResponse | undefined;
  readonly isLoading: boolean;
  readonly isError: boolean;
}

/**
 * Read the three-way coverage split for one area.
 *
 * `enabled` is the layer toggle: the counters are a panel surface, and a panel
 * nobody opened must not cost a request.
 */
export function useRelevamientoCobertura(
  areaId: string | null,
  enabled: boolean
): UseRelevamientoCoberturaResult {
  const query = useQuery({
    queryKey: [RELEVAMIENTO_QUERY_ROOT, 'cobertura', areaId ?? 'red'] as const,
    queryFn: ({ signal }) => fetchCobertura(areaId, signal),
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  return {
    data: query.data,
    isLoading: query.isLoading && query.fetchStatus !== 'idle',
    isError: query.isError,
  };
}

/**
 * Record one survey.
 *
 * The mutation REJECTS on failure on purpose: `TramoSurveySheet` awaits it and
 * keeps the three answers on screen when it throws (there is no offline queue —
 * design D6), so swallowing the error here would silently discard fieldwork.
 *
 * On success it invalidates the whole module root: the segment detail now has a
 * new `vigente`, and the coverage split may have moved a segment from
 * `solo_candidato` to `relevados`.
 */
export function useRegistrarRelevamiento(): (
  payload: RelevamientoTramoCreate
) => Promise<RelevamientoTramoResponse> {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (payload: RelevamientoTramoCreate) => registrarRelevamiento(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [RELEVAMIENTO_QUERY_ROOT] });
    },
  });

  return mutation.mutateAsync;
}
