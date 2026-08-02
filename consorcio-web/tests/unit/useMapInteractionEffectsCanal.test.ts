/**
 * useMapInteractionEffectsCanal.test.ts
 *
 * Canal resolution in `'ficha-canal'` mode (A7 slice 2). A click on a CURATED
 * relevados/propuestos line must resolve the canal's STRING id (`properties.id`)
 * and name (`properties.nombre`) from `canal_consorcio`, never a parcel:
 *   - `resolveCanalRef` reads `{ ref, nombre }` off a curated canal feature;
 *   - it returns null when the feature carries no usable string id;
 *   - the ficha-canal click path reports the resolved canal via `onCanalResolved`,
 *     clears any parcel/selection, and never fires the parcel path.
 */

import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import {
  resolveCanalRef,
  useMapInteractionEffects,
} from '../../src/components/map2d/useMapInteractionEffects';

const RELEVADOS_LAYER = `${SOURCE_IDS.CANALES_RELEVADOS}-line`;

function canalFeature(id: unknown, nombre?: unknown) {
  return {
    type: 'Feature',
    layer: { id: RELEVADOS_LAYER },
    properties: { id, ...(nombre === undefined ? {} : { nombre }) },
    geometry: { type: 'LineString', coordinates: [] },
  };
}

describe('resolveCanalRef', () => {
  it('reads the string id + nombre off a curated canal feature', () => {
    const features = [canalFeature('canal-ne-sin-intervencion', 'Canal NE sin intervención')];
    expect(resolveCanalRef(features as never)).toEqual({
      ref: 'canal-ne-sin-intervencion',
      nombre: 'Canal NE sin intervención',
    });
  });

  it('falls back to the ref as the name when nombre is missing', () => {
    expect(resolveCanalRef([canalFeature('canal-a')] as never)).toEqual({
      ref: 'canal-a',
      nombre: 'canal-a',
    });
  });

  it('returns null when the feature carries no usable string id', () => {
    expect(resolveCanalRef([canalFeature(42)] as never)).toBeNull();
    expect(resolveCanalRef([canalFeature('')] as never)).toBeNull();
    expect(resolveCanalRef([] as never)).toBeNull();
  });
});

function createMapMock(features: unknown[]) {
  const handlers = new Map<string, Array<(event: unknown) => void>>();
  return {
    handlers,
    map: {
      on: vi.fn((event: string, handler: (payload: unknown) => void) => {
        handlers.set(event, [...(handlers.get(event) ?? []), handler]);
      }),
      off: vi.fn(),
      getLayer: vi.fn(() => ({ id: 'layer' })),
      queryRenderedFeatures: vi.fn(() => features),
    },
  };
}

const clickEvent = {
  point: { x: 10, y: 10 },
  lngLat: { lat: -32.6, lng: -62.6 },
};

describe('useMapInteractionEffects — ficha-canal click resolution', () => {
  it('reports the resolved curated canal and never the parcel path', () => {
    const { map, handlers } = createMapMock([canalFeature('canal-a', 'Canal A')]);
    const onCanalResolved = vi.fn();
    const onParcelaResolved = vi.fn();
    const setSelectedFeatures = vi.fn();

    renderHook(() =>
      useMapInteractionEffects({
        mapRef: { current: map } as never,
        mapReady: true,
        measurementMode: 'ficha-canal',
        setSelectedFeatures,
        onParcelaResolved,
        onCanalResolved,
      })
    );

    handlers.get('click')?.[0]?.(clickEvent);

    expect(onCanalResolved).toHaveBeenCalledWith({
      ref: 'canal-a',
      nombre: 'Canal A',
    });
    // Canal mode never opens a parcel: the parcel path is cleared, not resolved.
    expect(onParcelaResolved).toHaveBeenCalledWith(null);
    expect(setSelectedFeatures).toHaveBeenCalledWith([]);
  });

  it('reports null when the ficha-canal click missed a curated canal', () => {
    const { map, handlers } = createMapMock([]);
    const onCanalResolved = vi.fn();

    renderHook(() =>
      useMapInteractionEffects({
        mapRef: { current: map } as never,
        mapReady: true,
        measurementMode: 'ficha-canal',
        setSelectedFeatures: vi.fn(),
        onParcelaResolved: vi.fn(),
        onCanalResolved,
      })
    );

    handlers.get('click')?.[0]?.(clickEvent);
    expect(onCanalResolved).toHaveBeenCalledWith(null);
  });
});
