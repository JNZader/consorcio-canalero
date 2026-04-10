/**
 * Territorial API module — canal km and soil area reports.
 *
 * Endpoints under /territorial/
 */

import { apiFetch } from './core';

// ===========================================
// TYPES
// ===========================================

export interface SueloBreakdown {
  simbolo: string;
  cap: string | null;
  ha: number;
  pct: number;
}

export interface CaminoConsorcioBreakdown {
  consorcio_codigo: string;
  consorcio_nombre: string;
  km: number;
  pct: number;
}

export interface TerritorialReportResponse {
  scope: 'consorcio' | 'cuenca' | 'zona';
  scope_name: string;
  km_canales: number;
  suelos: SueloBreakdown[];
  total_ha_analizada: number;
  caminos_por_consorcio: CaminoConsorcioBreakdown[];
  total_km_caminos: number;
}

export interface ImportResponse {
  imported: number;
  message: string;
}

export interface TerritorialStatus {
  has_suelos: boolean;
  has_canales: boolean;
  has_caminos: boolean;
}

// ===========================================
// API FUNCTIONS
// ===========================================

export async function getTerritorialReport(
  scope: 'consorcio' | 'cuenca' | 'zona',
  value?: string
): Promise<TerritorialReportResponse> {
  const params = new URLSearchParams({ scope });
  if (value) params.set('value', value);
  return apiFetch<TerritorialReportResponse>(`/territorial/report?${params}`);
}

export async function listCuencas(): Promise<string[]> {
  const res = await apiFetch<{ cuencas: string[] }>('/territorial/cuencas');
  return res.cuencas;
}

export async function getTerritorialStatus(): Promise<TerritorialStatus> {
  return apiFetch<TerritorialStatus>('/territorial/status');
}

export interface SyncResponse {
  message: string;
  details: Record<string, string>;
}

export async function syncGeodata(): Promise<SyncResponse> {
  return apiFetch<SyncResponse>('/territorial/sync', { method: 'POST' });
}

export async function importSuelos(geojson: object): Promise<ImportResponse> {
  return apiFetch<ImportResponse>('/territorial/import/suelos', {
    method: 'POST',
    body: JSON.stringify({ geojson }),
  });
}

export async function importCanales(geojson: object): Promise<ImportResponse> {
  return apiFetch<ImportResponse>('/territorial/import/canales', {
    method: 'POST',
    body: JSON.stringify({ geojson }),
  });
}

export async function importCaminos(geojson: object): Promise<ImportResponse> {
  return apiFetch<ImportResponse>('/territorial/import/caminos', {
    method: 'POST',
    body: JSON.stringify({ geojson }),
  });
}
