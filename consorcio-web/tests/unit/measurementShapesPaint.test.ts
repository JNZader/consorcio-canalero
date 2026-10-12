import { describe, expect, it, vi } from 'vitest';

import { scheduleMeasurementShapePaint } from '../../src/components/map2d/measurement/MeasurementShapes';

describe('scheduleMeasurementShapePaint', () => {
  it('paints immediately when the style is loaded', () => {
    const paint = vi.fn();
    scheduleMeasurementShapePaint(
      { isStyleLoaded: () => true, loaded: () => false, once: vi.fn() },
      paint,
    );
    expect(paint).toHaveBeenCalledOnce();
  });

  it('waits for idle when tiles are still in flight (load will not fire again)', () => {
    const once = vi.fn();
    const paint = vi.fn();
    scheduleMeasurementShapePaint(
      { isStyleLoaded: () => false, loaded: () => false, once },
      paint,
    );
    expect(paint).not.toHaveBeenCalled();
    expect(once).toHaveBeenCalledWith('idle', paint);
  });
});
