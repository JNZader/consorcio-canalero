import { describe, expect, it } from 'vitest';

import { buildTileUrl } from '../../src/hooks/useGeoLayers';

describe('buildTileUrl hazard options', () => {
  it('serializes rescale bounds alongside existing tile options', () => {
    const url = buildTileUrl('precip-annual', {
      hideRanges: [1, 3],
      rescaleMin: 0,
      rescaleMax: 1800,
    });

    expect(url).toContain('hide_ranges=1%2C3');
    expect(url).toContain('rescale_min=0');
    expect(url).toContain('rescale_max=1800');
  });

  it('keeps a zero rescale bound instead of treating it as absent', () => {
    expect(buildTileUrl('precip-month', { rescaleMin: 0 })).toContain('rescale_min=0');
  });
});
