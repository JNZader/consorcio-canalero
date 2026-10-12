import { describe, expect, it } from 'vitest';

import { LAYER_LEGEND_CONFIG } from '../../src/config/rasterLegend';

describe('slope legend (CART-01)', () => {
  it('uses YlOrBr instead of RdYlGn greens', () => {
    const slope = LAYER_LEGEND_CONFIG.slope;
    expect(slope.colorStops[0]).toBe('#ffffd4');
    expect(slope.colorStops.at(-1)).toBe('#993404');
    expect(slope.ranges?.some((range) => range.color === '#1a9850')).toBe(false);
  });
});
