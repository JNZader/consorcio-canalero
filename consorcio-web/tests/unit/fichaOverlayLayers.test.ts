/**
 * fichaOverlayLayers.test.ts
 *
 * The on-map ficha overlay sync helper (A(b) slice 1, soils). Confirms it:
 *   - adds a geojson source + fill + line layers when visible with data;
 *   - removes source + both layers when hidden or when data is absent;
 *   - is idempotent (re-sync updates the source, does not duplicate layers);
 *   - colors by `properties.clase` reusing the panel's SOIL_CAPABILITY_COLORS,
 *     with the shared neutral fallback for an unclassified clase.
 */

import type maplibregl from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import { describe, expect, it, vi } from 'vitest';

import {
  FICHA_OVERLAY_FILL_LAYER,
  FICHA_OVERLAY_LINE_LAYER,
  FICHA_OVERLAY_SOURCE,
  SOIL_OVERLAY_FALLBACK_COLOR,
  buildSoilOverlayColorExpression,
  syncFichaOverlayLayers,
} from '../../src/components/map2d/fichaOverlayLayers';
import { SOIL_CAPABILITY_COLORS } from '../../src/hooks/useSoilMap';

interface FakeLayer {
  id: string;
  type: string;
  source?: string;
  paint?: Record<string, unknown>;
}

interface FakeMap {
  map: maplibregl.Map;
  sources: Map<string, { data: unknown; setData: ReturnType<typeof vi.fn> }>;
  layers: Map<string, FakeLayer>;
}

function createFakeMap(): FakeMap {
  const sources = new Map<string, { data: unknown; setData: ReturnType<typeof vi.fn> }>();
  const layers = new Map<string, FakeLayer>();

  const map = {
    getSource: (id: string) => sources.get(id),
    addSource: (id: string, source: { data: unknown }) => {
      sources.set(id, {
        data: source.data,
        setData: vi.fn((next: unknown) => {
          const existing = sources.get(id);
          if (existing) existing.data = next;
        }),
      });
    },
    removeSource: (id: string) => {
      // Mirror MapLibre's runtime guard: a source cannot be removed while any
      // layer still references it. This makes the remove-layers-BEFORE-source
      // ordering in removeFichaOverlay a verified invariant, not an assumption.
      for (const layer of layers.values()) {
        if (layer.source === id) {
          throw new Error(
            `Source "${id}" cannot be removed while layer "${layer.id}" is using it.`
          );
        }
      }
      sources.delete(id);
    },
    getLayer: (id: string) => layers.get(id),
    addLayer: (layer: FakeLayer) => {
      layers.set(layer.id, layer);
    },
    removeLayer: (id: string) => {
      layers.delete(id);
    },
  } as unknown as maplibregl.Map;

  return { map, sources, layers };
}

const FC: FeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { clase: 'IV' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [-62, -32],
            [-61.99, -32],
            [-61.99, -31.99],
            [-62, -31.99],
            [-62, -32],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { clase: 'sin clasificar' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [-61.99, -32],
            [-61.98, -32],
            [-61.98, -31.99],
            [-61.99, -31.99],
            [-61.99, -32],
          ],
        ],
      },
    },
  ],
};

describe('syncFichaOverlayLayers · visible with data', () => {
  it('adds the geojson source + fill + line layers', () => {
    const { map, sources, layers } = createFakeMap();

    syncFichaOverlayLayers(map, {
      featureCollection: FC,
      dataset: 'suelos',
      visible: true,
    });

    expect(sources.has(FICHA_OVERLAY_SOURCE)).toBe(true);
    expect(sources.get(FICHA_OVERLAY_SOURCE)?.data).toEqual(FC);
    expect(layers.has(FICHA_OVERLAY_FILL_LAYER)).toBe(true);
    expect(layers.has(FICHA_OVERLAY_LINE_LAYER)).toBe(true);
    expect(layers.get(FICHA_OVERLAY_FILL_LAYER)?.type).toBe('fill');
    expect(layers.get(FICHA_OVERLAY_LINE_LAYER)?.type).toBe('line');
  });

  it('colors the fill by `properties.clase` with the shared soil palette', () => {
    const { map, layers } = createFakeMap();

    syncFichaOverlayLayers(map, {
      featureCollection: FC,
      dataset: 'suelos',
      visible: true,
    });

    const fill = layers.get(FICHA_OVERLAY_FILL_LAYER);
    const color = fill?.paint?.['fill-color'] as unknown as unknown[];
    expect(Array.isArray(color)).toBe(true);
    expect(color[0]).toBe('match');
    expect(color[1]).toEqual(['get', 'clase']);
    // Reuses the panel palette (NO second palette) + the shared neutral fallback.
    expect(color).toContain('IV');
    expect(color).toContain(SOIL_CAPABILITY_COLORS.IV);
    expect(color[color.length - 1]).toBe(SOIL_OVERLAY_FALLBACK_COLOR);
    // Opacity applied so the clipped analysis is translucent over the basemap.
    expect(fill?.paint?.['fill-opacity']).toBe(0.55);
  });

  it('is idempotent: re-sync updates the source, does not duplicate layers', () => {
    const { map, sources, layers } = createFakeMap();

    syncFichaOverlayLayers(map, {
      featureCollection: FC,
      dataset: 'suelos',
      visible: true,
    });
    const setData = sources.get(FICHA_OVERLAY_SOURCE)?.setData;

    const next: FeatureCollection = { type: 'FeatureCollection', features: [] };
    syncFichaOverlayLayers(map, {
      featureCollection: next,
      dataset: 'suelos',
      visible: true,
    });

    expect(setData).toHaveBeenCalledWith(next);
    // still exactly one fill + one line layer, one source
    expect([...layers.keys()].filter((id) => id.startsWith(FICHA_OVERLAY_SOURCE))).toHaveLength(2);
    expect(sources.size).toBe(1);
  });
});

describe('syncFichaOverlayLayers · hidden / no data', () => {
  it('removes the source + both layers when visible is false', () => {
    const { map, sources, layers } = createFakeMap();
    syncFichaOverlayLayers(map, {
      featureCollection: FC,
      dataset: 'suelos',
      visible: true,
    });

    syncFichaOverlayLayers(map, {
      featureCollection: FC,
      dataset: 'suelos',
      visible: false,
    });

    expect(sources.has(FICHA_OVERLAY_SOURCE)).toBe(false);
    expect(layers.has(FICHA_OVERLAY_FILL_LAYER)).toBe(false);
    expect(layers.has(FICHA_OVERLAY_LINE_LAYER)).toBe(false);
  });

  it('removes the layers when there is no featureCollection (stale overlay cleared)', () => {
    const { map, sources, layers } = createFakeMap();
    syncFichaOverlayLayers(map, {
      featureCollection: FC,
      dataset: 'suelos',
      visible: true,
    });

    syncFichaOverlayLayers(map, {
      featureCollection: null,
      dataset: 'suelos',
      visible: true,
    });

    expect(sources.has(FICHA_OVERLAY_SOURCE)).toBe(false);
    expect(layers.has(FICHA_OVERLAY_FILL_LAYER)).toBe(false);
  });
});

describe('buildSoilOverlayColorExpression', () => {
  it('maps every capability class I…VIII to its palette color', () => {
    const expr = buildSoilOverlayColorExpression() as unknown as unknown[];
    for (const [clase, color] of Object.entries(SOIL_CAPABILITY_COLORS)) {
      const idx = expr.indexOf(clase);
      expect(idx).toBeGreaterThan(0);
      expect(expr[idx + 1]).toBe(color);
    }
  });
});
