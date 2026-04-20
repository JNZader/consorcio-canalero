/**
 * Phase 2 — z-order click precedence regression.
 *
 * The `clickableLayers` array fed into `queryRenderedFeatures` determines
 * which layer wins when layers overlap. Per spec scenario "Click on overlapping
 * BPA + catastro", BPA-fill MUST appear BEFORE `catastro-fill` in this array
 * so MapLibre returns the BPA feature at index 0.
 *
 * We test the ordering via the `buildClickableLayers()` pure helper (exported
 * from `useMapInteractionEffects.ts`) rather than running the hook, because
 * the ordering is the only invariant we care about here.
 */

import { describe, expect, it } from 'vitest';

import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { buildClickableLayers } from '../../src/components/map2d/useMapInteractionEffects';

describe('buildClickableLayers · z-order click precedence', () => {
  it('lists BPA-fill BEFORE catastro-fill so BPA wins on overlap clicks', () => {
    const layers = buildClickableLayers();
    const bpaIdx = layers.indexOf(`${SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO}-fill`);
    const catastroIdx = layers.indexOf(`${SOURCE_IDS.CATASTRO}-fill`);

    expect(bpaIdx).toBeGreaterThanOrEqual(0);
    expect(catastroIdx).toBeGreaterThanOrEqual(0);
    expect(bpaIdx).toBeLessThan(catastroIdx);
  });

  it('includes the three Pilar Verde agro fill layers alongside BPA', () => {
    const layers = buildClickableLayers();
    expect(layers).toContain(`${SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO}-fill`);
    expect(layers).toContain(`${SOURCE_IDS.PILAR_VERDE_AGRO_ACEPTADA}-fill`);
    expect(layers).toContain(`${SOURCE_IDS.PILAR_VERDE_AGRO_PRESENTADA}-fill`);
  });

  it('does NOT include agro_zonas / porcentaje_forestacion in clickable layers — those are context only', () => {
    const layers = buildClickableLayers();
    expect(layers).not.toContain(`${SOURCE_IDS.PILAR_VERDE_AGRO_ZONAS}-fill`);
    expect(layers).not.toContain(`${SOURCE_IDS.PILAR_VERDE_PORCENTAJE_FORESTACION}-fill`);
  });

  it('preserves the existing clickable layers (waterways / soil / roads / catastro)', () => {
    const layers = buildClickableLayers();
    // Sanity: baseline layers that existed before Phase 2 still present.
    expect(layers).toContain(`${SOURCE_IDS.CATASTRO}-fill`);
    expect(layers).toContain(`${SOURCE_IDS.SOIL}-fill`);
    expect(layers).toContain(`${SOURCE_IDS.ROADS}-line`);
  });
});

describe('buildClickableLayers · Pilar Azul (Canales) inclusion', () => {
  it('includes both Canales line layer ids in the whitelist', () => {
    const layers = buildClickableLayers();
    expect(layers).toContain(`${SOURCE_IDS.CANALES_RELEVADOS}-line`);
    expect(layers).toContain(`${SOURCE_IDS.CANALES_PROPUESTOS}-line`);
  });

  it('canales sit AFTER Pilar Verde fills (BPA wins over canal on overlap)', () => {
    const layers = buildClickableLayers();
    const pvBpaIdx = layers.indexOf(`${SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO}-fill`);
    const canalRelIdx = layers.indexOf(`${SOURCE_IDS.CANALES_RELEVADOS}-line`);
    const canalPropIdx = layers.indexOf(`${SOURCE_IDS.CANALES_PROPUESTOS}-line`);
    expect(pvBpaIdx).toBeGreaterThanOrEqual(0);
    expect(canalRelIdx).toBeGreaterThan(pvBpaIdx);
    expect(canalPropIdx).toBeGreaterThan(pvBpaIdx);
  });

  it('canales sit BEFORE catastro-fill so canal wins over catastro on overlap', () => {
    const layers = buildClickableLayers();
    const catastroIdx = layers.indexOf(`${SOURCE_IDS.CATASTRO}-fill`);
    const canalRelIdx = layers.indexOf(`${SOURCE_IDS.CANALES_RELEVADOS}-line`);
    const canalPropIdx = layers.indexOf(`${SOURCE_IDS.CANALES_PROPUESTOS}-line`);
    expect(catastroIdx).toBeGreaterThan(0);
    expect(canalRelIdx).toBeLessThan(catastroIdx);
    expect(canalPropIdx).toBeLessThan(catastroIdx);
  });
});
