/**
 * informeAreaLayers.test.ts — the map surface of the informe de área.
 *
 * Pure layer/click helpers exercised against a fake maplibre Map: the
 * promoteId source + feature-state highlight, the selection outline with its
 * fitBounds bbox, resolverZona's property contract, and the module-level
 * click bridge (activate → deliver → deactivate).
 */

import { act, renderHook } from '@testing-library/react';
import type { FeatureCollection } from 'geojson';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  activarSeleccionDeZonas,
  aplicarSeleccionEnMapa,
  INFORME_AREA_FILL_LAYER,
  INFORME_AREA_LINE_LAYER,
  INFORME_AREA_OUTLINE_LAYER,
  INFORME_AREA_OUTLINE_SOURCE,
  INFORME_AREA_SOURCE,
  informeAreaPicked,
  limpiarCapasInformeArea,
  pintarContornoSeleccion,
  puenteInformeAreaActivo,
  quitarContornoSeleccion,
  registrarPuenteInformeArea,
  resolverZona,
  sincronizarFuenteZonas,
  useInformeAreaMap,
  type ZonaResuelta,
} from '../../../src/components/map2d/informeArea/informeAreaLayers';
import { mapColorTokens } from '../../../src/lib/theme';

type ConfigFuente = Record<string, unknown>;
type CapaAgregada = { id: string; type: string; source: string; paint?: Record<string, unknown> };

/** Mapa maplibre falso que graba todo lo que el módulo le pide. */
function crearMapa() {
  const fuentes = new Map<string, { setData: ReturnType<typeof vi.fn>; config: ConfigFuente }>();
  const capas = new Map<string, CapaAgregada>();
  const mapa = {
    getSource: (id: string) => fuentes.get(id) ?? undefined,
    addSource: vi.fn((id: string, config: ConfigFuente) => {
      fuentes.set(id, { setData: vi.fn(), config });
    }),
    getLayer: (id: string) => capas.get(id) ?? null,
    addLayer: vi.fn((capa: CapaAgregada) => {
      capas.set(capa.id, capa);
    }),
    removeLayer: vi.fn((id: string) => {
      capas.delete(id);
    }),
    removeSource: vi.fn((id: string) => {
      fuentes.delete(id);
    }),
    setFeatureState: vi.fn(),
    removeFeatureState: vi.fn(),
    fitBounds: vi.fn(),
  };
  return { mapa, fuentes, capas };
}

const COLECCION: FeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { id: 'z1', nombre: 'Zona uno', cuenca: 'Río Tercero' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [-62, -32],
            [-61, -32],
            [-61, -31],
            [-62, -31],
            [-62, -32],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { id: 'z2', nombre: 'Zona dos', cuenca: 'Arroyo Algodón' },
      geometry: {
        type: 'MultiPolygon',
        coordinates: [
          [
            [
              [-60, -30],
              [-59, -30],
              [-59, -29],
              [-60, -29],
              [-60, -30],
            ],
          ],
        ],
      },
    },
  ],
};

const POLIGONO_A = COLECCION.features[0].geometry;
const MULTIPOLIGONO_B = COLECCION.features[1].geometry;

/** Limpieza del bridge module-level entre tests. */
const limpiezas: Array<() => void> = [];
afterEach(() => {
  while (limpiezas.length > 0) limpiezas.pop()?.();
});

describe('resolverZona', () => {
  it('resuelve id/nombre/cuenca recortando espacios', () => {
    const zona = resolverZona([
      {
        type: 'Feature',
        properties: { id: ' z1 ', nombre: ' Zona uno ', cuenca: ' Río Tercero ' },
        geometry: { type: 'Point', coordinates: [0, 0] },
      },
    ]);
    expect(zona).toEqual({ id: 'z1', nombre: 'Zona uno', cuenca: 'Río Tercero' });
  });

  it('usa el id como nombre cuando el feature no trae nombre', () => {
    const zona = resolverZona([
      {
        type: 'Feature',
        properties: { id: 'z9' },
        geometry: { type: 'Point', coordinates: [0, 0] },
      },
    ]);
    expect(zona?.nombre).toBe('z9');
  });

  it('salta features sin id y devuelve null si ninguno sirve', () => {
    const sinId = {
      type: 'Feature',
      properties: { nombre: 'anónima' },
      geometry: { type: 'Point', coordinates: [0, 0] },
    } as const;
    expect(resolverZona([sinId])).toBeNull();
    expect(resolverZona([])).toBeNull();
  });
});

describe('puente de clicks', () => {
  it('activar entrega los picks al handler y desactivar corta la entrega', () => {
    const onZonaPicked = vi.fn();
    const desactivar = activarSeleccionDeZonas(onZonaPicked);
    limpiezas.push(desactivar);

    expect(puenteInformeAreaActivo()).toBe(true);
    const zona: ZonaResuelta = { id: 'z1', nombre: 'Zona uno', cuenca: 'Río Tercero' };
    informeAreaPicked(zona, true);
    expect(onZonaPicked).toHaveBeenCalledWith(zona, true);

    desactivar();
    expect(puenteInformeAreaActivo()).toBe(false);
    informeAreaPicked(zona, false);
    expect(onZonaPicked).toHaveBeenCalledTimes(1);
  });

  it('activar dispara el enter de transición salvo que se pida lo contrario', () => {
    const enter = vi.fn();
    const deshacer = registrarPuenteInformeArea({ getMap: () => null, enter });
    limpiezas.push(deshacer);

    const desactivar = activarSeleccionDeZonas(vi.fn());
    limpiezas.push(desactivar);
    expect(enter).toHaveBeenCalledTimes(1);

    desactivar();
    const desactivarSinDescarte = activarSeleccionDeZonas(vi.fn(), {
      descartarSeleccionPrevia: false,
    });
    limpiezas.push(desactivarSinDescarte);
    expect(enter).toHaveBeenCalledTimes(1); // no vuelve a disparar
  });

  it('registrar notifica a los listeners y desregistrar limpia el proveedor', () => {
    const { mapa } = crearMapa();
    const { result } = renderHook(() => useInformeAreaMap());
    expect(result.current).toBeNull();

    let deshacer: () => void = () => {};
    act(() => {
      deshacer = registrarPuenteInformeArea({ getMap: () => mapa, enter: vi.fn() });
    });
    limpiezas.push(deshacer);
    expect(result.current).toBe(mapa);

    act(() => deshacer());
    expect(result.current).toBeNull();
  });
});

describe('fuente de resaltado', () => {
  it('registra la fuente con promoteId y las capas fill/line con sus pinturas', () => {
    const { mapa, capas } = crearMapa();

    sincronizarFuenteZonas(mapa, COLECCION);

    expect(mapa.addSource).toHaveBeenCalledWith(INFORME_AREA_SOURCE, {
      type: 'geojson',
      data: COLECCION,
      promoteId: 'id',
    });

    const relleno = capas.get(INFORME_AREA_FILL_LAYER);
    expect(relleno?.type).toBe('fill');
    expect(relleno?.paint?.['fill-color']).toBe(mapColorTokens.h00897B);
    // La opacidad vive en un case sobre feature-state selected.
    expect(JSON.stringify(relleno?.paint?.['fill-opacity'])).toContain('feature-state');

    const linea = capas.get(INFORME_AREA_LINE_LAYER);
    expect(linea?.type).toBe('line');
    expect(linea?.source).toBe(INFORME_AREA_SOURCE);
    expect(JSON.stringify(linea?.paint?.['line-opacity'])).toContain('feature-state');
  });

  it('re-sincronizar reusa la fuente (setData) y no duplica capas', () => {
    const { mapa, fuentes } = crearMapa();

    sincronizarFuenteZonas(mapa, COLECCION);
    const otra: FeatureCollection = { ...COLECCION, features: COLECCION.features.slice(0, 1) };
    sincronizarFuenteZonas(mapa, otra);

    expect(mapa.addSource).toHaveBeenCalledTimes(1);
    expect(fuentes.get(INFORME_AREA_SOURCE)?.setData).toHaveBeenCalledWith(otra);
    expect(mapa.addLayer).toHaveBeenCalledTimes(2);
  });

  it('una colección null instala una fuente vacía', () => {
    const { mapa, fuentes } = crearMapa();

    sincronizarFuenteZonas(mapa, null);

    const config = fuentes.get(INFORME_AREA_SOURCE)?.config as { data: FeatureCollection };
    expect(config.data.features).toEqual([]);
  });
});

describe('aplicarSeleccionEnMapa', () => {
  it('setea feature-state selected por cada zona de la colección', () => {
    const { mapa } = crearMapa();
    sincronizarFuenteZonas(mapa, COLECCION);

    aplicarSeleccionEnMapa(mapa, COLECCION, new Set(['z1']));

    expect(mapa.setFeatureState).toHaveBeenCalledTimes(2);
    expect(mapa.setFeatureState).toHaveBeenCalledWith(
      { source: INFORME_AREA_SOURCE, id: 'z1' },
      { selected: true }
    );
    expect(mapa.setFeatureState).toHaveBeenCalledWith(
      { source: INFORME_AREA_SOURCE, id: 'z2' },
      { selected: false }
    );
  });

  it('sin fuente registrada no toca feature-states', () => {
    const { mapa } = crearMapa();

    aplicarSeleccionEnMapa(mapa, COLECCION, new Set(['z1']));

    expect(mapa.setFeatureState).not.toHaveBeenCalled();
  });
});

describe('contorno de la selección', () => {
  it('agrega la fuente/línea naranja y encuadra el bbox exacto', () => {
    const { mapa, capas } = crearMapa();

    pintarContornoSeleccion(mapa, [POLIGONO_A, MULTIPOLIGONO_B]);

    const linea = capas.get(INFORME_AREA_OUTLINE_LAYER);
    expect(linea?.type).toBe('line');
    expect(linea?.source).toBe(INFORME_AREA_OUTLINE_SOURCE);
    expect(linea?.paint?.['line-color']).toBe(mapColorTokens.hFF9800);
    expect(linea?.paint?.['line-width']).toBe(3);

    expect(mapa.fitBounds).toHaveBeenCalledWith([-62, -32, -59, -29], {
      padding: 64,
      duration: 600,
      maxZoom: 14,
    });
  });

  it('re-pintar reusa la fuente del contorno sin duplicar la capa', () => {
    const { mapa, fuentes } = crearMapa();

    pintarContornoSeleccion(mapa, [POLIGONO_A]);
    pintarContornoSeleccion(mapa, [MULTIPOLIGONO_B]);

    expect(mapa.addSource).toHaveBeenCalledTimes(1);
    expect(mapa.addLayer).toHaveBeenCalledTimes(1);
    expect(fuentes.get(INFORME_AREA_OUTLINE_SOURCE)?.setData).toHaveBeenCalledTimes(1);
  });

  it('geometrías no poligonales no generan encuadre', () => {
    const { mapa } = crearMapa();

    pintarContornoSeleccion(mapa, [{ type: 'Point', coordinates: [-62, -32] }]);

    expect(mapa.addSource).toHaveBeenCalledTimes(1);
    expect(mapa.fitBounds).not.toHaveBeenCalled();
  });

  it('quitar elimina la capa y la fuente del contorno', () => {
    const { mapa } = crearMapa();
    pintarContornoSeleccion(mapa, [POLIGONO_A]);

    quitarContornoSeleccion(mapa);

    expect(mapa.removeLayer).toHaveBeenCalledWith(INFORME_AREA_OUTLINE_LAYER);
    expect(mapa.removeSource).toHaveBeenCalledWith(INFORME_AREA_OUTLINE_SOURCE);
  });
});

describe('limpiarCapasInformeArea', () => {
  it('quita fuentes, capas y feature-states de todo el módulo', () => {
    const { mapa } = crearMapa();
    sincronizarFuenteZonas(mapa, COLECCION);
    pintarContornoSeleccion(mapa, [POLIGONO_A]);

    limpiarCapasInformeArea(mapa, COLECCION);

    expect(mapa.removeLayer).toHaveBeenCalledWith(INFORME_AREA_FILL_LAYER);
    expect(mapa.removeLayer).toHaveBeenCalledWith(INFORME_AREA_LINE_LAYER);
    expect(mapa.removeLayer).toHaveBeenCalledWith(INFORME_AREA_OUTLINE_LAYER);
    expect(mapa.removeSource).toHaveBeenCalledWith(INFORME_AREA_SOURCE);
    expect(mapa.removeSource).toHaveBeenCalledWith(INFORME_AREA_OUTLINE_SOURCE);
    expect(mapa.removeFeatureState).toHaveBeenCalledWith({ source: INFORME_AREA_SOURCE, id: 'z1' });
    expect(mapa.removeFeatureState).toHaveBeenCalledWith({ source: INFORME_AREA_SOURCE, id: 'z2' });
  });

  it('con colección null no recorre feature-states', () => {
    const { mapa } = crearMapa();

    limpiarCapasInformeArea(mapa, null);

    expect(mapa.removeFeatureState).not.toHaveBeenCalled();
    expect(mapa.removeLayer).not.toHaveBeenCalled();
  });
});
