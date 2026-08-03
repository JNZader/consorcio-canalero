/**
 * pilarVerdeGatingExpressions.test.ts — T3c final round, R3-001.
 *
 * Two load-bearing gating expressions had no test at all. Both decide whether
 * ~1.0 MB / ~512 KB of static payload is downloaded, and both are one typo away
 * from either a permanently dead layer family or an eager download on every
 * /mapa mount:
 *
 *   1. `MapaMapLibre` opens the `layers` gate with
 *      `PILAR_VERDE_LAYER_IDS.some((id) => vectorVisibility[id])`. If one id
 *      drifts from the panel item ids, that toggle silently never fetches.
 *   2. The BPA-join latch fires only for `tipo === 'parcela'` — the only tipo
 *      `PilarVerdeBadges` renders anything for.
 */

import { describe, expect, it } from 'vitest';

import {
  buildVectorLayerItems,
  LAYER_CATEGORY,
  shouldLatchBpaJoin,
} from '../../src/components/map2d/map2dDerived';
import { PILAR_VERDE_LAYER_IDS } from '../../src/stores/mapLayerSyncStore';

function pilarVerdePanelItemIds(): string[] {
  return buildVectorLayerItems({
    basins: null,
    approvedZonesCollection: null,
    roadsCollection: null,
    intersectionsLength: 0,
    showPilarVerde: true,
  })
    .filter((item) => item.category === LAYER_CATEGORY.PILAR_VERDE)
    .map((item) => item.id);
}

describe('PILAR_VERDE_LAYER_IDS ↔ panel items', () => {
  it('matches the panel item ids EXACTLY, id for id and in order', () => {
    expect(pilarVerdePanelItemIds()).toEqual([...PILAR_VERDE_LAYER_IDS]);
  });

  it('leaves no panel toggle without a gate id (and no gate id without a toggle)', () => {
    const panel = new Set(pilarVerdePanelItemIds());
    const gate = new Set<string>(PILAR_VERDE_LAYER_IDS);
    for (const id of panel) expect(gate.has(id)).toBe(true);
    for (const id of gate) expect(panel.has(id)).toBe(true);
  });
});

describe('shouldLatchBpaJoin', () => {
  it('fires for a parcela request', () => {
    expect(shouldLatchBpaJoin({ id: 'req' }, 'parcela')).toBe(true);
  });

  it('does NOT fire for any other tipo', () => {
    for (const tipo of ['parcelas', 'poligono', 'canal', 'canal_cuenca', 'Parcela', '']) {
      expect(shouldLatchBpaJoin({ id: 'req' }, tipo)).toBe(false);
    }
  });

  it('does NOT fire without a request, even for a parcela tipo', () => {
    expect(shouldLatchBpaJoin(null, 'parcela')).toBe(false);
    expect(shouldLatchBpaJoin(undefined, 'parcela')).toBe(false);
  });

  it('does NOT fire on a null/undefined tipo', () => {
    expect(shouldLatchBpaJoin({ id: 'req' }, null)).toBe(false);
    expect(shouldLatchBpaJoin({ id: 'req' }, undefined)).toBe(false);
  });
});
