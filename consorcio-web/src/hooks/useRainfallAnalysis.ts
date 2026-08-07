/**
 * useRainfallAnalysis (Lluvia v2 — Phase 3)
 *
 * TanStack Query hooks for the authenticated Rainfall v2 ficha detail; the
 * component owns only the selected scope/year (design "Frontend"). Staleness
 * contract as `useFichaTerritorial`: the key carries scope kind/id/version +
 * year and there is no keepPreviousData — switching selection never shows the
 * previous scope's numbers. A queued (202) answer keeps polling on a bounded
 * interval so the LABELLED pending state resolves by itself.
 */

import { useQuery } from '@tanstack/react-query';

import {
  type RainfallAnalysisResponse,
  type RainfallResolveResult,
  type RainfallScopeChoice,
  fetchRainfallAnalysis,
  resolveRainfallScopes,
} from '../lib/api/rainfall';

/** Poll cadence while an analysis is queued server-side. */
export const RAINFALL_QUEUED_POLL_MS = 5000;

export interface UseRainfallScopesResult {
  data: RainfallResolveResult | undefined;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

export function useRainfallScopes(nomenclatura: string | null): UseRainfallScopesResult {
  const query = useQuery({
    queryKey: nomenclatura
      ? (['rainfall-scopes', nomenclatura] as const)
      : (['rainfall-scopes', 'idle'] as const),
    queryFn: ({ signal }) =>
      resolveRainfallScopes({ kind: 'parcel', nomenclature: nomenclatura as string }, signal),
    enabled: nomenclatura !== null,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  return {
    data: query.data,
    isLoading: query.isLoading && query.fetchStatus !== 'idle',
    isError: query.isError,
    error: (query.error as Error | null) ?? null,
  };
}

export interface UseRainfallAnalysisOptions {
  /** Test seam: shorten the queued poll cadence. Defaults to 5 s. */
  pollIntervalMs?: number;
}

export interface UseRainfallAnalysisResult {
  data: RainfallAnalysisResponse | undefined;
  /** True while the server answer is a labelled queued state (202). */
  queued: boolean;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

export function useRainfallAnalysis(
  scope: RainfallScopeChoice | null,
  year: number,
  options: UseRainfallAnalysisOptions = {}
): UseRainfallAnalysisResult {
  const { pollIntervalMs = RAINFALL_QUEUED_POLL_MS } = options;
  const query = useQuery({
    queryKey: scope
      ? (['rainfall-analysis', scope.kind, scope.id, scope.version, year] as const)
      : (['rainfall-analysis', 'idle'] as const),
    queryFn: ({ signal }) => fetchRainfallAnalysis(scope as RainfallScopeChoice, year, signal),
    enabled: scope !== null,
    staleTime: 60 * 1000,
    retry: false,
    refetchInterval: (query) => (query.state.data?.type === 'queued' ? pollIntervalMs : false),
  });
  return {
    data: query.data,
    queued: query.data?.type === 'queued',
    isLoading: query.isLoading && query.fetchStatus !== 'idle',
    isError: query.isError,
    error: (query.error as Error | null) ?? null,
  };
}
