import { describe, expect, it } from 'vitest';

import { buildPuntosInteresLabelLayer } from '../../src/components/map2d/puntosInteresLayers';
import { buildRoadFlowConduccionArrowLayout } from '../../src/components/map2d/roadFlowLayers';

describe('label collision (CART-04)', () => {
  it('does not force POI text on top of other symbols', () => {
    const layer = buildPuntosInteresLabelLayer('poi-label', 'poi-src');
    expect(layer.minzoom).toBe(12);
    expect(layer.layout?.['text-allow-overlap']).toBe(false);
    expect(layer.layout?.['text-ignore-placement']).toBe(false);
  });

  it('lets MapLibre drop road-flow arrows when they collide', () => {
    const layout = buildRoadFlowConduccionArrowLayout();
    expect(layout['icon-allow-overlap']).toBe(false);
    expect(layout['icon-ignore-placement']).toBe(false);
  });
});
