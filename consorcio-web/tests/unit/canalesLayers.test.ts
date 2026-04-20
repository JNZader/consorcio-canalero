/**
 * canalesLayers.test.ts
 *
 * Unit tests for the Pilar Azul (Canales) colocated registry:
 *   - CANALES_COLORS palette (relevado / propuesto families + outlines)
 *   - CANALES_Z_ORDER — relevados BELOW propuestos in documentation, but the
 *     tuple follows the "iterate-and-moveLayer" convention (later wins the
 *     render order, matching `PILAR_VERDE_Z_ORDER`).
 *   - Paint factories: `match` on `source_style` (relevados) / `prioridad`
 *     (propuestos), dashed line for propuestos, solid line for relevados.
 *   - Filter builders: `buildCanalesRelevadosFilter`, `buildCanalesPropuestasFilter`.
 */

import { describe, expect, it } from 'vitest';

import {
  CANALES_COLORS,
  CANALES_Z_ORDER,
  buildCanalesPropuestasFilter,
  buildCanalesPropuestasPaint,
  buildCanalesRelevadosFilter,
  buildCanalesRelevadosPaint,
} from '../../src/components/map2d/canalesLayers';

describe('canalesLayers · colors', () => {
  it('exposes the 3 relevado family hexes', () => {
    expect(CANALES_COLORS.relevadoSinObra).toBe('#1D4ED8'); // blue-700
    expect(CANALES_COLORS.relevadoReadec).toBe('#3B82F6'); // blue-500
    expect(CANALES_COLORS.relevadoAsociada).toBe('#60A5FA'); // blue-400
  });

  it('exposes the 5 propuesto family hexes keyed by etapa', () => {
    expect(CANALES_COLORS.propuestoAlta).toBe('#DC2626'); // red-600
    expect(CANALES_COLORS.propuestoMediaAlta).toBe('#EA580C'); // orange-600
    expect(CANALES_COLORS.propuestoMedia).toBe('#CA8A04'); // yellow-600
    expect(CANALES_COLORS.propuestoOpcional).toBe('#64748B'); // slate-500
    expect(CANALES_COLORS.propuestoLargoPlazo).toBe('#94A3B8'); // slate-400
  });

  it('exposes outline color families', () => {
    // Outline keys exist (color values are implementation-free — just exist).
    expect(typeof CANALES_COLORS.outlineRelevado).toBe('string');
    expect(typeof CANALES_COLORS.outlinePropuesto).toBe('string');
  });
});

describe('canalesLayers · z-order', () => {
  it('relevados appears BEFORE propuestos in the z-order tuple', () => {
    expect(CANALES_Z_ORDER[0]).toBe('canales_relevados');
    expect(CANALES_Z_ORDER[1]).toBe('canales_propuestos');
    expect(CANALES_Z_ORDER).toHaveLength(2);
  });
});

describe('canalesLayers · relevados paint', () => {
  it('returns a MapLibre line paint with `match` expression on source_style', () => {
    const paint = buildCanalesRelevadosPaint();
    expect(paint['line-width']).toBe(3);

    const color = paint['line-color'] as unknown as unknown[];
    expect(Array.isArray(color)).toBe(true);
    expect(color[0]).toBe('match');
    expect(color[1]).toEqual(['get', 'source_style']);
    // 3 known source_style keys map to the 3 blue hexes
    expect(color).toContain('sin_obra');
    expect(color).toContain(CANALES_COLORS.relevadoSinObra);
    expect(color).toContain('readec');
    expect(color).toContain(CANALES_COLORS.relevadoReadec);
    expect(color).toContain('asociada');
    expect(color).toContain(CANALES_COLORS.relevadoAsociada);
  });

  it('relevados paint has NO `line-dasharray` (solid line)', () => {
    const paint = buildCanalesRelevadosPaint();
    expect(paint).not.toHaveProperty('line-dasharray');
  });
});

describe('canalesLayers · propuestas paint', () => {
  it('returns a MapLibre line paint with `match` on prioridad + dashed line', () => {
    const paint = buildCanalesPropuestasPaint();
    expect(paint['line-width']).toBe(2.5);
    expect(paint['line-dasharray']).toEqual([4, 2]);

    const color = paint['line-color'] as unknown as unknown[];
    expect(Array.isArray(color)).toBe(true);
    expect(color[0]).toBe('match');
    expect(color[1]).toEqual(['get', 'prioridad']);
    // 5 etapas → 5 hexes
    expect(color).toContain('Alta');
    expect(color).toContain(CANALES_COLORS.propuestoAlta);
    expect(color).toContain('Media-Alta');
    expect(color).toContain(CANALES_COLORS.propuestoMediaAlta);
    expect(color).toContain('Media');
    expect(color).toContain(CANALES_COLORS.propuestoMedia);
    expect(color).toContain('Opcional');
    expect(color).toContain(CANALES_COLORS.propuestoOpcional);
    expect(color).toContain('Largo plazo');
    expect(color).toContain(CANALES_COLORS.propuestoLargoPlazo);
  });
});

describe('canalesLayers · filter builders', () => {
  it('buildCanalesRelevadosFilter wraps the visible slugs in an `in` expression', () => {
    const filter = buildCanalesRelevadosFilter(['slug-a', 'slug-b']);
    expect(filter).toEqual(['in', ['get', 'id'], ['literal', ['slug-a', 'slug-b']]]);
  });

  it('buildCanalesRelevadosFilter empty list yields an `in` over an empty literal', () => {
    const filter = buildCanalesRelevadosFilter([]);
    expect(filter).toEqual(['in', ['get', 'id'], ['literal', []]]);
  });

  it('buildCanalesPropuestasFilter combines per-id + active-etapas via ["all", ...]', () => {
    const filter = buildCanalesPropuestasFilter(['slug-x', 'slug-y'], ['Alta', 'Media']);
    expect(Array.isArray(filter)).toBe(true);
    expect(filter[0]).toBe('all');
    // first child = id filter
    expect(filter[1]).toEqual(['in', ['get', 'id'], ['literal', ['slug-x', 'slug-y']]]);
    // second child = etapa filter
    expect(filter[2]).toEqual(['in', ['get', 'prioridad'], ['literal', ['Alta', 'Media']]]);
  });

  it('buildCanalesPropuestasFilter with empty etapa list still yields a valid expression', () => {
    const filter = buildCanalesPropuestasFilter(['slug-x'], []);
    expect(filter[0]).toBe('all');
    expect(filter[2]).toEqual(['in', ['get', 'prioridad'], ['literal', []]]);
  });
});
