import { describe, expect, it, vi } from 'vitest';

import {
  applyMapLabelSize,
  clampLabelSizeScale,
  scaleTextSizeExpression,
} from '../../src/components/map2d/mapLabelSize';
import { ROAD_LABEL_TEXT_SIZE } from '../../src/components/map2d/roadLabelLayer';

describe('clampLabelSizeScale', () => {
  it('keeps 1 and clamps the slider range', () => {
    expect(clampLabelSizeScale(1)).toBe(1);
    expect(clampLabelSizeScale(0.1)).toBe(0.75);
    expect(clampLabelSizeScale(9)).toBe(2.5);
    expect(clampLabelSizeScale(Number.NaN)).toBe(1);
  });
});

describe('scaleTextSizeExpression', () => {
  it('multiplies interpolate size stops at 150%', () => {
    expect(scaleTextSizeExpression(ROAD_LABEL_TEXT_SIZE, 1.5)).toEqual([
      'interpolate',
      ['linear'],
      ['zoom'],
      11,
      21,
      14,
      27,
    ]);
  });

  it('leaves zoom stops untouched', () => {
    const scaled = scaleTextSizeExpression(ROAD_LABEL_TEXT_SIZE, 2);
    expect(scaled[3]).toBe(11);
    expect(scaled[5]).toBe(14);
  });
});

describe('applyMapLabelSize', () => {
  it('no-ops when the map mock has no layout API', () => {
    expect(() => applyMapLabelSize({} as never, 1.5)).not.toThrow();
  });

  it('sets layout text-size on mounted label layers', () => {
    const setLayoutProperty = vi.fn();
    applyMapLabelSize(
      {
        getLayer: (id) => (id === 'map2d-roads-label' ? {} : null),
        setLayoutProperty,
      },
      2
    );
    expect(setLayoutProperty).toHaveBeenCalledWith(
      'map2d-roads-label',
      'text-size',
      scaleTextSizeExpression(ROAD_LABEL_TEXT_SIZE, 2)
    );
  });
});
