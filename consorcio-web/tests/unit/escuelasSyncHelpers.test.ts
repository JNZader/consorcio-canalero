/**
 * escuelasSyncHelpers.test.ts
 *
 * Tests for `syncEscuelasLayer` — the SYNCHRONOUS composer that mounts the
 * native MapLibre circle layer + companion label layer.
 *
 * This file was rewritten after the symbol+icon approach was abandoned (see
 * `escuelasLayers.ts` header for history). The helper now:
 *   1. Ensures one geojson source (`SOURCE_IDS.ESCUELAS`).
 *   2. Adds a `circle` layer (`escuelas-symbol`) bound to that source.
 *   3. Adds a `symbol` layer (`escuelas-label`) bound to the same source.
 *   4. Flips the visibility of BOTH layers together on the master toggle.
 *
 * No Promise. No `loadImage`. No `addImage`. Null-tolerant (empty
 * FeatureCollection when `collection` is null).
 */

import type { FeatureCollection, Point } from 'geojson';
import { describe, expect, it, vi } from 'vitest';

import type { EscuelaFeatureProperties } from '../../src/types/escuelas';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import {
  ESCUELAS_LABEL_LAYER_ID,
  ESCUELAS_LAYER_ID,
} from '../../src/components/map2d/escuelasLayers';
import { syncEscuelasLayer } from '../../src/components/map2d/mapLayerEffectHelpers';

// ---------------------------------------------------------------------------
// Map mock — minimal MapLibre surface area with call-ordering capture
// ---------------------------------------------------------------------------

function createMapMock(options?: {
  layers?: string[];
  sources?: string[];
}) {
  const layers = new Set<string>(options?.layers ?? []);
  const sources = new Set<string>(options?.sources ?? []);
  const callOrder: string[] = [];

  const map = {
    callOrder,
    layers,
    sources,
    getSource: vi.fn((id: string) => {
      callOrder.push(`getSource:${id}`);
      return sources.has(id) ? { id, setData: vi.fn() } : undefined;
    }),
    addSource: vi.fn((id: string) => {
      callOrder.push(`addSource:${id}`);
      sources.add(id);
    }),
    getLayer: vi.fn((id: string) => {
      callOrder.push(`getLayer:${id}`);
      return layers.has(id) ? { id } : undefined;
    }),
    addLayer: vi.fn((layer: { id: string; type: string; source: string }) => {
      callOrder.push(`addLayer:${layer.id}:${layer.type}`);
      layers.add(layer.id);
    }),
    setLayoutProperty: vi.fn((layerId: string, key: string, value: unknown) => {
      callOrder.push(`setLayoutProperty:${layerId}:${key}=${String(value)}`);
    }),
    removeLayer: vi.fn((id: string) => {
      callOrder.push(`removeLayer:${id}`);
      layers.delete(id);
    }),
    removeSource: vi.fn((id: string) => {
      callOrder.push(`removeSource:${id}`);
      sources.delete(id);
    }),
  };
  return map;
}

function fc(
  features: Array<{
    id: string;
    coordinates: [number, number];
    props: EscuelaFeatureProperties;
  }> = [],
): FeatureCollection<Point, EscuelaFeatureProperties> {
  return {
    type: 'FeatureCollection',
    features: features.map((f) => ({
      type: 'Feature',
      id: f.id,
      geometry: { type: 'Point', coordinates: f.coordinates },
      properties: f.props,
    })),
  };
}

const SAMPLE_PROPS: EscuelaFeatureProperties = {
  nombre: 'Esc. Test',
  localidad: 'Test Locality',
  ambito: 'Rural Aglomerado',
  nivel: 'Inicial',
};

// ---------------------------------------------------------------------------
// First mount — source + circle + label ordering
// ---------------------------------------------------------------------------

describe('syncEscuelasLayer · first mount', () => {
  it('adds source and BOTH circle + label layers with correct ids', () => {
    const map = createMapMock();

    syncEscuelasLayer(
      map as never,
      fc([{ id: 'esc-1', coordinates: [-62.5, -32.5], props: SAMPLE_PROPS }]),
      true,
    );

    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.addSource).toHaveBeenCalledWith(
      SOURCE_IDS.ESCUELAS,
      expect.objectContaining({ type: 'geojson' }),
    );

    expect(map.addLayer).toHaveBeenCalledTimes(2);

    const firstLayer = map.addLayer.mock.calls[0]![0] as {
      id: string;
      type: string;
      source: string;
    };
    expect(firstLayer.id).toBe(ESCUELAS_LAYER_ID);
    expect(firstLayer.type).toBe('circle');
    expect(firstLayer.source).toBe(SOURCE_IDS.ESCUELAS);

    const secondLayer = map.addLayer.mock.calls[1]![0] as {
      id: string;
      type: string;
      source: string;
    };
    expect(secondLayer.id).toBe(ESCUELAS_LABEL_LAYER_ID);
    expect(secondLayer.type).toBe('symbol');
    expect(secondLayer.source).toBe(SOURCE_IDS.ESCUELAS);
  });

  it('mounts the circle layer BEFORE the label layer so label draws on top', () => {
    const map = createMapMock();

    syncEscuelasLayer(map as never, fc(), true);

    const circleIdx = map.callOrder.findIndex(
      (c) => c === `addLayer:${ESCUELAS_LAYER_ID}:circle`,
    );
    const labelIdx = map.callOrder.findIndex(
      (c) => c === `addLayer:${ESCUELAS_LABEL_LAYER_ID}:symbol`,
    );

    expect(circleIdx).toBeGreaterThanOrEqual(0);
    expect(labelIdx).toBeGreaterThan(circleIdx);
  });

  it('does NOT touch any image / icon APIs (native circle layer — no asset pipeline)', () => {
    const map = createMapMock() as Record<string, unknown> & ReturnType<typeof createMapMock>;
    // Sanity: the mock exposes no image-related spies. If anyone adds back
    // loadImage/addImage/hasImage, this test will catch it because the helper
    // would fail to locate those methods on the mock.
    syncEscuelasLayer(map as never, fc(), true);

    expect((map as Record<string, unknown>).loadImage).toBeUndefined();
    expect((map as Record<string, unknown>).addImage).toBeUndefined();
    expect((map as Record<string, unknown>).hasImage).toBeUndefined();
  });

  it('toggle ON → setLayoutProperty(visibility, "visible") on BOTH layers', () => {
    const map = createMapMock();

    syncEscuelasLayer(map as never, fc(), true);

    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      ESCUELAS_LAYER_ID,
      'visibility',
      'visible',
    );
    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      ESCUELAS_LABEL_LAYER_ID,
      'visibility',
      'visible',
    );
  });

  it('toggle OFF → setLayoutProperty(visibility, "none") without removeLayer/removeSource', () => {
    const map = createMapMock();

    syncEscuelasLayer(map as never, fc(), false);

    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      ESCUELAS_LAYER_ID,
      'visibility',
      'none',
    );
    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      ESCUELAS_LABEL_LAYER_ID,
      'visibility',
      'none',
    );
    expect(map.removeLayer).not.toHaveBeenCalled();
    expect(map.removeSource).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Idempotency — re-runs must not duplicate source/layer
// ---------------------------------------------------------------------------

describe('syncEscuelasLayer · idempotency', () => {
  it('second call does not duplicate source/layers, only updates visibility', () => {
    const map = createMapMock();

    syncEscuelasLayer(map as never, fc(), true);
    map.addSource.mockClear();
    map.addLayer.mockClear();
    map.setLayoutProperty.mockClear();

    syncEscuelasLayer(map as never, fc(), false);

    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      ESCUELAS_LAYER_ID,
      'visibility',
      'none',
    );
    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      ESCUELAS_LABEL_LAYER_ID,
      'visibility',
      'none',
    );
  });
});

// ---------------------------------------------------------------------------
// Null tolerance — mirror `syncSoilLayers` behavior
// ---------------------------------------------------------------------------

describe('syncEscuelasLayer · null tolerance', () => {
  it('accepts null collection — renders empty source (matches syncSoilLayers pattern)', () => {
    const map = createMapMock();

    expect(() => syncEscuelasLayer(map as never, null, false)).not.toThrow();

    // Source is always mounted so visibility toggle has something to act on.
    expect(map.addSource).toHaveBeenCalledWith(
      SOURCE_IDS.ESCUELAS,
      expect.objectContaining({ type: 'geojson' }),
    );
  });
});

// ---------------------------------------------------------------------------
// Sync signature — no Promise returned
// ---------------------------------------------------------------------------

describe('syncEscuelasLayer · sync signature', () => {
  it('returns undefined synchronously (not a Promise)', () => {
    const map = createMapMock();
    const result = syncEscuelasLayer(map as never, fc(), true);
    expect(result).toBeUndefined();
    // Defensive: the helper must NOT return a thenable — callers rely on it
    // to run synchronously inside React effects.
    expect(
      result !== null &&
        typeof (result as unknown as { then?: unknown })?.then === 'function',
    ).toBe(false);
  });
});
