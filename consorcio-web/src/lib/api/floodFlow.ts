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
