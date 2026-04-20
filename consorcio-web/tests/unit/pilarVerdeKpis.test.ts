/**
 * pilarVerdeKpis.test.ts
 *
 * Unit tests for the PURE Pilar Verde KPI helpers that drive `PilarVerdeWidget`.
 *
 * Target module: `src/components/admin/pilarVerdeWidget/computeKpis.ts`
 *
 * These helpers are the Phase 4 Stryker target (≥85%). Tests are TIGHT:
 *   - boundary equality (aceptada=0 with presentada=0 → no NaN)
 *   - arithmetic pinning (values come straight from the pinned fixture)
 *   - sentinel return shape when aggregate slices are null/undefined
 *
 * All input is pulled from the FROZEN fixture
 * `tests/fixtures/pilarVerdeAggregates.json` which is a byte-identical copy of
 * the real ETL output. If the fixture drifts, the tests drift WITH IT — pinning
 * both the ETL schema and the widget's rendering contract.
 */

import { describe, expect, it } from 'vitest';

import {
  type KpiPair,
  computeBpaKpis,
  computeHistoricalKpis,
  computeLeyForestalKpis,
  humanizePracticaLabel,
} from '../../src/components/admin/pilarVerdeWidget/computeKpis';
import type { AggregatesBpa, AggregatesLeyForestal } from '../../src/types/pilarVerde';
import pilarVerdeAggregatesFixture from '../fixtures/pilarVerdeAggregates';

const FIXTURE = pilarVerdeAggregatesFixture;

// ---------------------------------------------------------------------------
// computeLeyForestalKpis
// ---------------------------------------------------------------------------

describe('computeLeyForestalKpis()', () => {
  it('projects the two-track ley_forestal slice verbatim from the fixture', () => {
    const kpis = computeLeyForestalKpis(FIXTURE.ley_forestal);
    // Real ETL values — pinned to the 2026-04-20 real run.
    expect(kpis.cumplen.parcelas).toBe(252);
    expect(kpis.cumplen.superficie_ha).toBe(27967.6);
    expect(kpis.noCumplen.parcelas).toBe(511);
    expect(kpis.noCumplen.superficie_ha).toBe(36252.1);
    expect(kpis.pctParcelas).toBe(33.0);
    expect(kpis.pctSuperficie).toBe(43.5);
  });

  it('returns the sentinel shape when input is null', () => {
    const kpis = computeLeyForestalKpis(null);
    expect(kpis.cumplen).toEqual<KpiPair>({ parcelas: null, superficie_ha: null });
    expect(kpis.noCumplen).toEqual<KpiPair>({ parcelas: null, superficie_ha: null });
    expect(kpis.pctParcelas).toBeNull();
    expect(kpis.pctSuperficie).toBeNull();
  });

  it('returns the sentinel shape when input is undefined', () => {
    const kpis = computeLeyForestalKpis(undefined);
    expect(kpis.cumplen.parcelas).toBeNull();
    expect(kpis.pctSuperficie).toBeNull();
  });

  it('never emits NaN when both counts are zero', () => {
    const zero: AggregatesLeyForestal = {
      aceptada_count: 0,
      presentada_count: 0,
      no_inscripta_count: 0,
      aceptada_superficie_ha: 0,
      presentada_superficie_ha: 0,
      cumplimiento_pct_parcelas: 0,
      cumplimiento_pct_superficie: 0,
    };
    const kpis = computeLeyForestalKpis(zero);
    expect(kpis.pctParcelas).toBe(0);
    expect(kpis.pctSuperficie).toBe(0);
    expect(kpis.cumplen.parcelas).toBe(0);
    expect(kpis.noCumplen.superficie_ha).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// computeBpaKpis
// ---------------------------------------------------------------------------

describe('computeBpaKpis()', () => {
  it('returns explotaciones_activas, superficie, top adoptada/no-adoptada from the fixture', () => {
    const kpis = computeBpaKpis(FIXTURE.bpa);
    expect(kpis.activas).toBe(70);
    expect(kpis.superficieHa).toBe(6097.3);
    expect(kpis.topAdoptada).toEqual({ nombre: 'rotacion_gramineas', pct: 92.9 });
    expect(kpis.topNoAdoptada).toEqual({ nombre: 'sistema_terraza', pct: 0.0 });
  });

  it('returns the sentinel shape when input is null', () => {
    const kpis = computeBpaKpis(null);
    expect(kpis.activas).toBeNull();
    expect(kpis.superficieHa).toBeNull();
    expect(kpis.topAdoptada).toBeNull();
    expect(kpis.topNoAdoptada).toBeNull();
  });

  it('returns the sentinel shape when input is undefined', () => {
    const kpis = computeBpaKpis(undefined);
    expect(kpis.activas).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// computeHistoricalKpis
// ---------------------------------------------------------------------------

describe('computeHistoricalKpis()', () => {
  it('projects the v1.1 historical fields from the fixture', () => {
    const kpis = computeHistoricalKpis(FIXTURE.bpa);
    expect(kpis.historicaCount).toBe(228);
    expect(kpis.historicaPct).toBe(17.2);
    expect(kpis.abandonaronCount).toBe(158);
    expect(kpis.abandonaronPct).toBe(12.0);
    expect(kpis.nuncaCount).toBe(1094);
    expect(kpis.evolucion).toEqual([
      { year: '2019', count: 122 },
      { year: '2020', count: 103 },
      { year: '2021', count: 96 },
      { year: '2022', count: 101 },
      { year: '2023', count: 80 },
      { year: '2024', count: 106 },
      { year: '2025', count: 70 },
    ]);
  });

  it('returns the sentinel shape when input is null', () => {
    const kpis = computeHistoricalKpis(null);
    expect(kpis.historicaCount).toBeNull();
    expect(kpis.historicaPct).toBeNull();
    expect(kpis.abandonaronCount).toBeNull();
    expect(kpis.abandonaronPct).toBeNull();
    expect(kpis.nuncaCount).toBeNull();
    expect(kpis.evolucion).toEqual([]);
  });

  it('returns a sentinel shape when input is undefined', () => {
    const kpis = computeHistoricalKpis(undefined);
    expect(kpis.evolucion).toEqual([]);
  });

  it('orders evolucion strictly by year ascending even if input order differs', () => {
    const scrambled: AggregatesBpa = {
      ...FIXTURE.bpa,
      evolucion_anual: {
        '2025': 70,
        '2019': 122,
        '2020': 103,
        '2021': 96,
        '2022': 101,
        '2023': 80,
        '2024': 106,
      },
    };
    const kpis = computeHistoricalKpis(scrambled);
    expect(kpis.evolucion.map((e) => e.year)).toEqual([
      '2019',
      '2020',
      '2021',
      '2022',
      '2023',
      '2024',
      '2025',
    ]);
    expect(kpis.evolucion[0].count).toBe(122);
    expect(kpis.evolucion[6].count).toBe(70);
  });
});

// ---------------------------------------------------------------------------
// humanizePracticaLabel
// ---------------------------------------------------------------------------

describe('humanizePracticaLabel()', () => {
  it('delegates to bpaPracticas.humanizePractica for known keys', () => {
    expect(humanizePracticaLabel('rotacion_gramineas')).toBe('Rotación de gramíneas');
    expect(humanizePracticaLabel('sistema_terraza')).toBe('Sistema de terrazas');
  });

  it('returns the em dash sentinel for null practice names', () => {
    expect(humanizePracticaLabel(null)).toBe('—');
  });

  it('returns the em dash sentinel for undefined practice names', () => {
    expect(humanizePracticaLabel(undefined)).toBe('—');
  });
});
