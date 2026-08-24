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

/** How often the bandeja re-reads while something is still queued. */
export const CONOCIMIENTO_POLL_MS = 15_000;

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
 * Two rules, both of them about not generating load nobody asked for:
 * poll only while at least one item is `pendiente` (a bandeja of settled answers
 * has nothing to wait for), and never poll after a refusal (an enablement 503 is
 * a deployment state, not a blip — re-asking every fifteen seconds turns a
 * readiness gate into a retry storm).
 */
export function intervaloDeSondeo(
  items: ConocimientoItem[] | undefined,
  error: unknown
): number | false {
  if (esRefusalTerminal(error)) return false;
  if (!items?.some((item) => item.estado === CONOCIMIENTO_ESTADOS.PENDIENTE)) return false;
  return CONOCIMIENTO_POLL_MS;
}

export interface UseConocimientoQAResult {
  items: ConocimientoItem[];
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  /** The LISTING failure. `ConocimientoApiError` carries status + codigo + causa. */
  error: ConocimientoApiError | Error | null;
  refetch: () => void;
  /** Enqueue one question. The answer arrives on a later poll, never from here. */
  enviar: (pregunta: string) => void;
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
    refetchInterval: (query) => intervaloDeSondeo(query.state.data, query.state.error),
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
    enviar: (pregunta: string) => {
      envio.mutate(pregunta);
    },
    isEnviando: envio.isPending,
    errorEnvio: (envio.error as ConocimientoApiError | Error | null) ?? null,
    limpiarErrorEnvio: () => {
      envio.reset();
    },
  };
}
