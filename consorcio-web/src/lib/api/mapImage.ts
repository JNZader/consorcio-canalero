/**
 * Map Image API module.
 *
 * Operator clients may persist/regenerate arbitrary supported selections through
 * the protected GEE surface. Public map viewers only receive the server-approved
 * current image through a fixed, no-parameter projection.
 */

import { GEE_TIMEOUT, apiFetch } from './core';

// ── Types ──

export interface ImagenMapaParams {
  sensor: string;
  target_date: string;
  visualization: string;
  max_cloud?: number | null;
  days_buffer: number;
  mode?: 'scene' | 'composite' | null;
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

export interface MapImageResult {
  tile_url: string;
  target_date: string;
  images_count: number;
  visualization: string;
  visualization_description: string;
  sensor: string;
  collection: string;
}

export interface PublicCurrentMapImage {
  tile_url: string;
  target_date: string;
  sensor: string;
  visualization: string;
  visualization_description: string;
  images_count: number;
  days_buffer: number;
  max_cloud: number | null;
  mode: 'scene' | 'composite';
}

export interface PublicCurrentMapImageResponse {
  status: 'available' | 'unavailable';
  image: PublicCurrentMapImage | null;
  reason: 'not_configured' | 'configuration_not_approved' | 'temporarily_unavailable' | null;
}

interface RegenerateTileOptions {
  signal?: AbortSignal;
}

// ── API ──

export const mapImageApi = {
  /**
   * Legacy saved-parameter response. The backend now requires operator auth.
   */
  getImageParams: () => apiFetch<ImagenMapaResponse>('/public/settings/mapa/imagen'),

  /**
   * Fetch the fixed public projection of the server-approved current image.
   * No caller-supplied GEE parameter is accepted by this endpoint.
   */
  getPublicCurrentImage: () =>
    apiFetch<PublicCurrentMapImageResponse>('/public/map/gee/current-image', {
      skipAuth: true,
      timeout: GEE_TIMEOUT,
    }),

  /** Save the main image parameters (requires operator+). */
  saveImagenPrincipal: (params: ImagenMapaParams) =>
    apiFetch<ImagenMapaResponse>('/settings/mapa/imagen-principal', {
      method: 'PUT',
      body: JSON.stringify(params),
    }),

  /** Save comparison image parameters (requires operator+). */
  saveImagenComparacion: (params: ImagenComparacionParams) =>
    apiFetch<ImagenMapaResponse>('/settings/mapa/imagen-comparacion', {
      method: 'PUT',
      body: JSON.stringify(params),
    }),

  /**
   * Authenticated backward-compatible regeneration for Admin Image Explorer.
   */
  regenerateTile: async (
    params: ImagenMapaParams,
    options: RegenerateTileOptions = {}
  ): Promise<MapImageResult> => {
    const sensorEndpointByLabel: Record<string, string> = {
      'Sentinel-1': 'sentinel1',
      'Sentinel-2': 'sentinel2',
      'Landsat 8': 'landsat8',
      'Landsat 7': 'landsat7',
      'Landsat 5': 'landsat5',
    };
    const sensorEndpoint = sensorEndpointByLabel[params.sensor] ?? 'sentinel2';

    const queryParams = new URLSearchParams({
      target_date: params.target_date,
      days_buffer: String(params.days_buffer),
      visualization: params.visualization,
    });

    if (params.sensor !== 'Sentinel-1') {
      queryParams.append('max_cloud', String(params.max_cloud ?? 80));
    }
    if (params.mode) {
      queryParams.append('mode', params.mode);
    }

    return apiFetch<MapImageResult>(`/geo/gee/images/${sensorEndpoint}?${queryParams.toString()}`, {
      timeout: GEE_TIMEOUT,
      signal: options.signal,
    });
  },
};
