/**
 * rainfallFormat.test.ts  (Lluvia v2 — Task 3.1 RED)
 *
 * Shared state/value formatting used by BOTH the rendered ficha and the export
 * summary (Task 3.4): one formatter, so the badge a user reads and the text the
 * CSV carries can never disagree. Null is never rendered as zero (spec
 * "Partial, Suppressed, and Unavailable Data States").
 */

import { describe, expect, it } from 'vitest';

import type {
  RainfallAnalysisSnapshot,
  RainfallMetric,
  RainfallScopeChoice,
} from '../../src/lib/api/rainfall';
import {
  compactAntecedent,
  deriveFreshness,
  describeMetricState,
  formatMetricValue,
  metricLabel,
  metricStateLabel,
  scopeChoiceLabel,
  scopeChoiceLabels,
  shouldUseSegmentedScope,
  wetnessFromPercentile,
  wetnessLabel,
} from '../../src/components/map2d/rainfall/rainfallFormat';

function metric(overrides: Partial<RainfallMetric> = {}): RainfallMetric {
  return {
    metric: 'selected',
    value: 850.24,
    unit: 'mm',
    state: 'available',
    reason: null,
    interval_start: '2025-01-01T00:00:00Z',
    interval_end: '2026-01-01T00:00:00Z',
    coverage: 1,
    completeness: 1,
    quality: { score: 0.9 },
    discrepancies: [],
    temporal_state: 'final',
    revision: 'policy-v1',
    provenance: {
      source_id: 'chirps-v3-final',
      source_class: 'estimated_satellite',
      method: 'sum',
      nominal_resolution: '0.05°',
      aggregation: 'daily',
      spatial_scope: 'zone',
      freshness: '2026-01-02T00:00:00Z',
      available_through: '2025-12-31T00:00:00Z',
    },
    fallback_used: false,
    ...overrides,
  };
}

describe('metricLabel', () => {
  it('labels the known metrics in Spanish', () => {
    expect(metricLabel('selected')).toBe('Acumulado del año');
    expect(metricLabel('d30')).toBe('Antecedente 30 días');
    expect(metricLabel('duration')).toBe('Duración del evento');
  });

  it('appends the SERVED baseline to the normal label, never a constant', () => {
    // RISK-001/LI4-004: regenerating the normals over another period must move
    // this label with no frontend edit involved.
    expect(metricLabel('normal', '1991-2020')).toBe('Normal 1991-2020');
    expect(metricLabel('normal', '2001-2030')).toBe('Normal 2001-2030');
  });

  it('names the metric without a period when no baseline is served', () => {
    // Honest degradation: a period-less "Normal" states what the metric IS.
    // Defaulting to a hardcoded period would assert a baseline the server
    // never sent — the defect itself, wearing a fallback's clothes.
    expect(metricLabel('normal')).toBe('Normal');
    expect(metricLabel('normal', '')).toBe('Normal');
    expect(metricLabel('normal', null)).toBe('Normal');
  });

  it('falls back to the raw key for an unknown metric', () => {
    expect(metricLabel('p95')).toBe('p95');
  });
});

describe('formatMetricValue', () => {
  it('formats value and unit, never inventing a zero for null', () => {
    expect(formatMetricValue(metric())).toBe('850.2 mm');
    expect(
      formatMetricValue(metric({ value: null, state: 'unavailable', reason: 'sin fuente' }))
    ).toBe('—');
    // A SERVED zero is data and must survive.
    expect(formatMetricValue(metric({ value: 0 }))).toBe('0.0 mm');
  });
});

describe('describeMetricState', () => {
  it('distinguishes the four states, carrying the reason where applicable', () => {
    expect(describeMetricState(metric())).toBe('Disponible');
    expect(describeMetricState(metric({ state: 'partial', coverage: 0.8 }))).toBe('Parcial');
    expect(
      describeMetricState(
        metric({ state: 'suppressed', value: null, reason: 'coverage_below_threshold' })
      )
    ).toBe('Suprimida: coverage_below_threshold');
    expect(
      describeMetricState(metric({ state: 'unavailable', value: null, reason: 'sin fuente' }))
    ).toBe('No disponible: sin fuente');
  });

  it('never renders suppressed or unavailable as zero or as a bare label', () => {
    const text = describeMetricState(
      metric({ state: 'suppressed', value: null, reason: 'cadence_unsupported' })
    );
    expect(text).not.toContain('0');
    expect(text).toContain('cadence_unsupported');
  });
});

/** A percentile metric — the ONLY input the interpretive label may read (R2). */
function percentile(overrides: Partial<RainfallMetric> = {}): RainfallMetric {
  return metric({ metric: 'percentile', unit: 'percentil', ...overrides });
}

describe('wetnessFromPercentile — every published cut-off from both sides', () => {
  // The published vocabulary (design D4, owner-ratified 2026-08-11) applied to
  // the ALREADY-rounded percentile — the same `Math.round` `percentilePhrase`
  // uses, because the card prints both and "Percentil 70 · año normal" is a
  // card contradicting itself. Every boundary is pinned from BOTH sides,
  // rounding included: a one-sided table passes a rounding error at the cut-off
  // it was supposed to guard (UXJA-009).
  it.each([
    [0, 'muy_seco'],
    [10, 'muy_seco'],
    [10.4, 'muy_seco'],
    [10.6, 'seco'],
    [30, 'seco'],
    [30.4, 'seco'],
    [30.6, 'normal'],
    [50, 'normal'],
    [69.4, 'normal'],
    [69.6, 'humedo'],
    [70, 'humedo'],
    [89, 'humedo'],
    [89.4, 'humedo'],
    [89.6, 'muy_humedo'],
    [90, 'muy_humedo'],
    [100, 'muy_humedo'],
  ])('percentile %s is %s', (value, expected) => {
    expect(wetnessFromPercentile(percentile({ value }))).toBe(expected);
  });

  it('derives no label when the percentile is not a served number', () => {
    // R2 + "Partial, Suppressed, and Unavailable Data States": an absent rank
    // is not a normal year, and a suppressed one is not a dry year. The label
    // is the loudest thing on the card, so it says NOTHING rather than guess.
    expect(wetnessFromPercentile(percentile({ value: null, state: 'unavailable' }))).toBeNull();
    expect(
      wetnessFromPercentile(
        percentile({ value: null, state: 'suppressed', reason: 'baseline_years_below_minimum' })
      )
    ).toBeNull();
    expect(wetnessFromPercentile(undefined)).toBeNull();
  });

  it('refuses a state-suppressed metric even if a value survived beside it', () => {
    // Defence in depth against a server that blanks the state but not the
    // number: the state is the disclosure decision, and a value the policy
    // withheld must not reappear as an adjective.
    expect(
      wetnessFromPercentile(percentile({ value: 95, state: 'suppressed', reason: 'policy' }))
    ).toBeNull();
    expect(
      wetnessFromPercentile(percentile({ value: 95, state: 'unavailable', reason: 'sin fuente' }))
    ).toBeNull();
  });

  it('keeps a served 0 as the driest label, never as a missing value', () => {
    // The driest year on record ranks at the bottom. That IS data.
    expect(wetnessFromPercentile(percentile({ value: 0 }))).toBe('muy_seco');
  });
});

describe('wetnessLabel', () => {
  it('publishes the user-visible vocabulary for every derived value', () => {
    expect(wetnessLabel('muy_seco')).toBe('muy seco');
    expect(wetnessLabel('seco')).toBe('seco');
    expect(wetnessLabel('normal')).toBe('normal');
    expect(wetnessLabel('humedo')).toBe('húmedo');
    expect(wetnessLabel('muy_humedo')).toBe('muy húmedo');
  });
});

function snapshot(overrides: Partial<RainfallAnalysisSnapshot> = {}): RainfallAnalysisSnapshot {
  return {
    analysis_revision_id: 'rev-9',
    data_revision: 'ab'.repeat(32),
    scope: { kind: 'zone', id: 'zona-ne', version: '3' },
    regional_estimate: true,
    year: 2025,
    comparison_end: '2025-12-31',
    baseline: '1991-2020',
    annual: { selected: metric({ metric: 'selected', value: 850.24 }) },
    ...overrides,
  };
}

/**
 * `service._unavailable`'s STRIPPED four-field shape (`service.py:466-472`):
 * `metric`/`value`/`state`/`reason` and nothing else — no `provenance`, no
 * `coverage`, no `interval_*`. Cast through `unknown` on purpose: the wire
 * really does serve this shape and `RainfallMetric` really does not describe
 * it, which is exactly why the gate has a third branch.
 */
function strippedMetric(reason: string): RainfallMetric {
  return {
    metric: 'selected',
    value: null,
    state: 'unavailable',
    reason,
  } as unknown as RainfallMetric;
}

describe('deriveFreshness — the three-branch evidence gate', () => {
  it('(a) states the analysis last day with evidence when the analysis carries some', () => {
    // `available_through` is the EXCLUSIVE window end, so the day WITH evidence
    // is the one before it — the same conversion the chart footer applies to
    // the series, reused rather than re-derived (R3, design D10).
    const freshness = deriveFreshness(snapshot());

    expect(freshness.kind).toBe('evidenced');
    expect(freshness.evidenceDay).toBe('2025-12-30');
    expect(freshness.sentence).toBe('Evidencia publicada hasta el 2025-12-30');
  });

  it('(b) keeps the real date for a metric SUPPRESSED by policy', () => {
    // UXJA-101 ≡ UXJB-101, the defect this gate exists for. `apply_metric_policy`
    // suppresses a metric for `coverage_below_threshold` while `_normalize_metric`
    // keeps its coverage, provenance and intervals — so a state-keyed gate would
    // print "no published evidence" directly above a chart footer declaring
    // evidence through the SAME day. Suppression is about whether the NUMBER may
    // be shown, never about whether days were measured.
    const freshness = deriveFreshness(
      snapshot({
        annual: {
          selected: metric({
            metric: 'selected',
            value: null,
            state: 'suppressed',
            reason: 'coverage_below_threshold',
            coverage: 0.62,
          }),
        },
      })
    );

    expect(freshness.kind).toBe('evidenced');
    expect(freshness.evidenceDay).toBe('2025-12-30');
    expect(freshness.sentence).toBe('Evidencia publicada hasta el 2025-12-30');
    expect(freshness.sentence).not.toMatch(/Sin días/);
  });

  it('(c) claims no evidence ONLY for a genuinely empty disclosure window', () => {
    // JDB-103 one layer up: with zero published intervals the window falls back
    // to `comparison_end + 1 day`, so `available_through` is present and
    // plausible-looking. `no_data_in_disclosure_window` (compute.py:649-650) is
    // the ONE server fact that means nothing was published.
    const freshness = deriveFreshness(
      snapshot({
        annual: {
          selected: metric({
            metric: 'selected',
            value: null,
            state: 'unavailable',
            reason: 'no_data_in_disclosure_window',
            coverage: 0,
            provenance: {
              ...metric().provenance,
              // The fallback bound: comparison_end + 1 day.
              available_through: '2026-01-01T00:00:00Z',
            },
          }),
        },
      })
    );

    expect(freshness.kind).toBe('no_evidence');
    expect(freshness.evidenceDay).toBeNull();
    expect(freshness.sentence).toBe('Sin días con evidencia publicada en este análisis');
    // The fallback bound must never surface as a day, in any spelling.
    expect(freshness.sentence).not.toContain('2025-12-31');
    expect(freshness.sentence).not.toContain('2026-01-01');
  });

  it('(d) asserts NEITHER claim when the analysis carries no evidence facts', () => {
    // Two shapes reach the indeterminate branch, and the point of the branch is
    // that it claims nothing: no date (there is no source for one) and no
    // no-evidence sentence (nothing proves the window was empty).
    const stripped = deriveFreshness(
      snapshot({ annual: { selected: strippedMetric('metric_contract_rejected') } })
    );
    expect(stripped.kind).toBe('unknown');
    expect(stripped.evidenceDay).toBeNull();
    expect(stripped.sentence).toBe('Frescura no disponible en este análisis');
    expect(stripped.sentence).not.toMatch(/Sin días/);
    // The served reason survives, so the card can carry it in title/aria-label.
    expect(stripped.reason).toBe('metric_contract_rejected');

    const absent = deriveFreshness(snapshot({ annual: {} }));
    expect(absent.kind).toBe('unknown');
    expect(absent.evidenceDay).toBeNull();
    expect(absent.sentence).toBe('Frescura no disponible en este análisis');
    expect(absent.reason).toBeNull();

    const noGroup = deriveFreshness(snapshot({ annual: undefined }));
    expect(noGroup.kind).toBe('unknown');
    expect(noGroup.evidenceDay).toBeNull();
  });

  it('(e) degrades an unparseable window bound to its own raw day instead of throwing', () => {
    // JDA-104, inherited from `lastEvidenceDay`: `toISOString()` on an invalid
    // Date raises, and the exception would take the card down over a footnote.
    const freshness = deriveFreshness(
      snapshot({
        annual: {
          selected: metric({
            metric: 'selected',
            provenance: { ...metric().provenance, available_through: 'no-es-fecha' },
          }),
        },
      })
    );

    expect(freshness.kind).toBe('evidenced');
    expect(freshness.evidenceDay).toBe('no-es-fech');
    expect(freshness.sentence).toContain('no-es-fech');
  });
});

function choice(kind: 'zone' | 'basin', id: string): RainfallScopeChoice {
  return { kind, id, version: '2024-01' };
}

describe('scopeChoiceLabel — two scopes of one kind must be tellable apart', () => {
  // OWN-001, owner screenshots: `Zona | Cuenca | Cuenca`, and a Bell Ville
  // parcel resolving to FIVE scopes as `Zona | Zona | Cuenca | Cuenca | Cuenca`.
  // The control labelled every option with its KIND, so the reader was asked to
  // choose between options that read identically — a control that cannot be
  // operated correctly, only guessed at.
  it('qualifies with the prettified id, dropping an id token that repeats the kind', () => {
    expect(scopeChoiceLabel(choice('basin', 'cuenca_sur'), true)).toBe('Cuenca · Sur');
    expect(scopeChoiceLabel(choice('zone', 'zona-ne'), true)).toBe('Zona · Ne');
    expect(scopeChoiceLabel(choice('basin', 'basin_rio_tercero_medio'), true)).toBe(
      'Cuenca · Rio Tercero Medio'
    );
  });

  it('degrades an opaque id to its own prettified text rather than dropping it', () => {
    // The repo's standing rule for an untranslated fact: show it. A blank
    // qualifier would put the reader back in front of two identical options.
    expect(scopeChoiceLabel(choice('basin', 'b-carcara-01'), true)).toBe('Cuenca · B Carcara 01');
  });

  it('states the kind alone when there is nothing left to qualify with', () => {
    expect(scopeChoiceLabel(choice('basin', 'cuenca'), true)).toBe('Cuenca');
    expect(scopeChoiceLabel(choice('zone', ''), true)).toBe('Zona');
  });

  it('stays plain when the kind is unique in the served set', () => {
    expect(scopeChoiceLabel(choice('basin', 'cuenca_sur'), false)).toBe('Cuenca');
  });
});

describe('scopeChoiceLabels — qualifies exactly the kinds that repeat', () => {
  it('leaves the ordinary zone+basin pair alone', () => {
    expect(scopeChoiceLabels([choice('zone', 'zona-ne'), choice('basin', 'cuenca_sur')])).toEqual([
      'Zona',
      'Cuenca',
    ]);
  });

  it('makes all five distinct for the five-scope parcel the owner hit', () => {
    const labels = scopeChoiceLabels([
      choice('zone', 'zona_bell_ville'),
      choice('zone', 'zona_norte'),
      choice('basin', 'cuenca_rio_tercero'),
      choice('basin', 'cuenca_algodon'),
      choice('basin', 'cuenca_litin'),
    ]);

    expect(labels).toHaveLength(5);
    expect(new Set(labels).size).toBe(5);
    expect(labels[0]).toBe('Zona · Bell Ville');
    expect(labels[2]).toBe('Cuenca · Rio Tercero');
  });
});

describe('shouldUseSegmentedScope — the control has to FIT', () => {
  it('keeps the segmented control for a short pair', () => {
    expect(shouldUseSegmentedScope(['Zona', 'Cuenca'])).toBe(true);
  });

  it('refuses more than three options, however short', () => {
    // Five segments in 348 px is the container-level version of the truncation
    // defect: every label becomes a fragment.
    expect(
      shouldUseSegmentedScope(['Zona', 'Zona · N', 'Cuenca', 'Cuenca · S', 'Cuenca · E'])
    ).toBe(false);
  });

  it('refuses three options whose labels do not fit', () => {
    expect(
      shouldUseSegmentedScope([
        'Zona · Bell Ville Norte',
        'Cuenca · Rio Tercero Medio',
        'Cuenca · Arroyo Algodon',
      ])
    ).toBe(false);
  });

  it('is a no-op for a single choice (the control does not render at all)', () => {
    expect(shouldUseSegmentedScope(['Zona'])).toBe(true);
  });
});

describe('metricStateLabel', () => {
  it('is the state WORD alone, so a badge can carry it whole', () => {
    // OWN-003: the badge used to carry `describeMetricState`, i.e. the state
    // AND its reason — "Suprimida: coverage_below_threshold" in a 348 px panel,
    // which is how the owner got `DISPONI…`. The reason keeps its own line.
    expect(metricStateLabel(metric())).toBe('Disponible');
    expect(metricStateLabel(metric({ state: 'partial' }))).toBe('Parcial');
    expect(
      metricStateLabel(metric({ state: 'suppressed', value: null, reason: 'coverage_below' }))
    ).toBe('Suprimida');
    expect(
      metricStateLabel(metric({ state: 'unavailable', value: null, reason: 'sin fuente' }))
    ).toBe('No disponible');
  });

  it('never carries a reason, an ellipsis or a separator', () => {
    for (const state of ['available', 'partial', 'suppressed', 'unavailable'] as const) {
      const label = metricStateLabel(metric({ state, reason: 'un_motivo_larguisimo_del_backend' }));
      expect(label).not.toContain('un_motivo_larguisimo_del_backend');
      expect(label).not.toMatch(/[…:]|\.\.\./);
    }
  });
});

describe('compactAntecedent', () => {
  // D2a: the collapsed `Antecedentes` header states its numbers, and
  // `formatAccumulated` cannot supply them — it is `toFixed(1) + unit`, i.e.
  // "31.0 mm", a decimal nobody reads off a header and a unit repeated three
  // times in a 348 px slot (UXJB-104 ≡ UXJA-106).
  it('rounds to a whole millimetre and carries no unit', () => {
    expect(compactAntecedent(metric({ value: 31.0 }))).toBe('31');
    expect(compactAntecedent(metric({ value: 83.7 }))).toBe('84');
    expect(compactAntecedent(metric({ value: 0 }))).toBe('0');
    for (const value of [31.0, 83.7, 0]) {
      expect(compactAntecedent(metric({ value }))).not.toContain('mm');
      expect(compactAntecedent(metric({ value }))).not.toContain('.');
    }
  });

  it('prints the unknown marker — never a zero — when there is no value to state', () => {
    expect(compactAntecedent(metric({ value: null, state: 'unavailable' }))).toBe('—');
    expect(
      compactAntecedent(
        metric({ value: null, state: 'suppressed', reason: 'coverage_below_threshold' })
      )
    ).toBe('—');
    expect(compactAntecedent(undefined)).toBe('—');
  });
});
