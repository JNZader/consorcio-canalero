import { describe, expect, it, vi } from 'vitest';

import {
  applyMapLineWidth,
  clampLineWidthScale,
  MAP_LINE_WIDTH_LAYERS,
} from '../../src/components/map2d/mapLineWidth';

describe('clampLineWidthScale', () => {
  it('keeps 1 and clamps the slider range', () => {
    expect(clampLineWidthScale(1)).toBe(1);
    expect(clampLineWidthScale(0.1)).toBe(0.75);
    expect(clampLineWidthScale(9)).toBe(2.5);
  });
});

describe('applyMapLineWidth', () => {
  it('no-ops on a dummy map', () => {
    expect(() => applyMapLineWidth({} as never, 2)).not.toThrow();
  });

  it('writes scaled width on mounted road line', () => {
    const setPaintProperty = vi.fn();
    const roads = MAP_LINE_WIDTH_LAYERS.find((layer) => layer.id === 'map2d-roads-line');
    applyMapLineWidth(
      {
        getLayer: (id) => (id === 'map2d-roads-line' ? {} : null),
        setPaintProperty,
      },
      2
    );
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-roads-line', 'line-width', (roads?.base ?? 0) * 2);
  });
});
