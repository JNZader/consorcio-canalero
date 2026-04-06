/**
 * Flood Flow API module — Kirpich + Método Racional peak flow estimation.
 *
 * Endpoints under /geo/hydrology/
 */

import { apiFetch, GEE_TIMEOUT } from './core';

// ===========================================
// TYPES
// ===========================================

export interface ZonaOperativaItem {
  id: string;
  nombre: string;
  cuenca: string;
  superficie_ha: number;
}

export interface FloodFlowRequest {
  zona_ids: string[];
  fecha_lluvia: string; // YYYY-MM-DD
}

export interface ZonaFloodFlowResult {
  zona_id: string;
  zona_nombre: string | null;
  tc_minutos: number;
  c_escorrentia: number;
  c_source: string;
  intensidad_mm_h: number;
  area_km2: number;
  caudal_m3s: number;
  capacidad_m3s: number | null;
  porcentaje_capacidad: number | null;
  nivel_riesgo: 'bajo' | 'moderado' | 'alto' | 'critico' | 'sin_capacidad';
  fecha_lluvia: string;
  fecha_calculo: string;
}

export interface FloodFlowResponse {
  total_zonas: number;
  fecha_lluvia: string;
  results: ZonaFloodFlowResult[];
  errors: Array<{ zona_id: string; error: string }>;
}

export interface FloodFlowHistoryResponse {
  zona_id: string;
  records: ZonaFloodFlowResult[];
  total: number;
}

// ===========================================
// API FUNCTIONS
// ===========================================

export async function listZonasOperativas(): Promise<ZonaOperativaItem[]> {
  const res = await apiFetch<{ items: ZonaOperativaItem[]; total: number }>('/geo/intelligence/zonas?limit=200');
  return res.items;
}

export async function computeFloodFlow(req: FloodFlowRequest): Promise<FloodFlowResponse> {
  return apiFetch<FloodFlowResponse>('/geo/hydrology/flood-flow', {
    method: 'POST',
    body: JSON.stringify(req),
    timeout: GEE_TIMEOUT,
  });
}

export async function getFloodFlowHistory(
  zonaId: string,
  limit = 10
): Promise<FloodFlowHistoryResponse> {
  return apiFetch<FloodFlowHistoryResponse>(
    `/geo/hydrology/flood-flow/${zonaId}?limit=${limit}`
  );
}

// ===========================================
// MANNING HYDRAULIC CAPACITY
// ===========================================

export interface ManningRequest {
  ancho_m: number;
  profundidad_m: number;
  slope: number;
  talud: number;
  material?: string | null;
  coef_manning?: number | null;
}

export interface ManningResponse {
  ancho_m: number;
  profundidad_m: number;
  talud: number;
  slope: number;
  n: number;
  area_m2: number;
  perimeter_m: number;
  radio_hidraulico_m: number;
  q_capacity_m3s: number;
  velocidad_ms: number;
}

export async function computeManning(req: ManningRequest): Promise<ManningResponse> {
  return apiFetch<ManningResponse>('/geo/hydrology/manning', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ===========================================
// RETURN PERIODS (GUMBEL EV-I)
// ===========================================

export interface ReturnPeriodResult {
  return_period_years: number;
  precipitation_mm: number;
}

export interface ReturnPeriodsResponse {
  zona_id: string;
  years_of_data: number;
  annual_maxima_count: number;
  mean_annual_max_mm: number;
  std_annual_max_mm: number;
  return_periods: ReturnPeriodResult[];
}

export async function getReturnPeriods(zonaId: string): Promise<ReturnPeriodsResponse> {
  return apiFetch<ReturnPeriodsResponse>(`/geo/hydrology/return-periods/${zonaId}`);
}
