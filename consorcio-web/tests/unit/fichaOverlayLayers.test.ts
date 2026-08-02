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
  FICHA_OVERLAY_FILL_OPACITY,
  FICHA_OVERLAY_LINE_COLOR,
  FICHA_OVERLAY_LINE_OPACITY,
  FICHA_OVERLAY_LINE_WIDTH,
  RIESGO_OVERLAY_FALLBACK_COLOR,
  SOIL_OVERLAY_FALLBACK_COLOR,
  buildRiesgoOverlayColorExpression,
  buildSoilOverlayColorExpression,
  riesgoClassColor,
  syncFichaOverlayLayers,
} from '../../src/components/map2d/fichaOverlayLayers';
import { LAYER_LEGEND_CONFIG } from '../../src/config/rasterLegend';
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
    setPaintProperty: (id: string, prop: string, value: unknown) => {
      const layer = layers.get(id);
      if (layer) layer.paint = { ...(layer.paint ?? {}), [prop]: value };
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
    // T3a fix 1b raised it 0.55 -> 0.7: at 0.55 the pale "Alto" swatch fused with
    // tan farmland and the class read as unpainted.
    expect(fill?.paint?.['fill-opacity']).toBe(FICHA_OVERLAY_FILL_OPACITY);
    expect(FICHA_OVERLAY_FILL_OPACITY).toBe(0.7);
  });

  // T3a, fix 1b - the outline used to reuse the per-class fill color, i.e. the
  // very color that failed to separate a class from the terrain. It is now a
  // neutral dark 1px hairline, so adjacent classes are always distinguishable.
  it('outlines each class with a thin neutral dark line, not the fill color', () => {
    const { map, layers } = createFakeMap();

    syncFichaOverlayLayers(map, {
      featureCollection: FC,
      dataset: 'flood_risk',
      visible: true,
    });

    const line = layers.get(FICHA_OVERLAY_LINE_LAYER);
    expect(line?.paint?.['line-color']).toBe(FICHA_OVERLAY_LINE_COLOR);
    expect(FICHA_OVERLAY_LINE_COLOR).toBe('#212121');
    expect(line?.paint?.['line-width']).toBe(FICHA_OVERLAY_LINE_WIDTH);
    expect(FICHA_OVERLAY_LINE_WIDTH).toBe(1);
    expect(line?.paint?.['line-opacity']).toBe(FICHA_OVERLAY_LINE_OPACITY);
    // Never a match expression - that was the old, unreadable behaviour.
    expect(Array.isArray(line?.paint?.['line-color'])).toBe(false);
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

describe('buildRiesgoOverlayColorExpression', () => {
  it.each(['flood_risk', 'drainage_need'] as const)(
    'resolves each %s class to the SAME color the panel legend uses (no new palette)',
    (dataset) => {
      const expr = buildRiesgoOverlayColorExpression(dataset) as unknown as unknown[];
      const ranges = LAYER_LEGEND_CONFIG[dataset]?.ranges ?? [];
      expect(ranges.length).toBeGreaterThan(0);
      for (const range of ranges) {
        const idx = expr.indexOf(range.label);
        expect(idx).toBeGreaterThan(0);
        // The color comes straight from LAYER_LEGEND_CONFIG, not a second palette.
        expect(expr[idx + 1]).toBe(range.color);
      }
      // Falls back to the shared neutral grey for an unknown clase.
      expect(expr[expr.length - 1]).toBe(RIESGO_OVERLAY_FALLBACK_COLOR);
    }
  );

  // T3a, fix 1a - the panel tables now read their chip colors from
  // `riesgoClassColor`, and the paint expression is built from that SAME
  // function, so a drift between legend and overlay is structurally impossible.
  it.each(['flood_risk', 'drainage_need'] as const)(
    'riesgoClassColor is the single %s source shared with the panel chips',
    (dataset) => {
      for (const range of LAYER_LEGEND_CONFIG[dataset]?.ranges ?? []) {
        expect(riesgoClassColor(dataset, range.label)).toBe(range.color);
      }
      expect(riesgoClassColor(dataset, 'clase inexistente')).toBe(
        RIESGO_OVERLAY_FALLBACK_COLOR
      );
    }
  );

  it("colors flood 'Medio' with the exact rasterLegend color", () => {
    const expr = buildRiesgoOverlayColorExpression('flood_risk') as unknown as unknown[];
    const medio = LAYER_LEGEND_CONFIG.flood_risk?.ranges?.find((r) => r.label === 'Medio');
    const idx = expr.indexOf('Medio');
    expect(idx).toBeGreaterThan(0);
    expect(expr[idx + 1]).toBe(medio?.color);
  });
});

describe('syncFichaOverlayLayers · dataset switch repaints', () => {
  it("repaints the fill with the new dataset's palette when the dataset changes", () => {
    const { map, layers } = createFakeMap();

    // First paint soils.
    syncFichaOverlayLayers(map, {
      featureCollection: FC,
      dataset: 'suelos',
      visible: true,
    });
    const soilColor = layers.get(FICHA_OVERLAY_FILL_LAYER)?.paint?.['fill-color'] as unknown[];
    expect(soilColor).toContain(SOIL_CAPABILITY_COLORS.IV);

    // Now switch to flood_risk over the same (still-mounted) layers.
    syncFichaOverlayLayers(map, {
      featureCollection: FC,
      dataset: 'flood_risk',
      visible: true,
    });
    const floodColor = layers.get(FICHA_OVERLAY_FILL_LAYER)?.paint?.['fill-color'] as unknown[];
    const medio = LAYER_LEGEND_CONFIG.flood_risk?.ranges?.find((r) => r.label === 'Medio');
    expect(floodColor).toContain('Medio');
    expect(floodColor).toContain(medio?.color);
    // The soils palette is gone — no stale soil color lingers on the flood overlay.
    expect(floodColor).not.toContain(SOIL_CAPABILITY_COLORS.IV);
  });
});
