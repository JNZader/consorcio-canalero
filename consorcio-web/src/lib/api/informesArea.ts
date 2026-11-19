/**
 * Informe de área API client (PR 2) — background informes + PDF download.
 *
 * Mirrors `gee-backend/app/domains/geo/informe_area/router.py`, mounted at
 * `/api/v2/geo/informes-area`:
 *
 *  - `POST /` → 202 + the pending row (or the SAME completed row with
 *    `desde_cache: true` when the S4 cache hit — nothing is enqueued);
 *  - `GET /` → the user's own rows, most recent first (`Mis informes`; an
 *    admin gets every row — S11);
 *  - `GET /{id}/pdf` → `application/pdf` bytes with the server-chosen
 *    filename in `Content-Disposition`.
 *
 * **Why a dedicated raw fetch instead of `apiFetch`** — same trade
 * `lib/api/ficha.ts` and `lib/api/conocimiento.ts` document, plus auth: these
 * routes are `current_active_user`-only (S11 — informes are private), and the
 * UI branches on the server's stable `codigo` (422 `cap_excedido`, 429
 * `limite_informes_en_curso`) which a bare `QueryError` does not carry. The
 * bearer token travels in the header, never in the URL (same discipline as
 * the rainfall exports).
 *
 * KNOWN LIMIT (same as conocimiento): bypassing `apiFetch` bypasses its
 * one-shot 401 refresh/retry. A 401 here surfaces as a typed error the drawer
 * renders — the informe flow already lives behind the authenticated map
 * workspace, so the blast radius is one visible error state.
 */

import { API_PREFIX, API_URL, getAuthToken } from './core';

/**
 * Mirror of `schemas.INFORME_AREA_NOMBRE_MAX`. The TextInput stops the user at
 * the ceiling instead of spending a rate-limit slot on a request the server
 * rejects with 422. The server remains the authority.
 */
export const INFORME_AREA_NOMBRE_MAX = 200;

/**
 * Mirror of `config.informe_area_max_ha` (S5). The Generar step disables the
 * create button above it with the cap copy; the 422 `cap_excedido` path is
 * still handled for the drift case.
 */
export const INFORME_AREA_MAX_HA = 150_000;

/** The four estados of `EstadoGeoJob` an informe row can carry (S8). */
export const INFORME_AREA_ESTADOS = {
  PENDIENTE: 'pending',
  GENERANDO: 'running',
  COMPLETO: 'completed',
  FALLIDO: 'failed',
} as const;

export type InformeAreaEstado = (typeof INFORME_AREA_ESTADOS)[keyof typeof INFORME_AREA_ESTADOS];

/** One row of `Mis informes` — verbatim from `schemas.InformeAreaResponse`. */
export interface InformeAreaItem {
  readonly id: string;
  readonly nombre: string;
  readonly estado: InformeAreaEstado;
  readonly progreso: number;
  /** True only on a create that reused a completed informe (S4 cache). */
  readonly desde_cache: boolean;
  /** Union hectares once `resultado` exists; `null` before completion. */
  readonly area_ha: number | null;
  readonly cantidad_zonas: number;
  /** Readable one-line reason, present only on `failed` (S8). */
  readonly error: string | null;
  readonly vence_at: string;
  readonly created_at: string;
  readonly updated_at: string;
}

/** `GET /` — `items` is most-recent-first, capped at the server's page size. */
export interface InformeAreaListado {
  readonly items: readonly InformeAreaItem[];
  readonly total: number;
}

/** The Generar step's create payload — `desglose` mirrors the SegmentedControl. */
export interface InformeAreaCreateParams {
  readonly nombre: string;
  readonly zona_ids: readonly string[];
  /** False → totals only; True → plus one row per subcuenca. */
  readonly desglose: boolean;
}

/**
 * Typed error carrying the HTTP status and the server contract fields, so the
 * UI can render an actionable message and the hook can decide whether to
 * retry. Same shape as `FichaApiError` (the error body is the same flat
 * `{detail, codigo, ...extra}` contract, `informe_area/errors.py`).
 */
export class InformesAreaApiError extends Error {
  readonly status: number;
  readonly codigo: string;
  /** Extra structured fields the server attached (cap name/limit, retry_after…). */
  readonly extra: Record<string, unknown>;

  constructor(status: number, codigo: string, detail: string, extra: Record<string, unknown> = {}) {
    super(detail);
    this.name = 'InformesAreaApiError';
    this.status = status;
    this.codigo = codigo;
    this.extra = extra;
  }
}

interface InformeAreaErrorBody {
  detail?: unknown;
  codigo?: unknown;
  [key: string]: unknown;
}

function toInformesAreaApiError(
  status: number,
  body: InformeAreaErrorBody | null
): InformesAreaApiError {
  const detail =
    typeof body?.detail === 'string' && body.detail.length > 0
      ? body.detail
      : `No se pudo completar el pedido (error ${status})`;
  const codigo = typeof body?.codigo === 'string' ? body.codigo : 'error_desconocido';
  const extra: Record<string, unknown> = {};
  if (body) {
    for (const [key, value] of Object.entries(body)) {
      if (key !== 'detail' && key !== 'codigo') extra[key] = value;
    }
  }
  return new InformesAreaApiError(status, codigo, detail, extra);
}

/**
 * The shared JSON request: auth header, content type and the flat error
 * mapping. The content type is sent on every call for symmetry with the
 * conocimiento request helper.
 */
async function pedirInformesArea(ruta: string, init: RequestInit = {}): Promise<Response> {
  const token = await getAuthToken();
  const response = await fetch(`${API_URL}${API_PREFIX}/geo/informes-area${ruta}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as InformeAreaErrorBody | null;
    throw toInformesAreaApiError(response.status, body);
  }
  return response;
}

/**
 * Launch one background informe. 202 + the pending row, or the same completed
 * row with `desde_cache: true` when the selection + layer versions already
 * produced one (S4) — the caller decides between instant download and
 * "Te avisamos cuando esté" on that flag.
 *
 * @throws {InformesAreaApiError} 422 `cap_excedido` / bad shape, 429
 * `limite_informes_en_curso` | `limite_de_tasa`, 404 `zona_no_encontrada`.
 */
export async function crearInformeArea(
  params: InformeAreaCreateParams,
  signal?: AbortSignal
): Promise<InformeAreaItem> {
  const response = await pedirInformesArea('', {
    method: 'POST',
    body: JSON.stringify(params),
    signal,
  });
  return (await response.json()) as InformeAreaItem;
}

/**
 * List the informes the CURRENT user may see (own rows; an admin gets all —
 * S11). Most recent first; `total` can exceed `items.length`.
 *
 * @throws {InformesAreaApiError} for any non-2xx response.
 */
export async function listarInformesArea(signal?: AbortSignal): Promise<InformeAreaListado> {
  const response = await pedirInformesArea('', { signal });
  return (await response.json()) as InformeAreaListado;
}

/**
 * Parse the server's `Content-Disposition` into a download filename.
 *
 * The backend sends `attachment; filename="ascii-slug.pdf"; filename*=UTF-8''
 * informe%20nombre.pdf` (`service._nombre_archivo`): the RFC 5987 half keeps
 * the original Spanish spelling (accents), so it wins when present.
 */
export function nombreArchivoDesdeDisposition(disposition: string | null): string | null {
  if (!disposition) return null;
  const utf8 = /filename\*=(?:utf-8|UTF-8)''([^;]+)/.exec(disposition);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch {
      // A malformed escape falls through to the ASCII half, never to a crash.
    }
  }
  const ascii = /filename="([^"]+)"/.exec(disposition);
  return ascii?.[1] ?? null;
}

/**
 * Download one informe's PDF: fetch as a blob with the bearer token in the
 * header, then hand it to the browser with the SERVER's filename (fallback:
 * the row's nombre). Raw fetch on purpose — `apiFetch` parses JSON.
 *
 * @throws {InformesAreaApiError} 409 `informe_en_progreso` /
 * `informe_fallido`, 503 `pdf_aun_no_disponible`, 404 private-or-missing.
 */
export async function descargarInformeAreaPdf(informeId: string, nombre: string): Promise<void> {
  const token = await getAuthToken();
  const response = await fetch(
    `${API_URL}${API_PREFIX}/geo/informes-area/${encodeURIComponent(informeId)}/pdf`,
    {
      headers: {
        Accept: 'application/pdf',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    }
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as InformeAreaErrorBody | null;
    throw toInformesAreaApiError(response.status, body);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download =
    nombreArchivoDesdeDisposition(response.headers.get('content-disposition')) ??
    `${nombre.trim() || 'informe-area'}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
