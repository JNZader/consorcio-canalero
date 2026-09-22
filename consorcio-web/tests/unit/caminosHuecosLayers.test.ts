/**
 * Staff-only OSM/IGN gap overlay — paint/filter on `fuente` + citizen never
 * mounts the GeoJSON source.
 */

import { describe, expect, it, vi } from 'vitest';

import { LAYER_RENDER_REGISTRY } from '../../src/components/map2d/layerRenderRegistry';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { syncCaminosHuecosLayers } from '../../src/components/map2d/mapLayerEffectHelpers';
import {
  CAMINOS_HUECOS_FUENTE,
  CAMINOS_HUECOS_GEOJSON_URL,
  CAMINOS_HUECOS_LAYER_IDS,
  CAMINOS_HUECOS_PAINT,
  CAMINOS_HUECOS_SOURCE_ID,
  buildCaminosHuecosFuenteFilter,
  buildCaminosHuecosIgnPaint,
  buildCaminosHuecosOsmPaint,
} from '../../src/components/map2d/caminosHuecosLayers';

function createMapMock() {
  const layers = new Set<string>();
  const sources = new Map<string, unknown>();
  return {
    getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
    getSource: vi.fn((id: string) => sources.get(id)),
    addSource: vi.fn((id: string, source?: unknown) => {
      sources.set(id, source ?? { id });
    }),
    addLayer: vi.fn((layer: { id: string }) => {
      layers.add(layer.id);
    }),
    removeLayer: vi.fn((id: string) => {
      layers.delete(id);
    }),
    removeSource: vi.fn((id: string) => {
      sources.delete(id);
    }),
    setLayoutProperty: vi.fn(),
    layers,
    sources,
  };
}

describe('caminosHuecosLayers · constants', () => {
  it('source id matches SOURCE_IDS.CAMINOS_HUECOS and the UI toggle key', () => {
    expect(CAMINOS_HUECOS_SOURCE_ID).toBe(SOURCE_IDS.CAMINOS_HUECOS);
    expect(CAMINOS_HUECOS_SOURCE_ID).toBe('caminos_huecos');
  });

  it('loads the gap GeoJSON, not caminos.geojson', () => {
    expect(CAMINOS_HUECOS_GEOJSON_URL).toBe('/capas/caminos_huecos.geojson');
    expect(CAMINOS_HUECOS_GEOJSON_URL).not.toContain('caminos.geojson');
  });
});

describe('caminosHuecosLayers · paint/filter uses fuente', () => {
  it('filters each layer on the fuente property', () => {
    expect(buildCaminosHuecosFuenteFilter(CAMINOS_HUECOS_FUENTE.OSM)).toEqual([
      '==',
      ['get', 'fuente'],
      'osm',
    ]);
    expect(buildCaminosHuecosFuenteFilter(CAMINOS_HUECOS_FUENTE.IGN)).toEqual([
      '==',
      ['get', 'fuente'],
      'ign',
    ]);
  });

  it('paints OSM unclassified violet solid', () => {
    const paint = buildCaminosHuecosOsmPaint();
    expect(paint['line-color']).toBe('#c026d3');
    expect(paint['line-width']).toBe(3);
    expect(paint['line-dasharray']).toBeUndefined();
    expect(CAMINOS_HUECOS_PAINT.osm.color).toBe('#c026d3');
  });

  it('paints IGN terciaria cyan dashed', () => {
    const paint = buildCaminosHuecosIgnPaint();
    expect(paint['line-color']).toBe('#0891b2');
    expect(paint['line-dasharray']).toEqual([3, 2]);
    expect(CAMINOS_HUECOS_PAINT.ign.color).toBe('#0891b2');
  });
});

describe('syncCaminosHuecosLayers · citizen never mounts', () => {
  it('does not addSource when shouldMount is false', () => {
    const map = createMapMock();
    syncCaminosHuecosLayers(map as never, false, false);
    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
  });

  it('mounts the clip URL for staff', () => {
    const map = createMapMock();
    syncCaminosHuecosLayers(map as never, true, true);
    expect(map.addSource).toHaveBeenCalledWith(
      CAMINOS_HUECOS_SOURCE_ID,
      expect.objectContaining({ type: 'geojson', data: CAMINOS_HUECOS_GEOJSON_URL })
    );
    expect(map.addLayer).toHaveBeenCalledTimes(2);
    expect(LAYER_RENDER_REGISTRY.caminos_huecos.mlLayers.map((ml) => ml.id)).toEqual([
      CAMINOS_HUECOS_LAYER_IDS.OSM,
      CAMINOS_HUECOS_LAYER_IDS.IGN,
    ]);
  });
});

describe('caminos_huecos.geojson · remainder only', () => {
  it('is schema 1.1 remainder after Red Vial ∪ IDECOR', async () => {
    const { readFileSync } = await import('node:fs');
    const { resolve } = await import('node:path');
    const data = JSON.parse(
      readFileSync(resolve(__dirname, '../../public/capas/caminos_huecos.geojson'), 'utf8')
    ) as {
      metadata: { schema_version: string; priority: string };
      features: Array<{ properties: { fuente: string; longitud_km: number } }>;
    };
    expect(data.metadata.schema_version).toBe('1.1');
    expect(data.metadata.priority).toMatch(/Red Vial/);
    expect(data.features.length).toBeGreaterThan(0);
    for (const feature of data.features) {
      expect(['osm', 'ign']).toContain(feature.properties.fuente);
      expect(feature.properties.longitud_km).toBeGreaterThan(0.05);
    }
  });
});
