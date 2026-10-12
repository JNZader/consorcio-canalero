import { describe, expect, it } from 'vitest';

import { coordsFromLngLat, formatMapCursorCoords } from '../../src/components/map2d/mapCursorCoords';

describe('mapCursorCoords UX-18', () => {
  it('formats southern-west pampa coords', () => {
    expect(formatMapCursorCoords({ lat: -32.545, lng: -62.54 })).toBe('32.54500° S  62.54000° O');
    expect(formatMapCursorCoords(null)).toBe('—');
  });

  it('rejects junk lng/lat', () => {
    expect(coordsFromLngLat({ lng: -62.5, lat: -32.5 })).toEqual({ lng: -62.5, lat: -32.5 });
    expect(coordsFromLngLat({ lng: 200, lat: 0 })).toBeNull();
    expect(coordsFromLngLat({ lng: 0, lat: 91 })).toBeNull();
    expect(coordsFromLngLat(undefined)).toBeNull();
  });
});
