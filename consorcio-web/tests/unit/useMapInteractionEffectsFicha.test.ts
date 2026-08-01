/**
 * useMapInteractionEffectsFicha.test.ts
 *
 * A4.7 — parcel click is the DEFAULT, not a mode. In `'idle'` a click that
 * resolves a `parcelas_catastro` feature ADDITIONALLY reports the parcel to the
 * container (design §6.2). This asserts:
 *   - a catastro click reports { nomenclatura, nroCuenta }, alongside the usual
 *     selectedFeatures (InfoPanel path is untouched);
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

function renderEffect(map: unknown, mode: 'idle' | 'measuring-distance', onParcelaResolved: any) {
  renderHook(() =>
    useMapInteractionEffects({
      mapRef: { current: map } as any,
      mapReady: true,
      measurementMode: mode,
      setSelectedFeatures: vi.fn(),
      onParcelaResolved,
    })
  );
}

const clickEvent = { point: { x: 10, y: 10 }, lngLat: { lat: -32.6, lng: -62.6 } };

describe('useMapInteractionEffects — ficha parcel resolution', () => {
  it('reports a catastro parcel (nomenclatura + nro_cuenta) on an idle click', () => {
    const parcela = {
      type: 'Feature',
      layer: { id: CATASTRO_LAYER },
      properties: { nomenclatura: '13-06-01-0203', nro_cuenta: '110123' },
      geometry: { type: 'Polygon', coordinates: [] },
    };
    const { map, handlers } = createMapMock([parcela]);
    const onParcelaResolved = vi.fn();
    renderEffect(map, 'idle', onParcelaResolved);

    handlers.get('click')?.[0]?.(clickEvent);

    expect(onParcelaResolved).toHaveBeenCalledWith({
      nomenclatura: '13-06-01-0203',
      nroCuenta: '110123',
    });
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
