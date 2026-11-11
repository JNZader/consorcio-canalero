import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('maplibre-gl', () => {
  class Popup {
    static instances: Popup[] = [];
    closeHandlers: Array<() => void> = [];
    constructor() {
      Popup.instances.push(this);
    }
    setDOMContent() {
      return this;
    }
    once(_event: 'close', handler: () => void) {
      this.closeHandlers.push(handler);
    }
    /** Test seam: dispatch the `close` event like the real Popup does. */
    emitClose() {
      for (const handler of [...this.closeHandlers]) handler();
    }
  }
  class Marker {
    static instances: Marker[] = [];
    lngLat: [number, number] | null = null;
    added = false;
    removed = false;
    popup: Popup | null = null;
    constructor() {
      Marker.instances.push(this);
    }
    setLngLat(value: [number, number]) {
      this.lngLat = value;
      return this;
    }
    setPopup(popup: Popup) {
      this.popup = popup;
      return this;
    }
    addTo() {
      this.added = true;
      return this;
    }
    togglePopup() {
      return this;
    }
    // Real maplibre fires `close` from Popup.remove(), which Marker.remove()
    // triggers — the hook's disposed guard exists precisely for this.
    remove() {
      this.removed = true;
      this.popup?.emitClose();
      return this;
    }
  }
  return { Popup, Marker, setWorkerUrl: () => {}, default: { Popup, Marker } };
});

import * as maplibregl from 'maplibre-gl';
import { useGeolocatePinMarker } from '../../src/components/map2d/useGeolocatePinMarker';
import { useReportAnchorStore } from '../../src/stores/reportAnchorStore';

interface TrackedMarker {
  lngLat: [number, number] | null;
  added: boolean;
  removed: boolean;
  popup: { emitClose: () => void } | null;
}

function trackedMarkers(): TrackedMarker[] {
  const Marker = (maplibregl as unknown as { Marker: { instances: TrackedMarker[] } }).Marker;
  return Marker.instances;
}

function trackedPopups(): Array<{ emitClose: () => void }> {
  const Popup = (maplibregl as unknown as { Popup: { instances: Array<{ emitClose: () => void }> } })
    .Popup;
  return Popup.instances;
}

describe('useGeolocatePinMarker', () => {
  beforeEach(() => {
    useReportAnchorStore.setState({ anchor: null, geolocatePin: null });
    (maplibregl as unknown as { Marker: { instances: unknown[] } }).Marker.instances = [];
    (maplibregl as unknown as { Popup: { instances: unknown[] } }).Popup.instances = [];
  });

  it('creates a marker when the geolocate pin is set and removes it when cleared', () => {
    const mapRef = { current: {} };
    const { result } = renderHook(({ mapReady }) => useGeolocatePinMarker({ mapRef, mapReady }), {
      initialProps: { mapReady: true },
    });
    expect(result.current).toBeUndefined();
    expect(trackedMarkers()).toHaveLength(0);

    act(() => {
      useReportAnchorStore.getState().setGeolocatePin({ lat: -32.63, lng: -62.688 });
    });
    expect(trackedMarkers()).toHaveLength(1);
    expect(trackedMarkers()[0].lngLat).toEqual([-62.688, -32.63]);
    expect(trackedMarkers()[0].added).toBe(true);

    act(() => {
      useReportAnchorStore.getState().setGeolocatePin(null);
    });
    expect(trackedMarkers()[0].removed).toBe(true);
    expect(useReportAnchorStore.getState().geolocatePin).toBeNull();
  });

  it('does not create a marker while the map is not ready', () => {
    const mapRef = { current: {} };
    renderHook(({ mapReady }) => useGeolocatePinMarker({ mapRef, mapReady }), {
      initialProps: { mapReady: false },
    });
    act(() => {
      useReportAnchorStore.getState().setGeolocatePin({ lat: -32.63, lng: -62.688 });
    });
    expect(trackedMarkers()).toHaveLength(0);
  });

  it('closing the popup clears the pin and removes the marker (salir del modo)', () => {
    const mapRef = { current: {} };
    renderHook(({ mapReady }) => useGeolocatePinMarker({ mapRef, mapReady }), {
      initialProps: { mapReady: true },
    });
    act(() => {
      useReportAnchorStore.getState().setGeolocatePin({ lat: -32.63, lng: -62.688 });
    });
    const marker = trackedMarkers()[0];
    expect(marker.removed).toBe(false);

    act(() => {
      trackedPopups()[0].emitClose();
    });
    expect(useReportAnchorStore.getState().geolocatePin).toBeNull();
    expect(marker.removed).toBe(true);
  });

  it('replacing the pin removes the old marker without clobbering the new pin', () => {
    const mapRef = { current: {} };
    renderHook(({ mapReady }) => useGeolocatePinMarker({ mapRef, mapReady }), {
      initialProps: { mapReady: true },
    });
    act(() => {
      useReportAnchorStore.getState().setGeolocatePin({ lat: -32.63, lng: -62.688 });
    });
    act(() => {
      useReportAnchorStore.getState().setGeolocatePin({ lat: -32.7, lng: -62.7 });
    });

    const markers = trackedMarkers();
    expect(markers).toHaveLength(2);
    expect(markers[0].removed).toBe(true);
    expect(markers[1].removed).toBe(false);
    expect(markers[1].lngLat).toEqual([-62.7, -32.7]);
    // The close event fired while disposing marker 0 (real maplibre behavior)
    // must NOT clear the fresh pin.
    expect(useReportAnchorStore.getState().geolocatePin).toEqual({ lat: -32.7, lng: -62.7 });
  });

  it('unmount removes the marker and resets the store pin', () => {
    const mapRef = { current: {} };
    const { unmount } = renderHook(({ mapReady }) => useGeolocatePinMarker({ mapRef, mapReady }), {
      initialProps: { mapReady: true },
    });
    act(() => {
      useReportAnchorStore.getState().setGeolocatePin({ lat: -32.63, lng: -62.688 });
    });
    const marker = trackedMarkers()[0];

    unmount();
    expect(marker.removed).toBe(true);
    expect(useReportAnchorStore.getState().geolocatePin).toBeNull();
  });
});
