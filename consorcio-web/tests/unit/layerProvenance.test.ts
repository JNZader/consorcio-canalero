/**
 * layerProvenance.test.ts — Batch 1 "datos honestos".
 *
 * Provenance answers WHEN the data was produced. The rule this file protects is
 * the honest one: ONLY the two families that ship a real `generated_at` get a
 * line. An invented or approximated date for waterways/basins/soil/catastro
 * would be worse than no date at all.
 */

import { describe, expect, it } from 'vitest';

import { buildLayerProvenance } from '../../src/components/map2d/layerProvenance';

const CANALES_ISO = '2026-04-20T20:18:51Z';
const PILAR_VERDE_ISO = '2026-02-01T10:00:00Z';

describe('buildLayerProvenance · formatting', () => {
  it('renders the es-AR short date behind the "Datos al" prefix', () => {
    const provenance = buildLayerProvenance({
      canalesGeneratedAt: CANALES_ISO,
    });

    // Pinned LITERAL, not `formatDate(...)` re-derived: comparing the output
    // against the same formatter that produced it would pass even if the date
    // came out as "4/20/2026" or "20 de abril de 2026".
    expect(provenance.canales).toBe('Datos al 20/04/2026');
  });

  it('emits both families when both dates are present', () => {
    const provenance = buildLayerProvenance({
      canalesGeneratedAt: CANALES_ISO,
      pilarVerdeGeneratedAt: PILAR_VERDE_ISO,
    });

    expect(Object.keys(provenance).sort()).toEqual(['canales', 'pilar_verde']);
  });
});

describe('buildLayerProvenance · honesty rules', () => {
  it('returns nothing for empty inputs — no family gets an invented date', () => {
    expect(buildLayerProvenance()).toEqual({});
    expect(buildLayerProvenance({})).toEqual({});
  });

  it('omits the key for a null / undefined / empty date', () => {
    expect(buildLayerProvenance({ canalesGeneratedAt: null }).canales).toBeUndefined();
    expect(buildLayerProvenance({ canalesGeneratedAt: undefined }).canales).toBeUndefined();
    expect(buildLayerProvenance({ canalesGeneratedAt: '' }).canales).toBeUndefined();
  });

  it('omits the key for an UNPARSEABLE date instead of rendering "Datos al -"', () => {
    const provenance = buildLayerProvenance({
      canalesGeneratedAt: 'no-es-una-fecha',
    });

    expect(provenance.canales).toBeUndefined();
    expect(provenance).toEqual({});
  });

  it('NEVER emits a line for a family without a real generated_at', () => {
    const provenance = buildLayerProvenance({
      canalesGeneratedAt: CANALES_ISO,
      pilarVerdeGeneratedAt: PILAR_VERDE_ISO,
    });

    // hidrografia / territorio / analisis / base ship no ETL timestamp.
    expect(provenance.hidrografia).toBeUndefined();
    expect(provenance.territorio).toBeUndefined();
    expect(provenance.analisis).toBeUndefined();
    expect(provenance.base).toBeUndefined();
  });
});
