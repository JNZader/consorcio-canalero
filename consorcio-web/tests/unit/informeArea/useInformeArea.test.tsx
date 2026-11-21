/**
 * useInformeArea.test.tsx — the background informes' polling contract (PR 2 T3).
 *
 * The hook owns four decisions and this file pins all four, mirroring the
 * bandeja's contract tests (`tests/hooks/useConocimientoQA.test.tsx`):
 *
 *  1. Polling is CONDITIONAL: it runs while any informe is pending/running
 *     and stops when every row is terminal — a settled list that keeps
 *     hitting an authenticated route every 5 s is self-inflicted load.
 *  2. Polling BACKS OFF, capped, on non-terminal failures (the ladder).
 *  3. Submit (create) does not return the informe: it returns the row, so a
 *     success MUST refetch the list, and the toast is the contract's fork —
 *     "Te avisamos cuando esté" on a plain 202, an INSTANT PDF download on
 *     `desde_cache` (S4).
 *  4. Observed transitions toast: a row that was running and arrives
 *     completed/failed announces it — that is the "te avisamos" promise.
 *
 * The api module is real (only `getAuthToken` is mocked); the wire is a
 * `global.fetch` mock, so the tests exercise the actual request/error mapping.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  descargarInformeAreaKmz,
  type InformeAreaItem,
  InformesAreaApiError,
  nombreArchivoDesdeDisposition,
  urlMapaCampo,
} from '../../../src/lib/api/informesArea';

vi.mock('../../../src/lib/api/core', async () => {
  const actual = await vi.importActual<typeof import('../../../src/lib/api/core')>(
    '../../../src/lib/api/core'
  );
  return { ...actual, getAuthToken: vi.fn(async () => 'token-de-prueba') };
});

const notificaciones = vi.hoisted(() => ({
  showInfo: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

vi.mock('../../../src/lib/notifications', () => ({
  showInfo: notificaciones.showInfo,
  showSuccess: notificaciones.showSuccess,
  showError: notificaciones.showError,
}));

import {
  INFORME_AREA_POLL_ESCALERA_MS,
  INFORME_AREA_POLL_MS,
  intervaloDeSondeoInformes,
  useCrearInformeArea,
  useMisInformes,
} from '../../../src/components/map2d/informeArea/useInformeArea';

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
  } as unknown as Response;
}

function pdfResponse(disposition: string): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-disposition': disposition }),
    blob: async () => new Blob(['%PDF-1.4 informe'], { type: 'application/pdf' }),
  } as unknown as Response;
}

function fila(parciales: Partial<InformeAreaItem> = {}, id = '11111111-1111-1111-1111-111111111111'): InformeAreaItem {
  return {
    id,
    nombre: 'Cuenca norte',
    estado: 'completed',
    progreso: 100,
    desde_cache: false,
    area_ha: 1234.5,
    cantidad_zonas: 2,
    error: null,
    vence_at: '2027-02-17T12:00:00Z',
    created_at: '2026-11-18T12:00:00Z',
    updated_at: '2026-11-18T12:01:00Z',
    ...parciales,
  };
}

/** The download anchor captured at click time (it is removed right after). */
let anchorCliqueado: HTMLAnchorElement | null = null;

beforeEach(() => {
  vi.clearAllMocks();
  // The download path drives the browser: a fake object URL + a spied click.
  // The anchor REALLY lands in the DOM (appendChild untouched); the spy grabs
  // it at click time because the download removes it right after.
  window.URL.createObjectURL = vi.fn(() => 'blob:informe');
  window.URL.revokeObjectURL = vi.fn();
  anchorCliqueado = null;
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement
  ) {
    anchorCliqueado = this;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('intervaloDeSondeoInformes', () => {
  it('polls while any informe is pending or running', () => {
    expect(intervaloDeSondeoInformes([fila({ estado: 'completed' }), fila({ estado: 'pending' }, 'b')], null)).toBe(
      INFORME_AREA_POLL_MS
    );
    expect(intervaloDeSondeoInformes([fila({ estado: 'running' })], null)).toBe(INFORME_AREA_POLL_MS);
  });

  it('stops once every informe is terminal', () => {
    expect(intervaloDeSondeoInformes([fila({ estado: 'completed' }), fila({ estado: 'failed' }, 'b')], null)).toBe(
      false
    );
  });

  it('stops on an empty list', () => {
    expect(intervaloDeSondeoInformes([], null)).toBe(false);
  });

  it('stops on a refusal even with an in-course informe, instead of retry-storming', () => {
    const rechazo = new InformesAreaApiError(429, 'limite_de_tasa', 'demasiados pedidos');
    expect(intervaloDeSondeoInformes([fila({ estado: 'running' })], rechazo)).toBe(false);
    expect(intervaloDeSondeoInformes([fila({ estado: 'pending' })], new InformesAreaApiError(503, 'x', 'y'))).toBe(
      false
    );
  });
});

describe('intervaloDeSondeoInformes backs off, capped, on non-terminal failures', () => {
  const quinientos = new InformesAreaApiError(500, 'error_desconocido', 'boom');

  it('polls at the base cadence while nothing is failing', () => {
    expect(intervaloDeSondeoInformes([fila({ estado: 'pending' })], null, 0)).toBe(
      INFORME_AREA_POLL_ESCALERA_MS[0]
    );
  });

  it.each([
    [1, INFORME_AREA_POLL_ESCALERA_MS[1]],
    [2, INFORME_AREA_POLL_ESCALERA_MS[2]],
  ])('escalates to step %i after that many consecutive failures', (fallos, esperado) => {
    expect(intervaloDeSondeoInformes([fila({ estado: 'pending' })], quinientos, fallos)).toBe(esperado);
  });

  it('caps at the last step instead of growing without bound', () => {
    for (const fallos of [3, 9, 500]) {
      expect(intervaloDeSondeoInformes([fila({ estado: 'pending' })], quinientos, fallos)).toBe(
        INFORME_AREA_POLL_ESCALERA_MS[INFORME_AREA_POLL_ESCALERA_MS.length - 1]
      );
    }
  });

  it('backs off on a network TypeError, which carries no HTTP status at all', () => {
    expect(intervaloDeSondeoInformes([fila({ estado: 'pending' })], new TypeError('Failed to fetch'), 2)).toBe(
      INFORME_AREA_POLL_ESCALERA_MS[2]
    );
  });

  it('returns to the base cadence when the failure count resets on success', () => {
    expect(intervaloDeSondeoInformes([fila({ estado: 'running' })], null, 0)).toBe(INFORME_AREA_POLL_MS);
  });
});

describe('useMisInformes', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('loads the list on mount, authenticated', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [fila()], total: 1 }));

    const { result } = renderHook(() => useMisInformes(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.informes).toHaveLength(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain('/api/v2/geo/informes-area');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer token-de-prueba');
  });

  it('toasts the completion of an informe it saw running, not one that arrives settled', async () => {
    const enCurso = fila({ estado: 'running', progreso: 40 });
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, { items: [enCurso], total: 1 }))
      .mockResolvedValueOnce(jsonResponse(200, { items: [fila({ estado: 'completed' })], total: 1 }));

    const { result } = renderHook(() => useMisInformes(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.informes[0].estado).toBe('running'));
    expect(notificaciones.showSuccess).not.toHaveBeenCalled();

    act(() => {
      result.current.refetch();
    });
    await waitFor(() => expect(result.current.informes[0].estado).toBe('completed'));

    expect(notificaciones.showSuccess).toHaveBeenCalledTimes(1);
    expect(notificaciones.showSuccess).toHaveBeenCalledWith(
      'Informe listo',
      expect.stringContaining('Cuenca norte')
    );
  });

  it('toasts a failure with the stored readable reason', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, { items: [fila({ estado: 'pending', progreso: 0 })], total: 1 }))
      .mockResolvedValueOnce(
        jsonResponse(200, { items: [fila({ estado: 'failed', error: 'GEE no disponible' })], total: 1 })
      );

    const { result } = renderHook(() => useMisInformes(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.informes[0].estado).toBe('pending'));

    act(() => {
      result.current.refetch();
    });
    await waitFor(() => expect(result.current.informes[0].estado).toBe('failed'));

    expect(notificaciones.showError).toHaveBeenCalledTimes(1);
    expect(notificaciones.showError).toHaveBeenCalledWith(
      'No se pudo generar el informe',
      expect.stringContaining('GEE no disponible')
    );
  });

  it('surfaces a typed list error to the caller', async () => {
    fetchMock.mockResolvedValue(jsonResponse(429, { detail: 'Demasiados pedidos', codigo: 'limite_de_tasa' }));

    const { result } = renderHook(() => useMisInformes(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(InformesAreaApiError);
    expect((result.current.error as InformesAreaApiError).codigo).toBe('limite_de_tasa');
  });
});

describe('useCrearInformeArea', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  /**
   * The mutation and the list must share ONE QueryClient — the whole contract
   * under test is the mutation's invalidation reaching the mounted list.
   */
  function envolver() {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return function Envoltura({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    };
  }

  it('on a plain 202 it refetches the list and promises "Te avisamos cuando esté"', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0 })) // list on mount
      .mockResolvedValueOnce(jsonResponse(202, fila({ estado: 'pending', progreso: 0 }))) // create
      .mockResolvedValue(jsonResponse(200, { items: [fila({ estado: 'pending', progreso: 0 })], total: 1 }));

    const Wrapper = envolver();
    const { result } = renderHook(() => useCrearInformeArea(), { wrapper: Wrapper });
    const otra = renderHook(() => useMisInformes(), { wrapper: Wrapper });
    await waitFor(() => expect(otra.result.current.informes).toEqual([]));

    act(() => {
      result.current.mutate({ nombre: 'Cuenca norte', zona_ids: ['z-1'], desglose: true });
    });

    await waitFor(() => expect(otra.result.current.informes).toHaveLength(1));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(String(url)).toContain('/api/v2/geo/informes-area');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      nombre: 'Cuenca norte',
      zona_ids: ['z-1'],
      desglose: true,
    });
    expect(notificaciones.showInfo).toHaveBeenCalledWith(
      'Generando «Cuenca norte»',
      'Te avisamos cuando esté.'
    );
    expect(notificaciones.showSuccess).not.toHaveBeenCalled();
  });

  it('on desde_cache it downloads the PDF instantly instead of promising a toast', async () => {
    // URL/method-driven (not queue-driven): the invalidation refetch and the
    // PDF download race each other after the 202, and queue order is not the
    // contract under test.
    fetchMock.mockImplementation((url: unknown, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith('/pdf')) {
        return Promise.resolve(
          pdfResponse(
            "attachment; filename=\"informe-cuenca-norte.pdf\"; filename*=UTF-8''Cuenca%20norte.pdf"
          )
        );
      }
      if (init?.method === 'POST') {
        return Promise.resolve(jsonResponse(202, fila({ estado: 'completed', desde_cache: true })));
      }
      return Promise.resolve(jsonResponse(200, { items: [fila()], total: 1 }));
    });

    const Wrapper = envolver();
    const { result } = renderHook(() => useCrearInformeArea(), { wrapper: Wrapper });
    const otra = renderHook(() => useMisInformes(), { wrapper: Wrapper });
    await waitFor(() => expect(otra.result.current.informes).toHaveLength(1));

    act(() => {
      result.current.mutate({ nombre: 'Cuenca norte', zona_ids: ['z-1'], desglose: false });
    });

    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/pdf'))).toBe(true)
    );
    expect(notificaciones.showInfo).not.toHaveBeenCalled();
    expect(notificaciones.showSuccess).toHaveBeenCalledTimes(1);

    // The browser download fired with the SERVER's filename (RFC 5987 half).
    await waitFor(() => expect(anchorCliqueado?.download).toBe('Cuenca norte.pdf'));
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:informe');
  });

  it('exposes a create refusal as a typed error with its stable codigo', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(429, { detail: 'Ya tenés 3 informes en curso.', codigo: 'limite_informes_en_curso' })
    );

    const { result } = renderHook(() => useCrearInformeArea(), { wrapper: wrapper() });

    act(() => {
      result.current.mutate({ nombre: 'Cuarto', zona_ids: ['z-1'], desglose: true });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(InformesAreaApiError);
    expect((result.current.error as InformesAreaApiError).codigo).toBe('limite_informes_en_curso');
    expect(notificaciones.showInfo).not.toHaveBeenCalled();
  });

  it('a download refusal surfaces the server detail as an error toast, never a crash', async () => {
    // e.g. a row the list still shows as completed but whose bytes never
    // rendered (the typed 503 `pdf_aun_no_disponible`) — the button was
    // legitimately enabled, the answer is still a refusal.
    fetchMock.mockImplementation((url: unknown, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith('/pdf')) {
        return Promise.resolve(
          jsonResponse(503, {
            detail: 'El PDF del informe todavía no está disponible en esta versión',
            codigo: 'pdf_aun_no_disponible',
          })
        );
      }
      if (init?.method === 'POST') {
        return Promise.resolve(jsonResponse(202, fila({ estado: 'completed', desde_cache: true })));
      }
      return Promise.resolve(
        jsonResponse(200, { items: [fila({ estado: 'completed' })], total: 1 })
      );
    });

    const Wrapper = envolver();
    const { result: creacion } = renderHook(() => useCrearInformeArea(), { wrapper: Wrapper });
    const otra = renderHook(() => useMisInformes(), { wrapper: Wrapper });
    await waitFor(() => expect(otra.result.current.informes).toHaveLength(1));

    act(() => {
      creacion.current.mutate({ nombre: 'Cuenca norte', zona_ids: ['z-1'], desglose: true });
    });

    await waitFor(() => expect(notificaciones.showError).toHaveBeenCalledTimes(1));
    expect(notificaciones.showError).toHaveBeenCalledWith(
      'No se pudo descargar el informe',
      'El PDF del informe todavía no está disponible en esta versión'
    );
  });
});

describe('nombreArchivoDesdeDisposition', () => {
  it('prefers the RFC 5987 UTF-8 half (accents survive)', () => {
    expect(
      nombreArchivoDesdeDisposition(
        "attachment; filename=\"informe-cuenca.pdf\"; filename*=UTF-8''Informe%20Cuenc%C3%B3n.pdf"
      )
    ).toBe('Informe Cuencón.pdf');
  });

  it('falls back to the ASCII filename half', () => {
    expect(nombreArchivoDesdeDisposition('attachment; filename="informe-cuenca.pdf"')).toBe(
      'informe-cuenca.pdf'
    );
  });

  it('returns null without a usable half', () => {
    expect(nombreArchivoDesdeDisposition(null)).toBeNull();
    expect(nombreArchivoDesdeDisposition('attachment')).toBeNull();
  });
});

describe('descargarInformeAreaKmz & urlMapaCampo', () => {
  it('descarga /kmz con Accept correcto y filename RFC 5987', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({
        'content-disposition':
          "attachment; filename=\"cuenca.kmz\"; filename*=UTF-8''Cuenc%C3%B3n%20norte.kmz",
      }),
      blob: async () => new Blob(['PK'], { type: 'application/vnd.google-earth.kmz' }),
    } as unknown as Response);
    global.fetch = fetchMock as unknown as typeof fetch;

    await descargarInformeAreaKmz('inf-99', 'Cuencón norte');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v2/geo/informes-area/inf-99/kmz');
    expect((init.headers as Record<string, string>).Accept).toBe(
      'application/vnd.google-earth.kmz'
    );
    expect(anchorCliqueado?.download).toBe('Cuencón norte.kmz');
  });

  it('arma la ruta pública de /campo con el token escapado', () => {
    expect(urlMapaCampo('tok/a b')).toContain('/campo/tok%2Fa%20b');
  });
});
