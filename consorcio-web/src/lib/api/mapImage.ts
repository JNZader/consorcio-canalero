/**
 * Map Image API module - Persist and fetch satellite image selection params.
 *
 * The GEE tile URLs are temporary and expire. We store the PARAMETERS
 * (sensor, date, visualization, etc.) and regenerate the tile on page load.
 */

import { apiFetch, GEE_TIMEOUT } from './core';

// ── Types ──

export interface ImagenMapaParams {
  sensor: string;
  target_date: string;
  visualization: string;
  max_cloud?: number | null;
  days_buffer: number;
}

export interface ImagenComparacionParams {
  enabled: boolean;
  left?: ImagenMapaParams | null;
  right?: ImagenMapaParams | null;
}

export interface ImagenMapaResponse {
  imagen_principal: ImagenMapaParams | null;
  imagen_comparacion: ImagenComparacionParams | null;
}

// ── API ──

export const mapImageApi = {
  /**
   * Fetch saved map image parameters (public, no auth).
   */
  getImageParams: () =>
    apiFetch<ImagenMapaResponse>('/public/settings/mapa/imagen', {
      skipAuth: true,
    }),

  /**
   * Save the main image parameters (requires operator+).
   */
  saveImagenPrincipal: (params: ImagenMapaParams) =>
    apiFetch<ImagenMapaResponse>('/settings/mapa/imagen-principal', {
      method: 'PUT',
      body: JSON.stringify(params),
    }),

  /**
   * Save comparison image parameters (requires operator+).
   */
  saveImagenComparacion: (params: ImagenComparacionParams) =>
    apiFetch<ImagenMapaResponse>('/settings/mapa/imagen-comparacion', {
      method: 'PUT',
      body: JSON.stringify(params),
    }),

  /**
   * Regenerate a tile URL by calling the GEE imagery endpoint with saved params.
   * Returns the full image result including the fresh tile_url.
   */
  regenerateTile: async (params: ImagenMapaParams) => {
    const sensorEndpoint =
      params.sensor === 'Sentinel-1' ? 'sentinel1' : 'sentinel2';

    const queryParams = new URLSearchParams({
      target_date: params.target_date,
      days_buffer: String(params.days_buffer),
      visualization: params.visualization,
    });

    if (params.sensor === 'Sentinel-2' && params.max_cloud != null) {
      queryParams.append('max_cloud', String(params.max_cloud));
    }

    return apiFetch<{
      tile_url: string;
      target_date: string;
      images_count: number;
      visualization: string;
      visualization_description: string;
      sensor: string;
      collection: string;
    }>(`/geo/gee/images/${sensorEndpoint}?${queryParams.toString()}`, {
      skipAuth: true,
      timeout: GEE_TIMEOUT,
    });
  },
};
