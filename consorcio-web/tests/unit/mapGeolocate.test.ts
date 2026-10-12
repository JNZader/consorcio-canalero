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
});
