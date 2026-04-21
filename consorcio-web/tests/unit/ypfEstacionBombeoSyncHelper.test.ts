/**
 * ypfEstacionBombeoSyncHelper.test.ts
 *
 * Tests for `syncYpfEstacionBombeoLayer` — the SYNCHRONOUS composer that
 * mounts the hardcoded YPF pump station circle. Unlike escuelas, this helper:
 *   - Has NO visibility flag. The layer is always mounted AND always visible.
 *   - Never tears down (no removeLayer / removeSource path).
 *   - Takes no data parameter — the GeoJSON is hardcoded in the module.
 *
 * The helper must be idempotent: calling it twice on the same map MUST NOT
 * duplicate the source or the layer.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  YPF_ESTACION_BOMBEO_LAYER_ID,
  YPF_ESTACION_BOMBEO_SOURCE_ID,
} from '../../src/components/map2d/ypfEstacionBombeoLayer';
import { syncYpfEstacionBombeoLayer } from '../../src/components/map2d/mapLayerEffectHelpers';

// ---------------------------------------------------------------------------
// Map mock — minimal MapLibre surface area
// ---------------------------------------------------------------------------

function createMapMock(options?: {
  layers?: string[];
  sources?: string[];
}) {
  const layers = new Set<string>(options?.layers ?? []);
  const sources = new Set<string>(options?.sources ?? []);

  const map = {
    layers,
    sources,
    getSource: vi.fn((id: string) =>
      sources.has(id) ? { id, setData: vi.fn() } : undefined,
    ),
    addSource: vi.fn((id: string) => {
      sources.add(id);
    }),
    getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
    addLayer: vi.fn((layer: { id: string; type: string; source: string }) => {
      layers.add(layer.id);
    }),
    setLayoutProperty: vi.fn(),
    removeLayer: vi.fn((id: string) => {
      layers.delete(id);
    }),
    removeSource: vi.fn((id: string) => {
      sources.delete(id);
    }),
  };
  return map;
}

// ---------------------------------------------------------------------------
// First mount — source + circle layer
// ---------------------------------------------------------------------------

describe('syncYpfEstacionBombeoLayer · first mount', () => {
  it('adds the source with the canonical id', () => {
    const map = createMapMock();

    syncYpfEstacionBombeoLayer(map as never);

    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.addSource).toHaveBeenCalledWith(
      YPF_ESTACION_BOMBEO_SOURCE_ID,
      expect.objectContaining({ type: 'geojson' }),
    );
  });

  it('adds the circle layer with the canonical id, type, and source binding', () => {
    const map = createMapMock();

    syncYpfEstacionBombeoLayer(map as never);

    expect(map.addLayer).toHaveBeenCalledTimes(1);
    const layerSpec = map.addLayer.mock.calls[0]![0] as {
      id: string;
      type: string;
      source: string;
    };
    expect(layerSpec.id).toBe(YPF_ESTACION_BOMBEO_LAYER_ID);
    expect(layerSpec.type).toBe('circle');
    expect(layerSpec.source).toBe(YPF_ESTACION_BOMBEO_SOURCE_ID);
  });

  it('does NOT hide the layer — no setLayoutProperty(visibility, none) path', () => {
    const map = createMapMock();

    syncYpfEstacionBombeoLayer(map as never);

    // The layer is always-on; the helper MUST NOT set any "none" visibility.
    const noneCalls = map.setLayoutProperty.mock.calls.filter(
      (call) => call[2] === 'none',
    );
    expect(noneCalls).toEqual([]);
  });

  it('does NOT tear down (no removeLayer / removeSource path)', () => {
    const map = createMapMock();

    syncYpfEstacionBombeoLayer(map as never);

    expect(map.removeLayer).not.toHaveBeenCalled();
    expect(map.removeSource).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Idempotency — re-runs must not duplicate source/layer
// ---------------------------------------------------------------------------

describe('syncYpfEstacionBombeoLayer · idempotency', () => {
  it('second call does not duplicate source or layer', () => {
    const map = createMapMock();

    syncYpfEstacionBombeoLayer(map as never);
    map.addSource.mockClear();
    map.addLayer.mockClear();

    syncYpfEstacionBombeoLayer(map as never);

    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Sync signature — no Promise returned
// ---------------------------------------------------------------------------

describe('syncYpfEstacionBombeoLayer · sync signature', () => {
  it('returns undefined synchronously (not a Promise)', () => {
    const map = createMapMock();
    const result = syncYpfEstacionBombeoLayer(map as never);
    expect(result).toBeUndefined();
    expect(
      result !== null &&
        typeof (result as unknown as { then?: unknown })?.then === 'function',
    ).toBe(false);
  });
});
