/**
 * mapActiveLayerCount.test.ts — T3c fix 3 (honest "N capas activas" badge).
 *
 * The workspace badge used to be `Object.values(vectorVisibility).filter(Boolean).length`,
 * which counts per-canal and per-waterway SUB-KEYS the panel never renders as
 * rows: it reported "68 activas" over a map showing ~6 layers, contradicting the
 * per-family badges beside it. Both numbers now come from
 * `buildFamilyActiveCounts`, so they agree by construction.
 */

import { describe, expect, it } from 'vitest';

import {
  buildFamilyActiveCounts,
  LAYER_CATEGORY,
  sumFamilyActiveCounts,
} from '../../src/components/map2d/map2dDerived';
import {
  buildTerrain3DLayerItems,
  PRIORITY_3D_VECTOR_LAYERS,
} from '../../src/components/terrain/terrainLayerConfig';
import { PILAR_VERDE_LAYER_IDS } from '../../src/stores/mapLayerSyncStore';

const layerItems = [
  { id: 'waterways', category: LAYER_CATEGORY.HIDROGRAFIA },
  { id: 'basins', category: LAYER_CATEGORY.HIDROGRAFIA },
  { id: 'roads', category: LAYER_CATEGORY.TERRITORIO },
  { id: 'catastro', category: LAYER_CATEGORY.TERRITORIO },
  { id: 'pilar_verde_agro_zonas', category: LAYER_CATEGORY.PILAR_VERDE },
  { id: 'canales_relevados', category: LAYER_CATEGORY.CANALES },
  { id: 'canales_propuestos', category: LAYER_CATEGORY.CANALES },
  { id: 'puntos_conflicto', category: LAYER_CATEGORY.ANALISIS },
];

// A realistic snapshot: 3 panel rows on (waterways, roads, catastro) plus the
// per-waterway and per-canal sub-keys the panel never shows as rows.
const vectorVisibility: Record<string, boolean> = {
  waterways: true,
  roads: true,
  catastro: true,
  basins: false,
  pilar_verde_agro_zonas: false,
  puntos_conflicto: false,
  canales_relevados: true,
  canales_propuestos: false,
  waterways_rio_tercero: true,
  waterways_canal_desviador: true,
  waterways_arroyo_algodon: true,
  canal_relevado_uno: true,
  canal_relevado_dos: false,
  canal_propuesto_tres: true,
};

const canalChildIds = ['canal_relevado_uno', 'canal_relevado_dos', 'canal_propuesto_tres'];

describe('buildFamilyActiveCounts (T3c fix 3)', () => {
  it('counts only what the panel renders as rows', () => {
    const counts = buildFamilyActiveCounts({ layerItems, vectorVisibility, canalChildIds });

    expect(counts[LAYER_CATEGORY.HIDROGRAFIA]).toBe(1); // waterways (not its 3 sub-keys)
    expect(counts[LAYER_CATEGORY.TERRITORIO]).toBe(2); // roads + catastro
    expect(counts[LAYER_CATEGORY.PILAR_VERDE]).toBe(0);
    expect(counts[LAYER_CATEGORY.ANALISIS]).toBe(0);
    expect(counts[LAYER_CATEGORY.CANALES]).toBe(2); // 2 visible children, not the masters
    expect(counts[LAYER_CATEGORY.BASE]).toBe(0);
  });

  it('pins the workspace total for that visibility state', () => {
    const total = sumFamilyActiveCounts(
      buildFamilyActiveCounts({ layerItems, vectorVisibility, canalChildIds })
    );

    // 1 hidrografía + 2 territorio + 2 canales = 5, NOT the 9 truthy raw keys.
    expect(total).toBe(5);
    expect(Object.values(vectorVisibility).filter(Boolean).length).toBe(9);
  });

  it('counts the structural Base overlays (IGN + DEM)', () => {
    const counts = buildFamilyActiveCounts({
      layerItems,
      vectorVisibility,
      canalChildIds,
      showIGNOverlay: true,
      showDemOverlay: true,
    });

    expect(counts[LAYER_CATEGORY.BASE]).toBe(2);
    expect(sumFamilyActiveCounts(counts)).toBe(7);
  });

  it('never double-counts the canal MASTER toggles', () => {
    // Masters on, every child off → the family badge is 0, not 2.
    const counts = buildFamilyActiveCounts({
      layerItems,
      vectorVisibility: { canales_relevados: true, canales_propuestos: true },
      canalChildIds,
    });

    expect(counts[LAYER_CATEGORY.CANALES]).toBe(0);
    expect(sumFamilyActiveCounts(counts)).toBe(0);
  });

  it('is zero for an empty visibility record', () => {
    const counts = buildFamilyActiveCounts({ layerItems, vectorVisibility: {} });
    expect(sumFamilyActiveCounts(counts)).toBe(0);
  });
});

/**
 * R2-002 — the 3D badge now runs the SAME derivation. `buildTerrain3DLayerItems`
 * is the adapter: the 3D chrome has no `buildVectorLayerItems`, its rows come
 * from `PRIORITY_3D_VECTOR_LAYERS` + the 5 Pilar Verde toggles.
 */
describe('buildTerrain3DLayerItems — 3D badge inputs (R2-002)', () => {
  it('emits one entry per 3D panel row, each with a family', () => {
    const items = buildTerrain3DLayerItems({ intersectionsLength: 1 });
    const ids = items.map((item) => item.id);

    // Every 3D vector row is represented…
    for (const layer of PRIORITY_3D_VECTOR_LAYERS) {
      expect(ids).toContain(layer.id);
    }
    // …plus the 5 Pilar Verde toggles.
    for (const id of PILAR_VERDE_LAYER_IDS) {
      expect(ids).toContain(id);
    }
    // Canal MASTERS are excluded — the family counts its children instead.
    expect(ids).not.toContain('canales_relevados');
    expect(ids).not.toContain('canales_propuestos');
  });

  it('drops "puntos conflicto" when the backend reports no intersections', () => {
    const ids = buildTerrain3DLayerItems({ intersectionsLength: 0 }).map((item) => item.id);
    expect(ids).not.toContain('puntos_conflicto');
  });

  it('counts the same way 2D does — rows, not raw visibility keys', () => {
    // 2 real rows on, plus 3 per-canal sub-keys the 3D panel lists as children.
    const vectorVisibility: Record<string, boolean> = {
      waterways: true,
      pilar_verde_agro_zonas: true,
      canales_relevados: true, // master — must NOT be counted
      canal_relevado_a: true,
      canal_relevado_b: true,
      canal_propuesto_c: false,
      // Per-waterway sub-keys: invisible to the panel as rows.
      waterway_rio_tercero: true,
      waterway_canal_desviador: true,
    };

    const total = sumFamilyActiveCounts(
      buildFamilyActiveCounts({
        layerItems: buildTerrain3DLayerItems({ intersectionsLength: 0 }),
        vectorVisibility,
        canalChildIds: ['canal_relevado_a', 'canal_relevado_b', 'canal_propuesto_c'],
      })
    );

    // waterways + pilar_verde_agro_zonas + 2 visible canal children = 4.
    expect(total).toBe(4);
    // The old formula would have said 7.
    expect(Object.values(vectorVisibility).filter(Boolean).length).toBe(7);
  });
});
