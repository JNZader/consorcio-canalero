/**
 * useMapInitialization.test.ts
 *
 * Regression guard for map creation options. The map MUST be constructed with
 * `cooperativeGestures: true` so wheel/one-finger gestures don't hijack the
 * page scroll (see change `rediseno-ux-mapa`, task 1.1).
 */

import type maplibregl from 'maplibre-gl';
import { renderHook } from '@testing-library/react';
import type { RefObject } from 'react';
import { describe, expect, it } from 'vitest';

import { useMapInitialization } from '../../src/components/map2d/useMapInitialization';

interface FakeMapCtorOptions {
  cooperativeGestures?: unknown;
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

describe('useMapInitialization', () => {
  it('creates the map with cooperativeGestures enabled', () => {
    const { maplibre, capturedOptions } = createFakeMaplibre();
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
      }),
    );

    expect(capturedOptions).toHaveLength(1);
    expect(capturedOptions[0]?.cooperativeGestures).toBe(true);
  });
});
