/**
 * Ficha Territorial API client.
 *
 * `POST /api/v2/geo/analisis-zona` is a PUBLIC endpoint (no operator token) that
 * returns a per-zone breakdown of soils / flood risk / drainage need (+ monthly
 * precipitation, wired in a later phase). Its request is a discriminated union
 * on `tipo`; A4 only exercises `tipo: "parcela"`, the other variants land in
 * A5/A6/A7.
 *
 * Why a dedicated fetch instead of `apiFetch`: `apiFetch` collapses every
 * non-2xx into a bare `Error` carrying only a message string. The ficha card
 * renders the server's actionable `detail` message verbatim (it does NOT branch
 * the UI on the HTTP status); the status is consumed only by the TanStack Query
 * `retry` predicate (413/422/429 are terminal, everything else gets one retry).
 * So this module throws a typed {@link FichaApiError} that preserves `status` +
 * the server `codigo` + the actionable `detail` message.
 *
 * The server error body is always the flat shape
 * `{ detail: string, codigo: string, ...extra }` (backend `ficha_errors.py`).
 */

import { API_PREFIX, API_URL } from './core';

/** One class row of a dataset breakdown. `pct` is authoritative (server-side). */
export interface FichaClase {
  clase: string;
  ha: number;
  pct: number;
  /** Full subclass string when classes are grouped by roman prefix (IVws → IV). */
  detalle?: string | null;
}

export type FichaCobertura = 'total' | 'parcial' | 'sin_cobertura';
export type FichaTipo = 'parcela' | 'poligono' | 'canal_buffer' | 'canal_cuenca';

export interface FichaDataset {
  cobertura: FichaCobertura;
  clases: FichaClase[];
  pixel_count: number;
  low_confidence: boolean;
  /** Fraction of the requested geometry the raster actually covered, 0..1. */
  cobertura_ratio: number;
}

export interface FichaPrecipMes {
  mes: number;
  mm: number;
}

/** Typed exception to `{clase, ha, pct}` — monthly normals are mean millimetres. */
export interface FichaPrecipitacion {
  cobertura: FichaCobertura;
  low_confidence: boolean;
  pixel_count: number;
  cobertura_ratio: number;
  unidad: 'mm';
  serie: FichaPrecipMes[];
  anual_mm: number | null;
}

export interface FichaResponse {
  tipo: FichaTipo;
  area_ha: number;
  suelos: FichaDataset;
  flood_risk: FichaDataset;
  drainage_need: FichaDataset;
  precipitacion_mensual: FichaPrecipitacion;
}

/** Server-resolved geometry from `parcelas_catastro`. */
export interface FichaParcelaRequest {
  tipo: 'parcela';
  nomenclatura: string;
}

/** Caller-supplied GeoJSON geometry, EPSG:4326 (phase A5). */
export interface FichaPoligonoRequest {
  tipo: 'poligono';
  geometry: Record<string, unknown>;
}

/** Influence strip around a canal (phase A6). */
export interface FichaCanalBufferRequest {
  tipo: 'canal_buffer';
  canal_id: number;
  buffer_m: number;
}

/** Precomputed catchment of a canal (phase A7). */
export interface FichaCanalCuencaRequest {
  tipo: 'canal_cuenca';
  canal_id: number;
  variante?: 'natural' | 'relevado';
}

export type FichaRequest =
  | FichaParcelaRequest
  | FichaPoligonoRequest
  | FichaCanalBufferRequest
  | FichaCanalCuencaRequest;

/**
 * Typed error carrying the HTTP status and the server contract fields so the
 * card can render an actionable message and the hook can decide whether to
 * retry.
 */
export class FichaApiError extends Error {
  readonly status: number;
  readonly codigo: string;
  /** Extra structured fields the server attached (cap name/limit, retry_after…). */
  readonly extra: Record<string, unknown>;

  constructor(status: number, codigo: string, detail: string, extra: Record<string, unknown> = {}) {
    super(detail);
    this.name = 'FichaApiError';
    this.status = status;
    this.codigo = codigo;
    this.extra = extra;
  }
}

interface FichaErrorBody {
  detail?: unknown;
  codigo?: unknown;
  [key: string]: unknown;
}

function toFichaApiError(status: number, body: FichaErrorBody | null): FichaApiError {
  const detail =
    typeof body?.detail === 'string' && body.detail.length > 0
      ? body.detail
      : `No se pudo completar el análisis (error ${status})`;
  const codigo = typeof body?.codigo === 'string' ? body.codigo : 'error_desconocido';
  const extra: Record<string, unknown> = {};
  if (body) {
    for (const [key, value] of Object.entries(body)) {
      if (key !== 'detail' && key !== 'codigo') extra[key] = value;
    }
  }
  return new FichaApiError(status, codigo, detail, extra);
}

/**
 * Request a ficha for the given area of interest.
 *
 * @throws {FichaApiError} for any non-2xx response (status + codigo preserved).
 * @throws {Error} for a network/parse failure with no HTTP response.
 */
export async function fetchAnalisisZona(
  request: FichaRequest,
  signal?: AbortSignal
): Promise<FichaResponse> {
  const response = await fetch(`${API_URL}${API_PREFIX}/geo/analisis-zona`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as FichaErrorBody | null;
    throw toFichaApiError(response.status, body);
  }

  return (await response.json()) as FichaResponse;
}
