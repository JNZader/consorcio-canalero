/**
 * Canal Suggestions API module — Network analysis suggestions endpoints.
 *
 * Endpoints under /geo/intelligence/suggestions/
 */

import { apiFetch, LONG_TIMEOUT } from './core';

// ===========================================
// TYPES
// ===========================================

export type SuggestionTipo = 'hotspot' | 'gap' | 'route' | 'maintenance' | 'bottleneck';

export interface CanalSuggestion {
  id: string;
  tipo: SuggestionTipo;
  score: number;
  metadata: Record<string, unknown> | null;
  batch_id: string;
  created_at: string;
}

export interface CanalSuggestionsResult {
  items: CanalSuggestion[];
  total: number;
  page: number;
  limit: number;
  batch_id: string | null;
}

export interface AnalyzeResponse {
  task_id: string;
  status: string;
}

export interface AnalyzeStatusResponse {
  task_id: string;
  status: string;
  batch_id?: string;
  total_suggestions?: number;
  by_tipo?: Partial<Record<SuggestionTipo, number>>;
  error?: string;
}

export interface SuggestionSummary {
  total_suggestions: number;
  by_tipo: Record<SuggestionTipo, CanalSuggestion[]>;
}

// ===========================================
// API
// ===========================================

const BASE = '/geo/intelligence/suggestions';

export const canalSuggestionsApi = {
  /**
   * Disparar analisis completo de la red de canales.
   * Retorna 202 con task_id para polling.
   */
  postAnalyze: (): Promise<AnalyzeResponse> =>
    apiFetch(`${BASE}/analyze`, {
      method: 'POST',
      timeout: LONG_TIMEOUT,
    }),

  getAnalyzeStatus: (taskId: string): Promise<AnalyzeStatusResponse> =>
    apiFetch(`${BASE}/analyze/status/${taskId}`),

  /**
   * Obtener resultados del ultimo analisis.
   * Opcionalmente filtrar por tipo de sugerencia.
   */
  getResults: (params: {
    tipo?: SuggestionTipo;
    page?: number;
    limit?: number;
  } = {}): Promise<CanalSuggestionsResult> => {
    const searchParams = new URLSearchParams();
    if (params.tipo) searchParams.set('tipo', params.tipo);
    if (params.page) searchParams.set('page', params.page.toString());
    if (params.limit) searchParams.set('limit', params.limit.toString());
    const qs = searchParams.toString();
    return apiFetch(`${BASE}/results${qs ? `?${qs}` : ''}`, {
      timeout: LONG_TIMEOUT,
    });
  },

  /**
   * Obtener resultados por batch_id especifico.
   */
  getResultsByBatch: (
    batchId: string,
    params: { tipo?: SuggestionTipo; page?: number; limit?: number } = {}
  ): Promise<CanalSuggestionsResult> => {
    const searchParams = new URLSearchParams();
    if (params.tipo) searchParams.set('tipo', params.tipo);
    if (params.page) searchParams.set('page', params.page.toString());
    if (params.limit) searchParams.set('limit', params.limit.toString());
    const qs = searchParams.toString();
    return apiFetch(`${BASE}/results/${batchId}${qs ? `?${qs}` : ''}`, {
      timeout: LONG_TIMEOUT,
    });
  },

  /**
   * Resumen del dashboard: conteo por tipo + top 5 sugerencias por tipo.
   */
  getSummary: (): Promise<SuggestionSummary> =>
    apiFetch(`${BASE}/summary`, {
      timeout: LONG_TIMEOUT,
    }),
};
