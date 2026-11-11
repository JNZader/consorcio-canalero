/**
 * Operator GEE flood analysis: POST/GET /geo/gee/analysis (tipo flood).
 * Date semantics match gee_tasks_support.build_flood_analysis_result:
 * start_date = flood/crecida, end_date = normal/referencia.
 */

import type { ImageResultLike } from '../../components/admin/images/imageExplorerUtils';
import { apiFetch, GEE_TIMEOUT } from './core';

export const FLOOD_ANALYSIS_METHODS = ['fusion', 'sar_only', 'optical_only'] as const;
export type FloodAnalysisMethod = (typeof FLOOD_ANALYSIS_METHODS)[number];

export type AnalisisGeoEstado = 'pending' | 'running' | 'completed' | 'failed' | string;

export interface AnalisisGeoResponse {
  id: string;
  tipo: string;
  estado: AnalisisGeoEstado;
  parametros?: Record<string, unknown> | null;
  resultado?: FloodAnalysisResultado | null;
  error?: string | null;
  celery_task_id?: string | null;
}

/** Nested tile blobs inside analisis.resultado after gee.analyze_flood. */
export interface FloodAnalysisResultado {
  method?: string;
  start_date?: string;
  end_date?: string;
  status?: string;
  optical?: Partial<ImageResultLike> & { tile_url?: string; warning?: string };
  ndwi?: Partial<ImageResultLike> & { tile_url?: string };
  sar?: Partial<ImageResultLike> & { tile_url?: string; warning?: string };
  comparison?: {
    flood_date?: string;
    normal_date?: string;
    flood_detection?: Partial<ImageResultLike> & { tile_url?: string };
    flood_rgb?: Partial<ImageResultLike> & { tile_url?: string };
    normal_rgb?: Partial<ImageResultLike> & { tile_url?: string };
  };
  comparison_error?: string;
}

export interface FloodAnalysisSubmitInput {
  startDate: string;
  endDate: string;
  method: FloodAnalysisMethod;
}

/** Minimum day span for backend fusion comparison (end - start >= 1). */
export const FUSION_COMPARISON_MIN_SPAN_DAYS = 1;

export function daySpanInclusiveStartExclusiveEnd(
  startDate: string,
  endDate: string
): number | null {
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return Math.round((end - start) / 86_400_000);
}

export function fusionComparisonReady(startDate: string, endDate: string): boolean {
  const span = daySpanInclusiveStartExclusiveEnd(startDate, endDate);
  return span != null && span >= FUSION_COMPARISON_MIN_SPAN_DAYS;
}

export function validateFloodAnalysisDates(
  startDate: string,
  endDate: string,
  _method: FloodAnalysisMethod
): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    return 'Usá fechas en formato AAAA-MM-DD.';
  }
  const span = daySpanInclusiveStartExclusiveEnd(startDate, endDate);
  if (span == null) return 'Fechas inválidas.';
  if (span < FUSION_COMPARISON_MIN_SPAN_DAYS) {
    return 'La fecha sin agua tiene que ser al menos 1 día después de la crecida.';
  }
  return null;
}

function asImageResult(
  partial: (Partial<ImageResultLike> & { tile_url?: string }) | undefined | null
): ImageResultLike | null {
  if (!partial?.tile_url || typeof partial.tile_url !== 'string') return null;
  return {
    tile_url: partial.tile_url,
    target_date: partial.target_date || '',
    dates_available: Array.isArray(partial.dates_available) ? partial.dates_available : [],
    images_count: typeof partial.images_count === 'number' ? partial.images_count : 1,
    visualization: partial.visualization || 'vv_flood',
    visualization_description:
      partial.visualization_description || partial.visualization || 'Detección de agua',
    sensor: partial.sensor || 'Sentinel-1',
    collection: partial.collection || 'COPERNICUS/S1_GRD',
    notes: partial.notes ?? null,
    days_buffer: partial.days_buffer ?? null,
    max_cloud: partial.max_cloud ?? null,
    cloud_cover: partial.cloud_cover ?? null,
    composition_mode: partial.composition_mode,
    flood_info: partial.flood_info,
  };
}

export interface FloodComparisonSides {
  left: ImageResultLike | null;
  right: ImageResultLike | null;
  source: 'comparison' | 'sar' | 'optical' | 'empty';
}

/**
 * Pick left (normal) / right (flood) tiles from a completed analisis.resultado.
 */
export function pickFloodComparisonSides(
  resultado: FloodAnalysisResultado | null | undefined
): FloodComparisonSides {
  if (!resultado) return { left: null, right: null, source: 'empty' };

  const comparison = resultado.comparison;
  if (comparison) {
    const left = asImageResult(comparison.normal_rgb);
    const right = asImageResult(comparison.flood_detection) ?? asImageResult(comparison.flood_rgb);
    if (left || right) {
      return { left, right, source: 'comparison' };
    }
  }

  const sar = asImageResult(resultado.sar);
  if (sar) return { left: null, right: sar, source: 'sar' };

  const optical = asImageResult(resultado.optical);
  if (optical) return { left: null, right: optical, source: 'optical' };

  return { left: null, right: null, source: 'empty' };
}

export async function submitFloodAnalysis(
  input: FloodAnalysisSubmitInput,
  signal?: AbortSignal
): Promise<AnalisisGeoResponse> {
  return apiFetch<AnalisisGeoResponse>('/geo/gee/analysis', {
    method: 'POST',
    body: JSON.stringify({
      tipo: 'flood',
      parametros: {
        start_date: input.startDate,
        end_date: input.endDate,
        method: input.method,
      },
    }),
    signal,
    timeout: GEE_TIMEOUT,
  });
}

export async function getFloodAnalysis(
  analisisId: string,
  signal?: AbortSignal
): Promise<AnalisisGeoResponse> {
  return apiFetch<AnalisisGeoResponse>(`/geo/gee/analysis/${analisisId}`, {
    signal,
    timeout: GEE_TIMEOUT,
  });
}

export interface PollFloodAnalysisOptions {
  intervalMs?: number;
  maxAttempts?: number;
  signal?: AbortSignal;
  onTick?: (analisis: AnalisisGeoResponse) => void;
}

export async function pollFloodAnalysisUntilDone(
  analisisId: string,
  options: PollFloodAnalysisOptions = {}
): Promise<AnalisisGeoResponse> {
  const intervalMs = options.intervalMs ?? 4000;
  const maxAttempts = options.maxAttempts ?? 75;
  let last: AnalisisGeoResponse | null = null;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (options.signal?.aborted) {
      throw new DOMException('Aborted', 'AbortError');
    }
    last = await getFloodAnalysis(analisisId, options.signal);
    options.onTick?.(last);
    if (last.estado === 'completed' || last.estado === 'failed') {
      return last;
    }
    await sleep(intervalMs, options.signal);
  }

  throw new Error(
    last
      ? `El análisis sigue en estado «${last.estado}» tras ${maxAttempts} intentos.`
      : 'No se pudo consultar el estado del análisis.'
  );
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/** Sync S1 vv_flood tile for a single date (normal side when job has no comparison). */
export async function fetchSentinel1FloodTile(
  targetDate: string,
  signal?: AbortSignal
): Promise<ImageResultLike> {
  const params = new URLSearchParams({
    target_date: targetDate,
    days_buffer: '3',
    visualization: 'vv_flood',
    mode: 'scene',
  });
  return apiFetch<ImageResultLike>(`/geo/gee/images/sentinel1?${params}`, {
    signal,
    timeout: GEE_TIMEOUT,
  });
}
