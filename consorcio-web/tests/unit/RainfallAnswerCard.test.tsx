/**
 * RainfallAnswerCard.test.tsx (Lluvia UX — answer-first hierarchy, slice 1)
 *
 * The ALWAYS-VISIBLE answer surface. The spec delta's "Answer-First Rainfall
 * Presentation Hierarchy" requires four facts above any disclosure control —
 * percentile, selected-year total, normal to the same date, and freshness as
 * the last day WITH evidence — so this file is where that requirement is
 * falsifiable.
 *
 * The five `AnnualText` tests moved here from `RainfallMetricList.test.tsx`:
 * the chart's textual equivalent now lives on the card, above the first fold,
 * which is what keeps it out of a region that unmounts when collapsed (R7).
 * The rules they lock are the ones the repo has already paid for twice:
 *   - the baseline period prints AS SERVED (`snapshot.baseline`), never as a
 *     constant in the frontend — the RISK-001 lesson from `PrecipChart`;
 *   - a metric with no value prints "—", never "0"; a served percentile of 0 IS
 *     data and must survive as "0";
 *   - a percentile the analysis did not carry produces no phrase at all rather
 *     than an empty slot that reads like a broken render.
 *
 * The card is a PURE function of `{ snapshot, freshness }` — no hook, no query,
 * no store (design D1). That props contract is what makes a future `/lluvia`
 * page a re-mount instead of a rewrite, and it is why this file can mount the
 * card directly with no providers beyond Mantine.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';

import { RainfallAnswerCard } from '../../src/components/map2d/rainfall/RainfallAnswerCard';
import {
  type RainfallFreshness,
  deriveFreshness,
} from '../../src/components/map2d/rainfall/rainfallFormat';
import type { RainfallAnalysisSnapshot, RainfallMetric } from '../../src/lib/api/rainfall';

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

function snapshot(overrides: Partial<RainfallAnalysisSnapshot> = {}): RainfallAnalysisSnapshot {
  const baseline = overrides.baseline ?? '1991-2020';
  return {
    analysis_revision_id: 'rev-9',
    data_revision: 'ab'.repeat(32),
    scope: { kind: 'zone', id: 'zona-ne', version: '3' },
    regional_estimate: true,
    year: 2025,
    comparison_end: '2025-12-31',
    baseline,
    annual: {
      selected: metric({ metric: 'selected', value: 850.24 }),
      normal: metric({ metric: 'normal', value: 1013.8 }),
      percentile: metric({ metric: 'percentile', value: 27.4, unit: 'percentil' }),
    },
    ...overrides,
  };
}

/** The card never derives freshness itself (D1a) — the panel hands it down. */
function renderCard(
  snap: RainfallAnalysisSnapshot,
  freshness: RainfallFreshness = deriveFreshness(snap)
): ReturnType<typeof render> {
  const ui: ReactElement = (
    <MantineProvider env="test">
      <RainfallAnswerCard snapshot={snap} freshness={freshness} />
    </MantineProvider>
  );
  return render(ui);
}

describe('RainfallAnswerCard — the annual textual equivalent (moved from the metric list)', () => {
  it('states the percentile beside the accumulation and the normal', () => {
    renderCard(snapshot());

    const text = screen.getByTestId('rainfall-annual-text');
    // The CUT DATE, not the year. "Año 2026: 503.4 mm" reads as a closed annual
    // total, and in August it is eight months of accumulation — a number a
    // reader would quote at an asamblea and be wrong. The day comes from the
    // freshness value the panel derived, never from the browser clock.
    expect(text).toHaveTextContent('Acumulado hasta el 2025-12-30: 850.2 mm');
    expect(text.textContent).not.toMatch(/Año 2025:/);
    // `annual.normal` is the normal accumulated TO THE SAME DATE, so it says
    // so — while still naming the SERVED baseline (RISK-001).
    expect(text).toHaveTextContent('Normal 1991-2020 al mismo período: 1013.8 mm');
    // Whole percentiles: a Weibull rank over 31 samples moves in steps of ~3,
    // so a tenth of a percentile is precision the number does not have.
    expect(text).toHaveTextContent('Percentil 27 de 1991-2020');
  });

  it('claims no cut date when freshness could not be established', () => {
    // The honest degradation: no fabricated day, and still no claim of a
    // CLOSED year — "parcial" is the fact that survives either way.
    renderCard(snapshot(), {
      kind: 'unknown',
      evidenceDay: null,
      sentence: 'Frescura no disponible en este análisis',
      reason: 'metric_contract_rejected',
    });

    const text = screen.getByTestId('rainfall-annual-text');
    expect(text).toHaveTextContent('Acumulado parcial del año 2025: 850.2 mm');
    expect(text.textContent).not.toMatch(/hasta el/);
  });

  it('prints the baseline period AS SERVED, in the phrase too', () => {
    // RISK-001 all over again: regenerating the normals over another period
    // must change this surface by itself, with no frontend edit involved.
    const snap = snapshot({ baseline: '2001-2030' });
    renderCard(snap);

    expect(screen.getByTestId('rainfall-annual-text')).toHaveTextContent(
      'Percentil 27 de 2001-2030'
    );
    expect(screen.getByTestId('rainfall-annual-text')).toHaveTextContent(
      'Normal 2001-2030 al mismo período: 1013.8 mm'
    );

    // …and the sweep that catches the surface nobody thought of. It compares
    // against `snapshot.baseline` rather than excluding the literal 1991-2020,
    // because a detector written as a denylist only ever catches the one
    // constant it was written for: this one fires on ANY period the server did
    // not serve, in either dash spelling. Its list-side half stayed in
    // `RainfallMetricList.test.tsx`, over the badged row and the summary.
    const periods = [
      ...(screen.getByTestId('rainfall-answer-card').textContent ?? '').matchAll(
        /\d{4}\s*[-–]\s*\d{4}/g
      ),
    ].map(([period]) => period);

    expect(periods.length).toBeGreaterThanOrEqual(2);
    expect([...new Set(periods)]).toEqual([snap.baseline]);
  });

  it('keeps a served percentile of 0 as a number, never as a missing value', () => {
    // The driest year on record ranks at the bottom. That is DATA — the single
    // most expensive thing this UI could round away into "—".
    renderCard(
      snapshot({
        annual: {
          selected: metric({ metric: 'selected', value: 12.5 }),
          percentile: metric({ metric: 'percentile', value: 0, unit: 'percentil' }),
        },
      })
    );

    expect(screen.getByTestId('rainfall-annual-text')).toHaveTextContent('Percentil 0 de 1991-2020');
    expect(screen.getByTestId('rainfall-headline')).toHaveTextContent('Percentil 0');
  });

  it('renders no value for a suppressed percentile, and never a zero', () => {
    renderCard(
      snapshot({
        annual: {
          selected: metric({ metric: 'selected', value: 850.24 }),
          percentile: metric({
            metric: 'percentile',
            value: null,
            unit: 'percentil',
            state: 'suppressed',
            reason: 'baseline_years_below_minimum',
          }),
        },
      })
    );

    const text = screen.getByTestId('rainfall-annual-text');
    expect(text.textContent).toContain('—');
    expect(text.textContent).not.toMatch(/Percentil 0\b/);
    // The reason is NOT lost when the badged row moves into the technical
    // fold: the card states it on the always-visible surface, which is what
    // the delta's "shown by state and reason" clause asks for.
    expect(screen.getByTestId('rainfall-answer-card').textContent).toContain(
      'baseline_years_below_minimum'
    );
  });

  it('states a withheld selected total by state and reason, never as a number', () => {
    // The delta's third THEN clause is symmetric between the two metrics: a
    // suppressed total is "shown by state and reason, never as a number and
    // never as zero". The value slot still prints "—"; the STATE and its
    // reason get their own always-visible line, exactly like the percentile's.
    renderCard(
      snapshot({
        annual: {
          selected: metric({
            metric: 'selected',
            value: null,
            state: 'unavailable',
            reason: 'coverage_below_threshold',
          }),
          percentile: metric({ metric: 'percentile', value: 46.9, unit: 'percentil' }),
        },
      })
    );

    const card = screen.getByTestId('rainfall-answer-card').textContent ?? '';
    expect(card).toContain('Acumulado del año: No disponible: coverage_below_threshold');
    expect(screen.getByTestId('rainfall-annual-text').textContent).toContain('—');
  });

  it('adds no state line when the selected total is readable', () => {
    // The other direction, and the one a "just always render it" fix breaks:
    // a healthy total is the number itself, and a permanent "Disponible" line
    // beside it is the noise the evidence footer exists to refuse.
    renderCard(snapshot());

    const card = screen.getByTestId('rainfall-answer-card').textContent ?? '';
    expect(card).not.toMatch(/Acumulado del año:/);
  });

  it('omits the phrase entirely when the analysis carries no percentile', () => {
    renderCard(
      snapshot({
        annual: { selected: metric({ metric: 'selected', value: 850.24 }) },
      })
    );

    const text = screen.getByTestId('rainfall-annual-text');
    expect(text).toHaveTextContent('Acumulado hasta el 2025-12-30: 850.2 mm');
    expect(text.textContent).not.toMatch(/Percentil/i);
  });
});

describe('RainfallAnswerCard — the headline is the answer', () => {
  it('makes the percentile the typographic headline, rounded like the phrase', () => {
    renderCard(snapshot({ annual: { percentile: metric({ value: 69.6, unit: 'percentil' }) } }));
    expect(screen.getByTestId('rainfall-headline')).toHaveTextContent('Percentil 70');
  });

  it('falls back to the selected-year total when no percentile is served', () => {
    renderCard(snapshot({ annual: { selected: metric({ value: 850.24 }) } }));

    const headline = screen.getByTestId('rainfall-headline');
    expect(headline).toHaveTextContent('Acumulado del año 850.2 mm');
    expect(headline.textContent).not.toMatch(/Percentil/i);
  });

  it('carries no badged percentile row on the always-visible surface', () => {
    // The delta forbids the BADGED row here and requires the headline instead;
    // the row itself is not deleted, it moves one click away into the
    // technical fold. Both halves matter, and this is the half the card owns.
    renderCard(snapshot());

    expect(screen.queryByTestId('rainfall-metric-percentile')).toBeNull();
    expect(screen.queryByTestId('rainfall-metrics')).toBeNull();
    expect(screen.getByTestId('rainfall-headline')).toBeInTheDocument();
  });

  it('renders as the ready sentinel even when the analysis answers nothing', () => {
    // The card is what the e2e waits on, so it must exist for EVERY ready
    // snapshot. With nothing to say it states the scope and stops.
    renderCard(snapshot({ annual: {} }));

    expect(screen.getByTestId('rainfall-answer-card')).toBeInTheDocument();
    expect(screen.queryByTestId('rainfall-headline')).toBeNull();
    expect(screen.getByTestId('rainfall-answer-card').textContent).toContain('Ámbito: Zona');
  });

  it('offers a compact mobile fact list without removing the complete accessible equivalent', () => {
    renderCard(snapshot());

    const compact = screen.getByTestId('rainfall-answer-compact');
    const compactQueries = within(compact);

    expect(compact).toHaveAttribute('aria-hidden', 'true');
    expect(compactQueries.getByText('Acumulado al 2025-12-30')).toBeInTheDocument();
    expect(compactQueries.getByText('850.2 mm')).toBeInTheDocument();
    expect(compactQueries.getByText('Normal 1991-2020 · mismo período')).toBeInTheDocument();
    expect(compactQueries.getByText('1013.8 mm')).toBeInTheDocument();
    expect(screen.getByTestId('rainfall-compact-wetness')).toHaveTextContent('Año seco');
    expect(screen.getByTestId('rainfall-compact-context')).toHaveTextContent(
      'Estimación regional: la zona Ne'
    );
    expect(screen.getByTestId('rainfall-compact-context')).toHaveTextContent(
      'comparación hasta el 2025-12-31'
    );
    expect(screen.getByTestId('rainfall-compact-context')).toHaveTextContent('CHIRPS (satelital)');

    // The compact copy is visual-only. Screen readers keep the complete prose
    // equivalent, including the ranking and same-period normal context.
    expect(screen.getByTestId('rainfall-annual-text')).toHaveTextContent(
      'Percentil 27 de 1991-2020'
    );
    expect(screen.getByTestId('rainfall-wetness')).toHaveTextContent(
      'categoría derivada del percentil 27 de 1991-2020'
    );
  });

  it('does not fabricate compact value rows for metrics the snapshot did not serve', () => {
    renderCard(
      snapshot({
        annual: { percentile: metric({ metric: 'percentile', value: 72, unit: 'percentil' }) },
      })
    );

    expect(screen.queryByTestId('rainfall-answer-compact')).toBeNull();
    expect(screen.getByTestId('rainfall-answer-card').textContent).not.toContain('—');
  });
});

describe('RainfallAnswerCard — the derived adjective (R2)', () => {
  it('states the derivation and the served baseline INSIDE the sentence', () => {
    renderCard(snapshot({ annual: { percentile: metric({ value: 72, unit: 'percentil' }) } }));

    expect(screen.getByTestId('rainfall-wetness')).toHaveTextContent(
      'Año húmedo · categoría derivada del percentil 72 de 1991-2020'
    );
  });

  it('follows the SERVED baseline, never a period frozen here', () => {
    renderCard(
      snapshot({
        baseline: '2001-2030',
        annual: { percentile: metric({ value: 5, unit: 'percentil' }) },
      })
    );

    expect(screen.getByTestId('rainfall-wetness')).toHaveTextContent(
      'Año muy seco · categoría derivada del percentil 5 de 2001-2030'
    );
  });

  it.each([
    ['suppressed', 'coverage_below_threshold'],
    ['unavailable', 'sin fuente elegible'],
  ] as const)('presents NO label for a %s percentile, reason still shown', (state, reason) => {
    renderCard(
      snapshot({
        annual: {
          selected: metric({ value: 850.24 }),
          percentile: metric({ value: null, unit: 'percentil', state, reason }),
        },
      })
    );

    expect(screen.queryByTestId('rainfall-wetness')).toBeNull();
    expect(screen.getByTestId('rainfall-answer-card').textContent).toContain(reason);
  });

  it('presents no label when the analysis carries no percentile at all', () => {
    renderCard(snapshot({ annual: { selected: metric({ value: 850.24 }) } }));
    expect(screen.queryByTestId('rainfall-wetness')).toBeNull();
    expect(screen.queryByTestId('rainfall-percentile-gloss')).toBeNull();
  });

  it('glosses the rank in words, using the SAME rounded number as the headline', () => {
    // A percentile is exactly the kind of number a reader nods at without
    // decoding. And the gloss must not become the screen's third spelling of
    // one fact: it reads the ROUNDED value, like the headline.
    renderCard(snapshot({ annual: { percentile: metric({ value: 46.9, unit: 'percentil' }) } }));

    expect(screen.getByTestId('rainfall-headline')).toHaveTextContent('Percentil 47');
    expect(screen.getByTestId('rainfall-percentile-gloss')).toHaveTextContent(
      'De cada 100 años, 47 fueron más secos que este.'
    );
    expect(screen.getByTestId('rainfall-percentile-gloss').textContent).not.toContain('46.9');
  });

  it('offers no gloss for a suppressed percentile', () => {
    // An interpretation of a withheld number IS the withheld number.
    renderCard(
      snapshot({
        annual: {
          selected: metric({ value: 850.24 }),
          percentile: metric({
            value: null,
            unit: 'percentil',
            state: 'suppressed',
            reason: 'baseline_years_below_minimum',
          }),
        },
      })
    );

    expect(screen.queryByTestId('rainfall-percentile-gloss')).toBeNull();
  });

  it.each([
    [5, 'muy seco'],
    [20, 'seco'],
    [50, 'normal'],
    [80, 'húmedo'],
    [95, 'muy húmedo'],
  ])('carries the WORD at percentile %s, whatever the colour does', (value, word) => {
    // The adjective may be tinted, and the tint is never the carrier: the word
    // is rendered in full, inside a sentence naming the percentile and the
    // baseline it came from. A greyscale printout and a screen reader get the
    // same fact a colour display does — the same rule the chart's
    // solid-versus-dashed distinction exists for.
    renderCard(snapshot({ annual: { percentile: metric({ value, unit: 'percentil' }) } }));

    const label = screen.getByTestId('rainfall-wetness');
    expect(label.textContent).toContain(`Año ${word}`);
    expect(label.textContent).toContain(`percentil ${value}`);
    expect(label.textContent).toContain('1991-2020');
  });
});

describe('RainfallAnswerCard — freshness on the answer surface (D1a)', () => {
  it('prints the sentence of the EVIDENCED branch', () => {
    renderCard(snapshot());

    const freshness = screen.getByTestId('rainfall-freshness');
    expect(freshness).toHaveTextContent('Evidencia publicada hasta el 2025-12-30');
    expect(freshness).not.toHaveAttribute('title');
  });

  it('prints the sentence of the EMPTY-WINDOW branch and no date', () => {
    const snap = snapshot({
      annual: {
        selected: metric({
          value: null,
          state: 'unavailable',
          reason: 'no_data_in_disclosure_window',
          coverage: 0,
          provenance: { ...metric().provenance, available_through: '2026-01-01T00:00:00Z' },
        }),
      },
    });
    renderCard(snap);

    const freshness = screen.getByTestId('rainfall-freshness');
    expect(freshness).toHaveTextContent('Sin días con evidencia publicada en este análisis');
    expect(freshness.textContent).not.toContain('2025-12-31');
    expect(freshness.textContent).not.toContain('2026-01-01');
  });

  it('asserts neither claim on the INDETERMINATE branch, and reaches the served reason', () => {
    renderCard(snapshot(), {
      kind: 'unknown',
      evidenceDay: null,
      sentence: 'Frescura no disponible en este análisis',
      reason: 'metric_contract_rejected',
    });

    const freshness = screen.getByTestId('rainfall-freshness');
    expect(freshness).toHaveTextContent('Frescura no disponible en este análisis');
    // The reason has to be reachable by a screen reader too, not just on hover.
    expect(freshness).toHaveAttribute('title', 'metric_contract_rejected');
    expect(freshness).toHaveAttribute('aria-label', expect.stringContaining('metric_contract_rejected'));
  });

  it('prints the sentence it was GIVEN, never one it re-derived', () => {
    // R3 / D1a: the panel derives once and passes the value down. A card that
    // recomputed would be a second derivation of the fact the spec forbids
    // deriving twice for one subject.
    renderCard(snapshot(), {
      kind: 'evidenced',
      evidenceDay: '1999-01-01',
      sentence: 'Evidencia publicada hasta el 1999-01-01',
      reason: null,
    });

    expect(screen.getByTestId('rainfall-freshness')).toHaveTextContent(
      'Evidencia publicada hasta el 1999-01-01'
    );
  });
});

describe('RainfallAnswerCard — the scope line (R1)', () => {
  it('names the spatial scope so two normals of different scope cannot be confused', () => {
    renderCard(snapshot());

    const card = screen.getByTestId('rainfall-answer-card');
    expect(card.textContent).toContain('Ámbito: Zona');
    expect(card.textContent).toContain('estimación regional');
    expect(card.textContent).toContain('comparación hasta el 2025-12-31');
  });

  it('names a basin scope as a basin', () => {
    renderCard(
      snapshot({
        scope: { kind: 'basin', id: 'zo-12', version: 'abc' },
        regional_estimate: false,
      })
    );

    const card = screen.getByTestId('rainfall-answer-card');
    expect(card.textContent).toContain('Ámbito: Cuenca');
    expect(card.textContent).not.toContain('estimación regional');
    // No badge, no explanation: there is no regional estimate to explain.
    expect(card.textContent).not.toContain('que contiene esta parcela');
  });

  it('says WHICH region the regional estimate is for, by name', () => {
    // The badge alone states a property of the number and leaves the reader to
    // guess which region produced it for the parcel they clicked.
    renderCard(snapshot({ scope: { kind: 'basin', id: 'cuenca_rio_tercero', version: '1' } }));

    expect(screen.getByTestId('rainfall-answer-card').textContent).toContain(
      'Estimación para la cuenca Rio Tercero, que contiene esta parcela.'
    );
  });

  it('still names the region when the served id carries no qualifier', () => {
    renderCard(snapshot({ scope: { kind: 'zone', id: 'zona', version: '1' } }));

    expect(screen.getByTestId('rainfall-answer-card').textContent).toContain(
      'Estimación para la zona, que contiene esta parcela.'
    );
  });
});

describe('RainfallAnswerCard — the evidence footer is a CLOSED set', () => {
  it('names the source in one token, not the whole provenance', () => {
    renderCard(snapshot());

    expect(screen.getByTestId('rainfall-source')).toHaveTextContent('Fuente: CHIRPS (satelital)');
    // The rest of the provenance belongs to the technical fold: the card
    // answers "can I trust this", the fold answers "how was it built".
    const card = screen.getByTestId('rainfall-answer-card').textContent ?? '';
    expect(card).not.toContain('chirps-v3-final');
    expect(card).not.toContain('0.05°');
    expect(card).not.toContain('policy-v1');
  });

  it('never states coverage on a normal analysis', () => {
    // Exception, not decoration: a permanent "Cobertura: 100%" is noise on
    // every healthy analysis, and a DEGRADED one already surfaces through the
    // state machinery that exists for it.
    renderCard(snapshot());

    const card = screen.getByTestId('rainfall-answer-card').textContent ?? '';
    expect(card).not.toMatch(/Cobertura/i);
    expect(card).not.toMatch(/Completitud/i);
  });

  it('renders no source line when the metric was served without provenance', () => {
    const stripped = {
      metric: 'selected',
      value: null,
      state: 'unavailable',
      reason: 'metric_contract_rejected',
    } as unknown as RainfallMetric;
    renderCard(snapshot({ annual: { selected: stripped } }));

    expect(screen.queryByTestId('rainfall-source')).toBeNull();
  });
});
