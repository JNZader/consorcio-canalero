/**
 * bpaPracticas.test.ts
 *
 * Unit tests for the Pilar Verde practice helpers — these are the pure-function
 * Stryker mutation target for Phase 3. They must stay 100% side-effect free.
 *
 * Coverage:
 *   - PRACTICAS_SORTED  → 21 unique keys, alphabetically sorted
 *   - humanizePractica  → Rioplatense label for every key (no English leftovers)
 *   - normalizeBpaFlat  → converts the flat GeoJSON `Bpa2025FeatureProperties` shape
 *     into the nested `Bpa2025EnrichedRecord` shape used by `<BpaCard>`. Tight
 *     null / missing / string-numeric handling so mutations can't slip through.
 *   - adoptedCount     → integer count of practices flagged "Si"
 *   - sortPracticasByAdopcion → optional ranking helper (Task 3.8 REFACTOR)
 *
 * The helpers are kept in a dedicated module so:
 *   (a) Stryker can mutation-test them in isolation (≥85% target per tasks.md 3.7)
 *   (b) <BpaCard> stays thin — ideally just layout + the results of these calls.
 */

import { describe, expect, it } from 'vitest';

import {
  adoptedCount,
  humanizePractica,
  normalizeBpaFlat,
  PRACTICAS_SORTED,
  sortPracticasByAdopcion,
} from '../../src/components/map2d/bpaPracticas';
import type {
  Bpa2025EnrichedRecord,
  Bpa2025FeatureProperties,
  BpaPracticesRecord,
  PilarVerdePracticaKey,
} from '../../src/types/pilarVerde';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function buildAllNoPractices(): BpaPracticesRecord {
  return {
    capacitacion: 'No',
    tranqueras_abiertas: 'No',
    polinizacion: 'No',
    integ_comunidad: 'No',
    nutricion_suelo: 'No',
    rotacion_gramineas: 'No',
    pasturas_implantadas: 'No',
    sistema_terraza: 'No',
    bioinsumos: 'No',
    manejo_de_cultivo_int: 'No',
    trazabilidad: 'No',
    tecn_pecuaria: 'No',
    agricultura_de_precision: 'No',
    economia_circular: 'No',
    participacion_grup_asociativo: 'No',
    indiacagro: 'No',
    caminos_rurales: 'No',
    ag_tech: 'No',
    bpa_tutor: 'No',
    corredores_bio: 'No',
    riego_precision: 'No',
  };
}

/**
 * Fully populated flat feature properties, matching the real
 * `bpa_2025.geojson` schema (flat eje_*, flat practica keys, activa as "1"/"0"
 * string, bpa_total as a string).
 */
function buildFlatProps(
  overrides: Partial<Bpa2025FeatureProperties> = {},
): Bpa2025FeatureProperties {
  return {
    n_explotacion: 'La Sentina',
    cuenta: '150115736126',
    superficie: 245.7,
    superficie_bpa: 245.7,
    bpa_total: '8',
    id_explotacion: '1010',
    activa: '1',
    eje_persona: 'Si',
    eje_planeta: 'Si',
    eje_prosperidad: 'No',
    eje_alianza: 'No',
    capacitacion: 'Si',
    tranqueras_abiertas: 'No',
    polinizacion: 'No',
    integ_comunidad: 'No',
    nutricion_suelo: 'Si',
    rotacion_gramineas: 'Si',
    pasturas_implantadas: 'No',
    sistema_terraza: 'No',
    bioinsumos: 'No',
    manejo_de_cultivo_int: 'No',
    trazabilidad: 'No',
    tecn_pecuaria: 'No',
    agricultura_de_precision: 'No',
    economia_circular: 'No',
    participacion_grup_asociativo: 'No',
    indiacagro: 'No',
    caminos_rurales: 'No',
    ag_tech: 'No',
    bpa_tutor: 'No',
    corredores_bio: 'No',
    riego_precision: 'No',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// PRACTICAS_SORTED
// ---------------------------------------------------------------------------

describe('PRACTICAS_SORTED', () => {
  it('has exactly 21 entries', () => {
    expect(PRACTICAS_SORTED).toHaveLength(21);
  });

  it('contains only unique keys (no duplicates)', () => {
    const set = new Set<string>(PRACTICAS_SORTED);
    expect(set.size).toBe(21);
  });

  it('is sorted alphabetically (locale-independent, stable, ascending)', () => {
    const copy = [...PRACTICAS_SORTED];
    const expected = [...PRACTICAS_SORTED].sort((a, b) => a.localeCompare(b));
    expect(copy).toEqual(expected);
  });

  it('first key is "ag_tech" and last is "trazabilidad" (guards against swaps)', () => {
    // ag_tech comes first because '_' sorts before letters in localeCompare.
    // trazabilidad comes last because 'traz' > 'tran' (n < z), and it beats
    // any other key whose prefix is ahead of 'tr'.
    expect(PRACTICAS_SORTED[0]).toBe('ag_tech');
    expect(PRACTICAS_SORTED[PRACTICAS_SORTED.length - 1]).toBe('trazabilidad');
  });
});

// ---------------------------------------------------------------------------
// humanizePractica
// ---------------------------------------------------------------------------

describe('humanizePractica', () => {
  const EXPECTED: Record<PilarVerdePracticaKey, string> = {
    capacitacion: 'Capacitación',
    tranqueras_abiertas: 'Tranqueras abiertas',
    polinizacion: 'Polinización',
    integ_comunidad: 'Integración con la comunidad',
    nutricion_suelo: 'Nutrición del suelo',
    rotacion_gramineas: 'Rotación de gramíneas',
    pasturas_implantadas: 'Pasturas implantadas',
    sistema_terraza: 'Sistema de terrazas',
    bioinsumos: 'Bioinsumos',
    manejo_de_cultivo_int: 'Manejo integrado de cultivos',
    trazabilidad: 'Trazabilidad',
    tecn_pecuaria: 'Tecnología pecuaria',
    agricultura_de_precision: 'Agricultura de precisión',
    economia_circular: 'Economía circular',
    participacion_grup_asociativo: 'Participación en grupo asociativo',
    indiacagro: 'IndicAgro',
    caminos_rurales: 'Caminos rurales',
    ag_tech: 'AgTech',
    bpa_tutor: 'Tutor BPA',
    corredores_bio: 'Corredores biológicos',
    riego_precision: 'Riego de precisión',
  };

  it.each(Object.entries(EXPECTED))('maps %s → "%s"', (key, label) => {
    expect(humanizePractica(key as PilarVerdePracticaKey)).toBe(label);
  });

  it('returns a non-empty string for every sorted key (no undefined labels)', () => {
    for (const k of PRACTICAS_SORTED) {
      const label = humanizePractica(k);
      expect(typeof label).toBe('string');
      expect(label.length).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// normalizeBpaFlat
// ---------------------------------------------------------------------------

describe('normalizeBpaFlat', () => {
  it('returns a nested Bpa2025EnrichedRecord for a fully populated flat input', () => {
    const props = buildFlatProps();
    const result = normalizeBpaFlat(props);
    expect(result).not.toBeNull();
    const nested = result as Bpa2025EnrichedRecord;
    expect(nested.n_explotacion).toBe('La Sentina');
    expect(nested.superficie_bpa).toBe(245.7);
    expect(nested.bpa_total).toBe('8');
    expect(nested.id_explotacion).toBe('1010');
    expect(nested.activa).toBe(true);
    expect(nested.ejes).toEqual({
      persona: 'Si',
      planeta: 'Si',
      prosperidad: 'No',
      alianza: 'No',
    });
    expect(nested.practicas.capacitacion).toBe('Si');
    expect(nested.practicas.rotacion_gramineas).toBe('Si');
    expect(nested.practicas.nutricion_suelo).toBe('Si');
    expect(nested.practicas.tranqueras_abiertas).toBe('No');
    expect(Object.keys(nested.practicas)).toHaveLength(21);
  });

  it('returns null when bpa_total is missing (not a BPA feature)', () => {
    const props = { cuenta: '999' } as unknown as Record<string, unknown>;
    expect(normalizeBpaFlat(props)).toBeNull();
  });

  it('returns null when bpa_total is explicitly null', () => {
    const props = {
      ...buildFlatProps(),
      bpa_total: null as unknown as string,
    } as Record<string, unknown>;
    expect(normalizeBpaFlat(props)).toBeNull();
  });

  it('returns null when bpa_total is undefined', () => {
    const props = {
      ...buildFlatProps(),
      bpa_total: undefined as unknown as string,
    } as Record<string, unknown>;
    expect(normalizeBpaFlat(props)).toBeNull();
  });

  it('normalizes activa="1" string to boolean true', () => {
    const result = normalizeBpaFlat(buildFlatProps({ activa: '1' }));
    expect(result?.activa).toBe(true);
  });

  it('normalizes activa=1 numeric to boolean true', () => {
    const props = { ...buildFlatProps(), activa: 1 } as unknown as Record<string, unknown>;
    const result = normalizeBpaFlat(props);
    expect(result?.activa).toBe(true);
  });

  it('normalizes activa="0" string to boolean false', () => {
    const result = normalizeBpaFlat(buildFlatProps({ activa: '0' }));
    expect(result?.activa).toBe(false);
  });

  it('treats missing practice keys as "No" (defensive default)', () => {
    const props = { ...buildFlatProps() } as Record<string, unknown>;
    // Remove one practice key entirely to simulate a malformed feature.
    delete props.capacitacion;
    const result = normalizeBpaFlat(props);
    expect(result?.practicas.capacitacion).toBe('No');
  });

  it('treats missing eje keys as "No" (defensive default)', () => {
    const props = { ...buildFlatProps() } as Record<string, unknown>;
    delete props.eje_persona;
    const result = normalizeBpaFlat(props);
    expect(result?.ejes.persona).toBe('No');
  });

  it('coerces bpa_total to string (real GeoJSON stores it as a string)', () => {
    const props = { ...buildFlatProps(), bpa_total: 8 } as unknown as Record<string, unknown>;
    const result = normalizeBpaFlat(props);
    expect(result?.bpa_total).toBe('8');
  });

  it('preserves superficie_bpa as a number', () => {
    const result = normalizeBpaFlat(buildFlatProps({ superficie_bpa: 100 }));
    expect(result?.superficie_bpa).toBe(100);
  });
});

// ---------------------------------------------------------------------------
// adoptedCount
// ---------------------------------------------------------------------------

describe('adoptedCount', () => {
  it('returns 0 when no practices are adopted', () => {
    expect(adoptedCount(buildAllNoPractices())).toBe(0);
  });

  it('returns 21 when ALL practices are adopted', () => {
    const all: BpaPracticesRecord = Object.fromEntries(
      PRACTICAS_SORTED.map((k) => [k, 'Si']),
    ) as BpaPracticesRecord;
    expect(adoptedCount(all)).toBe(21);
  });

  it('counts only Si values (3 Si → 3)', () => {
    const p = buildAllNoPractices();
    p.capacitacion = 'Si';
    p.bioinsumos = 'Si';
    p.riego_precision = 'Si';
    expect(adoptedCount(p)).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// sortPracticasByAdopcion (Task 3.8 REFACTOR)
// ---------------------------------------------------------------------------

describe('sortPracticasByAdopcion', () => {
  it('returns Si keys first (alphabetical) then No keys (alphabetical)', () => {
    const p = buildAllNoPractices();
    p.bioinsumos = 'Si';
    p.capacitacion = 'Si';
    p.riego_precision = 'Si';
    const sorted = sortPracticasByAdopcion(p);
    // First three should be Si-values, alphabetically sorted among themselves
    expect(sorted.slice(0, 3)).toEqual(['bioinsumos', 'capacitacion', 'riego_precision']);
    // All 21 keys present
    expect(sorted).toHaveLength(21);
    expect(new Set(sorted).size).toBe(21);
    // Remaining 18 are No values, alphabetical
    const remaining = sorted.slice(3);
    const expectedRemaining = [...remaining].sort((a, b) => a.localeCompare(b));
    expect(remaining).toEqual(expectedRemaining);
  });

  it('when all are No, returns the same alphabetical order as PRACTICAS_SORTED', () => {
    expect(sortPracticasByAdopcion(buildAllNoPractices())).toEqual([...PRACTICAS_SORTED]);
  });
});
