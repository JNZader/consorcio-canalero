/**
 * API Module Index - Re-exports all API modules for backwards compatibility.
 *
 * This file provides a unified entry point for all API functions and types.
 * Import from '@/lib/api' or '@/lib/api/index' to access all APIs.
 */

// ===========================================
// TYPE RE-EXPORTS (backwards compatibility)
// ===========================================
export type {
  Layer,
  LayerStyle,
  Report,
  ReportHistory,
  DashboardStats,
  PublicReportCreate,
  PublicReportResponse,
} from '../../types';

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
  unwrapItems,
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

// ===========================================
// MAP IMAGE EXPORTS
// ===========================================
export { mapImageApi } from './mapImage';
export type {
  ImagenMapaParams,
  ImagenComparacionParams,
  ImagenMapaResponse,
} from './mapImage';

// ===========================================
// CONFIG EXPORTS
// ===========================================
export { configApi } from './config';
export type {
  SystemConfig,
  MapConfig as MapConfigType,
  CuencaConfig,
  AnalysisConfig,
} from './config';

// ===========================================
// CANAL SUGGESTIONS EXPORTS
// ===========================================
export { canalSuggestionsApi } from './canalSuggestions';
export type {
  CanalSuggestion,
  CanalSuggestionsResult,
  AnalyzeResponse,
  SuggestionSummary,
  SuggestionTipo,
} from './canalSuggestions';

// ===========================================
// ROUTING EXPORTS
// ===========================================
export { routingApi } from './routing';
export type {
  RoutingMode,
  RoutingProfile,
  CorridorRoutingRequest,
  CorridorRoutingResponse,
  CorridorAlternative,
  CorridorFeature,
  CorridorFeatureCollection,
  CorridorScenario,
  CorridorScenarioListItem,
  CorridorScenarioSaveRequest,
  GeoJsonFeatureCollection,
} from './routing';

// ===========================================
// FLOOD CALIBRATION EXPORTS
// ===========================================
export { floodCalibrationApi } from './floodCalibration';
export type {
  FloodEventCreatePayload,
  FloodEventResponse,
  FloodEventListItem,
  FloodEventDetailResponse,
  TrainingResultResponse,
  RainfallRecord,
  RainfallSummaryItem,
  RainfallEvent,
  RainfallSuggestion,
  BackfillResponse,
} from './floodCalibration';
