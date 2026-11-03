import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mapConstructorCalls, addSourceMock, addLayerMock, fitBoundsMock } = vi.hoisted(() => ({
  mapConstructorCalls: [] as Array<Record<string, unknown>>,
  addSourceMock: vi.fn(),
  addLayerMock: vi.fn(),
  fitBoundsMock: vi.fn(),
}));

vi.mock('maplibre-gl', () => {
  class MockMap {
    constructor(options: Record<string, unknown>) {
      mapConstructorCalls.push(options);
    }
    on(event: string, cb: () => void) {
      if (event === 'load') cb();
      return this;
    }
    getSource() {
      return undefined;
    }
    addSource(...args: unknown[]) {
      addSourceMock(...args);
    }
    addLayer(...args: unknown[]) {
      addLayerMock(...args);
    }
    fitBounds(...args: unknown[]) {
      fitBoundsMock(...args);
    }
    remove() {}
  }

  return {
    Map: MockMap,
    setWorkerUrl: vi.fn(),
  };
});

vi.mock('../../src/lib/maplibreLoader', () => ({
  bootMapLibreWorker: vi.fn().mockResolvedValue(undefined),
}));

import {
  ESRI_WORLD_IMAGERY_TILES,
  SugerenciaGeometryMap,
} from '../../src/components/admin/sugerencias/components/SugerenciaGeometryMap';

describe('SugerenciaGeometryMap (ADM-05)', () => {
  beforeEach(() => {
    mapConstructorCalls.length = 0;
    addSourceMock.mockClear();
    addLayerMock.mockClear();
    fitBoundsMock.mockClear();
  });

  it('uses Esri World Imagery satellite tiles matching the citizen drawing basemap', async () => {
    render(
      <SugerenciaGeometryMap
        canales={[]}
        geometry={{
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: {},
              geometry: {
                type: 'LineString',
                coordinates: [
                  [-62.68, -32.62],
                  [-62.69, -32.63],
                ],
              },
            },
          ],
        }}
      />
    );

    await vi.waitFor(() => {
      expect(mapConstructorCalls.length).toBe(1);
    });

    const style = mapConstructorCalls[0]?.style as {
      sources: Record<string, { tiles: string[] }>;
    };
    expect(style.sources.basemap?.tiles).toEqual([ESRI_WORLD_IMAGERY_TILES]);
    expect(addLayerMock).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'sugerencia-geom-line' })
    );
    expect(addLayerMock).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'sugerencia-geom-point' })
    );
    expect(fitBoundsMock).toHaveBeenCalled();
  });
});
