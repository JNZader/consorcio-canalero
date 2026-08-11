/**
 * useRainfallAnalysis (Lluvia v2 — Phase 3)
 *
 * TanStack Query hooks for the authenticated Rainfall v2 ficha detail; the
 * component owns only the selected scope/year (design "Frontend"). Staleness
 * contract as `useFichaTerritorial`: the key carries scope kind/id/version +
 * year and there is no keepPreviousData — switching selection never shows the
 * previous scope's numbers. A queued (202) answer keeps polling on a BOUNDED
 * interval so the LABELLED pending state resolves by itself; once the
 * consecutive-queued budget is exhausted the hook gives up and exposes a
 * terminal `gaveUp` state instead of polling forever (RESILIENCE-001/002).
 */

import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  type RainfallAnalysisResponse,
  type RainfallConsistencyReason,
  type RainfallNormalCurveState,
  type RainfallResolveResult,
  type RainfallScopeChoice,
  type RainfallSeriesPoint,
  type RainfallSeriesResponse,
  fetchRainfallAnalysis,
  fetchRainfallSeries,
  resolveRainfallScopes,
} from '../lib/api/rainfall';

/** Poll cadence while an analysis is queued server-side. */
export const RAINFALL_QUEUED_POLL_MS = 5000;

/** Consecutive queued (202) answers tolerated before giving up: 12 × 5 s ≈ 60 s. */
export const RAINFALL_MAX_QUEUED_POLLS = 12;

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

/**
 * The cache key one scope/year analysis lives under.
 *
 * MODULE-PRIVATE, and that is the post-JD state rather than an oversight. It
 * was exported for the chart's re-request action, which wrote the server's
 * answer straight into this key (`queryClient.setQueryData`) — a genuine
 * second consumer. JD round 1 (JDA-003 ≡ JDB-003) removed that action: a moved
 * `data_revision` enqueues nothing and revisions are immutable, so the button
 * promised a remedy the backend cannot deliver. With it went the only caller
 * outside this file, so the `export` kept a public surface nothing imported
 * and a docstring that claimed two consumers when one was left (V-004).
 *
 * Still a named function rather than an inline literal: the key is built in
 * one place so the `enabled: false` idle branch below cannot drift from it.
 */
function rainfallAnalysisQueryKey(scope: RainfallScopeChoice, year: number) {
  return ['rainfall-analysis', scope.kind, scope.id, scope.version, year] as const;
}

export interface UseRainfallAnalysisOptions {
  /** Test seam: shorten the queued poll cadence. Defaults to 5 s. */
  pollIntervalMs?: number;
  /** Test seam: shrink the consecutive-queued budget. Defaults to 12. */
  maxQueuedPolls?: number;
}

export interface UseRainfallAnalysisResult {
  data: RainfallAnalysisResponse | undefined;
  /** True while the server answer is a labelled queued state (202). */
  queued: boolean;
  /** True once the queued poll budget is exhausted without a snapshot; the
   *  panel must show an honest terminal state, never an auto-update promise. */
  gaveUp: boolean;
  /** Re-run the analysis fetch and start a fresh polling budget. */
  retry: () => void;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

export function useRainfallAnalysis(
  scope: RainfallScopeChoice | null,
  year: number,
  options: UseRainfallAnalysisOptions = {}
): UseRainfallAnalysisResult {
  const { pollIntervalMs = RAINFALL_QUEUED_POLL_MS, maxQueuedPolls = RAINFALL_MAX_QUEUED_POLLS } =
    options;

  // Consecutive queued (202) answers observed for the CURRENT scope/year. The
  // budget resets when the selection changes (a new request starts fresh) and
  // on a manual retry; a ready answer also zeroes it.
  const queuedPolls = useRef(0);
  const selectionKey = scope ? `${scope.kind}:${scope.id}:${scope.version}:${year}` : 'idle';
  const previousSelectionKey = useRef(selectionKey);
  useEffect(() => {
    if (previousSelectionKey.current !== selectionKey) {
      previousSelectionKey.current = selectionKey;
      queuedPolls.current = 0;
    }
  }, [selectionKey]);

  const query = useQuery({
    queryKey: scope
      ? rainfallAnalysisQueryKey(scope, year)
      : (['rainfall-analysis', 'idle'] as const),
    queryFn: async ({ signal }) => {
      const response = await fetchRainfallAnalysis(scope as RainfallScopeChoice, year, signal);
      queuedPolls.current = response.type === 'queued' ? queuedPolls.current + 1 : 0;
      return response;
    },
    enabled: scope !== null,
    staleTime: 60 * 1000,
    retry: false,
    refetchInterval: (q) =>
      q.state.data?.type === 'queued' && queuedPolls.current < maxQueuedPolls
        ? pollIntervalMs
        : false,
  });

  function retry() {
    queuedPolls.current = 0;
    void query.refetch();
  }

  return {
    data: query.data,
    queued: query.data?.type === 'queued',
    gaveUp: query.data?.type === 'queued' && queuedPolls.current >= maxQueuedPolls,
    retry,
    isLoading: query.isLoading && query.fetchStatus !== 'idle',
    isError: query.isError,
    error: (query.error as Error | null) ?? null,
  };
}

/**
 * The daily series for one stored revision, with its consistency disclosures
 * surfaced as first-class fields.
 *
 * `consistentWithSnapshot: false` and a refused normal curve are DATA, not
 * error states: the chart still renders the series (it is the fresher
 * evidence), above the notice the disclosure requires. Leaving them inside an
 * optional response body is what would let a component forget to show them.
 */
export interface UseRainfallSeriesResult {
  data: RainfallSeriesResponse | undefined;
  /** Server-side pin (authoritative). `undefined` until the series arrives. */
  consistentWithSnapshot: boolean | undefined;
  /** Non-null exactly when the pin reports inconsistent. */
  consistencyReason: RainfallConsistencyReason | null | undefined;
  /** `suppressed` and `integrity_refused` are different facts — keep them apart. */
  normalCurveState: RainfallNormalCurveState | undefined;
  /** Empty until the series arrives — never a fabricated placeholder curve. */
  points: RainfallSeriesPoint[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

export function useRainfallSeries(revisionId: string | null): UseRainfallSeriesResult {
  const query = useQuery({
    queryKey: revisionId
      ? (['rainfall-series', revisionId] as const)
      : (['rainfall-series', 'idle'] as const),
    queryFn: ({ signal }) => fetchRainfallSeries(revisionId as string, signal),
    enabled: revisionId !== null,
    // The revision row is immutable, so its series only moves when the
    // underlying daily data is corrected — and when it does, the response says
    // so instead of the client having to poll for it. No refetchInterval: the
    // route is read-only server-side and must stay cheap on the client too.
    staleTime: 60 * 1000,
    retry: false,
  });

  return {
    data: query.data,
    consistentWithSnapshot: query.data?.consistent_with_snapshot,
    consistencyReason: query.data?.consistency_reason,
    normalCurveState: query.data?.normal_curve_state,
    points: query.data?.points ?? [],
    isLoading: query.isLoading && query.fetchStatus !== 'idle',
    isError: query.isError,
    error: (query.error as Error | null) ?? null,
  };
}
