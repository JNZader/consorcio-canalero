import { describe, expect, it } from 'vitest';

import { isRasterSourceId } from '../../src/components/map2d/useRasterTileLoading';

describe('isRasterSourceId (UX-11)', () => {
  it('recognizes DEM / overlay sources', () => {
    expect(isRasterSourceId('dem-overlay')).toBe(true);
    expect(isRasterSourceId('terrain-texture')).toBe(true);
    expect(isRasterSourceId('gee-flood')).toBe(true);
    expect(isRasterSourceId('roads')).toBe(false);
    expect(isRasterSourceId(undefined)).toBe(false);
  });
});
