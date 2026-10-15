/**
 * The selection highlight must end on top of every other line pass.
 *
 * Casing first, then the orange stroke: that order is what keeps the stroke
 * visible above its own casing. Skipping unmounted layers keeps this safe to
 * call from any sync pass, and a `moveLayer` race must not throw.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  hoistSelectedLineHighlight,
  SELECTED_LINE_CASING,
  SELECTED_LINE_LAYER,
} from '../../src/components/map2d/selectedLineHighlightLayers';

function mapWith(layers: readonly string[]) {
  const present = new Set(layers);
  return {
    getLayer: (id: string) => (present.has(id) ? { id } : undefined),
    moveLayer: vi.fn(),
  };
}

describe('hoistSelectedLineHighlight', () => {
  it('raises the casing before the line, so the stroke ends on top', () => {
    const map = mapWith([SELECTED_LINE_CASING, SELECTED_LINE_LAYER]);

    hoistSelectedLineHighlight(map as never);

    expect(map.moveLayer.mock.calls.map((call) => call[0])).toEqual([
      SELECTED_LINE_CASING,
      SELECTED_LINE_LAYER,
    ]);
  });

  it('skips layers that are not mounted', () => {
    const map = mapWith([SELECTED_LINE_LAYER]);

    hoistSelectedLineHighlight(map as never);

    expect(map.moveLayer).toHaveBeenCalledTimes(1);
    expect(map.moveLayer).toHaveBeenCalledWith(SELECTED_LINE_LAYER);
  });

  it('does nothing when the highlight is not mounted at all', () => {
    const map = mapWith([]);

    hoistSelectedLineHighlight(map as never);

    expect(map.moveLayer).not.toHaveBeenCalled();
  });

  it('survives a moveLayer race instead of breaking the sync pass', () => {
    const map = mapWith([SELECTED_LINE_CASING, SELECTED_LINE_LAYER]);
    map.moveLayer.mockImplementation(() => {
      throw new Error('style busy');
    });

    expect(() => hoistSelectedLineHighlight(map as never)).not.toThrow();
  });
});
