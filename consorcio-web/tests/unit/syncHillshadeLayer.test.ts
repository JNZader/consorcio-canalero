import { describe, expect, it, vi } from 'vitest';

import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { syncHillshadeLayer } from '../../src/components/map2d/mapRasterOverlayHelpers';

describe('syncHillshadeLayer', () => {
  it('does nothing when off and never mounted', () => {
    const map = {
      getSource: vi.fn(() => undefined),
      getLayer: vi.fn(() => undefined),
      addSource: vi.fn(),
      addLayer: vi.fn(),
    };
    syncHillshadeLayer(map as never, false, 'https://example/tiles/{z}/{x}/{y}.png');
    expect(map.addSource).not.toHaveBeenCalled();
  });

  it('adds raster-dem hillshade when turned on', () => {
    const map = {
      getSource: vi.fn(() => undefined),
      getLayer: vi.fn((id: string) => (id === 'vector-layers-start' ? {} : undefined)),
      addSource: vi.fn(),
      addLayer: vi.fn(),
      setLayoutProperty: vi.fn(),
    };
    syncHillshadeLayer(map as never, true, 'https://example/dem/{z}/{x}/{y}.png?encoding=terrain-rgb');
    expect(map.addSource).toHaveBeenCalledWith(
      SOURCE_IDS.HILLSHADE,
      expect.objectContaining({ type: 'raster-dem', encoding: 'mapbox' }),
    );
    expect(map.addLayer).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'hillshade', source: SOURCE_IDS.HILLSHADE }),
      'vector-layers-start',
    );
  });
});
