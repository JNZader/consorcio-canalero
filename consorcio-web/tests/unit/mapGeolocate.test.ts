import { describe, expect, it, vi } from 'vitest';

import { GEOLOCATE_MIN_ZOOM, geolocateFlyToOptions, requestMapGeolocate } from '../../src/components/map2d/mapGeolocate';

describe('mapGeolocate UX-20', () => {
  it('raises zoom to city scale', () => {
    expect(geolocateFlyToOptions({ longitude: -62.5, latitude: -32.5 }, 8)).toEqual({
      center: [-62.5, -32.5],
      zoom: GEOLOCATE_MIN_ZOOM,
      essential: false,
    });
    expect(geolocateFlyToOptions({ longitude: -62.5, latitude: -32.5 }, 16).zoom).toBe(16);
  });

  it('asks the browser only after a click', () => {
    const flyTo = vi.fn();
    const getCurrentPosition = vi.fn((ok: (pos: { coords: GeolocationCoordinates }) => void) => {
      ok({
        coords: {
          longitude: -62.54,
          latitude: -32.54,
          accuracy: 10,
          altitude: null,
          altitudeAccuracy: null,
          heading: null,
          speed: null,
          toJSON: () => ({}),
        },
      } as GeolocationPosition);
    });
    const map = { getZoom: () => 10, flyTo };
    expect(requestMapGeolocate(map, { getCurrentPosition })).toBe(true);
    expect(flyTo).toHaveBeenCalledWith({
      center: [-62.54, -32.54],
      zoom: GEOLOCATE_MIN_ZOOM,
      essential: false,
    });
    expect(requestMapGeolocate(null, { getCurrentPosition })).toBe(false);
  });

  it('invokes onError when browser geolocation rejects and guards #v= after delayed moveend', () => {
    vi.useFakeTimers();
    try {
      window.history.replaceState(null, '', '/mapa#v=10/-32.5/-62.5');
      const errorMock = { code: 1, message: 'User denied' } as GeolocationPositionError;
      const onError = vi.fn();
      const handlers = new Map<string, () => void>();
      const map = {
        getZoom: () => 10,
        flyTo: vi.fn(),
        once: vi.fn((event: 'moveend' | 'dragstart', handler: () => void) => {
          handlers.set(event, handler);
        }),
        off: vi.fn(),
      };

      requestMapGeolocate(
        map,
        {
          getCurrentPosition: (_ok, err) => {
            err?.(errorMock);
          },
        },
        undefined,
        onError
      );
      expect(onError).toHaveBeenCalledWith(errorMock);

      requestMapGeolocate(
        map,
        {
          getCurrentPosition: (ok) => {
            ok({
              coords: { longitude: -62.54, latitude: -32.54 },
            } as GeolocationPosition);
          },
        }
      );

      // Simulate MapLibre `moveend` followed by delayed `hash: 'v'` overwrite (~300ms).
      handlers.get('moveend')?.();
      window.history.replaceState(null, '', '/mapa#v=14/-32.54/-62.54');
      vi.advanceTimersByTime(500);
      expect(window.location.hash).toBe('#v=10/-32.5/-62.5');
    } finally {
      vi.useRealTimers();
      window.history.replaceState(null, '', '/');
    }
  });
});
