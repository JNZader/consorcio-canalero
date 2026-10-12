import { describe, expect, it } from 'vitest';

import { MAP_BOUNDS, MAP_CENTER, MAP_HOME_FIT_PADDING, MAP_MAX_BOUNDS, MAP_QUICK_PLACES } from '../../src/constants';

describe('MAP_BOUNDS (UX-21)', () => {
  it('matches the zona_cc_ampliada envelope, not the old 15 km-SW box', () => {
    expect(MAP_BOUNDS.west).toBeCloseTo(-62.79);
    expect(MAP_BOUNDS.east).toBeCloseTo(-62.29);
    expect(MAP_BOUNDS.south).toBeCloseTo(-32.7);
    expect(MAP_BOUNDS.north).toBeCloseTo(-32.39);
    expect(MAP_BOUNDS.west).toBeLessThan(MAP_BOUNDS.east);
    expect(MAP_BOUNDS.south).toBeLessThan(MAP_BOUNDS.north);
  });

  it('centers inside that envelope', () => {
    const [lat, lng] = MAP_CENTER;
    expect(lat).toBeGreaterThan(MAP_BOUNDS.south);
    expect(lat).toBeLessThan(MAP_BOUNDS.north);
    expect(lng).toBeGreaterThan(MAP_BOUNDS.west);
    expect(lng).toBeLessThan(MAP_BOUNDS.east);
  });

  it('pads home fitBounds more on the right for the control column', () => {
    expect(MAP_HOME_FIT_PADDING).toEqual({ top: 48, bottom: 48, left: 48, right: 72 });
  });

  it('keeps maxBounds as a padded envelope around MAP_BOUNDS', () => {
    expect(MAP_MAX_BOUNDS[0][0]).toBeLessThan(MAP_BOUNDS.west);
    expect(MAP_MAX_BOUNDS[1][0]).toBeGreaterThan(MAP_BOUNDS.east);
  });
});

describe('MAP_QUICK_PLACES (UX-22)', () => {
  it('lists more than the Bell Ville fixture and stays inside the zona envelope', () => {
    expect(MAP_QUICK_PLACES.length).toBeGreaterThanOrEqual(3);
    expect(MAP_QUICK_PLACES.map((place) => place.id)).toEqual([
      'bell-ville',
      'san-marcos-sud',
      'monte-lena',
    ]);
    for (const place of MAP_QUICK_PLACES) {
      const [lng, lat] = place.center;
      expect(lng).toBeGreaterThanOrEqual(MAP_BOUNDS.west);
      expect(lng).toBeLessThanOrEqual(MAP_BOUNDS.east);
      expect(lat).toBeGreaterThanOrEqual(MAP_BOUNDS.south);
      expect(lat).toBeLessThanOrEqual(MAP_BOUNDS.north);
    }
  });
});
