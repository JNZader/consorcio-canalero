import { describe, expect, it, vi } from 'vitest';

import {
  TERRAIN_SOURCE_IDS,
  syncTerrainVectorLayers,
} from '../../src/components/terrain/terrainVectorLayerEffects';

/**
 * Unit tests for the 3D terrain-viewer vector layer paint constants. These
 * values were tuned during the layer-visibility audit (2026-04) so cadastral
 * and soil detail stay readable on the 3D MapLibre-native terrain viewer,
 * matching the 2D MapaMapLibre paint after the same audit.
 *
 * The test intentionally doesn't exercise z-order — MapLibre's declaration
 * order is the source of truth; we simply assert catastro is added AFTER
 * soil in `ensureTerrainVectorLayers`, which the tests below verify via the
 * call-order of `addLayer` on the mock.
 */
function createMapMock() {
  const layers = new Set<string>();
  const sources = new Set<string>();

  return {
    getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
    getSource: vi.fn((id: string) => (sources.has(id) ? { id } : undefined)),
    addSource: vi.fn((id: string) => {
      sources.add(id);
    }),
    addLayer: vi.fn((layer: { id: string }) => {
      layers.add(layer.id);
    }),
    setLayoutProperty: vi.fn(),
  };
}

function emptyCollections() {
  const fc = { type: 'FeatureCollection' as const, features: [] };
  return {
    zonaCollection: fc,
    approvedZonesCollection: fc,
    cuencasCollection: fc,
    basins: fc,
    roadsCollection: fc,
    waterwaysCollection: fc,
    soilCollection: fc,
    catastroCollection: fc,
  };
}

function baselineVisibility() {
  return {
    zona: true,
    approved_zones: true,
    basins: true,
    roads: true,
    waterways: true,
    soil: true,
    catastro: true,
  };
}

describe('terrainVectorLayerEffects paint constants (layer-visibility audit)', () => {
  it('renders the 3D catastro line with a white high-contrast outline', () => {
    const map = createMapMock();

    syncTerrainVectorLayers(
      map as never,
      emptyCollections(),
      baselineVisibility(),
    );

    const catastroCall = map.addLayer.mock.calls.find(
      ([layer]) => layer?.id === `${TERRAIN_SOURCE_IDS.catastro}-line`,
    );
    expect(catastroCall).toBeDefined();
    const [catastroLayer] = catastroCall ?? [];
    expect(catastroLayer?.paint).toMatchObject({
      'line-color': '#FFFFFF',
      'line-width': 1.5,
      'line-opacity': 0.85,
    });
  });

  it('renders the 3D soil fill and line with the audited visibility-boost paint', () => {
    const map = createMapMock();

    syncTerrainVectorLayers(
      map as never,
      emptyCollections(),
      baselineVisibility(),
    );

    const fillCall = map.addLayer.mock.calls.find(
      ([layer]) => layer?.id === `${TERRAIN_SOURCE_IDS.soil}-fill`,
    );
    expect(fillCall).toBeDefined();
    const [fillLayer] = fillCall ?? [];
    expect(fillLayer?.paint).toMatchObject({
      'fill-opacity': 0.3,
    });

    const lineCall = map.addLayer.mock.calls.find(
      ([layer]) => layer?.id === `${TERRAIN_SOURCE_IDS.soil}-line`,
    );
    expect(lineCall).toBeDefined();
    const [lineLayer] = lineCall ?? [];
    expect(lineLayer?.paint).toMatchObject({
      'line-color': '#6d4c41',
      'line-width': 1.2,
      'line-opacity': 0.85,
    });
  });

  // Locks Fix 3 — MapLibre renders in declaration order (last = top). If a
  // future refactor inadvertently reorders the helper and pushes soil AFTER
  // catastro, this test will fail and force the author to re-think the stack.
  it('declares catastro AFTER soil so parcela outlines render above soil fill', () => {
    const map = createMapMock();

    syncTerrainVectorLayers(
      map as never,
      emptyCollections(),
      baselineVisibility(),
    );

    const ids = map.addLayer.mock.calls.map(([layer]) => layer?.id as string);
    const soilFillIdx = ids.indexOf(`${TERRAIN_SOURCE_IDS.soil}-fill`);
    const soilLineIdx = ids.indexOf(`${TERRAIN_SOURCE_IDS.soil}-line`);
    const catastroLineIdx = ids.indexOf(`${TERRAIN_SOURCE_IDS.catastro}-line`);

    expect(soilFillIdx).toBeGreaterThanOrEqual(0);
    expect(soilLineIdx).toBeGreaterThanOrEqual(0);
    expect(catastroLineIdx).toBeGreaterThanOrEqual(0);

    expect(catastroLineIdx).toBeGreaterThan(soilFillIdx);
    expect(catastroLineIdx).toBeGreaterThan(soilLineIdx);
  });
});
