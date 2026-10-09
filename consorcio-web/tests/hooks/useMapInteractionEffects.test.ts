import type { Feature } from 'geojson';
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { useMapInteractionEffects } from '../../src/components/map2d/useMapInteractionEffects';

function createMapMock() {
  const handlers = new Map<string, Array<(event: any) => void>>();

  return {
    handlers,
    map: {
      on: vi.fn((event: string, handler: (payload: any) => void) => {
        handlers.set(event, [...(handlers.get(event) ?? []), handler]);
      }),
      off: vi.fn((event: string, handler: (payload: any) => void) => {
        handlers.set(
          event,
          (handlers.get(event) ?? []).filter((candidate) => candidate !== handler),
        );
      }),
      getLayer: vi.fn(() => ({ id: 'layer' })),
      queryRenderedFeatures: vi.fn(() => []),
    },
  };
}

describe('useMapInteractionEffects', () => {
  it('registers click handler and selects a rendered feature', () => {
    const { map, handlers } = createMapMock();
    const setSelectedFeatures = vi.fn();
    const selectedFeature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
      properties: { id: 'feat-1' },
    };
    map.queryRenderedFeatures.mockReturnValue([selectedFeature]);

    renderHook(() =>
      useMapInteractionEffects({
        mapRef: { current: map } as any,
        mapReady: true,
        measurementMode: 'idle',
        setSelectedFeatures,
      }),
    );

    const clickHandler = handlers.get('click')?.[0];
    expect(clickHandler).toBeTruthy();

    clickHandler?.({
      point: { x: 10, y: 10 },
      lngLat: { lat: -32.6, lng: -62.6 },
    });

    // Phase 8 — hook now forwards the FULL feature array (top-most first)
    // instead of the single first element; InfoPanel stacks them.
    expect(setSelectedFeatures).toHaveBeenCalledWith([selectedFeature]);
  });

  it('accumulates tramos on Ctrl-click and toggles the same tramo off', () => {
    const { map, handlers } = createMapMock();
    const setSelectedFeatures = vi.fn();
    const canalLayer = `${SOURCE_IDS.CANALES_RELEVADOS}-line`;
    const waterway = {
      type: 'Feature',
      id: 'rio',
      layer: { id: `${SOURCE_IDS.WATERWAYS}-rio-tercero-line` },
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.7, -32.6],
          [-62.71, -32.61],
        ],
      },
      properties: { id: 'rio' },
    } as Feature;
    const first: Feature = {
      type: 'Feature',
      id: 't1',
      layer: { id: canalLayer },
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.7, -32.6],
          [-62.71, -32.61],
        ],
      },
      properties: { id: 't1' },
    };
    const second: Feature = {
      type: 'Feature',
      id: 't2',
      layer: { id: canalLayer },
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.72, -32.62],
          [-62.73, -32.63],
        ],
      },
      properties: { id: 't2' },
    };
    map.queryRenderedFeatures.mockReturnValue([waterway, second]);

    renderHook(() =>
      useMapInteractionEffects({
        mapRef: { current: map } as any,
        mapReady: true,
        measurementMode: 'idle',
        setSelectedFeatures,
        selectedFeatures: [first],
      }),
    );

    handlers.get('click')?.[0]?.({
      point: { x: 10, y: 10 },
      lngLat: { lat: -32.6, lng: -62.6 },
      originalEvent: { ctrlKey: true, metaKey: false },
    });
    expect(setSelectedFeatures.mock.calls.at(-1)?.[0].map((f: Feature) => f.id)).toEqual(['t1', 't2']);
  });

  it('plain-click picks the canal, not the overlapping waterway', () => {
    const { map, handlers } = createMapMock();
    const setSelectedFeatures = vi.fn();
    const waterway = {
      type: 'Feature',
      id: 'rio',
      layer: { id: `${SOURCE_IDS.WATERWAYS}-rio-tercero-line` },
      geometry: { type: 'LineString', coordinates: [[-62.7, -32.6], [-62.71, -32.61]] },
      properties: { id: 'rio' },
    } as Feature;
    const canal = {
      type: 'Feature',
      id: 'c1',
      layer: { id: `${SOURCE_IDS.CANALES_RELEVADOS}-line` },
      geometry: { type: 'LineString', coordinates: [[-62.7, -32.6], [-62.71, -32.61]] },
      properties: { id: 'c1' },
    } as Feature;
    map.queryRenderedFeatures.mockReturnValue([waterway, canal]);

    renderHook(() =>
      useMapInteractionEffects({
        mapRef: { current: map } as any,
        mapReady: true,
        measurementMode: 'idle',
        setSelectedFeatures,
      }),
    );

    handlers.get('click')?.[0]?.({
      point: { x: 10, y: 10 },
      lngLat: { lat: -32.6, lng: -62.6 },
    });
    expect(setSelectedFeatures.mock.calls.at(-1)?.[0].map((f: Feature) => f.id)).toEqual(['c1']);
  });

  it('does not query/select underlying features while measurement mode is active', () => {
    const { map, handlers } = createMapMock();
    const setSelectedFeatures = vi.fn();

    renderHook(() =>
      useMapInteractionEffects({
        mapRef: { current: map } as any,
        mapReady: true,
        measurementMode: 'measuring-distance',
        setSelectedFeatures,
      }),
    );

    for (const clickHandler of handlers.get('click') ?? []) {
      clickHandler({
        point: { x: 12, y: 12 },
        lngLat: { lat: -32.63, lng: -62.63 },
      });
    }

    expect(map.queryRenderedFeatures).not.toHaveBeenCalled();
    expect(setSelectedFeatures).toHaveBeenCalledWith([]);
  });
});
