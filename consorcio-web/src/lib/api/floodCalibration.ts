/**
 * Flood Calibration API module - CRUD for flood events + model training + rainfall.
 */

import { apiFetch, LONG_TIMEOUT } from './core';

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
  getRainfallSuggestions: (): Promise<RainfallSuggestion[]> =>
    apiFetch('/geo/rainfall/suggestions'),

  /**
   * Disparar backfill de datos CHIRPS (admin-only).
   * Retorna 202 con job_id de Celery.
   */
  triggerBackfill: (
    startDate: string,
    endDate: string,
  ): Promise<BackfillResponse> =>
    apiFetch('/geo/rainfall/backfill', {
      method: 'POST',
      body: JSON.stringify({ start_date: startDate, end_date: endDate }),
      timeout: LONG_TIMEOUT,
    }),
};
