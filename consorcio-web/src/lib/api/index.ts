/**
 * API Module Index - Re-exports all API modules for backwards compatibility.
 *
 * This file provides a unified entry point for all API functions and types.
 * Import from '@/lib/api' or '@/lib/api/index' to access all APIs.
 */

// ===========================================
// CORE EXPORTS
// ===========================================
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
} from './core';
export type { ApiFetchOptions } from './core';

// ===========================================
// REPORTS EXPORTS
// ===========================================
export { reportsApi, publicApi, statsApi } from './reports';

// ===========================================
// LAYERS EXPORTS
// ===========================================
export { layersApi } from './layers';

// ===========================================
// SUGERENCIAS EXPORTS
// ===========================================
export { sugerenciasApi } from './sugerencias';
export type {
  Sugerencia,
  SugerenciaCreate,
  RateLimitInfo,
  SugerenciaInternaCreate,
  SugerenciasStats,
  HistorialEntry,
} from './sugerencias';

// ===========================================
// MONITORING EXPORTS
// ===========================================
export { monitoringApi } from './monitoring';
export type { MonitoringDashboardData } from './monitoring';
