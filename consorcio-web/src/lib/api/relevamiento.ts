/**
 * Segment survey API client (flujo-caminos — Slice 4).
 *
 * Mirrors `gee-backend/app/domains/geo/relevamiento/router.py`
 * (`/api/v2/geo/relevamiento/*`), operator-only on every route.
 *
 * ⚠️ `nivel_sugerido` IS A SERVER FIELD. It arrives on `candidata` as a
 * computed field derived from the backend's single `CANDIDATA_A_NIVEL` table
 * (`relevamiento/schemas.py`). Translating `clasificacion_candidata` into a
 * level HERE would be a second copy of that table, and the day the two
 * disagreed the form would pre-fill a value the server then refused to call
 * confirmed. There is no such mapping in this file, and there must never be one.
 */

import { apiFetch } from './core';

export const NIVELES_RELATIVOS = {
  MENOR: 'menor',
  IGUAL: 'igual',
  MAYOR: 'mayor',
} as const;

export type NivelRelativo = (typeof NIVELES_RELATIVOS)[keyof typeof NIVELES_RELATIVOS];

export const TIENE_CUNETA_OPCIONES = {
  SI: 'si',
  NO: 'no',
  PARCIAL: 'parcial',
} as const;

export type TieneCuneta = (typeof TIENE_CUNETA_OPCIONES)[keyof typeof TIENE_CUNETA_OPCIONES];

export const ESTADOS_CUNETA = {
  LIMPIA: 'limpia',
  COLMATADA: 'colmatada',
} as const;

export type EstadoCuneta = (typeof ESTADOS_CUNETA)[keyof typeof ESTADOS_CUNETA];

export const CLASIFICACIONES_CANDIDATA = {
  TERRAPLEN: 'terraplen',
  CANAL: 'canal',
  NEUTRO: 'neutro',
} as const;

export type ClasificacionCandidata =
  (typeof CLASIFICACIONES_CANDIDATA)[keyof typeof CLASIFICACIONES_CANDIDATA];

/** One survey submission. Three answers, an optional note, nothing measured. */
export interface RelevamientoTramoCreate {
  readonly tramo_ref: string;
  readonly nivel_relativo: NivelRelativo;
  readonly tiene_cuneta: TieneCuneta;
  readonly estado_cuneta?: EstadoCuneta | null;
  readonly observaciones?: string | null;
  /**
   * The client's claim that the level control was left exactly as pre-filled.
   * The server corroborates it against the candidate row before storing
   * `nivel_desde_candidata`, so this is a claim, never the stored fact.
   */
  readonly nivel_confirmado_sin_cambios: boolean;
}

/** A stored survey. Always carries its author and its moment. */
export interface RelevamientoTramoResponse {
  readonly id: string;
  readonly tramo_ref: string;
  readonly nivel_relativo: NivelRelativo;
  readonly tiene_cuneta: TieneCuneta;
  readonly estado_cuneta: EstadoCuneta | null;
  readonly observaciones: string | null;
  readonly relevado_por: string;
  readonly relevado_en: string;
  readonly version: number;
  readonly nivel_desde_candidata: boolean;
  readonly es_vigente: boolean;
}

/** The DEM's guess. Labelled a candidate everywhere it appears. */
export interface CandidataResponse {
  readonly tramo_ref: string;
  readonly geo_job_id: string;
  readonly dem_layer_id: string | null;
  readonly clasificacion_candidata: ClasificacionCandidata;
  /** SIGNED median difference in metres. A magnitude, not a confidence score. */
  readonly confianza_m: number;
  readonly calculada_en: string;
  /** SERVER-COMPUTED. Never derived client-side — see the module docstring. */
  readonly nivel_sugerido: NivelRelativo;
}

/** Three NAMED fields — never merged into one "the value of this segment". */
export interface TramoRelevamientoDetalle {
  readonly tramo_ref: string;
  readonly vigente: RelevamientoTramoResponse | null;
  readonly historial: readonly RelevamientoTramoResponse[];
  readonly candidata: CandidataResponse | null;
}

/** Three counters that are NEVER summed into one "surveyed" figure (RSS-R4). */
export interface CoberturaResponse {
  readonly area_id: string | null;
  readonly relevados: number;
  readonly solo_candidato: number;
  readonly sin_datos: number;
  readonly total_activos: number;
}

/** Read `{vigente, historial[], candidata}` for one segment. */
export async function fetchTramoRelevamiento(
  tramoRef: string,
  signal?: AbortSignal
): Promise<TramoRelevamientoDetalle> {
  return apiFetch<TramoRelevamientoDetalle>(
    `/geo/relevamiento/tramos/${encodeURIComponent(tramoRef)}`,
    { signal }
  );
}

/**
 * Record one survey. The author is the authenticated session, never a field of
 * this payload — the backend forbids extra fields and would refuse the attempt
 * by name.
 */
export async function registrarRelevamiento(
  payload: RelevamientoTramoCreate,
  signal?: AbortSignal
): Promise<RelevamientoTramoResponse> {
  return apiFetch<RelevamientoTramoResponse>('/geo/relevamiento/tramos', {
    method: 'POST',
    body: JSON.stringify(payload),
    signal,
  });
}

/**
 * Read the three-way coverage split.
 *
 * With `areaId` the scope is that area's DEM footprint; an area with no
 * registered footprint answers 404 naming the area, which callers render as a
 * coverage STATE, never as the network's numbers wearing the area's label.
 */
export async function fetchCobertura(
  areaId?: string | null,
  signal?: AbortSignal
): Promise<CoberturaResponse> {
  const suffix = areaId ? `?${new URLSearchParams({ area_id: areaId })}` : '';
  return apiFetch<CoberturaResponse>(`/geo/relevamiento/cobertura${suffix}`, { signal });
}
