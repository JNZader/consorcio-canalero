/**
 * conocimientoApi.test.ts — the mailbox wire contract (U8, task 8.2).
 *
 * The three things this pins, and why each of them is not decoration:
 *
 *  1. `POST /preguntas` is a SUBMIT, not an ask. It returns an id and
 *     `pendiente` and the client must not expect an answer from it (amendment
 *     A3). A client that read an answer off the submit response would be reading
 *     a field the server never sends.
 *  2. The 503 the enablement gate raises carries a NAMED CAUSE
 *     (`terminos_no_verificados` / `credencial_ausente` / `embedder_no_listo`),
 *     and the panel renders it as a state of the SERVICE. `apiFetch` cannot
 *     carry it: `getApiErrorMessage` only reads a STRING `detail`, and this
 *     surface's detail is an object, so every cause would collapse to
 *     "API Error: 503". That is the whole reason this module has its own fetch.
 *  3. The bearer token is attached. The route is `require_admin` server-side;
 *     an unauthenticated GET would 401 and the bandeja would render an error
 *     state for a logged-in admin.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  CONOCIMIENTO_PREGUNTA_MAX_CHARS,
  ConocimientoApiError,
  enviarPregunta,
  listarPreguntas,
} from '../../src/lib/api/conocimiento';

vi.mock('../../src/lib/api/core', async () => {
  const actual =
    await vi.importActual<typeof import('../../src/lib/api/core')>('../../src/lib/api/core');
  return { ...actual, getAuthToken: vi.fn(async () => 'token-de-prueba') };
});

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  global.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('enviarPregunta', () => {
  it('POSTs the question and returns the queued id with estado pendiente', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(202, {
        id: '11111111-1111-4111-8111-111111111111',
        estado: 'pendiente',
        creada_en: '2026-08-24T12:00:00Z',
      })
    );

    const encolada = await enviarPregunta('¿Quién aprueba el presupuesto?');

    expect(encolada.estado).toBe('pendiente');
    expect(encolada.id).toBe('11111111-1111-4111-8111-111111111111');

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v2/conocimiento/preguntas');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      pregunta: '¿Quién aprueba el presupuesto?',
    });
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer token-de-prueba');
  });

  it('refuses a question over the server ceiling without spending a request', async () => {
    await expect(enviarPregunta('a'.repeat(CONOCIMIENTO_PREGUNTA_MAX_CHARS + 1))).rejects.toThrow(
      ConocimientoApiError
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('preserves the NAMED CAUSE of the enablement 503', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(503, {
        detail: {
          error: 'base_de_conocimiento_no_lista',
          causa: 'terminos_no_verificados',
          detalle: 'the provider terms record is not verified for this pin',
        },
      })
    );

    const error = await enviarPregunta('¿Qué dice el estatuto?').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ConocimientoApiError);
    const apiError = error as ConocimientoApiError;
    expect(apiError.status).toBe(503);
    expect(apiError.codigo).toBe('base_de_conocimiento_no_lista');
    expect(apiError.causa).toBe('terminos_no_verificados');
    expect(apiError.message).toContain('terms record');
  });

  it('carries retry_after off a 429 so the panel can say when', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(429, { detail: { error: 'limite_de_tasa', retry_after: 42 } })
    );

    const apiError = (await enviarPregunta('¿Y ahora?').catch(
      (e: unknown) => e
    )) as ConocimientoApiError;

    expect(apiError.status).toBe(429);
    expect(apiError.codigo).toBe('limite_de_tasa');
    expect(apiError.extra.retry_after).toBe(42);
  });
});

describe('listarPreguntas', () => {
  it('GETs the requester bandeja and returns the items verbatim', async () => {
    const items = [
      {
        id: '22222222-2222-4222-8222-222222222222',
        pregunta: '¿Quién aprueba el presupuesto?',
        estado: 'pendiente',
        creada_en: '2026-08-24T12:00:00Z',
        procesada_en: null,
        demorado: false,
        respuesta: null,
      },
    ];
    fetchMock.mockResolvedValue(jsonResponse(200, items));

    expect(await listarPreguntas()).toEqual(items);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v2/conocimiento/preguntas');
    expect(init?.method ?? 'GET').toBe('GET');
  });
});
