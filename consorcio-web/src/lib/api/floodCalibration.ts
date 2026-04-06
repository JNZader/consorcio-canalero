/**
 * Flood Calibration API module - CRUD for flood events + model training + rainfall.
 */

import { apiFetch, GEE_TIMEOUT, LONG_TIMEOUT } from './core';

// ===========================================
// TYPES — NDWI Baseline
// ===========================================

export interface NdwiBaselineResponse {
  id: string;
  zona_operativa_id: string;
  ndwi_mean: number;
  ndwi_std: number;
  sample_count: number;
  dry_season_months: number[];
  years_back: number;
  computed_at: string;
  created_at: string;
  updated_at: string;
}

// ===========================================
// TYPES — Flood Events
// ===========================================

export interface FloodEventCreatePayload {
  event_date: string;
  description?: string | null;
  labeled_zones: Record<string, boolean>;
}

export interface FloodEventResponse {
  id: string;
  event_date: string;
  description: string | null;
  satellite_source: string;
  label_count: number;
  features_extracted: boolean;
  created_at: string;
}

export interface FloodEventListItem {
  id: string;
  event_date: string;
  label_count: number;
  created_at: string;
  description?: string | null;
}

export interface FloodEventDetailResponse {
  id: string;
  event_date: string;
  description: string | null;
  satellite_source: string;
  label_count: number;
  features_extracted: boolean;
  created_at: string;
  labels: Array<{
    id: string;
    zona_id: string;
    is_flooded: boolean;
    ndwi_value: number | null;
    extracted_features: Record<string, number> | null;
  }>;
}

export interface TrainingResultResponse {
  events_used: number;
  epochs: number;
  initial_loss: number;
  final_loss: number;
  weights: Record<string, number>;
  bias: number;
  backup_path: string;
}

// ===========================================
// TYPES — Rainfall
// ===========================================

export interface RainfallRecord {
  date: string;
  precipitation_mm: number;
}

export interface RainfallSummaryItem {
  zone_id: string;
  zone_name: string;
  total_mm: number;
  avg_mm: number;
  max_mm: number;
  rainy_days: number;
}

export interface RainfallEvent {
  event_date: string;
  zones: string[];
  accumulated_mm: number;
  duration_hours: number;
}

export interface RainfallSuggestion {
  event_date: string;
  suggested_image_date: string;
  cloud_cover: number;
  zone_names: string[];
  accumulated_mm: number;
}

export interface BackfillResponse {
  job_id: string;
  status: string;
}

export interface BackfillStatusResponse {
  state: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE' | string;
  current: number;
  total: number;
  records: number;
  source?: string;
  errors?: string[];
  error?: string;
}

// ===========================================
// TYPES — Afectados por zona de riesgo
// ===========================================

export interface AfectadoItem {
  consorcista_id: string;
  nombre: string;
  parcela: string | null;
  hectareas: number | null;
  nomenclatura: string;
  zona_nombre: string;
}

export interface AfectadosResponse {
  zona_id: string;
  zona_nombre: string;
  total_consorcistas: number;
  total_ha: number;
  afectados: AfectadoItem[];
}

export interface EventoAfectadosResponse {
  event_id: string;
  event_date: string;
  total_consorcistas: number;
  total_ha: number;
  zonas_afectadas: AfectadosResponse[];
}

export interface ParcelaImportResult {
  imported: number;
  skipped: number;
  total: number;
}

// ===========================================
// API
// ===========================================

export const floodCalibrationApi = {
  /**
   * Crear un evento de inundacion con labels por zona.
   *
   * Transforms frontend `labeled_zones` (Record<string, bool>) into
   * backend `labels` (list of {zona_id, is_flooded}) format.
   */
  createEvent: (payload: FloodEventCreatePayload): Promise<FloodEventResponse> => {
    // Transform flat dict → list format expected by backend FloodEventCreate schema
    const labels = Object.entries(payload.labeled_zones).map(([zona_id, is_flooded]) => ({
      zona_id,
      is_flooded,
    }));

    return apiFetch('/geo/flood-events', {
      method: 'POST',
      body: JSON.stringify({
        event_date: payload.event_date,
        description: payload.description,
        labels,
      }),
    });
  },

  /**
   * Listar todos los eventos de inundacion.
   */
  listEvents: (): Promise<FloodEventListItem[]> =>
    apiFetch('/geo/flood-events'),

  /**
   * Obtener detalle de un evento con sus labels.
   */
  getEvent: (id: string): Promise<FloodEventDetailResponse> =>
    apiFetch(`/geo/flood-events/${id}`),

  /**
   * Eliminar un evento de inundacion y sus labels (cascade).
   */
  deleteEvent: async (id: string): Promise<void> => {
    await apiFetch(`/geo/flood-events/${id}`, {
      method: 'DELETE',
    });
  },

  /**
   * Entrenar el modelo de prediccion de inundacion.
   * Usa LONG_TIMEOUT porque el entrenamiento puede tardar.
   */
  trainModel: (): Promise<TrainingResultResponse> =>
    apiFetch('/geo/ml/flood-prediction/train', {
      method: 'POST',
      timeout: LONG_TIMEOUT,
    }),

  // =========================================
  // RAINFALL
  // =========================================

  /**
   * Obtener datos de lluvia diarios para una zona operativa.
   */
  getRainfallForZone: (
    zonaId: string,
    start: string,
    end: string,
  ): Promise<RainfallRecord[]> =>
    apiFetch(`/geo/rainfall/zones/${zonaId}?start=${start}&end=${end}`),

  /**
   * Obtener resumen de lluvia agregado por zona.
   */
  getRainfallSummary: (
    start: string,
    end: string,
  ): Promise<RainfallSummaryItem[]> =>
    apiFetch(`/geo/rainfall/summary?start=${start}&end=${end}`),

  /**
   * Obtener max diario de lluvia entre todas las zonas (para calendario).
   * source: "CHIRPS" | "IMERG" | undefined (sin filtro → IMERG tiene prioridad)
   */
  getRainfallDaily: (
    start: string,
    end: string,
    source?: 'CHIRPS' | 'IMERG',
  ): Promise<RainfallRecord[]> => {
    const qs = source ? `&source=${source}` : '';
    return apiFetch(`/geo/rainfall/daily?start=${start}&end=${end}${qs}`);
  },

  /**
   * Obtener eventos de lluvia detectados por umbral.
   */
  getRainfallEvents: (params?: {
    threshold_mm?: number;
    window_days?: number;
    start?: string;
    end?: string;
  }): Promise<RainfallEvent[]> => {
    const searchParams = new URLSearchParams();
    if (params?.threshold_mm != null) searchParams.set('threshold_mm', String(params.threshold_mm));
    if (params?.window_days != null) searchParams.set('window_days', String(params.window_days));
    if (params?.start) searchParams.set('start', params.start);
    if (params?.end) searchParams.set('end', params.end);
    const qs = searchParams.toString();
    return apiFetch(`/geo/rainfall/events${qs ? `?${qs}` : ''}`);
  },

  /**
   * Obtener sugerencias de imagenes S2 post-evento de lluvia.
   */
  getRainfallSuggestions: (params?: {
    threshold_mm?: number;
    window_days?: number;
    start?: string;
    end?: string;
  }): Promise<RainfallSuggestion[]> => {
    const qs = new URLSearchParams();
    if (params?.threshold_mm != null) qs.set('threshold_mm', String(params.threshold_mm));
    if (params?.window_days != null) qs.set('window_days', String(params.window_days));
    if (params?.start) qs.set('start', params.start);
    if (params?.end) qs.set('end', params.end);
    const query = qs.toString();
    return apiFetch(`/geo/rainfall/suggestions${query ? `?${query}` : ''}`, {
      timeout: GEE_TIMEOUT,
    });
  },

  /**
   * Disparar backfill de datos de lluvia (admin-only).
   * source: "CHIRPS" (registro historico) o "IMERG" (mejor para eventos extremos).
   * Retorna 202 con job_id de Celery.
   */
  triggerBackfill: (
    startDate: string,
    endDate: string,
    source: 'CHIRPS' | 'IMERG' = 'CHIRPS',
  ): Promise<BackfillResponse> =>
    apiFetch('/geo/rainfall/backfill', {
      method: 'POST',
      body: JSON.stringify({ start_date: startDate, end_date: endDate, source }),
      timeout: LONG_TIMEOUT,
    }),

  /**
   * Poll the status of a running backfill task.
   */
  getBackfillStatus: (taskId: string): Promise<BackfillStatusResponse> =>
    apiFetch(`/geo/rainfall/backfill/${taskId}`),

  // =========================================
  // NDWI BASELINE
  // =========================================

  /**
   * Get NDWI dry-season baselines for all zones.
   * Use these to compute z-scores: z = (ndwi - mean) / std
   */
  getNdwiBaselines: (): Promise<NdwiBaselineResponse[]> =>
    apiFetch('/geo/ndwi/baseline'),

  /**
   * Trigger NDWI baseline computation (admin only).
   */
  computeNdwiBaseline: (params?: {
    zona_ids?: string[];
    dry_season_months?: number[];
    years_back?: number;
  }): Promise<{ job_id: string; status: string; message: string }> =>
    apiFetch('/geo/ndwi/baseline/compute', {
      method: 'POST',
      body: JSON.stringify(params ?? {}),
      timeout: GEE_TIMEOUT,
    }),

  // =========================================
  // AFECTADOS POR ZONA DE RIESGO
  // =========================================

  getAfectadosByZona: (zonaId: string): Promise<AfectadosResponse> =>
    apiFetch(`/geo/zonas/${zonaId}/afectados`),

  getAfectadosByEvento: (eventId: string): Promise<EventoAfectadosResponse> =>
    apiFetch(`/geo/flood-events/${eventId}/afectados`),

  importCatastro: (geojsonData: object): Promise<ParcelaImportResult> =>
    apiFetch('/geo/catastro/import', {
      method: 'POST',
      body: JSON.stringify(geojsonData),
      timeout: LONG_TIMEOUT,
    }),
};
