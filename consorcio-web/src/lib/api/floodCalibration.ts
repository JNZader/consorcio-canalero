/**
 * Flood Calibration API module - CRUD for flood events + model training.
 */

import { apiFetch, LONG_TIMEOUT } from './core';

// ===========================================
// TYPES
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
};
