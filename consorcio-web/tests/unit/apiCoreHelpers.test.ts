/**
 * Fronteras y helpers de `src/lib/api/core.ts`.
 *
 * El archivo puntuaba 53.60% con 55 mutantes SIN COBERTURA. Los tests que ya
 * existen (`apiCore.test.ts`) son buenos y cubren lo dificil —refresh tras un
 * 401, propagacion de AbortSignal, el tombstone de logout cross-tab— asi que
 * el hueco no estaba ahi: estaba en el guard de URLs de fotos protegidas, en
 * el health check, y en los helpers chicos que nadie mira porque "son
 * triviales". Justamente los triviales son los que se rompen sin ruido.
 *
 * `resolveProtectedPhotoUrl` es lo mas importante de este archivo: decide si
 * una URL que viene de datos se puede pedir con el Bearer del usuario. Sin
 * tests, cualquier relajacion de esas condiciones -un `startsWith` que se
 * afloja, un chequeo de origen que se cae- pasa desapercibida y convierte al
 * cliente en un mensajero que le manda el token a un servidor ajeno.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetAccessToken = vi.fn();
const mockReplaceAccessToken = vi.fn();
const mockClearTokens = vi.fn();

vi.mock('../../src/lib/auth/index', () => ({
  authAdapter: {
    getAccessToken: mockGetAccessToken,
    replaceAccessToken: mockReplaceAccessToken,
    clearTokens: mockClearTokens,
  },
}));

/** El API_URL por defecto cuando no hay variables de entorno definidas. */
const BASE = 'http://localhost:8000';

function respuestaOk(cuerpo: unknown = { ok: true }, headers = new Headers()) {
  return { ok: true, status: 200, headers, json: async () => cuerpo, blob: async () => cuerpo };
}

describe('api core — helpers', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    global.fetch = vi.fn();
    window.localStorage.removeItem('consorcio_auth_logout_tombstone');
    mockGetAccessToken.mockResolvedValue('jwt-ok');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('unwrapItems', () => {
    it('devuelve el arreglo tal cual cuando la respuesta ya es una lista', async () => {
      const { unwrapItems } = await import('../../src/lib/api/core');
      const lista = [1, 2, 3];
      expect(unwrapItems(lista)).toBe(lista);
    });

    it('extrae items de una respuesta paginada', async () => {
      const { unwrapItems } = await import('../../src/lib/api/core');
      expect(unwrapItems({ items: ['a'] })).toEqual(['a']);
    });

    it('devuelve lista vacia -no null- cuando la forma no se reconoce', async () => {
      // Que devuelva [] y no null/undefined es lo que permite hacer `.map()`
      // directo en los componentes sin guardas por todos lados.
      const { unwrapItems } = await import('../../src/lib/api/core');
      for (const basura of [null, undefined, 'texto', 42, {}, { items: 'no-es-arreglo' }]) {
        expect(unwrapItems(basura)).toEqual([]);
      }
    });
  });

  describe('getExportAcceptHeader', () => {
    it.each([
      ['csv', 'text/csv'],
      ['json', 'application/json'],
      ['pdf', 'application/pdf'],
      ['cualquier-otra-cosa', 'application/pdf'],
    ])('para %s pide %s', async (formato, esperado) => {
      const { getExportAcceptHeader } = await import('../../src/lib/api/core');
      expect(getExportAcceptHeader(formato)).toBe(esperado);
    });
  });

  describe('healthCheck', () => {
    it('es true cuando el backend responde ok', async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true });
      const { healthCheck } = await import('../../src/lib/api/core');

      await expect(healthCheck()).resolves.toBe(true);
      expect(String((global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0])).toContain(
        '/health'
      );
    });

    it('es false ante una respuesta no-ok, sin lanzar', async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false });
      const { healthCheck } = await import('../../src/lib/api/core');

      await expect(healthCheck()).resolves.toBe(false);
    });

    it('es false ante un fallo de red, sin lanzar', async () => {
      // El health check se usa para decidir si mostrar un cartel de "sin
      // conexion". Si lanzara, tumbaria al que lo llama.
      (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('sin red'));
      const { healthCheck } = await import('../../src/lib/api/core');

      await expect(healthCheck()).resolves.toBe(false);
    });

    it('no manda Authorization: es un chequeo publico', async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true });
      const { healthCheck } = await import('../../src/lib/api/core');

      await healthCheck();

      const init = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1] ?? {};
      expect(init.headers).toBeUndefined();
    });
  });

  describe('apiFetch — respuestas sin cuerpo', () => {
    it('devuelve undefined ante un 204 sin intentar parsear JSON', async () => {
      const json = vi.fn(async () => ({ no: 'deberia' }));
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        status: 204,
        headers: new Headers(),
        json,
      });
      const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
      clearAuthTokenCache();

      await expect(apiFetch('/borrar')).resolves.toBeUndefined();
      // Parsear el cuerpo de un 204 lanza; por eso se corta antes.
      expect(json).not.toHaveBeenCalled();
    });

    it('devuelve undefined cuando content-length es 0', async () => {
      const json = vi.fn(async () => ({}));
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-length': '0' }),
        json,
      });
      const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
      clearAuthTokenCache();

      await expect(apiFetch('/vacio')).resolves.toBeUndefined();
      expect(json).not.toHaveBeenCalled();
    });

    it('parsea el cuerpo normalmente cuando hay contenido', async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
        respuestaOk({ id: 7 }, new Headers({ 'content-length': '9' }))
      );
      const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
      clearAuthTokenCache();

      await expect(apiFetch('/algo')).resolves.toEqual({ id: 7 });
    });
  });

  describe('mensajes de error de la API', () => {
    async function pedirYCapturar(cuerpo: unknown, status = 400) {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: false,
        status,
        headers: new Headers(),
        json: async () => cuerpo,
      });
      const { apiFetch, clearAuthTokenCache } = await import('../../src/lib/api/core');
      clearAuthTokenCache();
      return apiFetch('/x').catch((e: Error) => e.message);
    }

    it('prefiere `detail` sobre el resto', async () => {
      await expect(pedirYCapturar({ detail: 'el detalle', message: 'el mensaje' })).resolves.toBe(
        'el detalle'
      );
    });

    it('usa `message` cuando no hay detail', async () => {
      await expect(
        pedirYCapturar({ message: 'el mensaje', error: { message: 'anidado' } })
      ).resolves.toBe('el mensaje');
    });

    it('usa `error.message` como tercera opcion', async () => {
      await expect(pedirYCapturar({ error: { message: 'anidado' } })).resolves.toBe('anidado');
    });

    it('cae al status cuando ningun campo sirve', async () => {
      await expect(pedirYCapturar({ detail: 123 }, 503)).resolves.toBe('API Error: 503');
    });

    it('cae al status cuando el cuerpo no es un objeto', async () => {
      await expect(pedirYCapturar('vaya lio', 500)).resolves.toBe('API Error: 500');
    });

    it('cae al status cuando el cuerpo es null', async () => {
      await expect(pedirYCapturar(null, 500)).resolves.toBe('API Error: 500');
    });
  });
});

describe('fetchAuthenticatedBlob — guard de URLs protegidas', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      blob: async () => new Blob(['x']),
    });
    window.localStorage.removeItem('consorcio_auth_logout_tombstone');
    mockGetAccessToken.mockResolvedValue('jwt-ok');
  });

  async function pedirFoto(recurso: string) {
    const { fetchAuthenticatedBlob, clearAuthTokenCache } = await import('../../src/lib/api/core');
    clearAuthTokenCache();
    return fetchAuthenticatedBlob(recurso);
  }

  it('acepta una ruta relativa dentro de uploads/denuncias', async () => {
    await expect(pedirFoto('/uploads/denuncias/foto.jpg')).resolves.toBeInstanceOf(Blob);
    expect(String((global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0])).toBe(
      `${BASE}/uploads/denuncias/foto.jpg`
    );
  });

  it('acepta la URL absoluta del propio servidor', async () => {
    await expect(pedirFoto(`${BASE}/uploads/denuncias/foto.jpg`)).resolves.toBeInstanceOf(Blob);
  });

  it('RECHAZA otro origen: ahi es donde se filtraria el Bearer', async () => {
    // Este es el punto del guard. La URL sale de datos; si se aceptara un
    // origen ajeno, el cliente le mandaria el token del usuario a un servidor
    // de terceros.
    await expect(pedirFoto('https://evil.example.com/uploads/denuncias/foto.jpg')).rejects.toThrow(
      'no pertenece al servidor autorizado'
    );
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('RECHAZA una ruta fuera de uploads/denuncias en el mismo servidor', async () => {
    // Sin el prefijo, la misma funcion serviria para pedir cualquier endpoint
    // interno con el Bearer puesto.
    await expect(pedirFoto('/api/v2/admin/users')).rejects.toThrow(
      'no pertenece al servidor autorizado'
    );
  });

  it('RECHAZA el truco de la ruta que solo PARECE estar bajo uploads', async () => {
    await expect(pedirFoto('/uploads/denuncias-falso/foto.jpg')).rejects.toThrow(
      'no pertenece al servidor autorizado'
    );
  });

  it('RECHAZA credenciales embebidas en la URL', async () => {
    await expect(
      pedirFoto('http://alguien:secreto@localhost:8000/uploads/denuncias/foto.jpg')
    ).rejects.toThrow('no pertenece al servidor autorizado');
  });

  it('RECHAZA un access_token colado como query param', async () => {
    // Un token en la query se filtra por logs, Referer e historial. La funcion
    // existe justamente para NO poner credenciales en la URL.
    await expect(pedirFoto('/uploads/denuncias/foto.jpg?access_token=robado')).rejects.toThrow(
      'no pertenece al servidor autorizado'
    );
  });

  it('manda el Bearer por cabecera, nunca en la URL', async () => {
    await pedirFoto('/uploads/denuncias/foto.jpg');

    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(String(url)).not.toContain('jwt-ok');
    expect(init.headers).toMatchObject({ Authorization: 'Bearer jwt-ok' });
  });
});
