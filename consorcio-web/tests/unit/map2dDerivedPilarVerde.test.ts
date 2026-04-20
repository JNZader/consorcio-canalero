/**
 * Phase 2 test — `buildVectorLayerItems` must append 5 Pilar Verde toggle
 * entries with Spanish labels, gated by `showPilarVerde` (defaults to true
 * in Phase 2 because the data is static and available). The existing entries
 * ("Subcuencas", "Hidrografía", etc.) are not asserted here — see
 * `map2dDerived.test.ts` for the broader coverage.
 */

import { describe, expect, it } from 'vitest';

import { buildVectorLayerItems } from '../../src/components/map2d/map2dDerived';

describe('buildVectorLayerItems · Pilar Verde', () => {
  it('appends the 5 Pilar Verde toggle entries with Spanish labels when pilarVerde is available', () => {
    const items = buildVectorLayerItems({
      basins: null,
      approvedZonesCollection: null,
      roadsCollection: null,
      intersectionsLength: 0,
      isAdmin: false,
      showPilarVerde: true,
    });

    const ids = items.map((item) => item.id);
    expect(ids).toContain('pilar_verde_bpa');
    expect(ids).toContain('pilar_verde_agro_aceptada');
    expect(ids).toContain('pilar_verde_agro_presentada');
    expect(ids).toContain('pilar_verde_agro_zonas');
    expect(ids).toContain('pilar_verde_porcentaje_forestacion');

    const labelFor = (id: string) => items.find((item) => item.id === id)?.label;
    expect(labelFor('pilar_verde_bpa')).toBe('BPA 2025');
    expect(labelFor('pilar_verde_agro_aceptada')).toBe('Agroforestal: Cumplen');
    expect(labelFor('pilar_verde_agro_presentada')).toBe('Agroforestal: Presentaron');
    expect(labelFor('pilar_verde_agro_zonas')).toBe('Zonas Agroforestales');
    expect(labelFor('pilar_verde_porcentaje_forestacion')).toBe('% Forestación obligatoria');
  });

  it('hides the 5 Pilar Verde toggles when data is not available (showPilarVerde=false)', () => {
    const items = buildVectorLayerItems({
      basins: null,
      approvedZonesCollection: null,
      roadsCollection: null,
      intersectionsLength: 0,
      isAdmin: false,
      showPilarVerde: false,
    });

    const ids = items.map((item) => item.id);
    expect(ids).not.toContain('pilar_verde_bpa');
    expect(ids).not.toContain('pilar_verde_agro_aceptada');
    expect(ids).not.toContain('pilar_verde_agro_presentada');
    expect(ids).not.toContain('pilar_verde_agro_zonas');
    expect(ids).not.toContain('pilar_verde_porcentaje_forestacion');
  });

  it('defaults to hiding Pilar Verde entries when `showPilarVerde` is omitted (back-compat)', () => {
    const items = buildVectorLayerItems({
      basins: null,
      approvedZonesCollection: null,
      roadsCollection: null,
      intersectionsLength: 0,
      isAdmin: false,
    });
    const ids = items.map((item) => item.id);
    expect(ids).not.toContain('pilar_verde_bpa');
  });
});
