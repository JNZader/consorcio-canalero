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
  it('exports the historical-gradient stop palette (Phase 7)', () => {
    expect(PILAR_VERDE_COLORS.bpaHistoricoStop1).toBe('#BBF7D0');
    expect(PILAR_VERDE_COLORS.bpaHistoricoStop3).toBe('#4ADE80');
    expect(PILAR_VERDE_COLORS.bpaHistoricoStop5).toBe('#22C55E');
    expect(PILAR_VERDE_COLORS.bpaHistoricoStop7).toBe('#15803D');
    expect(PILAR_VERDE_COLORS.bpaHistoricoLine).toBe('#166534');
  });

  it('exports the semantic DEFAULT agro palette per spec', () => {
    expect(PILAR_VERDE_COLORS.agroAceptadaFill).toBe('#22C55E');
    expect(PILAR_VERDE_COLORS.agroPresentadaFill).toBe('#EF4444');
    expect(PILAR_VERDE_COLORS.agroZonasFill).toBe('#06B6D4');
  });

  it('exports the 3-tier porcentaje forestación palette (baja/media/alta)', () => {
    expect(PILAR_VERDE_COLORS.porcentajeForestacionBaja).toBe('#C4B5FD');
    expect(PILAR_VERDE_COLORS.porcentajeForestacionMedia).toBe('#A78BFA');
    expect(PILAR_VERDE_COLORS.porcentajeForestacionAlta).toBe('#7C3AED');
  });

  it('exports the eje palette used by InfoPanel (phase 3) — kept in sync here', () => {
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
    // Stops 1, 3, 5, 7 with their matching colors.
    expect(fillColor[3]).toBe(1);
    expect(fillColor[4]).toBe('#BBF7D0');
    expect(fillColor[5]).toBe(3);
    expect(fillColor[6]).toBe('#4ADE80');
    expect(fillColor[7]).toBe(5);
    expect(fillColor[8]).toBe('#22C55E');
    expect(fillColor[9]).toBe(7);
    expect(fillColor[10]).toBe('#15803D');
  });

  it('bpa_historico line: thin dark-green outline', () => {
    const paint = buildBpaHistoricoLinePaint();
    expect(paint['line-color']).toBe('#166534');
    expect(paint['line-width']).toBe(0.5);
  });

  it('agro aceptada fill: green @ 0.30 opacity', () => {
    const paint = buildAgroAceptadaFillPaint();
    expect(paint['fill-color']).toBe('#22C55E');
    expect(paint['fill-opacity']).toBe(0.3);
  });

  it('agro aceptada line: green outline', () => {
    const paint = buildAgroAceptadaLinePaint();
    expect(paint['line-color']).toBe('#22C55E');
    expect(paint['line-width']).toBe(1);
  });

  it('agro presentada fill: red @ 0.30 opacity', () => {
    const paint = buildAgroPresentadaFillPaint();
    expect(paint['fill-color']).toBe('#EF4444');
    expect(paint['fill-opacity']).toBe(0.3);
  });

  it('agro presentada line: red outline', () => {
    const paint = buildAgroPresentadaLinePaint();
    expect(paint['line-color']).toBe('#EF4444');
    expect(paint['line-width']).toBe(1);
  });

  it('agro zonas fill: cyan @ 0.20 opacity — context layer, subtle', () => {
    const paint = buildAgroZonasFillPaint();
    expect(paint['fill-color']).toBe('#06B6D4');
    expect(paint['fill-opacity']).toBe(0.2);
  });

  it('agro zonas line: thin cyan outline', () => {
    const paint = buildAgroZonasLinePaint();
    expect(paint['line-color']).toBe('#06B6D4');
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
