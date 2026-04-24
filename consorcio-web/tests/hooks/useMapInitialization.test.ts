import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  installMapNativeDragGuards,
  useMapInitialization,
} from '../../src/components/map2d/useMapInitialization';

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
