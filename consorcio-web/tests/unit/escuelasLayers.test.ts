/**
 * escuelasLayers.test.ts
 *
 * Unit tests for the Pilar Azul (Escuelas rurales) colocated layer registry.
 *
 * This file was rewritten after the symbol+icon approach was abandoned in
 * favor of a native MapLibre `circle` layer (see `escuelasLayers.ts` header
 * for the history). There is no icon asset, no `loadImage`, no `addImage` —
 * nothing in this file should reference them.
 *
 * The short-lived companion text-only `symbol` label layer was also removed:
 * it required a `glyphs` URL on the map style (which this deployment does not
 * configure). The feature name is shown on click via `EscuelaCard` instead.
 *
 * What we pin here:
 *   - Public constants: `ESCUELAS_LAYER_ID` (`'escuelas-symbol'` —
 *     intentionally unchanged) and `ESCUELAS_SOURCE_ID`.
 *   - Circle paint factory — exact paint keys + values expected by the
 *     legend swatch and the map render.
 */

import { describe, expect, it } from 'vitest';

import {
  ESCUELAS_LAYER_ID,
  ESCUELAS_SOURCE_ID,
  buildEscuelasCirclePaint,
} from '../../src/components/map2d/escuelasLayers';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

describe('escuelasLayers · constants', () => {
  it('exposes the canonical layer id `escuelas-symbol` (kept for click-precedence compat)', () => {
    // The `-symbol` suffix is retained even though the layer is now a
    // `circle` type — renaming it would cascade into the click-precedence
    // test pinning index 10 in `buildClickableLayers` AND the InfoPanel
    // discriminator branch without any visual payoff.
    expect(ESCUELAS_LAYER_ID).toBe('escuelas-symbol');
  });

  it('exposes the source id `escuelas` (matches SOURCE_IDS.ESCUELAS)', () => {
    expect(ESCUELAS_SOURCE_ID).toBe('escuelas');
  });
});

// ---------------------------------------------------------------------------
// Circle paint factory — the main visual contract
// ---------------------------------------------------------------------------

describe('buildEscuelasCirclePaint', () => {
  it('uses a zoom-interpolated circle-radius from 4 @ z10 to 8 @ z16', () => {
    const paint = buildEscuelasCirclePaint();
    expect(paint['circle-radius']).toEqual([
      'interpolate',
      ['linear'],
      ['zoom'],
      10,
      4,
      16,
      8,
    ]);
  });

  it('fills the circle in the Pilar Azul blue `#1976d2`', () => {
    const paint = buildEscuelasCirclePaint();
    expect(paint['circle-color']).toBe('#1976d2');
  });

  it('strokes the circle with a 2px white outline so it reads on any basemap', () => {
    const paint = buildEscuelasCirclePaint();
    expect(paint['circle-stroke-color']).toBe('#ffffff');
    expect(paint['circle-stroke-width']).toBe(2);
  });
});
