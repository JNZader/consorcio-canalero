import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const HELPERS = readFileSync(
  resolve(process.cwd(), 'src/components/map2d/mapRasterOverlayHelpers.ts'),
  'utf-8',
);

describe('DEM overlay opacity (CART-07)', () => {
  it('starts below 1 so labels stay readable', () => {
    expect(HELPERS).toContain("'raster-opacity': 0.7");
    expect(HELPERS).not.toContain("'raster-opacity': 0.85");
  });
});
