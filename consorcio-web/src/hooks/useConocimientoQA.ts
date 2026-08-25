/**
 * useConocimientoQA — the bandeja's data owner (U8, task 8.2).
 *
 * TanStack Query over the two mailbox surfaces of
 * `gee-backend/app/domains/conocimiento/router.py`: a MUTATION that enqueues one
 * question and a QUERY that lists the requester's own items. Under amendment A3
 * the submit call cannot answer, so the flow is submit → refetch the listing →
 * poll while anything is still `pendiente`.
 *
 * **Cache policy (design G2d / G6).** Finite `staleTime` and finite `gcTime`, and
 * NO persistence: nothing here touches `localStorage` or `IndexedDB`. A legal
 * answer is bound to a corpus snapshot and to a classification that is verified
 * at processing time; a copy of it surviving in browser storage would be a
 * second, unverified store of corpus text on a device the deployment does not
 * control.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type ConocimientoApiError,
  type ConocimientoItem,
  CONOCIMIENTO_ESTADOS,
  enviarPregunta,
  listarPreguntas,
} from '../lib/api/conocimiento';

export const CONOCIMIENTO_QA_KEY = ['conocimiento', 'bandeja'] as const;

/**
 * The poll interval ladder, in milliseconds, indexed by consecutive fetch
 * failures.
 *
 * Step 0 is the healthy cadence. The later steps exist because the terminal
 * refusal list below cannot cover everything a broken deployment produces: a
 * 500, an HTML error page from a proxy, or a `TypeError` from a dropped
 * connection are all NON-terminal by that list, and a fixed 15 s interval would
 * keep hammering the route forever while the bandeja still holds a `pendiente`.
 * The ladder is capped rather than unbounded so a recovered service is still
 * noticed within a minute.
 */
export const CONOCIMIENTO_POLL_ESCALERA_MS = [15_000, 30_000, 60_000] as const;

/** How often the bandeja re-reads while something is still queued and healthy. */
export const CONOCIMIENTO_POLL_MS = CONOCIMIENTO_POLL_ESCALERA_MS[0];

/**
 * HTTP statuses a blind retry cannot fix, so neither the retry predicate nor the
 * poll should keep hitting them: a refused session (401/403), a spent rate-limit
 * window (429) and a deployment that is not ready (503) all stay refused.
 */
const ESTADOS_TERMINALES_HTTP = [401, 403, 429, 503];

function esRefusalTerminal(error: unknown): boolean {
  const status = (error as ConocimientoApiError | null)?.status;
  return typeof status === 'number' && ESTADOS_TERMINALES_HTTP.includes(status);
}

/**
 * The polling decision, pure and exported so it is testable without a clock.
 *
 * Three rules, all of them about not generating load nobody asked for:
 *
 *  1. poll only while at least one item is `pendiente` — a bandeja of settled
 *     answers has nothing to wait for;
 *  2. never poll after a terminal refusal — an enablement 503 is a deployment
 *     state, not a blip, and re-asking turns a readiness gate into a retry storm;
 *  3. back off, capped, while fetches keep failing for any OTHER reason. A 500,
 *     a proxy's HTML error page and a network `TypeError` are all outside rule 2
 *     and would otherwise poll at full cadence forever.
 *
 * `failureCount` is TanStack Query's `fetchFailureCount`, which the library
 * resets to 0 on every successful fetch — so recovery restores step 0 with no
 * bookkeeping here, and this function stays pure.
 */
export function intervaloDeSondeo(
  items: ConocimientoItem[] | undefined,
  error: unknown,
  failureCount = 0
): number | false {
  if (esRefusalTerminal(error)) return false;
  if (!items?.some((item) => item.estado === CONOCIMIENTO_ESTADOS.PENDIENTE)) return false;
  const paso = Math.min(
    Math.max(Math.trunc(failureCount), 0),
    CONOCIMIENTO_POLL_ESCALERA_MS.length - 1
  );
  return CONOCIMIENTO_POLL_ESCALERA_MS[paso];
}

export interface UseConocimientoQAResult {
  items: ConocimientoItem[];
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  /** The LISTING failure. `ConocimientoApiError` carries status + codigo + causa. */
  error: ConocimientoApiError | Error | null;
  refetch: () => void;
  /**
   * Enqueue one question. The answer arrives on a later poll, never from here.
   *
   * `onSuccess` fires only when the server ACCEPTED the question. The caller
   * needs that hook because clearing the composer optimistically would destroy
   * up to 2000 characters of a rejected question (429/422) that the user would
   * then have to retype.
   */
  enviar: (pregunta: string, opciones?: { onSuccess?: () => void }) => void;
  isEnviando: boolean;
  /** The SUBMIT failure, kept separate: a rejected question is not a broken bandeja. */
  errorEnvio: ConocimientoApiError | Error | null;
  limpiarErrorEnvio: () => void;
}

export function useConocimientoQA(): UseConocimientoQAResult {
  const queryClient = useQueryClient();

  const listado = useQuery({
    queryKey: CONOCIMIENTO_QA_KEY,
    queryFn: ({ signal }) => listarPreguntas(signal),
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchInterval: (query) =>
      intervaloDeSondeo(query.state.data, query.state.error, query.state.fetchFailureCount),
    retry: (failureCount, error) => failureCount < 1 && !esRefusalTerminal(error),
  });

  const envio = useMutation({
    mutationFn: (pregunta: string) => enviarPregunta(pregunta),
    // The submit response carries an id and `pendiente` and nothing else, so the
    // ONLY way the new item reaches the screen is a re-read of the listing.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONOCIMIENTO_QA_KEY });
    },
    retry: false,
  });

  return {
    items: listado.data ?? [],
    isLoading: listado.isLoading,
    isFetching: listado.isFetching,
    isError: listado.isError,
    error: (listado.error as ConocimientoApiError | Error | null) ?? null,
    refetch: () => {
      void listado.refetch();
    },
    enviar: (pregunta: string, opciones?: { onSuccess?: () => void }) => {
      envio.mutate(pregunta, { onSuccess: opciones?.onSuccess });
    },
    isEnviando: envio.isPending,
    errorEnvio: (envio.error as ConocimientoApiError | Error | null) ?? null,
    limpiarErrorEnvio: () => {
      envio.reset();
    },
  };
}
