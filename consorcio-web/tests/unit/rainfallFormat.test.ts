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
  formatDiscrepancies,
  formatMetricValue,
  hoistProvenance,
  metricEvidenceLine,
  metricLabel,
  metricStateLabel,
  scopeChoiceLabel,
  scopeChoiceLabels,
  shouldUseSegmentedScope,
  stringifyUnknownFields,
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
    expect(metricLabel('percentile')).toBe('Percentil histórico');
  });

  it('degrades a PRUNED intensity key to its raw name, rather than to a fiction', () => {
    // Slice 2 deleted the eight `intensity` labels: `build_snapshot` cannot
    // emit that group, so they were vocabulary for data nobody serves. The
    // prune is only honest because the group renderer is key-driven now (D8) —
    // an intensity group served tomorrow renders under its raw key with these
    // raw metric keys, which is visible. `duration` used to read 'Duración del
    // evento' here; that string described a metric this frontend never met.
    expect(metricLabel('duration')).toBe('duration');
    expect(metricLabel('p24h')).toBe('p24h');
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

  /**
   * The rolling-window reference pair (SDD S3, design D1).
   *
   * `metricLabel` used to append the period on the IDENTITY `key === 'normal'`,
   * which is exactly right for a snapshot with one normal in it and exactly
   * wrong for one with four. The backend now serves `d7_normal`, `d30_normal`
   * and `d90_normal` beside `annual_normal`, and an identity test labels three
   * of the four without a period — one fold, four normals, one of them
   * announcing 1991-2020 and three announcing nothing.
   */
  describe('the antecedent window reference metrics', () => {
    const WINDOW_NORMALS = ['d7_normal', 'd30_normal', 'd90_normal'] as const;
    const WINDOW_PERCENTILES = ['d7_percentile', 'd30_percentile', 'd90_percentile'] as const;

    it('gives each of the six a Spanish label of its own', () => {
      // NOT the raw key: an unlabelled key degrades to its wire name, which is
      // honest and unreadable. `metricLabel` cannot distinguish the two, so the
      // assertion is that the label is not the key.
      for (const key of [...WINDOW_NORMALS, ...WINDOW_PERCENTILES]) {
        expect(metricLabel(key)).not.toBe(key);
      }
      // Six keys, six distinct labels: two rows carrying two numbers under one
      // name is the same unreadable screen from the other direction.
      const labels = new Set([...WINDOW_NORMALS, ...WINDOW_PERCENTILES].map((k) => metricLabel(k)));
      expect(labels.size).toBe(6);
    });

    it('appends the SERVED baseline to every window normal, by membership', () => {
      // Derived from the argument, never a constant: regenerating the normals
      // over another period must move all four labels with no frontend edit.
      for (const key of WINDOW_NORMALS) {
        expect(metricLabel(key, '2001-2030')).toBe(`${metricLabel(key)} 2001-2030`);
      }
    });

    it('leaves the window percentiles period-less, like the annual one', () => {
      // A percentile's period belongs to the SENTENCE that states the rank
      // ("Percentil 27 de 1991-2020"), not to the metric's name — the reason
      // `percentile` was never in this set either.
      for (const key of WINDOW_PERCENTILES) {
        expect(metricLabel(key, '1991-2020')).toBe(metricLabel(key));
      }
    });

    it('names a window normal without a period when none is served', () => {
      expect(metricLabel('d7_normal', '')).toBe(metricLabel('d7_normal'));
      expect(metricLabel('d7_normal', null)).toBe(metricLabel('d7_normal'));
    });

    it('LI4-004: one fold, four normals, one period', () => {
      // The defect this slice exists to close, asserted as the comparison a
      // reader actually makes: the annual normal and the three window normals
      // on one screen, every one of them stating the same thirty years.
      const labels = ['normal', ...WINDOW_NORMALS].map((k) => metricLabel(k, '2001-2030'));
      expect(labels.every((label) => label.endsWith(' 2001-2030'))).toBe(true);
      expect(labels.filter((label) => label.includes('1991'))).toEqual([]);
      expect(new Set(labels).size).toBe(labels.length);
    });

    it('still falls back to the raw key for an unknown key ending in _normal', () => {
      // The membership set is a SET, not a suffix match: a `d15_normal` this
      // frontend has never met renders under its raw key, which is visible,
      // rather than under an invented label with a period attached to it.
      expect(metricLabel('d15_normal', '1991-2020')).toBe('d15_normal');
    });
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

describe('hoistProvenance — per-field, over the metrics that carry provenance', () => {
  // D5: a field is SHARED only when every metric in the comparison set agrees
  // on it. All-or-nothing would under-hoist the common case (one revision
  // differing after a policy bump puts six identical provenance blocks back on
  // the rows), and hoisting a per-metric fact would state a claim about metrics
  // that never made it.
  it('(a) hoists every candidate field when the whole set agrees', () => {
    const hoist = hoistProvenance([
      metric({ metric: 'selected' }),
      metric({ metric: 'normal' }),
      metric({ metric: 'd7' }),
    ]);

    expect(hoist.perMetric).toEqual([]);
    expect(hoist.shared).toEqual({
      source_id: 'chirps-v3-final',
      source_class: 'estimated_satellite',
      method: 'sum',
      nominal_resolution: '0.05°',
      aggregation: 'daily',
      spatial_scope: 'zone',
      freshness: '2026-01-02T00:00:00Z',
      revision: 'policy-v1',
    });
  });

  it('(a2) never hoists available_through — it is the input of the per-metric evidence gate', () => {
    // UXJB-201. `available_through` decides, PER METRIC, whether an evidence
    // claim may be made at all (D9a rule 2); a hoisted date cannot be gated per
    // metric, so it is pinned to the rows and leaves the candidate set. Eight
    // candidates, not nine.
    const hoist = hoistProvenance([metric(), metric({ metric: 'normal' })]);

    expect(Object.keys(hoist.shared)).not.toContain('available_through');
    expect(hoist.perMetric).not.toContain('available_through');
    expect(Object.keys(hoist.shared)).toHaveLength(8);
  });

  it('(b) keeps exactly the divergent fields on the rows, and hoists the other six', () => {
    const hoist = hoistProvenance([
      metric({ metric: 'selected', revision: 'policy-v2' }),
      metric({
        metric: 'normal',
        provenance: { ...metric().provenance, source_id: 'chirps-v3-prelim' },
      }),
    ]);

    expect([...hoist.perMetric].sort()).toEqual(['revision', 'source_id']);
    expect(hoist.shared).toEqual({
      source_class: 'estimated_satellite',
      method: 'sum',
      nominal_resolution: '0.05°',
      aggregation: 'daily',
      spatial_scope: 'zone',
      freshness: '2026-01-02T00:00:00Z',
    });
  });

  it('(c) excludes a metric served WITHOUT provenance from the comparison set', () => {
    // UXJB-110: including the stripped four-field shape would make every field
    // diverge against a metric that carries none — one rejected metric putting
    // six identical provenance blocks back on the rows, which is the exact
    // defect the hoist exists to remove.
    const hoist = hoistProvenance([
      metric({ metric: 'selected' }),
      strippedMetric('metric_contract_rejected'),
      metric({ metric: 'd7' }),
    ]);

    expect(hoist.perMetric).toEqual([]);
    expect(Object.keys(hoist.shared)).toHaveLength(8);
    expect(hoist.shared.source_id).toBe('chirps-v3-final');
  });

  it('(d) shares nothing when every metric was served stripped', () => {
    // The empty comparison set. There is no shared block at all then, which
    // D9a rule 3 already covers: a stripped metric renders its state and reason
    // and nothing else.
    const hoist = hoistProvenance([strippedMetric('a'), strippedMetric('b')]);

    expect(hoist.shared).toEqual({});
    expect(hoist.perMetric).toHaveLength(8);
  });

  it('shares nothing for an empty set', () => {
    expect(hoistProvenance([]).shared).toEqual({});
  });
});

describe('stringifyUnknownFields — object fields never print [object Object]', () => {
  // D9a rule 4: ONE guard, TWO callers (`quality` per metric and
  // `source_health` per analysis). Both arrive `unknown` on the wire, and two
  // renderings of "what does an object look like here" is how the pair drifts.
  it('prints scalar pairs in key order', () => {
    expect(stringifyUnknownFields({ score: 0.9, source: 'chirps', degraded: false })).toBe(
      'score=0.9; source=chirps; degraded=false'
    );
  });

  it('SKIPS null, arrays, nested objects and functions rather than coercing them', () => {
    // Coercion is what produces `[object Object]` — a string that looks like a
    // fact and is not one.
    const printed = stringifyUnknownFields({
      score: 0.9,
      missing: null,
      windows: [1, 2],
      nested: { a: 1 },
      compute: () => 1,
    });

    expect(printed).toBe('score=0.9');
    expect(printed).not.toContain('[object Object]');
  });

  it('prints a scalar input as itself (rule 4 wins over the D9 table)', () => {
    // UXJB-207: where D9's table and D9a rule 4 disagree on a scalar
    // `source_health`, rule 4 wins — a scalar prints as itself, never as a
    // `k=v` pair with an invented key.
    expect(stringifyUnknownFields('degradado')).toBe('degradado');
    expect(stringifyUnknownFields(3)).toBe('3');
    expect(stringifyUnknownFields(false)).toBe('false');
  });

  it('yields nothing when there is nothing scalar to say, so the caller renders no line', () => {
    expect(stringifyUnknownFields({})).toBe('');
    expect(stringifyUnknownFields({ nested: { a: 1 }, list: [] })).toBe('');
    expect(stringifyUnknownFields(null)).toBe('');
    expect(stringifyUnknownFields(undefined)).toBe('');
    expect(stringifyUnknownFields([1, 2, 3])).toBe('');
  });
});

describe('formatDiscrepancies — consecutive expected_interval tokens collapse to a range', () => {
  const DAY_MS = 86_400_000;

  function utcMidnightIso(ms: number): string {
    return new Date(ms).toISOString().replace('.000Z', '+00:00');
  }

  function expectedInterval(dayOffset: number, startIso = '2024-01-02T00:00:00+00:00'): string {
    return `expected_interval=${utcMidnightIso(Date.parse(startIso) + dayOffset * DAY_MS)}`;
  }

  function expectedIntervalDays(count: number, startOffset = 0): string[] {
    return Array.from({ length: count }, (_, index) => expectedInterval(startOffset + index));
  }

  it('yields nothing for an empty list', () => {
    expect(formatDiscrepancies([])).toBe('');
  });

  it('leaves a single interval unchanged', () => {
    expect(formatDiscrepancies([expectedInterval(0)])).toBe(
      'expected_interval=2024-01-02T00:00:00+00:00'
    );
  });

  it('collapses two consecutive UTC days into one range with (2)', () => {
    expect(formatDiscrepancies(expectedIntervalDays(2))).toBe(
      'expected_interval=2024-01-02T00:00:00+00:00 → 2024-01-03T00:00:00+00:00 (2)'
    );
  });

  it('collapses 153 consecutive UTC days into one fragment with first, last and count', () => {
    const count = 153;
    const firstIso = '2024-01-02T00:00:00+00:00';
    const lastIso = utcMidnightIso(Date.parse(firstIso) + (count - 1) * DAY_MS);
    const compressed = formatDiscrepancies(expectedIntervalDays(count));

    expect(compressed).toBe(`expected_interval=${firstIso} → ${lastIso} (${count})`);
    expect(compressed).toContain(firstIso);
    expect(compressed).toContain(lastIso);
    expect(compressed).toContain(String(count));
    expect(compressed.split('; ')).toHaveLength(1);
  });

  it('splits a gap into two ranges', () => {
    // day1, day2, skip, day4, day5 — two regular runs, not one range over the hole.
    expect(
      formatDiscrepancies([
        expectedInterval(0),
        expectedInterval(1),
        expectedInterval(3),
        expectedInterval(4),
      ])
    ).toBe(
      'expected_interval=2024-01-02T00:00:00+00:00 → 2024-01-03T00:00:00+00:00 (2); expected_interval=2024-01-05T00:00:00+00:00 → 2024-01-06T00:00:00+00:00 (2)'
    );
  });

  it('keeps non-interval tokens in original relative order', () => {
    expect(
      formatDiscrepancies([
        'coverage_below_threshold',
        expectedInterval(0),
        expectedInterval(1),
        'source_lag',
      ])
    ).toBe(
      'coverage_below_threshold; expected_interval=2024-01-02T00:00:00+00:00 → 2024-01-03T00:00:00+00:00 (2); source_lag'
    );
  });

  it('joins a list with zero interval tokens unchanged', () => {
    expect(formatDiscrepancies(['coverage_below_threshold', 'source_lag'])).toBe(
      'coverage_below_threshold; source_lag'
    );
  });
});

describe('metricEvidenceLine — the same three-branch gate, applied PER METRIC', () => {
  // UXJA-205: `evidenceFooter` says "en este análisis" — it is analysis-scoped
  // and MUST NOT be reused on a metric row, where "this analysis" is a claim
  // about the whole envelope rather than about the metric being read.
  it('states the metric own last day with evidence', () => {
    expect(metricEvidenceLine(metric())).toBe('Evidencia publicada hasta el 2025-12-30');
  });

  it('keeps the real date for a metric SUPPRESSED by policy', () => {
    // The counterexample that rules out a state-keyed gate: `_normalize_metric`
    // blanks only the VALUE, so coverage and provenance survive suppression.
    expect(
      metricEvidenceLine(
        metric({
          value: null,
          state: 'suppressed',
          reason: 'coverage_below_threshold',
          coverage: 0.62,
        })
      )
    ).toBe('Evidencia publicada hasta el 2025-12-30');
  });

  it('says the window published nothing FOR THIS METRIC, in its own words', () => {
    expect(
      metricEvidenceLine(
        metric({
          value: null,
          coverage: 0,
          state: 'unavailable',
          reason: 'no_data_in_disclosure_window',
        })
      )
    ).toBe('Sin días con evidencia publicada para esta métrica');
  });

  it('never borrows the analysis-scoped sentence', () => {
    const line = metricEvidenceLine(
      metric({
        value: null,
        coverage: 0,
        state: 'unavailable',
        reason: 'no_data_in_disclosure_window',
      })
    );

    expect(line).not.toContain('en este análisis');
  });

  it('renders NO line at all when neither claim can be made', () => {
    // The indeterminate branch: a stripped metric proves neither evidence nor
    // an empty window, so the row simply has no evidence line — never a
    // fabricated date and never a placeholder (D9a rule 3).
    expect(metricEvidenceLine(strippedMetric('metric_contract_rejected'))).toBeNull();
    expect(
      metricEvidenceLine(
        metric({ value: null, coverage: 0, state: 'unavailable', reason: 'sin fuente elegible' })
      )
    ).toBeNull();
  });
});
