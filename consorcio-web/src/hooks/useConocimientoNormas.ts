/**
 * useConocimientoNormas — the norms surface's data owner (unit 6).
 *
 * Two MUTATIONS, deliberately not queries. A search is a POST whose body is the
 * operator's query, and an export is a POST that produces a document: neither is
 * a cacheable read, and a cache entry would be a second copy of corpus text held
 * in the browser. Nothing here touches `localStorage` or `IndexedDB`, and there
 * is no polling: a refusal (flag off, no active corpus) is a deployment state
 * that re-asking cannot change.
 */

import { useMutation } from '@tanstack/react-query';

import {
  buscarNormas,
  type ConocimientoApiError,
  type ConocimientoBorradorExportado,
  type ConocimientoResultadoNormas,
  exportarPedido,
} from '../lib/api/conocimiento';

type ErrorDeNormas = ConocimientoApiError | Error | null;

export interface UseConocimientoNormasResult {
  resultado: ConocimientoResultadoNormas | null;
  isBuscando: boolean;
  /** The SEARCH failure: status + codigo + causa survive on `ConocimientoApiError`. */
  errorBusqueda: ErrorDeNormas;
  buscar: (consulta: string, k?: number) => void;
  /** Resolves with the draft so the caller can hand it to the browser as a download. */
  exportar: (
    pedidoId: string,
    opciones?: { onSuccess?: (borrador: ConocimientoBorradorExportado) => void }
  ) => void;
  isExportando: boolean;
  /** The EXPORT failure, kept apart from the search one: a refused draft is not a broken search. */
  errorExportacion: ErrorDeNormas;
  limpiarErrorExportacion: () => void;
}

export function useConocimientoNormas(): UseConocimientoNormasResult {
  const busqueda = useMutation({
    mutationFn: ({ consulta, k }: { consulta: string; k?: number }) => buscarNormas(consulta, k),
    retry: false,
  });

  const exportacion = useMutation({
    mutationFn: (pedidoId: string) => exportarPedido(pedidoId),
    retry: false,
  });

  return {
    resultado: busqueda.data ?? null,
    isBuscando: busqueda.isPending,
    errorBusqueda: (busqueda.error as ErrorDeNormas) ?? null,
    buscar: (consulta, k) => {
      busqueda.mutate({ consulta, k });
    },
    exportar: (pedidoId, opciones) => {
      exportacion.mutate(pedidoId, { onSuccess: opciones?.onSuccess });
    },
    isExportando: exportacion.isPending,
    errorExportacion: (exportacion.error as ErrorDeNormas) ?? null,
    limpiarErrorExportacion: () => {
      exportacion.reset();
    },
  };
}
