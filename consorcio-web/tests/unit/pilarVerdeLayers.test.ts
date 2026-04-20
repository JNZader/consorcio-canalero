/**
 * Unit tests for `pilarVerdeLayers` — the colocated registry of Pilar Verde
 * colors, z-order and MapLibre paint factories.
 *
 * Phase 7 refinement — the single-color BPA 2025 fill was replaced by a
 * gradient driven by `años_bpa`. Colors are asserted as 4 explicit stop hex
 * values, and the fill paint uses a MapLibre `interpolate` expression.
 */
import { describe, expect, it } from 'vitest';

import {
  PILAR_VERDE_COLORS,
  PILAR_VERDE_Z_ORDER,
  buildAgroAceptadaFillPaint,
  buildAgroAceptadaLinePaint,
  buildAgroPresentadaFillPaint,
  buildAgroPresentadaLinePaint,
  buildAgroZonasFillPaint,
  buildAgroZonasLinePaint,
  buildBpaHistoricoFillPaint,
  buildBpaHistoricoLinePaint,
  buildPorcentajeForestacionFillPaint,
} from '../../src/components/map2d/pilarVerdeLayers';

describe('pilarVerdeLayers · colors', () => {
  it('exports the historical-gradient stop palette stretched across green 100→900', () => {
    // Palette redesign: stretched from greens 200/400/500/800 to 100/300/600/900
    // so each tier reads as a clearly distinct step over the basemap.
    expect(PILAR_VERDE_COLORS.bpaHistoricoStop1).toBe('#DCFCE7'); // green-100
    expect(PILAR_VERDE_COLORS.bpaHistoricoStop3).toBe('#86EFAC'); // green-300
    expect(PILAR_VERDE_COLORS.bpaHistoricoStop5).toBe('#16A34A'); // green-600
    expect(PILAR_VERDE_COLORS.bpaHistoricoStop7).toBe('#14532D'); // green-900
    expect(PILAR_VERDE_COLORS.bpaHistoricoLine).toBe('#14532D');
  });

  it('exports the semantic DEFAULT agro palette — each layer in its own hue family', () => {
    // Aceptada moved from green (conflicted with BPA gradient) to blue-600.
    expect(PILAR_VERDE_COLORS.agroAceptadaFill).toBe('#2563EB');
    expect(PILAR_VERDE_COLORS.agroAceptadaLine).toBe('#1E40AF');
    // Presentada bumped from red-500 to red-600 for a stronger contrast with
    // the red-800 outline.
    expect(PILAR_VERDE_COLORS.agroPresentadaFill).toBe('#DC2626');
    expect(PILAR_VERDE_COLORS.agroPresentadaLine).toBe('#991B1B');
    // Zonas fallback now matches the Río Tercero anchor color (warm palette).
    expect(PILAR_VERDE_COLORS.agroZonasFill).toBe('#FCD34D');
    expect(PILAR_VERDE_COLORS.agroZonasLine).toBe('#B45309');
  });

  it('exports the 3 per-zone agroforestal colors as warm hues (amber / orange / deep-amber)', () => {
    // The consorcio zone has EXACTLY 3 agroforestal systems identified by the
    // `leyenda` property. Palette redesign moved these from cool cyan/teal/sky
    // (which read as identical tones) to 3 warm hues with strong separation.
    expect(PILAR_VERDE_COLORS.agroZonaRioTercero).toBe('#FCD34D'); // amber-300
    expect(PILAR_VERDE_COLORS.agroZonaCarcarana).toBe('#F97316'); // orange-500
    expect(PILAR_VERDE_COLORS.agroZonaTortugas).toBe('#B45309'); // amber-700
  });

  it('exports the 3-tier porcentaje forestación palette — violet 100/500/900 for max contrast', () => {
    // Stops jump 100 → 500 → 900 (not 300/400/600) so the 3 tiers stay
    // visually distinct when rendered over the basemap.
    expect(PILAR_VERDE_COLORS.porcentajeForestacionBaja).toBe('#EDE9FE'); // violet-100
    expect(PILAR_VERDE_COLORS.porcentajeForestacionMedia).toBe('#8B5CF6'); // violet-500
    expect(PILAR_VERDE_COLORS.porcentajeForestacionAlta).toBe('#4C1D95'); // violet-900
  });

  it('exports the eje palette used by InfoPanel (phase 3) — UNCHANGED by palette redesign', () => {
    expect(PILAR_VERDE_COLORS.ejePersona).toBe('#3B82F6');
    expect(PILAR_VERDE_COLORS.ejePlaneta).toBe('#10B981');
    expect(PILAR_VERDE_COLORS.ejeProsperidad).toBe('#F59E0B');
    expect(PILAR_VERDE_COLORS.ejeAlianza).toBe('#8B5CF6');
  });
});

describe('pilarVerdeLayers · z-order', () => {
  it('orders layers bottom → top per design § Map Layer Registry', () => {
    expect(PILAR_VERDE_Z_ORDER).toEqual([
      'pilar_verde_agro_zonas',
      'pilar_verde_porcentaje_forestacion',
      'pilar_verde_agro_presentada',
      'pilar_verde_agro_aceptada',
      'pilar_verde_bpa_historico',
    ]);
  });

  it('places bpa_historico at the top so it wins click precedence over catastro', () => {
    expect(PILAR_VERDE_Z_ORDER[PILAR_VERDE_Z_ORDER.length - 1]).toBe('pilar_verde_bpa_historico');
  });

  it('is a readonly tuple — length matches the 5 Pilar Verde layers', () => {
    expect(PILAR_VERDE_Z_ORDER.length).toBe(5);
  });
});

describe('pilarVerdeLayers · paint factories', () => {
  it('bpa_historico fill uses an interpolate expression on años_bpa', () => {
    const paint = buildBpaHistoricoFillPaint();
    expect(paint['fill-opacity']).toBe(0.45);
    const fillColor = paint['fill-color'] as unknown as unknown[];
    expect(Array.isArray(fillColor)).toBe(true);
    expect(fillColor[0]).toBe('interpolate');
    expect(fillColor[1]).toEqual(['linear']);
    expect(fillColor[2]).toEqual(['get', 'años_bpa']);
    // Stops 1, 3, 5, 7 must pull from PILAR_VERDE_COLORS (single source of
    // truth) — never hardcode hex here. The palette redesign proved this
    // matters: changing a stop used to require two edits that could drift.
    expect(fillColor[3]).toBe(1);
    expect(fillColor[4]).toBe(PILAR_VERDE_COLORS.bpaHistoricoStop1);
    expect(fillColor[5]).toBe(3);
    expect(fillColor[6]).toBe(PILAR_VERDE_COLORS.bpaHistoricoStop3);
    expect(fillColor[7]).toBe(5);
    expect(fillColor[8]).toBe(PILAR_VERDE_COLORS.bpaHistoricoStop5);
    expect(fillColor[9]).toBe(7);
    expect(fillColor[10]).toBe(PILAR_VERDE_COLORS.bpaHistoricoStop7);
  });

  it('bpa_historico line: thin green-900 outline', () => {
    const paint = buildBpaHistoricoLinePaint();
    expect(paint['line-color']).toBe(PILAR_VERDE_COLORS.bpaHistoricoLine);
    expect(paint['line-width']).toBe(0.5);
  });

  it('agro aceptada fill: blue-600 @ 0.30 opacity', () => {
    const paint = buildAgroAceptadaFillPaint();
    expect(paint['fill-color']).toBe(PILAR_VERDE_COLORS.agroAceptadaFill);
    expect(paint['fill-opacity']).toBe(0.3);
  });

  it('agro aceptada line: blue-800 outline (darker than the blue-600 fill)', () => {
    const paint = buildAgroAceptadaLinePaint();
    expect(paint['line-color']).toBe(PILAR_VERDE_COLORS.agroAceptadaLine);
    expect(paint['line-width']).toBe(1);
  });

  it('agro presentada fill: red-600 @ 0.30 opacity', () => {
    const paint = buildAgroPresentadaFillPaint();
    expect(paint['fill-color']).toBe(PILAR_VERDE_COLORS.agroPresentadaFill);
    expect(paint['fill-opacity']).toBe(0.3);
  });

  it('agro presentada line: red-800 outline (darker than the red-600 fill)', () => {
    const paint = buildAgroPresentadaLinePaint();
    expect(paint['line-color']).toBe(PILAR_VERDE_COLORS.agroPresentadaLine);
    expect(paint['line-width']).toBe(1);
  });

  it('agro zonas fill: match expression on `leyenda` with 3 per-zone colors @ 0.30 opacity', () => {
    const paint = buildAgroZonasFillPaint();
    // Opacity raised 0.20 → 0.30 after the cool→warm palette swap: pale warm
    // hues (amber-300) looked washed out at 0.20.
    expect(paint['fill-opacity']).toBe(0.3);

    const fillColor = paint['fill-color'] as unknown as unknown[];
    expect(Array.isArray(fillColor)).toBe(true);
    // MapLibre match shape:
    //   ['match', input, label1, out1, label2, out2, label3, out3, fallback]
    expect(fillColor[0]).toBe('match');
    expect(fillColor[1]).toEqual(['get', 'leyenda']);

    expect(fillColor[2]).toBe('11 - Sist Rio Tercero - Este');
    expect(fillColor[3]).toBe(PILAR_VERDE_COLORS.agroZonaRioTercero);

    expect(fillColor[4]).toBe('50 - Sist. Rio Carcarañá');
    expect(fillColor[5]).toBe(PILAR_VERDE_COLORS.agroZonaCarcarana);

    expect(fillColor[6]).toBe('48 - Sist Arroyo Tortugas - Este');
    expect(fillColor[7]).toBe(PILAR_VERDE_COLORS.agroZonaTortugas);

    // Fallback — used if a future zone is added without updating the match.
    expect(fillColor[8]).toBe(PILAR_VERDE_COLORS.agroZonaRioTercero);
    expect(fillColor.length).toBe(9);
  });

  it('agro zonas line: thin amber-700 outline (darker than any of the 3 fills)', () => {
    const paint = buildAgroZonasLinePaint();
    expect(paint['line-color']).toBe(PILAR_VERDE_COLORS.agroZonasLine);
    expect(paint['line-width']).toBe(1);
  });

  it('porcentaje forestacion fill: `step` expression over forest_obligatoria with 3 violet tiers @ 0.30 opacity', () => {
    const paint = buildPorcentajeForestacionFillPaint();
    // Opacity raised from 0.15 → 0.30 so the 3 tiers stay distinguishable.
    expect(paint['fill-opacity']).toBe(0.3);

    const fillColor = paint['fill-color'] as unknown as unknown[];
    expect(Array.isArray(fillColor)).toBe(true);
    // MapLibre step shape: ['step', input, baseOutput, stop, out, stop, out, ...]
    expect(fillColor[0]).toBe('step');
    expect(fillColor[1]).toEqual(['get', 'forest_obligatoria']);
    // Base (< 2.31) → Baja
    expect(fillColor[2]).toBe(PILAR_VERDE_COLORS.porcentajeForestacionBaja);
    // [2.31, 2.61) → Media
    expect(fillColor[3]).toBe(2.31);
    expect(fillColor[4]).toBe(PILAR_VERDE_COLORS.porcentajeForestacionMedia);
    // ≥ 2.61 → Alta
    expect(fillColor[5]).toBe(2.61);
    expect(fillColor[6]).toBe(PILAR_VERDE_COLORS.porcentajeForestacionAlta);
    expect(fillColor.length).toBe(7);
  });
});
