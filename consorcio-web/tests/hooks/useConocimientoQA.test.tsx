/**
 * useConocimientoQA.test.tsx — the bandeja's polling contract (U8, task 8.2).
 *
 * The hook owns three decisions and this file pins all three:
 *
 *  1. Submit does NOT return an answer. It enqueues; the answer arrives on a
 *     later poll of the LISTING. So a successful submit must refetch the list —
 *     without that the new question would not appear until the user reloaded.
 *  2. Polling is CONDITIONAL. It runs while at least one item is `pendiente` and
 *     stops when every item is terminal: a bandeja of settled answers that keeps
 *     hitting an admin-only route every few seconds is a self-inflicted load.
 *  3. Polling stops on a refusal. An enablement 503 is a deployment state, not a
 *     transient blip — re-asking every few seconds turns a readiness gate into a
 *     retry storm against a service that is already not ready.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  CONOCIMIENTO_POLL_ESCALERA_MS,
  CONOCIMIENTO_POLL_MS,
  intervaloDeSondeo,
  useConocimientoQA,
} from '../../src/hooks/useConocimientoQA';
import { ConocimientoApiError, type ConocimientoItem } from '../../src/lib/api/conocimiento';

vi.mock('../../src/lib/api/core', async () => {
  const actual = await vi.importActual<typeof import('../../src/lib/api/core')>(
    '../../src/lib/api/core'
  );
  return { ...actual, getAuthToken: vi.fn(async () => 'token-de-prueba') };
});

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

function item(estado: ConocimientoItem['estado'], id = '1'): ConocimientoItem {
  return {
    id,
    pregunta: '¿Quién aprueba el presupuesto?',
    estado,
    creada_en: '2026-08-24T12:00:00Z',
    procesada_en: null,
    demorado: false,
    respuesta: null,
  };
}

describe('intervaloDeSondeo', () => {
  it('polls while any item is pendiente', () => {
    expect(intervaloDeSondeo([item('respuesta', 'a'), item('pendiente', 'b')], null)).toBe(
      CONOCIMIENTO_POLL_MS
    );
  });

  it('stops once every item is terminal', () => {
    expect(intervaloDeSondeo([item('respuesta', 'a'), item('abstencion', 'b')], null)).toBe(false);
  });

  it('stops on an empty bandeja', () => {
    expect(intervaloDeSondeo([], null)).toBe(false);
  });

  it('stops on a refusal even with a pendiente item, instead of retry-storming', () => {
    const noLista = new ConocimientoApiError(
      503,
      'base_de_conocimiento_no_lista',
      'no lista',
      'embedder_no_listo'
    );
    expect(intervaloDeSondeo([item('pendiente')], noLista)).toBe(false);
  });
});

// A 500, a proxy's HTML error page and a network `TypeError` are all OUTSIDE the
// terminal-refusal list, so without a ladder the bandeja would re-ask every
// fifteen seconds forever while a `pendiente` sits there. The escalation is the
// whole point of the failure count reaching this function.
describe('intervaloDeSondeo backs off, capped, on non-terminal failures', () => {
  const quinientos = new ConocimientoApiError(500, 'error_desconocido', 'boom');

  it('polls at the base cadence while nothing is failing', () => {
    expect(intervaloDeSondeo([item('pendiente')], null, 0)).toBe(CONOCIMIENTO_POLL_ESCALERA_MS[0]);
  });

  it.each([
    [1, CONOCIMIENTO_POLL_ESCALERA_MS[1]],
    [2, CONOCIMIENTO_POLL_ESCALERA_MS[2]],
  ])('escalates to step %i after that many consecutive failures', (fallos, esperado) => {
    expect(intervaloDeSondeo([item('pendiente')], quinientos, fallos)).toBe(esperado);
  });

  it('caps at the last step instead of growing without bound', () => {
    for (const fallos of [3, 7, 500]) {
      expect(intervaloDeSondeo([item('pendiente')], quinientos, fallos)).toBe(
        CONOCIMIENTO_POLL_ESCALERA_MS[CONOCIMIENTO_POLL_ESCALERA_MS.length - 1]
      );
    }
  });

  it('backs off on a network TypeError too, which carries no HTTP status at all', () => {
    expect(intervaloDeSondeo([item('pendiente')], new TypeError('Failed to fetch'), 2)).toBe(
      CONOCIMIENTO_POLL_ESCALERA_MS[2]
    );
  });

  it('returns to the base cadence when the failure count resets on success', () => {
    expect(intervaloDeSondeo([item('pendiente')], null, 0)).toBe(CONOCIMIENTO_POLL_MS);
  });

  it('still refuses to poll a terminal refusal, however many failures preceded it', () => {
    const rateLimit = new ConocimientoApiError(429, 'limite_de_tasa', 'demasiadas');
    expect(intervaloDeSondeo([item('pendiente')], rateLimit, 5)).toBe(false);
  });
});

describe('useConocimientoQA', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('loads the bandeja on mount', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, [item('respuesta')]));

    const { result } = renderHook(() => useConocimientoQA(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/v2/conocimiento/preguntas');
  });

  it('refetches the bandeja after a successful submit, because submit carries no answer', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, []))
      .mockResolvedValueOnce(
        jsonResponse(202, { id: '9', estado: 'pendiente', creada_en: '2026-08-24T12:00:00Z' })
      )
      .mockResolvedValue(jsonResponse(200, [item('pendiente', '9')]));

    const { result } = renderHook(() => useConocimientoQA(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.items).toEqual([]));

    act(() => {
      result.current.enviar('¿Quién aprueba el presupuesto?');
    });

    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.items[0].estado).toBe('pendiente');
  });

  it('exposes the submit refusal as a typed error with its cause', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, [])).mockResolvedValueOnce(
      jsonResponse(503, {
        detail: {
          error: 'base_de_conocimiento_no_lista',
          causa: 'credencial_ausente',
          detalle: 'conocimiento_proveedor_api_key is unset',
        },
      })
    );

    const { result } = renderHook(() => useConocimientoQA(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.items).toEqual([]));

    act(() => {
      result.current.enviar('¿Qué dice el estatuto?');
    });

    await waitFor(() => expect(result.current.errorEnvio).toBeInstanceOf(ConocimientoApiError));
    expect((result.current.errorEnvio as ConocimientoApiError).causa).toBe('credencial_ausente');
  });

  // The composer clears on this callback and nowhere else, so a callback that
  // fired on rejection would be the optimistic clear wearing a different hat.
  it('runs the caller onSuccess only when the question was accepted', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, []))
      .mockResolvedValueOnce(
        jsonResponse(429, { detail: { error: 'limite_de_tasa', retry_after: 30 } })
      )
      .mockResolvedValue(
        jsonResponse(202, { id: '9', estado: 'pendiente', creada_en: '2026-08-24T12:00:00Z' })
      );

    const alAceptar = vi.fn();
    const { result } = renderHook(() => useConocimientoQA(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.items).toEqual([]));

    act(() => {
      result.current.enviar('¿Qué dice el estatuto?', { onSuccess: alAceptar });
    });
    await waitFor(() => expect(result.current.errorEnvio).toBeInstanceOf(ConocimientoApiError));
    expect(alAceptar).not.toHaveBeenCalled();

    act(() => {
      result.current.enviar('¿Qué dice el estatuto?', { onSuccess: alAceptar });
    });
    await waitFor(() => expect(alAceptar).toHaveBeenCalledTimes(1));
  });
});
