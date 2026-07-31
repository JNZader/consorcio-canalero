/**
 * map2d3dLabelParity.test.ts
 *
 * Phase 2.5 of `rediseno-ux-mapa`: the 2D `LayerControlsPanel` and the 3D
 * `TerrainLayerTogglesPanel` must use the SAME wording for shared layers so a
 * user recognises the same capa across views. The 3D config
 * (`PRIORITY_3D_VECTOR_LAYERS`) is the naming source of truth; this test
 * asserts the 2D labels produced by `buildVectorLayerItems` match it for every
 * shared layer id.
 */

import type { FeatureCollection } from 'geojson';
import { describe, expect, it } from 'vitest';

import { buildVectorLayerItems } from '../../src/components/map2d/map2dDerived';
import { PILAR_VERDE_ITEMS } from '../../src/components/terrain/TerrainLayerTogglesPanel';
import { PRIORITY_3D_VECTOR_LAYERS } from '../../src/components/terrain/terrainLayerConfig';

function nonEmpty(): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: {} },
    ],
  };
}

describe('2D / 3D layer label parity', () => {
  it('2D labels match the 3D config for every shared layer id', () => {
    const items2d = buildVectorLayerItems({
      basins: nonEmpty(),
      approvedZonesCollection: nonEmpty(),
      roadsCollection: nonEmpty(),
      intersectionsLength: 1,
    });
    const labelById = new Map(items2d.map((item) => [item.id, item.label]));

    const shared = PRIORITY_3D_VECTOR_LAYERS.filter((layer) => labelById.has(layer.id));
    // Guard against a false-green if the id sets ever drift apart entirely.
    expect(shared.length).toBeGreaterThan(0);

    for (const layer of shared) {
      expect(labelById.get(layer.id)).toBe(layer.label);
    }
  });

  it('2D Pilar Verde labels match the 3D PILAR_VERDE_ITEMS source (FF4)', () => {
    const items2d = buildVectorLayerItems({
      basins: null,
      approvedZonesCollection: null,
      roadsCollection: null,
      intersectionsLength: 0,
      showPilarVerde: true,
    });
    const labelById = new Map(items2d.map((item) => [item.id, item.label]));

    // The 5 pilar_verde_* labels are duplicated literals across 2D
    // (map2dDerived) and 3D (TerrainLayerTogglesPanel.PILAR_VERDE_ITEMS). Bind
    // them so a divergence in either side turns this test red.
    expect(PILAR_VERDE_ITEMS.length).toBe(5);
    for (const item of PILAR_VERDE_ITEMS) {
      expect(labelById.get(item.id)).toBe(item.label);
    }
  });
});
