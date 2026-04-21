/**
 * escuelasSyncHelpers.test.ts
 *
 * Tests for `syncEscuelasLayer` — the composer that mounts the escuelas-symbol
 * layer on the MapLibre map. Mirrors `canalesSyncHelpers.test.ts` for the
 * line-layer case but adapted to the symbol-layer + icon-registration flow.
 *
 * Contract (design §6.4):
 *   1. First mount: `registerEscuelaIcon(map)` (internally loadImage + addImage
 *      with pixelRatio 2) MUST complete BEFORE `addLayer` is called — the
 *      layer references `icon-image: 'escuela'` and MapLibre silently hides
 *      the symbol if the image is not yet registered.
 *   2. `addSource(SOURCE_IDS.ESCUELAS)` is called on first mount, never
 *      duplicated on re-runs.
 *   3. `addLayer` for `ESCUELAS_LAYER_ID='escuelas-symbol'` is called once
 *      with `type: 'symbol'`, `source: SOURCE_IDS.ESCUELAS`, and the layout
 *      + paint factories from `buildEscuelasSymbolLayout/Paint`.
 *   4. Toggle ON → `setLayoutProperty(layer, 'visibility', 'visible')`.
 *      Toggle OFF → `setLayoutProperty(layer, 'visibility', 'none')`.
 *      No `removeLayer` / `removeSource` on OFF (design §6.4 — visibility only).
 *   5. Idempotent re-run: no duplicate `addSource` / `addLayer` / `addImage`.
 *   6. Null collection tolerance: mounts source with empty FeatureCollection
 *      (same pattern as `syncSoilLayers` — see design §6.4 step 2 +
 *      apply-progress #2061 risk #2).
 */

import type { FeatureCollection, Point } from 'geojson';
import { describe, expect, it, vi } from 'vitest';

import type { EscuelaFeatureProperties } from '../../src/types/escuelas';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import {
  ESCUELA_ICON_NAME,
  ESCUELA_ICON_URL,
  ESCUELAS_LAYER_ID,
} from '../../src/components/map2d/escuelasLayers';
import { syncEscuelasLayer } from '../../src/components/map2d/mapLayerEffectHelpers';

// ---------------------------------------------------------------------------
// Map mock — minimal MapLibre surface area with call ordering capture
// ---------------------------------------------------------------------------

interface MockImage {
  width: number;
  height: number;
}

function createMapMock(options?: {
  images?: string[];
  layers?: string[];
  sources?: string[];
  /** When set, `loadImage` rejects with this error — tests the error path. */
  loadImageError?: Error;
}) {
  const images = new Set<string>(options?.images ?? []);
  const layers = new Set<string>(options?.layers ?? []);
  const sources = new Set<string>(options?.sources ?? []);
  const callOrder: string[] = [];

  const map = {
    callOrder,
    images,
    layers,
    sources,
    hasImage: vi.fn((name: string) => {
      callOrder.push(`hasImage:${name}`);
      return images.has(name);
    }),
    addImage: vi.fn((name: string) => {
      callOrder.push(`addImage:${name}`);
      images.add(name);
    }),
    // MapLibre GL JS 4.x: loadImage(url) returns Promise<{data: Image}>.
    loadImage: vi.fn((url: string) => {
      callOrder.push(`loadImage:${url}`);
      if (options?.loadImageError) {
        return Promise.reject(options.loadImageError);
      }
      return Promise.resolve({ data: { width: 64, height: 64 } as MockImage });
    }),
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
      callOrder.push(`addLayer:${layer.id}`);
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

function fc(features: Array<{ id: string; coordinates: [number, number]; props: EscuelaFeatureProperties }> = []):
  FeatureCollection<Point, EscuelaFeatureProperties> {
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
// First mount — loadImage → addImage → addSource → addLayer ordering
// ---------------------------------------------------------------------------

describe('syncEscuelasLayer · first mount', () => {
  it('adds source and layer with correct ids and symbol type', async () => {
    const map = createMapMock();

    await syncEscuelasLayer(
      map as never,
      fc([{ id: 'esc-1', coordinates: [-62.5, -32.5], props: SAMPLE_PROPS }]),
      true,
    );

    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.addSource).toHaveBeenCalledWith(
      SOURCE_IDS.ESCUELAS,
      expect.objectContaining({ type: 'geojson' }),
    );

    expect(map.addLayer).toHaveBeenCalledTimes(1);
    const addedLayer = map.addLayer.mock.calls[0]![0] as {
      id: string;
      type: string;
      source: string;
    };
    expect(addedLayer.id).toBe(ESCUELAS_LAYER_ID);
    expect(addedLayer.type).toBe('symbol');
    expect(addedLayer.source).toBe(SOURCE_IDS.ESCUELAS);
  });

  it('registers the icon BEFORE adding the layer (design §6.4 step 1)', async () => {
    const map = createMapMock();

    await syncEscuelasLayer(map as never, fc(), true);

    const loadImageIdx = map.callOrder.findIndex((c) => c === `loadImage:${ESCUELA_ICON_URL}`);
    const addImageIdx = map.callOrder.findIndex((c) => c === `addImage:${ESCUELA_ICON_NAME}`);
    const addLayerIdx = map.callOrder.findIndex((c) => c === `addLayer:${ESCUELAS_LAYER_ID}`);

    expect(loadImageIdx).toBeGreaterThanOrEqual(0);
    expect(addImageIdx).toBeGreaterThan(loadImageIdx);
    expect(addLayerIdx).toBeGreaterThan(addImageIdx);
  });

  it('toggle ON → setLayoutProperty(visibility, "visible")', async () => {
    const map = createMapMock();

    await syncEscuelasLayer(map as never, fc(), true);

    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      ESCUELAS_LAYER_ID,
      'visibility',
      'visible',
    );
  });

  it('toggle OFF → setLayoutProperty(visibility, "none") without removeLayer/removeSource', async () => {
    const map = createMapMock();

    await syncEscuelasLayer(map as never, fc(), false);

    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      ESCUELAS_LAYER_ID,
      'visibility',
      'none',
    );
    expect(map.removeLayer).not.toHaveBeenCalled();
    expect(map.removeSource).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Idempotency — re-runs must not duplicate source/layer/image
// ---------------------------------------------------------------------------

describe('syncEscuelasLayer · idempotency', () => {
  it('second call does not duplicate source/layer/image, only updates visibility', async () => {
    const map = createMapMock();

    await syncEscuelasLayer(map as never, fc(), true);
    map.addSource.mockClear();
    map.addLayer.mockClear();
    map.addImage.mockClear();
    map.setLayoutProperty.mockClear();

    await syncEscuelasLayer(map as never, fc(), false);

    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
    expect(map.addImage).not.toHaveBeenCalled();
    expect(map.setLayoutProperty).toHaveBeenCalledWith(
      ESCUELAS_LAYER_ID,
      'visibility',
      'none',
    );
  });
});

// ---------------------------------------------------------------------------
// Null tolerance — mirror `syncSoilLayers` behavior
// ---------------------------------------------------------------------------

describe('syncEscuelasLayer · null tolerance', () => {
  it('accepts null collection — renders empty source (matches syncSoilLayers pattern)', async () => {
    const map = createMapMock();

    await expect(
      syncEscuelasLayer(map as never, null, false),
    ).resolves.toBeUndefined();

    // Source is always mounted so visibility toggle has something to act on.
    expect(map.addSource).toHaveBeenCalledWith(
      SOURCE_IDS.ESCUELAS,
      expect.objectContaining({ type: 'geojson' }),
    );
  });
});
