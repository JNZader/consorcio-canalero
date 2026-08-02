/**
 * useMapInteractionEffectsFicha.test.ts
 *
 * A4.7 — parcel click is the DEFAULT, not a mode. In `'idle'` a click that
 * resolves a `parcelas_catastro` feature ADDITIONALLY reports the parcel to the
 * container (design §6.2).
 *
 * De-duplication, NOT mutual exclusion: a resolved parcel drops ONLY the
 * redundant catastro card (the ficha header already carries that identity).
 * Suppressing the whole InfoPanel made canal / escuela / BPA / suelo / camino
 * cards unreachable on any rural click once catastro defaulted to ON; the
 * panel overlap that motivated the blanket suppression is solved by LAYOUT
 * instead (`.infoPanelCompact` / `.fichaPanelCompact`).
 *
 * This asserts:
 *   - a catastro click reports { nomenclatura, nroCuenta };
 *   - a resolved parcel filters out the catastro feature but PASSES THROUGH
 *     every other feature under the same click (canal, escuela, BPA);
 *   - with NO parcel resolved the InfoPanel path is untouched (passthrough);
 *   - a click that hits no parcel clears the ficha (null);
 *   - a click while measuring clears the ficha and selects nothing.
 */

import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { useMapInteractionEffects } from '../../src/components/map2d/useMapInteractionEffects';

const CATASTRO_LAYER = `${SOURCE_IDS.CATASTRO}-fill`;

function createMapMock(features: unknown[]) {
  const handlers = new Map<string, Array<(event: any) => void>>();
  return {
    handlers,
    map: {
      on: vi.fn((event: string, handler: (payload: any) => void) => {
        handlers.set(event, [...(handlers.get(event) ?? []), handler]);
      }),
      off: vi.fn(),
      getLayer: vi.fn(() => ({ id: 'layer' })),
      queryRenderedFeatures: vi.fn(() => features),
    },
  };
}

function renderEffect(
  map: unknown,
  mode: 'idle' | 'measuring-distance',
  onParcelaResolved: any,
  setSelectedFeatures: any = vi.fn()
) {
  renderHook(() =>
    useMapInteractionEffects({
      mapRef: { current: map } as any,
      mapReady: true,
      measurementMode: mode,
      setSelectedFeatures,
      onParcelaResolved,
    })
  );
}

const clickEvent = {
  point: { x: 10, y: 10 },
  lngLat: { lat: -32.6, lng: -62.6 },
};

describe('useMapInteractionEffects — ficha parcel resolution', () => {
  it('reports a catastro parcel (nomenclatura + nro_cuenta + display props) on an idle click', () => {
    const parcela = {
      type: 'Feature',
      layer: { id: CATASTRO_LAYER },
      properties: {
        nomenclatura: '13-06-01-0203',
        nro_cuenta: '110123',
        desig_oficial: 'Lote 4',
        superficie_ha: '25.4',
        departamento: 'General San Martín',
        pedania: 'Arroyo Algodón',
        tipo_parcela: 'rural',
      },
      geometry: { type: 'Polygon', coordinates: [] },
    };
    const { map, handlers } = createMapMock([parcela]);
    const onParcelaResolved = vi.fn();
    renderEffect(map, 'idle', onParcelaResolved);

    handlers.get('click')?.[0]?.(clickEvent);

    expect(onParcelaResolved).toHaveBeenCalledWith({
      nomenclatura: '13-06-01-0203',
      nroCuenta: '110123',
      props: {
        nomenclatura: '13-06-01-0203',
        nroCuenta: '110123',
        desigOficial: 'Lote 4',
        superficieHa: '25.4',
        departamento: 'General San Martín',
        pedania: 'Arroyo Algodón',
        tipoParcela: 'rural',
      },
    });
  });

  it('drops the redundant catastro card when the parcel is the ONLY hit', () => {
    const parcela = {
      type: 'Feature',
      layer: { id: CATASTRO_LAYER },
      properties: { nomenclatura: '13-06-01-0203', nro_cuenta: '110123' },
      geometry: { type: 'Polygon', coordinates: [] },
    };
    const { map, handlers } = createMapMock([parcela]);
    const onParcelaResolved = vi.fn();
    const setSelectedFeatures = vi.fn();
    renderEffect(map, 'idle', onParcelaResolved, setSelectedFeatures);

    handlers.get('click')?.[0]?.(clickEvent);

    expect(onParcelaResolved).toHaveBeenCalledWith(
      expect.objectContaining({ nomenclatura: '13-06-01-0203' })
    );
    // Nothing left after the catastro card is filtered out → no InfoPanel.
    expect(setSelectedFeatures).toHaveBeenCalledWith([]);
  });

  it('KEEPS the canal card when a canal feature sits under the same parcel click', () => {
    // Regression guard (R3-001/R4-002): the blanket `parcela ? [] : …`
    // suppression made every non-catastro card unreachable on rural clicks once
    // catastro defaulted to ON. Only the redundant catastro card is dropped.
    const parcela = {
      type: 'Feature',
      layer: { id: CATASTRO_LAYER },
      properties: { nomenclatura: '13-06-01-0203', nro_cuenta: '110123' },
      geometry: { type: 'Polygon', coordinates: [] },
    };
    const canal = {
      type: 'Feature',
      layer: { id: 'canales_relevados-line' },
      properties: { estado: 'relevado' },
      geometry: { type: 'LineString', coordinates: [] },
    };
    const { map, handlers } = createMapMock([parcela, canal]);
    const onParcelaResolved = vi.fn();
    const setSelectedFeatures = vi.fn();
    renderEffect(map, 'idle', onParcelaResolved, setSelectedFeatures);

    handlers.get('click')?.[0]?.(clickEvent);

    // The ficha still fires for the parcel…
    expect(onParcelaResolved).toHaveBeenCalledWith(
      expect.objectContaining({ nomenclatura: '13-06-01-0203' })
    );
    // …and the canal card survives: catastro filtered, canal passed through.
    expect(setSelectedFeatures).toHaveBeenCalledWith([canal]);
  });

  it('KEEPS escuela and BPA cards under the same parcel click (ordered passthrough)', () => {
    const bpa = {
      type: 'Feature',
      layer: { id: `${SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO}-fill` },
      properties: { bpa_total: 3 },
      geometry: { type: 'Polygon', coordinates: [] },
    };
    const escuela = {
      type: 'Feature',
      layer: { id: `${SOURCE_IDS.ESCUELAS}-circle` },
      properties: { nombre: 'Escuela Rural 12' },
      geometry: { type: 'Point', coordinates: [0, 0] },
    };
    const parcela = {
      type: 'Feature',
      layer: { id: CATASTRO_LAYER },
      properties: { nomenclatura: '13-06-01-0203', nro_cuenta: '110123' },
      geometry: { type: 'Polygon', coordinates: [] },
    };
    // MapLibre order: top-most first (BPA, escuela, then catastro).
    const { map, handlers } = createMapMock([bpa, escuela, parcela]);
    const onParcelaResolved = vi.fn();
    const setSelectedFeatures = vi.fn();
    renderEffect(map, 'idle', onParcelaResolved, setSelectedFeatures);

    handlers.get('click')?.[0]?.(clickEvent);

    expect(onParcelaResolved).toHaveBeenCalledWith(
      expect.objectContaining({ nomenclatura: '13-06-01-0203' })
    );
    expect(setSelectedFeatures).toHaveBeenCalledWith([bpa, escuela]);
  });

  it('passes ALL features to InfoPanel when no catastro parcel resolved', () => {
    const canal = {
      type: 'Feature',
      layer: { id: 'canales_relevados-line' },
      properties: { estado: 'relevado' },
      geometry: { type: 'LineString', coordinates: [] },
    };
    const { map, handlers } = createMapMock([canal]);
    const setSelectedFeatures = vi.fn();
    renderEffect(map, 'idle', vi.fn(), setSelectedFeatures);

    handlers.get('click')?.[0]?.(clickEvent);

    expect(setSelectedFeatures).toHaveBeenCalledWith([canal]);
  });

  it('clears the ficha when the click hits no catastro parcel', () => {
    const other = {
      type: 'Feature',
      layer: { id: 'something-else-fill' },
      properties: { estado: 'relevado' },
      geometry: { type: 'LineString', coordinates: [] },
    };
    const { map, handlers } = createMapMock([other]);
    const onParcelaResolved = vi.fn();
    renderEffect(map, 'idle', onParcelaResolved);

    handlers.get('click')?.[0]?.(clickEvent);

    expect(onParcelaResolved).toHaveBeenCalledWith(null);
  });

  it('clears the ficha while a measurement mode is active', () => {
    const { map, handlers } = createMapMock([]);
    const onParcelaResolved = vi.fn();
    renderEffect(map, 'measuring-distance', onParcelaResolved);

    handlers.get('click')?.[0]?.(clickEvent);

    expect(onParcelaResolved).toHaveBeenCalledWith(null);
  });
});
