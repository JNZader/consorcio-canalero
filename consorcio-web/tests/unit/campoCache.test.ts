/**
 * Campo (PR 6, S5) — the loader that makes "/campo sin señal" real:
 * network-first write to Cache Storage, cache fallback when the network is
 * gone, honest error when both fail.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { cargarPaqueteCampo, urlPaqueteCampo } from '@/components/campo/campoCache';
import type { PaqueteCampo } from '@/components/campo/tiposCampo';

const paquete: PaqueteCampo = {
  version: 1,
  nombre: 'Informe test',
  generado_el: '2026-11-19T12:00:00Z',
  area_ha: 123.4,
  limites: { seleccion: { type: 'Polygon', coordinates: [] }, subcuencas: [] },
  temas: { riesgo: { titulo: 'Riesgo hídrico', clases: [] } },
  basemap: null,
  notas: [],
};

function respuestaOk(body: unknown = paquete): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

class CacheFake {
  private readonly mapa = new Map<string, Response>();

  async put(url: string, respuesta: Response): Promise<void> {
    this.mapa.set(url, respuesta.clone());
  }

  async match(url: string): Promise<Response | undefined> {
    return this.mapa.get(url);
  }
}

function instalarCaches(): { cache: CacheFake; caches: CacheStorage } {
  const cache = new CacheFake();
  const storage = { open: vi.fn().mockResolvedValue(cache) } as unknown as CacheStorage;
  vi.stubGlobal('caches', storage);
  return { cache, caches: storage };
}

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('cargarPaqueteCampo', () => {
  it('red OK: devuelve el paquete y lo guarda en Cache Storage', async () => {
    const fetchMock = vi.fn().mockResolvedValue(respuestaOk());
    vi.stubGlobal('fetch', fetchMock);
    const { caches: storage } = instalarCaches();

    const r = await cargarPaqueteCampo('http://api/campo/t1');

    expect(r.desdeCache).toBe(false);
    expect(r.paquete.nombre).toBe('Informe test');
    expect(fetchMock).toHaveBeenCalledWith('http://api/campo/t1', { cache: 'no-store' });
    expect(storage.open).toHaveBeenCalledWith('campo-packages');
  });

  it('red caída (sin señal): responde desde la cache y marca desdeCache', async () => {
    instalarCaches();
    // Prime the cache with one good fetch.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuestaOk()));
    await cargarPaqueteCampo('http://api/campo/t1');

    // Airplane mode: fetch rejects entirely.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    const r = await cargarPaqueteCampo('http://api/campo/t1');
    expect(r.desdeCache).toBe(true);
    expect(r.paquete.temas.riesgo.titulo).toBe('Riesgo hídrico');
  });

  it('token muerto (404) con cache previa: sigue andando offline', async () => {
    instalarCaches();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuestaOk()));
    await cargarPaqueteCampo('http://api/campo/t1');

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('gone', { status: 404 })));
    const r = await cargarPaqueteCampo('http://api/campo/t1');
    expect(r.desdeCache).toBe(true);
  });

  it('red caída y sin cache: error honesto, nunca un mapa vacío', async () => {
    instalarCaches();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(cargarPaqueteCampo('http://api/campo/nunca-visto')).rejects.toThrow();
  });

  it('Cache Storage ausente: funciona por red igual (y no explota)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuestaOk()));
    // No `caches` global at all.
    const r = await cargarPaqueteCampo('http://api/campo/t1');
    expect(r.paquete.version).toBe(1);
  });
});

describe('urlPaqueteCampo', () => {
  it('arma la URL pública con el token escapado', () => {
    expect(urlPaqueteCampo('abc-123', 'http://localhost:8000')).toBe(
      'http://localhost:8000/api/v2/public/campo/abc-123'
    );
    expect(urlPaqueteCampo('a/b c', 'http://x')).toBe('http://x/api/v2/public/campo/a%2Fb%20c');
  });
});
