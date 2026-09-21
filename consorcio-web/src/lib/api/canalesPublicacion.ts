import { apiFetch } from './core';

export interface CanalPublicacionRow {
  readonly id: string;
  readonly estado: 'relevado' | 'propuesto';
  readonly nombre_interno: string;
  readonly nombre_publico: string;
  readonly publicado: boolean;
  readonly longitud_m: number | null;
}

export function listCanalPublicacion(): Promise<{ items: CanalPublicacionRow[] }> {
  return apiFetch('/geo/canales/publicacion');
}

export function patchCanalPublicacion(
  canalId: string,
  payload: { publicado?: boolean; nombre_publico?: string }
): Promise<CanalPublicacionRow> {
  return apiFetch(`/geo/canales/publicacion/${encodeURIComponent(canalId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}
