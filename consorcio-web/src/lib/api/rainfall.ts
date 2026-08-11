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
  /**
   * Content address of the daily evidence this revision was built from
   * (backend design.md D3). Injected server-side at disclosure time from the
   * revision row, so it identifies WHICH data the card is showing, not just
   * which row served it. The `/series` response echoes the same digest: the
   * server-side pin is authoritative, and comparing these two is the cheap
   * cross-check that also catches a stale snapshot held open in a tab.
   */
  data_revision: string;
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

/**
 * Why a daily point has no value. `unavailable` means the provider has not
 * published that day inside the analysis' own disclosure window — it is NOT a
 * measured zero, and a chart that draws it as one invents a dry day.
 */
export const RAINFALL_SERIES_POINT_STATE = {
  AVAILABLE: 'available',
  UNAVAILABLE: 'unavailable',
} as const;

export type RainfallSeriesPointState =
  (typeof RAINFALL_SERIES_POINT_STATE)[keyof typeof RAINFALL_SERIES_POINT_STATE];

/**
 * Why a series no longer matches the revision it illustrates (backend
 * design.md D3). Non-null exactly when `consistent_with_snapshot` is false.
 * The backend documents this enum as closed at these two values: the pin
 * reports `interval_family_ambiguous` for both "two live families" and "no
 * rows at all", deliberately, rather than adding a third.
 */
export const RAINFALL_CONSISTENCY_REASON = {
  DATA_REVISION_MOVED: 'data_revision_moved',
  INTERVAL_FAMILY_AMBIGUOUS: 'interval_family_ambiguous',
} as const;

export type RainfallConsistencyReason =
  (typeof RAINFALL_CONSISTENCY_REASON)[keyof typeof RAINFALL_CONSISTENCY_REASON];

/**
 * Whether the 1991–2020 normal curve is drawable, and if not, WHY NOT
 * (backend LI3A-001). `suppressed` (no baseline to compare against) and
 * `integrity_refused` (a curve was computed and discarded for contradicting
 * the stored `annual.normal`) arrive with byte-identical null columns, so this
 * field is the only thing that keeps an honest absence distinguishable from a
 * refusal. The UI must render the two differently.
 */
export const RAINFALL_NORMAL_CURVE_STATE = {
  AVAILABLE: 'available',
  SUPPRESSED: 'suppressed',
  INTEGRITY_REFUSED: 'integrity_refused',
} as const;

export type RainfallNormalCurveState =
  (typeof RAINFALL_NORMAL_CURVE_STATE)[keyof typeof RAINFALL_NORMAL_CURVE_STATE];

/** One calendar day of the analysis' disclosure window. `null` is UNKNOWN. */
export interface RainfallSeriesPoint {
  date: string;
  mm: number | null;
  accumulated: number | null;
  normal_accumulated: number | null;
  state: RainfallSeriesPointState;
}

/**
 * The daily series for one stored revision, pinned to it server-side.
 *
 * `consistent_with_snapshot` is authoritative: the backend recomputes the
 * revision's `data_revision` digest over exactly the window the build read and
 * compares it with the one stored on the row. Comparing this response's
 * `data_revision` against the snapshot the tab is holding is the cheap client
 * cross-check on top of it, and it also catches a stale snapshot left open.
 */
export interface RainfallSeriesResponse {
  analysis_revision_id: string;
  data_revision: string;
  scope: RainfallScopeChoice;
  year: number;
  unit: string;
  comparison_end: string;
  available_through: string;
  consistent_with_snapshot: boolean;
  consistency_reason: RainfallConsistencyReason | null;
  normal_curve_state: RainfallNormalCurveState;
  points: RainfallSeriesPoint[];
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
    typeof body === 'object' && body !== null && (body as { status?: unknown }).status === 'queued'
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
  // The server serializes the full AnalysisScope dataclass, which carries a
  // `regional_estimate` flag inside each choice. The wire contract for a scope
  // reference is flat {kind,id,version} and the backend forbids extra fields
  // (extra="forbid"), so strip the flag before it is re-sent in /analyses.
  const normalize = (choice: RainfallScopeChoice): RainfallScopeChoice => ({
    kind: choice.kind,
    id: choice.id,
    version: choice.version,
  });
  if (Array.isArray(body.choices)) {
    return {
      kind: 'choices',
      choices: (body.choices as RainfallScopeChoice[]).map(normalize),
      regional_estimate: body.regional_estimate === true,
    };
  }
  return {
    kind: 'scope',
    scope: normalize(body.scope as RainfallScopeChoice),
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
  const body = await apiFetch<RainfallAnalysisSnapshot | RainfallQueued>('/geo/rainfall/analyses', {
    method: 'POST',
    body: JSON.stringify({ scope, year }),
    signal,
  });
  return isQueuedBody(body) ? { type: 'queued', queued: body } : { type: 'ready', snapshot: body };
}

/**
 * Read the daily series for one stored analysis revision.
 *
 * Read-only server-side (it enqueues nothing), so it is safe to fetch whenever
 * the chart mounts — but it is not a substitute for the analysis itself: the
 * consistency fields it carries describe THAT revision, not a fresher one.
 * @throws {Error} with the server `detail` on 401/403/404/503.
 */
export async function fetchRainfallSeries(
  revisionId: string,
  signal?: AbortSignal
): Promise<RainfallSeriesResponse> {
  return apiFetch<RainfallSeriesResponse>(
    `/geo/rainfall/analyses/${encodeURIComponent(revisionId)}/series`,
    { signal }
  );
}

/**
 * Fetch one revision export and hand it to the browser as a download.
 *
 * Raw fetch (not apiFetch) because the response is a blob — same pattern as
 * the photo upload path. The bearer token travels in the header, NEVER in the
 * URL, where it would be recorded in browser history and server access logs.
 * Both export formats share this body so the two can never drift apart on the
 * half that carries the credential.
 * @throws {Error} with the server `detail` when the export is denied.
 */
async function downloadRainfallExport(revisionId: string, extension: string): Promise<void> {
  const token = await getAuthToken();
  const response = await fetch(
    `${API_URL}${API_PREFIX}/geo/rainfall/analyses/${encodeURIComponent(revisionId)}.${extension}`,
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
  link.download = `lluvia_${revisionId}.${extension}`;
  link.click();
  window.URL.revokeObjectURL(url);
}

/** Download the audit CSV export of one analysis revision. */
export async function downloadRainfallCsv(revisionId: string): Promise<void> {
  return downloadRainfallExport(revisionId, 'csv');
}

/**
 * Download the friendly two-sheet xlsx export of one analysis revision
 * (Resumen + Serie diaria, backend design.md D7). Same authorization boundary
 * as the CSV; the workbook stamps the series-consistency pin and the
 * normal-curve state inside itself, because it outlives the screen that would
 * have shown them.
 */
export async function downloadRainfallXlsx(revisionId: string): Promise<void> {
  return downloadRainfallExport(revisionId, 'xlsx');
}
