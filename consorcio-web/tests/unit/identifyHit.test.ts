import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  IDENTIFY_HIT_RADIUS_COARSE_PX,
  IDENTIFY_HIT_RADIUS_FINE_PX,
  identifyHitBbox,
  identifyHitRadiusPx,
  pointerIsCoarse,
} from '../../src/components/map2d/identifyHit';

describe('identifyHit', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('uses ±6 px on fine pointers and ±10 px on coarse', () => {
    expect(identifyHitRadiusPx(false)).toBe(IDENTIFY_HIT_RADIUS_FINE_PX);
    expect(identifyHitRadiusPx(true)).toBe(IDENTIFY_HIT_RADIUS_COARSE_PX);
    expect(identifyHitBbox(100, 50, 10)).toEqual([
      [90, 40],
      [110, 60],
    ]);
  });

  it('reads matchMedia(pointer: coarse)', () => {
    vi.stubGlobal('window', {
      matchMedia: (query: string) => ({ matches: query.includes('coarse') }),
    });
    expect(pointerIsCoarse()).toBe(true);
  });
});
