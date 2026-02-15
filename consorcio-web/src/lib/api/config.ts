/**
 * Config API module - Handles fetching system configuration from backend.
 */

import { apiFetch } from './core';

export interface MapConfig {
  center: {
    lat: number;
    lng: number;
  };
  zoom: number;
  bounds: {
    north: number;
    south: number;
    east: number;
    west: number;
  };
}

export interface CuencaConfig {
  id: string;
  nombre: string;
  ha: number;
  color: string;
}

export interface AnalysisConfig {
  default_max_cloud: number;
  default_days_back: number;
}

export interface SystemConfig {
  consorcio_area_ha: number;
  consorcio_km_caminos: number;
  map: MapConfig;
  cuencas: CuencaConfig[];
  analysis: AnalysisConfig;
}

/**
 * Configuration API methods.
 */
export const configApi = {
  /**
   * Fetches global system configuration.
   * This includes map center, cuencas stats, and analysis defaults.
   * It is a public endpoint.
   */
  getSystemConfig: () => apiFetch<SystemConfig>('/config/system', { skipAuth: true }),
};
