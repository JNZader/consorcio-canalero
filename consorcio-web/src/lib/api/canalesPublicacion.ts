import type { FeatureCollection, LineString, MultiLineString } from 'geojson';

import { apiFetch } from './core';

export const CANAL_ORIGEN = {
  KMZ: 'kmz',
  APRHI: 'aprhi',
} as const;

export type CanalOrigen = (typeof CANAL_ORIGEN)[keyof typeof CANAL_ORIGEN];

export type CanalLineGeometry = LineString | MultiLineString;
export type CanalLineCollection = FeatureCollection<CanalLineGeometry>;

export interface CanalPublicacionRow {
  readonly id: string;
  readonly estado: 'relevado' | 'propuesto';
  readonly nombre_interno: string;
  readonly nombre_publico: string;
  readonly publicado: boolean;
  readonly longitud_m: number | null;
  readonly origen?: CanalOrigen;
}

export interface CanalPublicacionPatch {
  readonly publicado?: boolean;
  readonly nombre_publico?: string;
}

export interface CanalPublicacionCatalog {
  readonly items: CanalPublicacionRow[];
  readonly geojson: CanalLineCollection;
  readonly aprhi_items?: CanalPublicacionRow[];
  readonly geojson_aprhi?: CanalLineCollection;
}

export function listCanalPublicacion(): Promise<CanalPublicacionCatalog> {
  return apiFetch('/geo/canales/publicacion');
}

export function fetchAprhiReferencia(): Promise<CanalLineCollection> {
  return apiFetch('/geo/canales/aprhi-referencia');
}

export function patchCanalPublicacion(
  canalId: string,
  payload: CanalPublicacionPatch
): Promise<CanalPublicacionRow> {
  return apiFetch(`/geo/canales/publicacion/${encodeURIComponent(canalId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function patchCanalPublicacionAprhi(
  canalId: string,
  payload: CanalPublicacionPatch
): Promise<CanalPublicacionRow> {
  return apiFetch(`/geo/canales/publicacion/aprhi/${encodeURIComponent(canalId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}
