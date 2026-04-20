/**
 * Unit tests for `pilarVerdeLayers` — the colocated registry of Pilar Verde
 * colors, z-order and MapLibre paint factories.
 *
 * These tests pin the public surface that Phase 2 sync helpers, map derived
 * state, and Phase 6 e2e will rely on. DEFAULT color choices are documented
 * in the module JSDoc — tests assert those defaults explicitly so a silent
 * change in palette breaks CI.
 */
import { describe, expect, it } from 'vitest';

import {
  PILAR_VERDE_COLORS,
  PILAR_VERDE_Z_ORDER,
  buildBpaFillPaint,
  buildBpaLinePaint,
  buildAgroAceptadaFillPaint,
  buildAgroAceptadaLinePaint,
  buildAgroPresentadaFillPaint,
  buildAgroPresentadaLinePaint,
  buildAgroZonasFillPaint,
  buildAgroZonasLinePaint,
  buildPorcentajeForestacionFillPaint,
} from '../../src/components/map2d/pilarVerdeLayers';

describe('pilarVerdeLayers · colors', () => {
  it('exports the semantic DEFAULT color palette per spec', () => {
    expect(PILAR_VERDE_COLORS.bpaFill).toBe('#FACC15');
    expect(PILAR_VERDE_COLORS.agroAceptadaFill).toBe('#22C55E');
    expect(PILAR_VERDE_COLORS.agroPresentadaFill).toBe('#EF4444');
    expect(PILAR_VERDE_COLORS.agroZonasFill).toBe('#06B6D4');
    expect(PILAR_VERDE_COLORS.porcentajeForestacionFill).toBe('#A78BFA');
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
      'pilar_verde_bpa',
    ]);
  });

  it('places bpa at the top so it wins click precedence over catastro', () => {
    expect(PILAR_VERDE_Z_ORDER[PILAR_VERDE_Z_ORDER.length - 1]).toBe('pilar_verde_bpa');
  });

  it('is a readonly tuple — length matches the 5 Pilar Verde layers', () => {
    expect(PILAR_VERDE_Z_ORDER.length).toBe(5);
  });
});

describe('pilarVerdeLayers · paint factories', () => {
  it('bpa fill: amber/yellow @ 0.40 opacity', () => {
    const paint = buildBpaFillPaint();
    expect(paint['fill-color']).toBe('#FACC15');
    expect(paint['fill-opacity']).toBe(0.4);
  });

  it('bpa line: amber 1.5 px', () => {
    const paint = buildBpaLinePaint();
    expect(paint['line-color']).toBe('#FACC15');
    expect(paint['line-width']).toBe(1.5);
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

  it('porcentaje forestacion fill: violet @ 0.15 opacity — lowest, background context', () => {
    const paint = buildPorcentajeForestacionFillPaint();
    expect(paint['fill-color']).toBe('#A78BFA');
    expect(paint['fill-opacity']).toBe(0.15);
  });
});
