import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('maplibre-gl', () => {
  class Popup {
    setDOMContent() {
      return this;
    }
  }
  class Marker {
    static instances: Marker[] = [];
    lngLat: [number, number] | null = null;
    added = false;
    removed = false;
    constructor() {
      Marker.instances.push(this);
    }
    setLngLat(value: [number, number]) {
      this.lngLat = value;
      return this;
    }
    setPopup() {
      return this;
    }
    addTo() {
      this.added = true;
      return this;
    }
    togglePopup() {
      return this;
    }
    remove() {
      this.removed = true;
    }
  }
  return { default: { Popup, Marker } };
});

import * as maplibregl from 'maplibre-gl';
import { useQuickPlaceMarker } from '../../src/components/map2d/useQuickPlaceMarker';

describe('useQuickPlaceMarker', () => {
  it('adds a marker at the place and removes it when cleared', () => {
    const Marker = (maplibregl as unknown as { Marker: { instances: Array<{ lngLat: [number, number] | null; added: boolean; removed: boolean }> } }).Marker;
    Marker.instances = [];
    const mapRef = { current: {} };
    const { rerender, unmount } = renderHook(
      ({ place }) => useQuickPlaceMarker({ mapRef, mapReady: true, place }),
      {
        initialProps: {
          place: { label: 'Bell Ville', lng: -62.688, lat: -32.63 } as
            | { label: string; lng: number; lat: number }
            | null,
        },
      },
    );
    expect(Marker.instances).toHaveLength(1);
    expect(Marker.instances[0].lngLat).toEqual([-62.688, -32.63]);
    expect(Marker.instances[0].added).toBe(true);

    rerender({ place: null });
    expect(Marker.instances[0].removed).toBe(true);

    unmount();
  });
});
