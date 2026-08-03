import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  installMapNativeDragGuards,
  useMapInitialization,
} from '../../src/components/map2d/useMapInitialization';
import { logger } from '../../src/lib/logger';

describe('useMapInitialization', () => {
  it('prevents native browser dragstart on the map container so pan is not hijacked', () => {
    const container = document.createElement('div');
    const removeGuards = installMapNativeDragGuards(container);

    const event = new DragEvent('dragstart', {
      bubbles: true,
      cancelable: true,
    });

    container.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(container.style.userSelect).toBe('none');
    expect(container.style.webkitUserSelect).toBe('none');
    expect(container.style.getPropertyValue('-webkit-user-drag')).toBe('none');

    removeGuards();

    const nextEvent = new DragEvent('dragstart', {
      bubbles: true,
      cancelable: true,
    });

    container.dispatchEvent(nextEvent);

    expect(nextEvent.defaultPrevented).toBe(false);
    expect(container.style.userSelect).toBe('');
    expect(container.style.webkitUserSelect).toBe('');
    expect(container.style.getPropertyValue('-webkit-user-drag')).toBe('');
  });

  it('installs and removes native drag guards with the MapLibre lifecycle', () => {
    const mockMap = {
      addControl: vi.fn(),
      on: vi.fn(),
      remove: vi.fn(),
    };

    const mapConstructor = vi.fn(function MockMap() {
      return mockMap;
    });
    const navigationControl = vi.fn(function NavigationControl() {
      return { nav: true };
    });
    const scaleControl = vi.fn(function ScaleControl() {
      return { scale: true };
    });
    const fullscreenControl = vi.fn(function FullscreenControl() {
      return { fullscreen: true };
    });

    const maplibre = {
      Map: mapConstructor,
      NavigationControl: navigationControl,
      ScaleControl: scaleControl,
      FullscreenControl: fullscreenControl,
    } as any;

    const containerRef = { current: document.createElement('div') };
    const mapRef = { current: null };
    const setMapReady = vi.fn();

    const { unmount } = renderHook(() =>
      useMapInitialization({
        maplibre,
        containerRef: containerRef as any,
        centerLat: -32.62,
        centerLng: -62.68,
        zoom: 10,
        mapRef: mapRef as any,
        setMapReady,
      })
    );

    const event = new DragEvent('dragstart', {
      bubbles: true,
      cancelable: true,
    });
    containerRef.current.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);

    unmount();

    const nextEvent = new DragEvent('dragstart', {
      bubbles: true,
      cancelable: true,
    });
    containerRef.current.dispatchEvent(nextEvent);

    expect(nextEvent.defaultPrevented).toBe(false);
  });

  it('creates a map, registers controls and disposes on unmount', () => {
    const mockMap = {
      addControl: vi.fn(),
      on: vi.fn(),
      remove: vi.fn(),
    };

    const mapConstructor = vi.fn(function MockMap() {
      return mockMap;
    });
    const navigationControl = vi.fn(function NavigationControl() {
      return { nav: true };
    });
    const scaleControl = vi.fn(function ScaleControl() {
      return { scale: true };
    });
    const fullscreenControl = vi.fn(function FullscreenControl() {
      return { fullscreen: true };
    });

    const maplibre = {
      Map: mapConstructor,
      NavigationControl: navigationControl,
      ScaleControl: scaleControl,
      FullscreenControl: fullscreenControl,
    } as any;

    const containerRef = { current: document.createElement('div') };
    const mapRef = { current: null };
    const setMapReady = vi.fn();

    const { unmount } = renderHook(() =>
      useMapInitialization({
        maplibre,
        containerRef: containerRef as any,
        centerLat: -32.62,
        centerLng: -62.68,
        zoom: 10,
        mapRef: mapRef as any,
        setMapReady,
      })
    );

    expect(mapConstructor).toHaveBeenCalledWith(
      expect.objectContaining({
        container: containerRef.current,
        center: [-62.68, -32.62],
        zoom: 10,
      })
    );
    expect(mockMap.addControl).toHaveBeenCalledTimes(3);
    expect(mockMap.on).toHaveBeenCalledWith('load', expect.any(Function));
    expect(mockMap.on).toHaveBeenCalledWith('error', expect.any(Function));
    expect(mapRef.current).toBe(mockMap);

    unmount();

    expect(mockMap.remove).toHaveBeenCalledTimes(1);
    expect(setMapReady).toHaveBeenCalledWith(false);
  });

  it('registers a FullscreenControl at top-right on the 2D map', () => {
    const mockMap = {
      addControl: vi.fn(),
      on: vi.fn(),
      remove: vi.fn(),
    };

    const mapConstructor = vi.fn(function MockMap() {
      return mockMap;
    });
    const NavigationControl = vi.fn(function NavigationControl() {
      return { nav: true };
    });
    const ScaleControl = vi.fn(function ScaleControl() {
      return { scale: true };
    });
    const FullscreenControl = vi.fn(function FullscreenControl() {
      return { fullscreen: true };
    });

    const maplibre = {
      Map: mapConstructor,
      NavigationControl,
      ScaleControl,
      FullscreenControl,
    } as any;

    const containerRef = { current: document.createElement('div') };
    const mapRef = { current: null };
    const setMapReady = vi.fn();

    renderHook(() =>
      useMapInitialization({
        maplibre,
        containerRef: containerRef as any,
        centerLat: -32.62,
        centerLng: -62.68,
        zoom: 10,
        mapRef: mapRef as any,
        setMapReady,
      })
    );

    expect(FullscreenControl).toHaveBeenCalledTimes(1);
    const fullscreenCall = mockMap.addControl.mock.calls.find(
      ([control]) => control && control.fullscreen === true
    );
    expect(fullscreenCall).toBeDefined();
    expect(fullscreenCall?.[1]).toBe('top-right');
  });

  it('initializes the MapLibre map with preserveDrawingBuffer=true so PNG/PDF export is not blank', () => {
    const mockMap = {
      addControl: vi.fn(),
      on: vi.fn(),
      remove: vi.fn(),
    };

    const mapConstructor = vi.fn(function MockMap() {
      return mockMap;
    });
    const NavigationControl = vi.fn(function NavigationControl() {
      return { nav: true };
    });
    const ScaleControl = vi.fn(function ScaleControl() {
      return { scale: true };
    });
    const FullscreenControl = vi.fn(function FullscreenControl() {
      return { fullscreen: true };
    });

    const maplibre = {
      Map: mapConstructor,
      NavigationControl,
      ScaleControl,
      FullscreenControl,
    } as any;

    const containerRef = { current: document.createElement('div') };
    const mapRef = { current: null };
    const setMapReady = vi.fn();

    renderHook(() =>
      useMapInitialization({
        maplibre,
        containerRef: containerRef as any,
        centerLat: -32.62,
        centerLng: -62.68,
        zoom: 10,
        mapRef: mapRef as any,
        setMapReady,
      })
    );

    expect(mapConstructor).toHaveBeenCalledWith(
      expect.objectContaining({
        preserveDrawingBuffer: true,
      })
    );
  });
});

/**
 * Batch 1 "datos honestos" — the `onMapError` observer.
 *
 * Two contracts live here. The observable one: every MapLibre `error` reaches
 * the callback ALREADY CLASSIFIED (tile vs real), and a real error still lands
 * in `logger.error` exactly as before. The invisible one, and the reason this
 * batch's riskiest wiring is a ref: changing the callback's identity must NOT
 * remount the map — the init effect's cleanup calls `map.remove()`.
 */
describe('useMapInitialization — onMapError', () => {
  function setup() {
    const mockMap = {
      addControl: vi.fn(),
      on: vi.fn(),
      remove: vi.fn(),
    };
    const maplibre = {
      Map: vi.fn(function MockMap() {
        return mockMap;
      }),
      NavigationControl: vi.fn(function NavigationControl() {
        return { nav: true };
      }),
      ScaleControl: vi.fn(function ScaleControl() {
        return { scale: true };
      }),
      FullscreenControl: vi.fn(function FullscreenControl() {
        return { fullscreen: true };
      }),
      // biome-ignore lint/suspicious/noExplicitAny: minimal MapLibre test double
    } as any;

    const containerRef = { current: document.createElement('div') };
    const mapRef = { current: null };

    /** The handler MapLibre would invoke on `map.on('error', …)`. */
    const emitError = (event: unknown) => {
      const call = mockMap.on.mock.calls.find(([name]) => name === 'error');
      (call?.[1] as (e: unknown) => void)(event);
    };

    return { mockMap, maplibre, containerRef, mapRef, emitError };
  }

  it('hands the callback an ALREADY CLASSIFIED tile error', () => {
    const { maplibre, containerRef, mapRef, emitError } = setup();
    const onMapError = vi.fn();

    renderHook(() =>
      useMapInitialization({
        maplibre,
        containerRef: containerRef as any,
        centerLat: -32.62,
        centerLng: -62.68,
        zoom: 10,
        mapRef: mapRef as any,
        setMapReady: vi.fn(),
        onMapError,
      })
    );

    const error = Object.assign(new Error('AJAXError: Not Found (404)'), {
      status: 404,
      url: 'https://tiles.example/1/2/3.png',
    });
    emitError({ sourceId: 'dem-tiles', error });

    expect(onMapError).toHaveBeenCalledTimes(1);
    expect(onMapError).toHaveBeenCalledWith({
      kind: 'tile',
      sourceId: 'dem-tiles',
      status: 404,
      url: 'https://tiles.example/1/2/3.png',
      message: 'AJAXError: Not Found (404)',
    });
  });

  it('still routes a NON-tile error to logger.error (unchanged behaviour)', () => {
    const { maplibre, containerRef, mapRef, emitError } = setup();
    const errorSpy = vi.spyOn(logger, 'error').mockImplementation(() => {});
    const onMapError = vi.fn();

    renderHook(() =>
      useMapInitialization({
        maplibre,
        containerRef: containerRef as any,
        centerLat: -32.62,
        centerLng: -62.68,
        zoom: 10,
        mapRef: mapRef as any,
        setMapReady: vi.fn(),
        onMapError,
      })
    );

    const realError = new Error('Style is not done loading');
    emitError({ error: realError });

    expect(onMapError).toHaveBeenCalledWith(expect.objectContaining({ kind: 'other' }));
    expect(errorSpy).toHaveBeenCalledWith('MapaMapLibre error', realError);
    errorSpy.mockRestore();
  });

  it('does NOT log a tile error to logger.error', () => {
    const { maplibre, containerRef, mapRef, emitError } = setup();
    const errorSpy = vi.spyOn(logger, 'error').mockImplementation(() => {});

    renderHook(() =>
      useMapInitialization({
        maplibre,
        containerRef: containerRef as any,
        centerLat: -32.62,
        centerLng: -62.68,
        zoom: 10,
        mapRef: mapRef as any,
        setMapReady: vi.fn(),
        onMapError: vi.fn(),
      })
    );

    emitError({ tile: {}, error: new Error('boom') });

    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it('NEVER remounts the map when the callback identity changes', () => {
    const { mockMap, maplibre, containerRef, mapRef, emitError } = setup();
    const first = vi.fn();
    const second = vi.fn();
    const third = vi.fn();
    // Stable: `setMapReady` IS a dependency of the init effect, so an inline
    // arrow here would remount the map for a reason unrelated to what we test.
    const setMapReady = vi.fn();

    const { rerender } = renderHook(
      ({ onMapError }: { onMapError: (e: unknown) => void }) =>
        useMapInitialization({
          maplibre,
          containerRef: containerRef as any,
          centerLat: -32.62,
          centerLng: -62.68,
          zoom: 10,
          mapRef: mapRef as any,
          setMapReady,
          onMapError: onMapError as never,
        }),
      { initialProps: { onMapError: first as (e: unknown) => void } }
    );

    // A brand-new inline arrow on every render is exactly what the container
    // does; if it were a dependency, the map would be torn down each time.
    rerender({ onMapError: second as (e: unknown) => void });
    rerender({ onMapError: third as (e: unknown) => void });

    expect(mockMap.remove).not.toHaveBeenCalled();
    expect(maplibre.Map).toHaveBeenCalledTimes(1);

    // Not remounting is only half the contract: the ref must also be CURRENT,
    // so the latest callback — and only it — receives the event. A ref that
    // silently kept the first callback would pass every assertion above.
    emitError({ tile: {}, error: new Error('boom') });
    expect(third).toHaveBeenCalledTimes(1);
    expect(third).toHaveBeenCalledWith(expect.objectContaining({ kind: 'tile' }));
    expect(first).not.toHaveBeenCalled();
    expect(second).not.toHaveBeenCalled();
  });

  it('keeps working when no callback is passed at all', () => {
    const { maplibre, containerRef, mapRef, emitError } = setup();

    renderHook(() =>
      useMapInitialization({
        maplibre,
        containerRef: containerRef as any,
        centerLat: -32.62,
        centerLng: -62.68,
        zoom: 10,
        mapRef: mapRef as any,
        setMapReady: vi.fn(),
      })
    );

    expect(() => emitError({ tile: {}, error: new Error('boom') })).not.toThrow();
  });
});
