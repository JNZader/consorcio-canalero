import type { Feature } from 'geojson';
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

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
    const setNewPoint = vi.fn();
    const setSelectedFeatures = vi.fn();
    const setSelectedDraftBasinId = vi.fn();
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
        markingMode: false,
        measurementMode: 'idle',
        setNewPoint,
        setSelectedFeatures,
        showSuggestedZonesPanel: false,
        setSelectedDraftBasinId,
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
    expect(setNewPoint).not.toHaveBeenCalled();
  });

  it('creates a new point in marking mode and captures basin id in zoning mode', () => {
    const { map, handlers } = createMapMock();
    const setNewPoint = vi.fn();
    const setSelectedFeatures = vi.fn();
    const setSelectedDraftBasinId = vi.fn();

    map.queryRenderedFeatures.mockReturnValue([{ properties: { id: 'basin-1' } }]);

    const { rerender } = renderHook(
      (props: { markingMode: boolean; showSuggestedZonesPanel: boolean }) =>
        useMapInteractionEffects({
          mapRef: { current: map } as any,
          mapReady: true,
          markingMode: props.markingMode,
          measurementMode: 'idle',
          setNewPoint,
          setSelectedFeatures,
          showSuggestedZonesPanel: props.showSuggestedZonesPanel,
          setSelectedDraftBasinId,
        }),
      { initialProps: { markingMode: true, showSuggestedZonesPanel: false } },
    );

    const firstClickHandler = handlers.get('click')?.[0];
    firstClickHandler?.({
      point: { x: 10, y: 10 },
      lngLat: { lat: -32.61, lng: -62.61 },
    });
    expect(setNewPoint).toHaveBeenCalledWith({ lat: -32.61, lng: -62.61 });

    rerender({ markingMode: false, showSuggestedZonesPanel: true });

    const clickHandlers = handlers.get('click') ?? [];
    const basinClickHandler = clickHandlers.at(-1);
    basinClickHandler?.({
      point: { x: 11, y: 11 },
      lngLat: { lat: -32.62, lng: -62.62 },
    });

    expect(setSelectedDraftBasinId).toHaveBeenCalledWith('basin-1');
    expect(setSelectedFeatures).not.toHaveBeenCalled();
  });

  it('does not query/select underlying features while measurement mode is active', () => {
    const { map, handlers } = createMapMock();
    const setNewPoint = vi.fn();
    const setSelectedFeatures = vi.fn();
    const setSelectedDraftBasinId = vi.fn();

    renderHook(() =>
      useMapInteractionEffects({
        mapRef: { current: map } as any,
        mapReady: true,
        markingMode: false,
        measurementMode: 'measuring-distance',
        setNewPoint,
        setSelectedFeatures,
        showSuggestedZonesPanel: true,
        setSelectedDraftBasinId,
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
    expect(setSelectedDraftBasinId).not.toHaveBeenCalled();
    expect(setNewPoint).not.toHaveBeenCalled();
  });
});
