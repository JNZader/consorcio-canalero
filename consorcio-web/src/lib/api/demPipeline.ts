/**
 * DEM Pipeline API module.
 *
 * Handles triggering the DEM pipeline, polling job status,
 * and fetching generated layers/basins.
 */

import { API_PREFIX, API_URL, GEE_TIMEOUT, apiFetch, fetchAuthenticatedFile } from './core';

// ===========================================
// TYPES
// ===========================================

export interface DemPipelineResponse {
  job_id: string;
  tipo: string;
  estado: string;
}

export interface GeoJobResponse {
  id: string;
  tipo: string;
  estado: string;
  progreso: number | null;
  parametros: Record<string, unknown> | null;
  resultado: Record<string, unknown> | null;
  error: string | null;
  celery_task_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface GeoLayerResponse {
  id: string;
  nombre: string;
  tipo: string;
  fuente: string;
  archivo_path: string;
  formato: string;
  area_id: string | null;
  created_at: string;
}

export interface GeoLayerListResponse {
  items: GeoLayerResponse[];
  total: number;
  page: number;
  limit: number;
}

export interface BasinsGeoJSON {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: Record<string, unknown>;
    properties: {
      basin_id: number;
      area_ha: number;
    };
  }>;
  metadata?: {
    layer_id: string;
    area_id: string | null;
    created_at: string;
  };
}

export interface SubmitDemPipelineParams {
  area_id?: string;
  min_basin_area_ha?: number;
}

// ===========================================
// API
// ===========================================

export const demPipelineApi = {
  /**
   * Trigger the full DEM pipeline.
   */
  submit: (params: SubmitDemPipelineParams = {}): Promise<DemPipelineResponse> =>
    apiFetch('/geo/dem-pipeline', {
      method: 'POST',
      body: JSON.stringify(params),
      timeout: GEE_TIMEOUT,
    }),

  /**
   * Get job status by ID.
   */
  getJob: (jobId: string): Promise<GeoJobResponse> => apiFetch(`/geo/jobs/${jobId}`),

  /**
   * List generated geo layers.
   */
  getLayers: (tipo?: string): Promise<GeoLayerListResponse> => {
    const params = tipo ? `?tipo=${tipo}&limit=50` : '?limit=50';
    return apiFetch(`/geo/layers${params}`);
  },

  /**
   * Get basin polygons as GeoJSON.
   */
  getBasins: (): Promise<BasinsGeoJSON> => apiFetch('/geo/basins', { skipAuth: true }),

  /**
   * Get download URL for a layer file.
   */
  getLayerFileUrl: (layerId: string): string =>
    `${API_URL}${API_PREFIX}/geo/layers/${layerId}/file`,

  /**
   * Download a layer file with Bearer authentication and trigger a browser download.
   */
  downloadLayerFile: async (layerId: string, fallbackFilename?: string): Promise<void> => {
    const { blob, filename } = await fetchAuthenticatedFile(`/geo/layers/${layerId}/file`, {
      timeout: GEE_TIMEOUT,
    });
    const objectUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename || fallbackFilename || `layer-${layerId}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
  },
};
