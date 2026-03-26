/**
 * SAR Temporal Analysis API module.
 *
 * Handles submitting SAR temporal analyses and fetching results.
 */

import { apiFetch, GEE_TIMEOUT } from './core';

// ===========================================
// TYPES
// ===========================================

export interface SarTemporalAnomaly {
  date: string;
  vv: number;
}

export interface SarTemporalResultado {
  dates: string[];
  vv_mean: number[];
  image_count: number;
  baseline: number | null;
  std: number | null;
  threshold: number | null;
  anomalies: SarTemporalAnomaly[];
  start_date: string;
  end_date: string;
  scale_m: number;
  status: string;
  warning?: string;
}

export interface AnalisisGeoResponse {
  id: string;
  tipo: string;
  fecha_analisis: string;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  parametros: Record<string, unknown> | null;
  resultado: SarTemporalResultado | null;
  estado: string;
  error: string | null;
  celery_task_id: string | null;
  usuario_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SubmitSarTemporalParams {
  start_date: string;
  end_date: string;
  scale?: number;
}

// ===========================================
// API
// ===========================================

export const sarTemporalApi = {
  /**
   * Submit a new SAR temporal analysis.
   */
  submit: (params: SubmitSarTemporalParams): Promise<AnalisisGeoResponse> =>
    apiFetch('/geo/gee/analysis', {
      method: 'POST',
      body: JSON.stringify({
        tipo: 'sar_temporal',
        parametros: params,
      }),
      timeout: GEE_TIMEOUT,
    }),

  /**
   * Get analysis result by ID.
   */
  getById: (id: string): Promise<AnalisisGeoResponse> =>
    apiFetch(`/geo/gee/analysis/${id}`),
};
