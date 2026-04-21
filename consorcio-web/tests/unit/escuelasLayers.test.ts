/**
 * escuelasLayers.test.ts
 *
 * Unit tests for the Pilar Azul (Escuelas rurales) colocated layer registry.
 *
 * This file was rewritten after the symbol+icon approach was abandoned in
 * favor of a native MapLibre `circle` layer + companion text-only `symbol`
 * layer (see `escuelasLayers.ts` header for the history). There is no icon
 * asset, no `loadImage`, no `addImage` — nothing in this file should
 * reference them.
 *
 * What we pin here:
 *   - Public constants: `ESCUELAS_LAYER_ID` (`'escuelas-symbol'` —
 *     intentionally unchanged), `ESCUELAS_LABEL_LAYER_ID`,
 *     `ESCUELAS_SOURCE_ID`.
 *   - Circle paint factory — exact paint keys + values expected by the
 *     legend swatch and the map render.
 *   - Label layout/paint factory — kept lightweight (text-only, no icon).
 */

import { describe, expect, it } from 'vitest';

import {
  ESCUELAS_LABEL_LAYER_ID,
  ESCUELAS_LAYER_ID,
  ESCUELAS_SOURCE_ID,
  buildEscuelasCirclePaint,
  buildEscuelasLabelLayout,
  buildEscuelasLabelPaint,
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

  it('exposes the companion label layer id `escuelas-label`', () => {
    expect(ESCUELAS_LABEL_LAYER_ID).toBe('escuelas-label');
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

// ---------------------------------------------------------------------------
// Label layout/paint factories — companion text-only symbol layer
// ---------------------------------------------------------------------------

describe('buildEscuelasLabelLayout', () => {
  it('reads text-field from the `nombre` property', () => {
    const layout = buildEscuelasLabelLayout();
    expect(layout['text-field']).toEqual(['get', 'nombre']);
  });

  it('sets text-size 11, text-offset [0, 1.2], text-optional true (drop label below circle)', () => {
    const layout = buildEscuelasLabelLayout();
    expect(layout['text-size']).toBe(11);
    expect(layout['text-offset']).toEqual([0, 1.2]);
    expect(layout['text-optional']).toBe(true);
  });

  it('does NOT define an `icon-image` (text-only layer — the circle handles the point glyph)', () => {
    const layout = buildEscuelasLabelLayout();
    expect(layout['icon-image']).toBeUndefined();
  });
});

describe('buildEscuelasLabelPaint', () => {
  it('renders the label in `#1a237e` with a white halo of width 1.5', () => {
    const paint = buildEscuelasLabelPaint();
    expect(paint['text-color']).toBe('#1a237e');
    expect(paint['text-halo-color']).toBe('#ffffff');
    expect(paint['text-halo-width']).toBe(1.5);
  });
});
