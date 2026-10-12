import { describe, expect, it, vi } from 'vitest';

import {
  LINE_CASING_COLOR_DARK,
  LINE_CASING_COLOR_LIGHT,
  LINE_CASING_EXTRA_WIDTH,
  LINE_CASING_OPACITY,
  buildLineCasingLayer,
  casingLayerId,
  ensureLineCasing,
  parseDashArray,
  shouldAddCasing,
} from '../../src/components/map2d/lineCasing';

describe('lineCasing CART-05', () => {
  it('names the halo after the thematic line', () => {
    expect(casingLayerId('rio_tercero-line')).toBe('rio_tercero-line-casing');
  });

  it('parses dash arrays and rejects junk', () => {
    expect(parseDashArray('4,2')).toEqual([4, 2]);
    expect(parseDashArray(' 1 , 3 ')).toEqual([1, 3]);
    expect(parseDashArray('4')).toBeUndefined();
    expect(parseDashArray(undefined)).toBeUndefined();
    expect(parseDashArray('x,y')).toBeUndefined();
  });

  it('builds a wider light halo for waterways', () => {
    const layer = buildLineCasingLayer({
      lineLayerId: 'rio_tercero-line',
      source: 'rio_tercero',
      width: 3,
    });
    expect(layer.id).toBe('rio_tercero-line-casing');
    expect(layer.type).toBe('line');
    expect(layer.source).toBe('rio_tercero');
    expect(layer.paint?.['line-color']).toBe(LINE_CASING_COLOR_LIGHT);
    expect(layer.paint?.['line-width']).toBe(3 + LINE_CASING_EXTRA_WIDTH);
    expect(layer.paint?.['line-opacity']).toBe(LINE_CASING_OPACITY);
    expect(layer.paint?.['line-dasharray']).toBeUndefined();
  });

  it('copies dashes and uses a dark halo for canales', () => {
    const layer = buildLineCasingLayer({
      lineLayerId: 'canales_propuestos-line',
      source: 'canales_propuestos',
      width: 2.5,
      dashArray: '4,2',
      darkHalo: true,
    });
    expect(layer.paint?.['line-color']).toBe(LINE_CASING_COLOR_DARK);
    expect(layer.paint?.['line-dasharray']).toEqual([4, 2]);
    expect(layer.layout?.['line-cap']).toBe('round');
  });

  it('ensureLineCasing inserts below the color line once', () => {
    const layers = new Set(['rio_tercero-line']);
    const map = {
      getLayer: (id: string) => (layers.has(id) ? {} : undefined),
      addLayer: vi.fn((layer: { id: string }, before?: string) => {
        layers.add(layer.id);
        return before;
      }),
    };
    ensureLineCasing(map, { lineLayerId: 'rio_tercero-line', source: 'rio_tercero', width: 3 });
    expect(map.addLayer).toHaveBeenCalledTimes(1);
    expect(map.addLayer.mock.calls[0][1]).toBe('rio_tercero-line');
    ensureLineCasing(map, { lineLayerId: 'rio_tercero-line', source: 'rio_tercero', width: 3 });
    expect(map.addLayer).toHaveBeenCalledTimes(1);
  });

  it('does not add casing before the color line exists', () => {
    const map = {
      getLayer: () => undefined,
      addLayer: vi.fn(),
    };
    ensureLineCasing(map, { lineLayerId: 'missing-line', source: 'x', width: 1 });
    expect(map.addLayer).not.toHaveBeenCalled();
    expect(shouldAddCasing({ getLayer: () => undefined }, 'missing-line')).toBe(true);
  });
});
