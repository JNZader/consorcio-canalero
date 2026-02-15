/**
 * Cliente API para el backend GEE.
 * Maneja todas las llamadas al backend Python.
 *
 * BACKWARDS COMPATIBILITY FILE
 * This file re-exports all APIs from the modular api/ directory.
 * New code should import directly from '@/lib/api' or specific modules.
 *
 * Module structure:
 * - api/core.ts - Base fetch function, auth token handling, API_URL, API_PREFIX
 * - api/reports.ts - reportsApi, publicApi, statsApi
 * - api/layers.ts - layersApi
 * - api/sugerencias.ts - sugerenciasApi
 * - api/monitoring.ts - monitoringApi
 *
 * Note: GEE layers are loaded directly via useGEELayers hook (not through API module)
 */

// Re-export common types from types/ for backwards compatibility
export type {
  Layer,
  LayerStyle,
  Report,
  ReportHistory,
  DashboardStats,
  PublicReportCreate,
  PublicReportResponse,
} from '../types';

// ===========================================
// RE-EXPORT ALL FROM MODULAR API
// ===========================================

// Core exports
export {
  API_URL,
  API_PREFIX,
  DEFAULT_TIMEOUT,
  LONG_TIMEOUT,
  HEALTH_TIMEOUT,
  apiFetch,
  getAuthToken,
  clearAuthTokenCache,
  healthCheck,
  getExportAcceptHeader,
} from './api/core';
export type { ApiFetchOptions } from './api/core';

// Reports exports
export { reportsApi, publicApi, statsApi } from './api/reports';

// Layers exports
export { layersApi } from './api/layers';

// Sugerencias exports
export { sugerenciasApi } from './api/sugerencias';
export type {
  Sugerencia,
  SugerenciaCreate,
  RateLimitInfo,
  SugerenciaInternaCreate,
  SugerenciasStats,
} from './api/sugerencias';

// Monitoring exports
export { monitoringApi } from './api/monitoring';
export type { MonitoringDashboardData } from './api/monitoring';

// Config exports
export { configApi } from './api/config';
export type { SystemConfig, MapConfig as MapConfigType, CuencaConfig, AnalysisConfig } from './api/config';
