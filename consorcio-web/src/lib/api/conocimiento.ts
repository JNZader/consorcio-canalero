/**
 * Conocimiento mailbox API client (U8, task 8.2).
 *
 * Mirrors `gee-backend/app/domains/conocimiento/router.py`, mounted at
 * `/api/v2/conocimiento`. Under amendment A3 this surface does NOT answer:
 * `POST /preguntas` ENQUEUES and returns an id plus `pendiente`, and
 * `GET /preguntas` is the requester's own bandeja. The answer, when it exists,
 * arrives on a later poll of the listing — never on the submit response.
 *
 * **Why a dedicated fetch instead of `apiFetch`.** Two reasons, both contract:
 *
 *  1. `apiFetch` collapses every non-2xx into a bare `Error` whose message comes
 *     from `getApiErrorMessage`, which reads `detail` only when it is a STRING.
 *     This surface's errors are OBJECTS — `{error, causa, detalle}` — and the
 *     `causa` is the whole point: an enablement 503 names which of the three
 *     ANDed facts is false (`terminos_no_verificados`, `credencial_ausente`,
 *     `embedder_no_listo`), and the panel renders that as a state of the SERVICE
 *     rather than as a generic red box. Through `apiFetch` every one of those
 *     causes becomes the string "API Error: 503".
 *  2. The panel branches on the HTTP status (503 service state vs 429 rate limit
 *     vs 422 rejected question), and a bare `Error` carries no status.
 *
 * This is the same trade `lib/api/ficha.ts` documents, plus the explicit
 * `getAuthToken()` forwarding `reports.ts::uploadPhoto` uses when it has to
 * bypass `apiFetch` — the routes here are `require_admin` server-side.
 *
 * KNOWN LIMIT, stated rather than discovered: bypassing `apiFetch` also bypasses
 * its one-shot 401 refresh/retry. A 401 here surfaces as a `ConocimientoApiError`
 * and the panel says the session expired instead of silently refreshing. The
 * bandeja is a polled read behind an admin layout that already runs the auth
 * guard, so the blast radius is one visible error state, not a silent failure.
 */

import { API_PREFIX, API_URL, getAuthToken } from './core';

/**
 * The six item states, verbatim from `schemas.ItemBuzon.estado`.
 *
 * `pendiente` is the initial state of every item (A3); the other five are the
 * terminal states of the LEGAL leg and are mutually exclusive with each other.
 * `redireccion_parcial` is ORTHOGONAL to all six and is not a seventh state —
 * see {@link ConocimientoRespuesta}.
 */
export const CONOCIMIENTO_ESTADOS = {
  PENDIENTE: 'pendiente',
  RESPUESTA: 'respuesta',
  ABSTENCION: 'abstencion',
  REDIRECCION: 'redireccion',
  GENERACION_FALLIDA: 'generacion_fallida',
  NO_DISPONIBLE: 'no_disponible',
} as const;

export type ConocimientoEstado = (typeof CONOCIMIENTO_ESTADOS)[keyof typeof CONOCIMIENTO_ESTADOS];

/**
 * Mirrors `buzon.PREGUNTA_MAX_CHARS`. Mirrored so the form stops the user at the
 * ceiling instead of spending a rate-limit slot and a quota slot on a request
 * the server refuses with 422. The server remains the authority — this is a
 * courtesy bound, and the 422 path is still handled.
 */
export const CONOCIMIENTO_PREGUNTA_MAX_CHARS = 2000;

/**
 * One citation card's data, verbatim from `schemas.CitaRecuperada`.
 *
 * Only the fields the card renders are typed here. `texto` is the byte-exact
 * unit text and is the ONLY text ever shown as a citation; `estado_vigencia` and
 * `relevancia_consorcio` are SERVER-AUTHORED markers that the panel displays as
 * given and never re-derives.
 */
export interface ConocimientoCita {
  readonly citation_key: string;
  readonly documento_id: string;
  readonly epigrafe?: string | null;
  readonly texto: string;
  readonly tipo: string;
  readonly es_secundaria: boolean;
  readonly jurisdiccion: string;
  readonly estado_vigencia?: string | null;
  readonly relevancia_consorcio?: string | null;
  readonly fuente_url?: string | null;
}

/**
 * Where a non-legal question (or the non-legal half of a `mixto`) belongs.
 *
 * `superficie` is the path the SERVER named (`/tramites`, `/finanzas`,
 * `/denuncias`, `/mapa`). The panel links to it as given: the routing spec makes
 * the classification→surface mapping deterministic and server-side, and a local
 * lookup table here would be a second mapping free to drift from it.
 */
export interface ConocimientoRedireccion {
  readonly superficie: string;
  readonly motivo: string;
}

/**
 * The processed outcome of one item, verbatim from `schemas.RespuestaConocimiento`.
 *
 * The server validates the invariants the panel relies on, so the panel does not
 * re-check them: `respuesta` carries BOTH non-empty prose and at least one
 * citation; the non-answer states carry neither; `estado='redireccion'` always
 * names a surface and never carries a partial redirect. Those shapes are
 * unconstructible server-side, which is why rendering can trust them.
 */
export interface ConocimientoRespuesta {
  readonly estado: ConocimientoEstado;
  readonly respuesta?: string | null;
  /** Exactly the POST-EXCLUSION payload — the panel cannot render an excluded unit. */
  readonly citas: ConocimientoCita[];
  /** Keys dropped by the classification gate. Keys ONLY: never text, never provenance. */
  readonly claves_excluidas: string[];
  readonly motivo?: string | null;
  readonly violaciones: string[];
  readonly intentos: number;
  readonly llamadas_proveedor: number;
  /** Present iff `estado='redireccion'` (the PURE redirect). */
  readonly redireccion?: ConocimientoRedireccion | null;
  /** ORTHOGONAL to `estado`: present on ANY state iff the question was `mixto`. */
  readonly redireccion_parcial?: ConocimientoRedireccion | null;
}

/** One row of the bandeja, verbatim from `schemas.ItemBuzon`. */
export interface ConocimientoItem {
  readonly id: string;
  readonly pregunta: string;
  readonly estado: ConocimientoEstado;
  readonly creada_en: string;
  readonly procesada_en?: string | null;
  /**
   * Server-computed: a `pendiente` older than the configured worker window.
   * A3's honesty obligation as a FIELD rather than a UI guess — "pendiente" is
   * only honest while it is true, and only the server knows when the worker last
   * ran.
   */
  readonly demorado: boolean;
  /** Absent exactly while `estado='pendiente'`. */
  readonly respuesta?: ConocimientoRespuesta | null;
}

/** What `POST /preguntas` returns: an identifier and `pendiente`. Never an answer. */
export interface ConocimientoConsultaEncolada {
  readonly id: string;
  readonly estado: 'pendiente';
  readonly creada_en: string;
}

/**
 * Typed error preserving the HTTP status, the server error code and — for the
 * enablement 503 — the named `causa`. The panel branches on all three.
 */
export class ConocimientoApiError extends Error {
  readonly status: number;
  readonly codigo: string;
  /** `terminos_no_verificados` | `credencial_ausente` | `embedder_no_listo` | … */
  readonly causa: string | null;
  readonly extra: Record<string, unknown>;

  constructor(
    status: number,
    codigo: string,
    detalle: string,
    causa: string | null = null,
    extra: Record<string, unknown> = {}
  ) {
    super(detalle);
    this.name = 'ConocimientoApiError';
    this.status = status;
    this.codigo = codigo;
    this.causa = causa;
    this.extra = extra;
  }
}

interface ErrorEnvelope {
  detail?: unknown;
}

function toConocimientoApiError(status: number, body: ErrorEnvelope | null): ConocimientoApiError {
  const detail = body?.detail;

  // FastAPI's own validation errors and the house string errors both arrive as a
  // plain string; this surface's own refusals arrive as an object.
  if (typeof detail === 'string') {
    return new ConocimientoApiError(status, 'error_desconocido', detail);
  }
  if (typeof detail !== 'object' || detail === null) {
    return new ConocimientoApiError(
      status,
      'error_desconocido',
      `No se pudo contactar el buzón de consultas (error ${status})`
    );
  }

  const campos = detail as Record<string, unknown>;
  const codigo = typeof campos.error === 'string' ? campos.error : 'error_desconocido';
  const causa = typeof campos.causa === 'string' ? campos.causa : null;
  const mensaje =
    typeof campos.detalle === 'string' && campos.detalle.length > 0
      ? campos.detalle
      : `No se pudo contactar el buzón de consultas (error ${status})`;

  const extra: Record<string, unknown> = {};
  for (const [clave, valor] of Object.entries(campos)) {
    if (clave !== 'error' && clave !== 'causa' && clave !== 'detalle') extra[clave] = valor;
  }

  return new ConocimientoApiError(status, codigo, mensaje, causa, extra);
}

async function conocimientoFetch<T>(ruta: string, init: RequestInit = {}): Promise<T> {
  const token = await getAuthToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_URL}${API_PREFIX}/conocimiento${ruta}`, {
    ...init,
    headers: { ...headers, ...(init.headers as Record<string, string> | undefined) },
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ErrorEnvelope | null;
    throw toConocimientoApiError(response.status, body);
  }

  return (await response.json()) as T;
}

/**
 * Enqueue one question. Returns its id and `pendiente` — never an answer (A3).
 *
 * @throws {ConocimientoApiError} on any non-2xx, status + codigo + causa preserved.
 */
export async function enviarPregunta(
  pregunta: string,
  signal?: AbortSignal
): Promise<ConocimientoConsultaEncolada> {
  const limpia = pregunta.trim();
  if (limpia.length === 0) {
    throw new ConocimientoApiError(
      0,
      'pregunta_invalida',
      'Escribí una pregunta antes de enviarla.'
    );
  }
  if (limpia.length > CONOCIMIENTO_PREGUNTA_MAX_CHARS) {
    // Refused here rather than truncated, for the same reason the server refuses:
    // a truncated legal question is a DIFFERENT question.
    throw new ConocimientoApiError(
      0,
      'pregunta_invalida',
      `La pregunta tiene ${limpia.length} caracteres y el máximo es ${CONOCIMIENTO_PREGUNTA_MAX_CHARS}.`
    );
  }

  return conocimientoFetch<ConocimientoConsultaEncolada>('/preguntas', {
    method: 'POST',
    body: JSON.stringify({ pregunta: limpia }),
    signal,
  });
}

/** The requester's own bandeja, newest first. */
export async function listarPreguntas(
  signal?: AbortSignal,
  limite?: number
): Promise<ConocimientoItem[]> {
  const query = limite === undefined ? '' : `?limite=${limite}`;
  return conocimientoFetch<ConocimientoItem[]>(`/preguntas${query}`, { method: 'GET', signal });
}
