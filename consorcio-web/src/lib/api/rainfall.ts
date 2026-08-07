/**
 * Rainfall v2 API client (Lluvia v2 — Phase 3).
 *
 * Authenticated technical rainfall analysis for the ficha. Mirrors the backend
 * (`gee-backend/app/domains/geo/rainfall/router.py`): scopes:resolve turns a
 * parcel into ordered regional scope choices (always regional estimates;
 * direct parcel/geometry compute is rejected server-side), analyses answers
 * 200 snapshot OR 202 queued-with-labels (queued is DATA — the panel labels it
 * and polls, never a silent spinner), and the CSV export carries the bearer
 * token in the Authorization header, never in the URL.
 *
 * Contracts are strict and flat: server snake_case, one interface per level.
 */

import { API_PREFIX, API_URL, apiFetch, getAuthToken } from './core';

export type RainfallScopeKind = 'zone' | 'basin' | 'parcel' | 'geometry';

/** One executable regional scope (kind/id/version), as resolved server-side. */
export interface RainfallScopeChoice {
  kind: 'zone' | 'basin';
  id: string;
  version: string;
}

/** Scope resolve request; wire fields mirror the backend schema (English). */
export interface RainfallScopeRequest {
  kind: RainfallScopeKind;
  id?: string;
  version?: string;
  nomenclature?: string;
}

export type RainfallResolveResult =
  | { kind: 'choices'; choices: RainfallScopeChoice[]; regional_estimate: boolean }
  | { kind: 'scope'; scope: RainfallScopeChoice; regional_estimate: boolean };

export type RainfallMetricState = 'available' | 'partial' | 'suppressed' | 'unavailable';
export type RainfallTemporalState = 'provisional' | 'final';
export type RainfallSourceClass = 'observed_station' | 'estimated_radar' | 'estimated_satellite';

export interface RainfallProvenance {
  source_id: string;
  source_class: RainfallSourceClass;
  method: string;
  nominal_resolution: string;
  aggregation: string;
  spatial_scope: 'zone' | 'basin';
  freshness: string;
  available_through: string;
}

/** One metric record. `value: null` is UNKNOWN, never zero; suppressed and
 * unavailable carry no value and must carry a `reason` (backend-enforced). */
export interface RainfallMetric {
  metric: string;
  value: number | null;
  unit: string;
  state: RainfallMetricState;
  reason: string | null;
  interval_start: string;
  interval_end: string;
  coverage: number;
  completeness: number;
  quality: Record<string, unknown>;
  discrepancies: string[];
  temporal_state: RainfallTemporalState;
  revision: string;
  provenance: RainfallProvenance;
  fallback_used: boolean;
}

/** Immutable analysis snapshot (200). Metric groups are keyed dicts. */
export interface RainfallAnalysisSnapshot {
  analysis_revision_id: string;
  scope: RainfallScopeChoice;
  regional_estimate: boolean;
  year: number;
  comparison_end: string;
  baseline: string;
  annual?: Record<string, RainfallMetric>;
  antecedents?: Record<string, RainfallMetric>;
  intensity?: Record<string, RainfallMetric>;
  summary?: unknown;
  source_health?: unknown;
}

/** Queued analysis (202): the work is labelled and resolves on a poll. */
export interface RainfallQueued {
  status: 'queued';
  outbox_id: string;
  scope: RainfallScopeChoice;
  year: number;
  labels: string[];
}

export type RainfallAnalysisResponse =
  | { type: 'ready'; snapshot: RainfallAnalysisSnapshot }
  | { type: 'queued'; queued: RainfallQueued };

function isQueuedBody(body: unknown): body is RainfallQueued {
  return (
    typeof body === 'object' &&
    body !== null &&
    (body as { status?: unknown }).status === 'queued'
  );
}

/**
 * Resolve a scope request into executable regional scope(s).
 * @throws {Error} with the server `detail` on 401/403/422/429 (via apiFetch).
 */
export async function resolveRainfallScopes(
  request: RainfallScopeRequest,
  signal?: AbortSignal
): Promise<RainfallResolveResult> {
  const body = await apiFetch<Record<string, unknown>>('/geo/rainfall/scopes:resolve', {
    method: 'POST',
    body: JSON.stringify(request),
    signal,
  });
  if (Array.isArray(body.choices)) {
    return {
      kind: 'choices',
      choices: body.choices as RainfallScopeChoice[],
      regional_estimate: body.regional_estimate === true,
    };
  }
  return {
    kind: 'scope',
    scope: body.scope as RainfallScopeChoice,
    regional_estimate: body.regional_estimate === true,
  };
}

/**
 * Read the analysis snapshot for one resolved scope and calendar year. The 202
 * queued answer maps to a labelled `queued` result, never an error.
 * @throws {Error} with the server `detail` on 401/403/422/429/503.
 */
export async function fetchRainfallAnalysis(
  scope: RainfallScopeChoice,
  year: number,
  signal?: AbortSignal
): Promise<RainfallAnalysisResponse> {
  const body = await apiFetch<RainfallAnalysisSnapshot | RainfallQueued>(
    '/geo/rainfall/analyses',
    { method: 'POST', body: JSON.stringify({ scope, year }), signal }
  );
  return isQueuedBody(body)
    ? { type: 'queued', queued: body }
    : { type: 'ready', snapshot: body };
}

/**
 * Download the CSV export of one analysis revision. Raw fetch (not apiFetch)
 * because the response is a blob — same pattern as the photo upload path.
 * @throws {Error} with the server `detail` when the export is denied.
 */
export async function downloadRainfallCsv(revisionId: string): Promise<void> {
  const token = await getAuthToken();
  const response = await fetch(
    `${API_URL}${API_PREFIX}/geo/rainfall/analyses/${encodeURIComponent(revisionId)}.csv`,
    { headers: token ? { Authorization: `Bearer ${token}` } : undefined }
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(
      typeof body.detail === 'string' && body.detail.length > 0
        ? body.detail
        : 'No se pudo exportar el análisis de lluvia.'
    );
  }
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `lluvia_${revisionId}.csv`;
  link.click();
  window.URL.revokeObjectURL(url);
}
