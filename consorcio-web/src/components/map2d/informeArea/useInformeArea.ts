/**
 * useInformeArea — the data owner of the PR 2 background informes (T3).
 *
 * TanStack Query over `/api/v2/geo/informes-area`, same shape as
 * `useConocimientoQA` (the house's submit→list→poll pattern): a MUTATION that
 * launches one informe and a QUERY that lists the user's own rows. The list
 * keeps polling — on a backoff ladder — while ANY row is still
 * `pending`/`running`, and stops when every row is terminal or the service
 * answered with a refusal a retry cannot fix.
 *
 * **The "Te avisamos cuando esté" promise, scoped honestly**: the completion
 * and failure toasts fire on a poll OBSERVED TRANSITION, and polling lives
 * only while the informe drawer is mounted (`{informeAbierto && <Drawer/>}`).
 * If the user closes the drawer, no toast — the finished state is waiting in
 * «Mis informes» on the next open. Over-promising an OS-level notification is
 * not something this surface can deliver.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import {
  crearInformeArea,
  descargarInformeAreaPdf,
  INFORME_AREA_ESTADOS,
  type InformeAreaCreateParams,
  type InformeAreaItem,
  InformesAreaApiError,
  listarInformesArea,
} from '../../../lib/api/informesArea';
import { showError, showInfo, showSuccess } from '../../../lib/notifications';

/** The list query key. The create mutation invalidates the 'informes-area' prefix. */
export const INFORMES_AREA_KEY = ['informes-area', 'mis-informes'] as const;

/**
 * The poll interval ladder, in milliseconds, indexed by consecutive fetch
 * failures. Step 0 is the healthy cadence (a informe takes up to ~5 min, so a
 * 5 s progress bar is responsive without hammering); later steps back off a
 * broken deployment, capped so a recovered service is still noticed fast
 * (same rationale as `CONOCIMIENTO_POLL_ESCALERA_MS`).
 */
export const INFORME_AREA_POLL_ESCALERA_MS = [5_000, 15_000, 30_000] as const;

/** How often the list re-reads while something is still in course and healthy. */
export const INFORME_AREA_POLL_MS = INFORME_AREA_POLL_ESCALERA_MS[0];

/**
 * HTTP statuses a blind retry cannot fix: a refused session (401/403), a
 * spent rate-limit window (429) and a deployment gate (503) all stay refused.
 */
const ESTADOS_TERMINALES_HTTP = [401, 403, 429, 503];

export function esRechazoTerminal(error: unknown): boolean {
  const status = (error as { status?: unknown } | null)?.status;
  return typeof status === 'number' && ESTADOS_TERMINALES_HTTP.includes(status);
}

/** True while the informe still has to run (pending) or is running. */
export function informeEnCurso(informe: { estado: string }): boolean {
  return (
    informe.estado === INFORME_AREA_ESTADOS.PENDIENTE ||
    informe.estado === INFORME_AREA_ESTADOS.GENERANDO
  );
}

/**
 * The polling decision, pure and exported so it is testable without a clock
 * (the `intervaloDeSondeo` contract):
 *
 *  1. poll only while at least one informe is pending/running;
 *  2. never poll after a terminal refusal (a retry storm against a service
 *     that already said no);
 *  3. back off, capped, while fetches keep failing for any other reason.
 *
 * `failureCount` is TanStack Query's `fetchFailureCount`, reset to 0 on every
 * successful fetch — recovery restores step 0 with no bookkeeping here.
 */
export function intervaloDeSondeoInformes(
  informes: readonly InformeAreaItem[] | undefined,
  error: unknown,
  failureCount = 0
): number | false {
  if (esRechazoTerminal(error)) return false;
  if (!informes?.some(informeEnCurso)) return false;
  const paso = Math.min(
    Math.max(Math.trunc(failureCount), 0),
    INFORME_AREA_POLL_ESCALERA_MS.length - 1
  );
  return INFORME_AREA_POLL_ESCALERA_MS[paso];
}

/** Human copy for a download failure (typed detail, or the generic fallback). */
function copiaDeErrorDescarga(error: unknown): string {
  if (error instanceof InformesAreaApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return 'Revisá la conexión e intentá de nuevo.';
}

/**
 * Download one informe's PDF, surfacing a failure as a toast. Shared by the
 * Mis informes buttons and the desde_cache instant-download path (both live
 * outside a single component's error boundary by design — a failed download
 * must never take the table with it).
 */
export async function descargarInformeConAviso(informe: InformeAreaItem): Promise<void> {
  try {
    await descargarInformeAreaPdf(informe.id, informe.nombre);
  } catch (error) {
    showError('No se pudo descargar el informe', copiaDeErrorDescarga(error));
  }
}

export interface UseMisInformesResult {
  informes: readonly InformeAreaItem[];
  total: number;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

/**
 * The user's informes, polled while any row is in course. Completion and
 * failure transitions toast (the "te avisamos" half of the contract); the
 * FIRST load never toasts — a row that arrives already terminal was not a
 * transition this session observed.
 */
export function useMisInformes(): UseMisInformesResult {
  const estadosPrevios = useRef<ReadonlyMap<string, string>>(new Map());

  const listado = useQuery({
    queryKey: INFORMES_AREA_KEY,
    queryFn: ({ signal }) => listarInformesArea(signal),
    staleTime: 30_000,
    refetchInterval: (query) =>
      intervaloDeSondeoInformes(
        query.state.data?.items,
        query.state.error,
        query.state.fetchFailureCount
      ),
    retry: (fallos: number, error: unknown) => fallos < 1 && !esRechazoTerminal(error),
  });

  // Observed-transition toasts. Runs on every data identity change (each poll
  // produces a new array); the previous-estado map makes repeats no-ops.
  useEffect(() => {
    const items = listado.data?.items;
    if (!items) return;
    const previos = estadosPrevios.current;
    for (const informe of items) {
      const previa = previos.get(informe.id);
      if (previa === undefined || previa === informe.estado) continue;
      if (informe.estado === INFORME_AREA_ESTADOS.COMPLETO) {
        showSuccess('Informe listo', `«${informe.nombre}» ya se puede descargar.`);
      } else if (informe.estado === INFORME_AREA_ESTADOS.FALLIDO) {
        showError(
          'No se pudo generar el informe',
          `«${informe.nombre}»: ${informe.error ?? 'intentá generarlo de nuevo.'}`
        );
      }
    }
    estadosPrevios.current = new Map(items.map((informe) => [informe.id, informe.estado]));
  }, [listado.data]);

  return {
    informes: listado.data?.items ?? [],
    total: listado.data?.total ?? 0,
    isLoading: listado.isLoading && listado.fetchStatus !== 'idle',
    isError: listado.isError,
    error: listado.error,
    refetch: () => {
      void listado.refetch();
    },
  };
}

/**
 * Launch one background informe. On 202 the toast is the contract's fork:
 * `desde_cache` means the S4 cache already had a completed informe for this
 * exact selection — the PDF downloads INSTANTLY — otherwise
 * "Te avisamos cuando esté". The list is invalidated so the new row reaches
 * the table (and the Generar step's inline progress) without a reload.
 */
export function useCrearInformeArea() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: InformeAreaCreateParams) => crearInformeArea(params),
    retry: false,
    onSuccess: (informe) => {
      void queryClient.invalidateQueries({ queryKey: ['informes-area'] });
      if (informe.desde_cache) {
        showSuccess(
          'El informe ya estaba listo',
          'Esta selección tenía un informe generado; descargamos el PDF.'
        );
        void descargarInformeConAviso(informe);
      } else {
        showInfo(`Generando «${informe.nombre}»`, 'Te avisamos cuando esté.');
      }
    },
  });
}

/**
 * The per-row/per-inline download action, with its loading state surfaced so
 * the clicked button can show it (and only that button).
 */
export function useDescargarInformeArea() {
  return useMutation({
    mutationFn: (informe: InformeAreaItem) => descargarInformeConAviso(informe),
    retry: false,
  });
}
