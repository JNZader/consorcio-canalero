/**
 * useMapInitialization.test.ts
 *
 * Regression guard for map creation options.
 *
 * `cooperativeGestures` is now POINTER-CONDITIONAL (map-fluidity T1):
 *   - fine pointer (desktop mouse)  → true  — Ctrl+wheel to zoom, the wheel
 *     never hijacks page scroll (original `rediseno-ux-mapa` task 1.1 intent);
 *   - coarse pointer (touch)        → false — otherwise MapLibre demands TWO
 *     fingers to pan and a one-finger drag scrolls the PAGE, leaving the map
 *     effectively unpannable on phones.
 *
 * The remaining desktop hint is localised via the `locale` option.
 */

import { renderHook } from '@testing-library/react';
import type maplibregl from 'maplibre-gl';
import type { RefObject } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  MAP_LOCALE_ES,
  isCoarsePointerDevice,
  useMapInitialization,
} from '../../src/components/map2d/useMapInitialization';

interface FakeMapCtorOptions {
  cooperativeGestures?: unknown;
  locale?: Record<string, string>;
  [key: string]: unknown;
}

function createFakeMaplibre() {
  const capturedOptions: FakeMapCtorOptions[] = [];

  class FakeMap {
    constructor(options: FakeMapCtorOptions) {
      capturedOptions.push(options);
    }
    addControl(): void {}
    on(): void {}
    remove(): void {}
  }

  const maplibre = {
    Map: FakeMap,
    NavigationControl: class {},
    FullscreenControl: class {},
    ScaleControl: class {},
  } as unknown as typeof maplibregl;

  return { maplibre, capturedOptions };
}

/** Force `matchMedia('(pointer: coarse)')` to a known answer for one test. */
function stubPointerCoarse(coarse: boolean) {
  const original = window.matchMedia;
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn((query: string) => ({
      matches: query.includes('pointer: coarse') ? coarse : false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  return () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: original,
    });
  };
}

function renderInit(maplibre: typeof maplibregl) {
  const container = document.createElement('div');
  const containerRef: RefObject<HTMLDivElement | null> = { current: container };
  const mapRef: RefObject<maplibregl.Map | null> = { current: null };

  renderHook(() =>
    useMapInitialization({
      maplibre,
      containerRef,
      centerLat: -32.5,
      centerLng: -62.3,
      zoom: 10,
      mapRef,
      setMapReady: () => {},
    })
  );
}

describe('useMapInitialization — cooperative gestures', () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it('ENABLES cooperativeGestures on a fine pointer (desktop mouse)', () => {
    restore = stubPointerCoarse(false);
    const { maplibre, capturedOptions } = createFakeMaplibre();

    renderInit(maplibre);

    expect(capturedOptions).toHaveLength(1);
    expect(capturedOptions[0]?.cooperativeGestures).toBe(true);
  });

  it('DISABLES cooperativeGestures on a coarse pointer so one-finger pan works', () => {
    restore = stubPointerCoarse(true);
    const { maplibre, capturedOptions } = createFakeMaplibre();

    renderInit(maplibre);

    expect(capturedOptions).toHaveLength(1);
    expect(capturedOptions[0]?.cooperativeGestures).toBe(false);
  });

  it('passes the Spanish locale for the cooperative-gestures hint', () => {
    restore = stubPointerCoarse(false);
    const { maplibre, capturedOptions } = createFakeMaplibre();

    renderInit(maplibre);

    // Keys are the canonical MapLibre locale ids — a typo here silently leaves
    // the English default in place, so pin them explicitly.
    expect(capturedOptions[0]?.locale).toEqual({
      'CooperativeGesturesHandler.WindowsHelpText': 'Usá Ctrl + desplazamiento para hacer zoom',
      'CooperativeGesturesHandler.MacHelpText': 'Usá ⌘ + desplazamiento para hacer zoom',
      'CooperativeGesturesHandler.MobileHelpText': 'Usá dos dedos para mover el mapa',
    });
    expect(capturedOptions[0]?.locale).toEqual({ ...MAP_LOCALE_ES });
  });

  it('falls back to fine-pointer behaviour when matchMedia is unavailable', () => {
    const original = window.matchMedia;
    // biome-ignore lint/performance/noDelete: restoring the descriptor needs a true removal
    delete (window as { matchMedia?: unknown }).matchMedia;
    restore = () => {
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        configurable: true,
        value: original,
      });
    };

    expect(isCoarsePointerDevice()).toBe(false);
  });
});

/**
 * Batch 1 "datos honestos" — map-construction guard for the new `onMapError`.
 *
 * The observer must never reach the init effect's dependency array: that effect
 * builds the MapLibre map and its cleanup destroys it, so one careless dep would
 * rebuild the WebGL context (and lose the viewport and every source) on each
 * render. `capturedOptions` counts map CONSTRUCTIONS, which is the cheapest
 * possible assertion of that invariant.
 */
describe('useMapInitialization — onMapError does not rebuild the map', () => {
  it('constructs the map exactly ONCE across renders with a new callback each time', () => {
    const { maplibre, capturedOptions } = createFakeMaplibre();
    const container = document.createElement('div');
    const containerRef: RefObject<HTMLDivElement | null> = { current: container };
    const mapRef: RefObject<maplibregl.Map | null> = { current: null };
    const setMapReady = () => {};

    const { rerender } = renderHook(
      ({ onMapError }: { onMapError: () => void }) =>
        useMapInitialization({
          maplibre,
          containerRef,
          centerLat: -32.5,
          centerLng: -62.3,
          zoom: 10,
          mapRef,
          setMapReady,
          onMapError,
        }),
      { initialProps: { onMapError: () => {} } }
    );

    rerender({ onMapError: () => {} });
    rerender({ onMapError: () => {} });
    rerender({ onMapError: () => {} });

    expect(capturedOptions).toHaveLength(1);
  });
});
