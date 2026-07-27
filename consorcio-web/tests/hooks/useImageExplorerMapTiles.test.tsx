/**
 * Regresión: al cambiar la imagen mostrada, el mapa tiene que actualizarse
 * SIEMPRE, incluso mientras todavía está cargando los tiles anteriores.
 *
 * El bug: `updateTileLayer` hacía `if (map.isStyleLoaded()) apply(); else
 * map.once('load', apply)`. El evento `load` de MapLibre dispara UNA sola vez
 * en toda la vida del mapa —lo guarda un flag `_loaded` en el propio Map— así
 * que a partir de la segunda imagen ese callback no corre nunca y la
 * actualización se descarta EN SILENCIO.
 *
 * Y se caía en esa rama seguido: `isStyleLoaded()` no mira solo el estilo,
 * agrega el estado de los tiles. Con tiles de Earth Engine que en producción
 * tardaron 20-35 segundos, cualquier cambio de visualización dentro de esa
 * ventana se perdía. El síntoma reportado fue exactamente ese: "cambio la
 * visualización y no hace nada", con el pedido saliendo y respondiendo 200.
 */

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mapaSimulado = {
  isStyleLoaded: vi.fn(() => true),
  getLayer: vi.fn(() => undefined),
  getSource: vi.fn(() => undefined),
  addSource: vi.fn(),
  addLayer: vi.fn(),
  removeLayer: vi.fn(),
  removeSource: vi.fn(),
  once: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
  remove: vi.fn(),
  fitBounds: vi.fn(),
  addControl: vi.fn(),
};

vi.mock('maplibre-gl', () => ({
  default: {
    // `function` y no arrow: el hook hace `new maplibregl.Map(...)` y una
    // arrow no puede usarse como constructor.
    Map: vi.fn(function MapaFalso() {
      return mapaSimulado;
    }),
    NavigationControl: vi.fn(function NavFalso() {
      return {};
    }),
    FullscreenControl: vi.fn(function PantallaCompletaFalsa() {
      return {};
    }),
  },
}));
vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}));
vi.mock('../../src/lib/api', () => ({
  apiFetch: vi.fn(() => new Promise(() => undefined)),
  GEE_TIMEOUT: 1000,
}));
vi.mock('../../src/lib/logger', () => ({
  logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import { useImageExplorerMap } from '../../src/components/admin/images/useImageExplorerMap';

type Api = ReturnType<typeof useImageExplorerMap>;

/** Monta el hook con un contenedor real para que el efecto cree el mapa. */
function montar(): Api {
  let api!: Api;
  function Sonda() {
    api = useImageExplorerMap();
    return <div ref={api.mapRef} />;
  }
  render(<Sonda />);
  return api;
}

/** Devuelve el callback que se registró para el evento pedido. */
function callbackDe(evento: string): (() => void) | undefined {
  const llamada = mapaSimulado.once.mock.calls.find(([nombre]) => nombre === evento);
  return llamada?.[1] as (() => void) | undefined;
}

/** URLs con las que se agregó la fuente raster de la imagen. */
function urlsAplicadas(): string[] {
  return mapaSimulado.addSource.mock.calls
    .filter(([id]) => id === 'gee-image')
    .map(([, cfg]) => (cfg as { tiles: string[] }).tiles[0]);
}

const A = 'https://earthengine.googleapis.com/mapa-A/{z}/{x}/{y}';
const B = 'https://earthengine.googleapis.com/mapa-B/{z}/{x}/{y}';

describe('updateTileLayer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mapaSimulado.isStyleLoaded.mockReturnValue(true);
  });

  it('aplica la imagen enseguida cuando el mapa está quieto', () => {
    const api = montar();

    api.updateTileLayer(A);

    expect(urlsAplicadas()).toEqual([A]);
    expect(mapaSimulado.addLayer).toHaveBeenCalled();
  });

  it('reemplaza la capa anterior en vez de apilarla', () => {
    const api = montar();
    mapaSimulado.getLayer.mockReturnValue({ id: 'gee-image-layer' } as never);
    mapaSimulado.getSource.mockReturnValue({ id: 'gee-image' } as never);

    api.updateTileLayer(B);

    expect(mapaSimulado.removeLayer).toHaveBeenCalledWith('gee-image-layer');
    expect(mapaSimulado.removeSource).toHaveBeenCalledWith('gee-image');
  });

  describe('cuando el mapa todavía está cargando tiles', () => {
    beforeEach(() => {
      mapaSimulado.isStyleLoaded.mockReturnValue(false);
    });

    it('espera en `idle` y NO en `load`', () => {
      const api = montar();
      // Se limpian los listeners del montaje: el efecto que carga la capa de
      // zona tambien usa `once('load')`, y ahi SI corresponde porque corre al
      // crear el mapa, antes de que ese evento haya disparado. Lo que se mide
      // aca es solo lo que registra `updateTileLayer`.
      mapaSimulado.once.mockClear();

      api.updateTileLayer(A);

      // `load` ya disparó cuando el mapa se creó: engancharse ahí es perder
      // la actualización para siempre.
      expect(callbackDe('load')).toBeUndefined();
      expect(callbackDe('idle')).toBeDefined();
      expect(urlsAplicadas()).toEqual([]);
    });

    it('aplica la imagen cuando el mapa se acomoda', () => {
      const api = montar();

      api.updateTileLayer(A);
      callbackDe('idle')?.();

      expect(urlsAplicadas()).toEqual([A]);
    });

    it('con dos cambios seguidos aplica el ÚLTIMO, no el primero', () => {
      // Es lo que pasa al tocar el dropdown dos veces mientras carga: pintar
      // la imagen vieja sería peor que no pintar nada.
      const api = montar();

      api.updateTileLayer(A);
      api.updateTileLayer(B);
      callbackDe('idle')?.();

      expect(urlsAplicadas()).toEqual([B]);
    });

    it('no apila un listener de `idle` por cada cambio', () => {
      const api = montar();

      api.updateTileLayer(A);
      api.updateTileLayer(B);

      const enIdle = mapaSimulado.once.mock.calls.filter(([n]) => n === 'idle');
      expect(enIdle).toHaveLength(1);
    });

    it('vuelve a esperar en `idle` para el cambio siguiente', () => {
      // El flag de "ya hay uno en cola" tiene que liberarse al aplicar; si no,
      // el primer cambio funciona y todos los demás se pierden — el bug de
      // origen con otra forma.
      const api = montar();

      api.updateTileLayer(A);
      callbackDe('idle')?.();
      mapaSimulado.once.mockClear();

      api.updateTileLayer(B);

      expect(mapaSimulado.once.mock.calls.filter(([n]) => n === 'idle')).toHaveLength(1);
    });
  });
});
