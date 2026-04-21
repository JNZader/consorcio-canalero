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

  // Removal task — the "Zona Consorcio" outline is redundant in 3D because
  // the 3D mesh IS the consorcio zone (rendering a red outline around the
  // whole viewport is visual noise). The zona layer was removed from the 3D
  // viewer entirely in Batch G; 2D still renders it via its own pipeline.
  // This test locks the contract so it cannot come back silently.
  it('does NOT register any zona source or line layer in the 3D viewer', () => {
    const map = createMapMock();

    syncTerrainVectorLayers(
      map as never,
      emptyCollections(),
      baselineVisibility(),
    );

    const sourceIds = map.addSource.mock.calls.map(([id]) => id as string);
    const layerIds = map.addLayer.mock.calls.map(([layer]) => layer?.id as string);

    expect(sourceIds.some((id) => id.includes('zona'))).toBe(false);
    expect(layerIds.some((id) => id.includes('zona'))).toBe(false);
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
