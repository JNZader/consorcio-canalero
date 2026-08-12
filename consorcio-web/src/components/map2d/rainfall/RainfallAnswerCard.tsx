/**
 * RainfallAnswerCard.tsx (Lluvia UX — answer-first hierarchy, design D1/D3/D4)
 *
 * The ALWAYS-VISIBLE answer surface of the Lluvia tab: the contextualized
 * answer for the selected year — percentile headline, derived adjective, the
 * chart's textual equivalent (selected-year total + normal to the same date +
 * the ranking) and the analysis' freshness — before any historical or
 * climatological context, and none of it behind a disclosure control (spec
 * "Answer-First Rainfall Presentation Hierarchy").
 *
 * A PURE function of its props: `{ snapshot, freshness }`, no hook, no query,
 * no store. That is a contract, not a coincidence — `RainfallDetailPanel` is
 * the only stateful node (design D1), and a card that read `useRainfallAnalysis`
 * itself would be welded to the floating panel and would have to be rewritten,
 * not re-mounted, the day this content moves to a page of its own.
 *
 * WHAT THIS CARD REFUSES TO DO
 * ────────────────────────────
 * · Re-derive freshness. The panel derives it ONCE per subject and hands the
 *   value down (D1a). A second derivation here is the duplication the spec
 *   forbids, and it is how two surfaces of one screen start disagreeing.
 * · Print a number the policy withheld. A suppressed or unavailable percentile
 *   is stated by state and reason — never as a value, never as a zero, and
 *   never as an adjective, which is the loudest thing on the card.
 * · Freeze a baseline period. Every phrase reads `snapshot.baseline` as served
 *   (RISK-001/LI4-004): regenerating the normals over another period must move
 *   this card with no frontend edit.
 * · Repeat the percentile as a badged metric row. The badged row moves into
 *   the technical fold; what stays here is the headline and the restatement
 *   inside the textual equivalent, which "Progressive Disclosure Without Data
 *   Loss" requires to remain COMPLETE for a reader who cannot see the plot.
 */

import { Stack, Text } from '@mantine/core';

import type { RainfallAnalysisSnapshot, RainfallMetric } from '../../../lib/api/rainfall';
import {
  RAINFALL_SCOPE_LABELS,
  type RainfallFreshness,
  describeMetricState,
  formatMetricValue,
  metricLabel,
  percentileGloss,
  percentilePhrase,
  scopeSentence,
  shortSource,
  wetnessColor,
  wetnessFromPercentile,
  wetnessLabel,
} from './rainfallFormat';

export interface RainfallAnswerCardProps {
  readonly snapshot: RainfallAnalysisSnapshot;
  /** Derived ONCE by the panel (D1a) — never recomputed here. */
  readonly freshness: RainfallFreshness;
}

/**
 * The percentile only when it may be READ as a number.
 *
 * Same predicate the adjective uses, and deliberately so: a card that printed
 * `Percentil 95` in the headline while withholding the same number in the row
 * below would have leaked exactly what the policy suppressed.
 */
function readablePercentile(metric: RainfallMetric | undefined): RainfallMetric | undefined {
  if (metric === undefined || metric.value === null) return undefined;
  if (metric.state === 'suppressed' || metric.state === 'unavailable') return undefined;
  return metric;
}

/**
 * Textual annual comparison — the chart's accessible equivalent.
 *
 * Lives on the CARD, above the first fold, and that placement is the whole
 * mechanism behind R7: `CollapsibleSection` UNMOUNTS its body when closed, so
 * an equivalent inside a fold disappears from the accessibility tree for
 * exactly the readers it exists for. Structure, not discipline.
 *
 * THE PERIOD IS NAMED, and that is not cosmetic. `Año 2026: 503.4 mm` reads as
 * a CLOSED annual total; in August it is eight months of accumulation, and a
 * reader quoting it at an asamblea would be quoting a number that does not
 * exist. So the sentence states the cut: `Acumulado hasta el {día}`, where the
 * day is the analysis' own last day WITH evidence — taken from the `freshness`
 * value the panel derived, NEVER from the browser clock, which knows nothing
 * about what the provider published. When freshness could not be established
 * the sentence says `Acumulado parcial` instead: no date, and still no claim of
 * a closed year.
 *
 * `annual.normal` is likewise the normal accumulated TO THE SAME DATE, not the
 * full-year normal, so it says so — while still naming the SERVED baseline
 * (RISK-001), because those are two different facts about one number.
 */
function AnnualText({
  snapshot,
  freshness,
}: {
  readonly snapshot: RainfallAnalysisSnapshot;
  readonly freshness: RainfallFreshness;
}) {
  const selected = snapshot.annual?.selected;
  const normal = snapshot.annual?.normal;
  // Task 4.8: the percentile is what answers "wet or dry against the record?"
  // — the question the chart's two lines answer visually. Without it here, a
  // reader who cannot see the chart gets two absolute numbers and no ranking.
  const percentile = snapshot.annual?.percentile;
  if (!selected && !normal && !percentile) return null;
  const cut =
    freshness.evidenceDay !== null
      ? `Acumulado hasta el ${freshness.evidenceDay}`
      : `Acumulado parcial del año ${snapshot.year}`;
  const parts: string[] = [];
  if (selected) parts.push(`${cut}: ${formatMetricValue(selected)}`);
  if (normal) {
    parts.push(`Normal ${snapshot.baseline} al mismo período: ${formatMetricValue(normal)}`);
  }
  if (percentile) parts.push(percentilePhrase(percentile, snapshot.baseline));
  return (
    <Text size="sm" fw={600} data-testid="rainfall-annual-text">
      {parts.join(' · ')}
    </Text>
  );
}

export function RainfallAnswerCard({ snapshot, freshness }: RainfallAnswerCardProps) {
  const percentile = snapshot.annual?.percentile;
  const readable = readablePercentile(percentile);
  const selected = snapshot.annual?.selected;
  const wetness = wetnessFromPercentile(percentile);
  const gloss = percentileGloss(percentile);
  // The evidence footer is a CLOSED set: cut date (inside the accumulation
  // phrase), scope, and the short source. Coverage is deliberately NOT here —
  // a permanent "Cobertura: 100%" is noise on every normal analysis, and a
  // DEGRADED coverage already surfaces through the state machinery that exists
  // for it. Exception, not decoration.
  const source = shortSource(selected ?? snapshot.annual?.normal ?? percentile);

  // The headline is the ANSWER: the ranking when it may be read, the year's
  // own total when it may not. Nothing at all when the analysis answers
  // neither — the card still renders, because it is the ready sentinel.
  const headline =
    readable !== undefined
      ? `Percentil ${Math.round(readable.value ?? 0)}`
      : selected && selected.value !== null
        ? `Acumulado del año ${formatMetricValue(selected)}`
        : null;

  // A withheld percentile is a FACT the reader is owed on the always-visible
  // surface, not something to discover by opening the technical fold: the
  // badged row that used to carry it is now one click away.
  const withheld = percentile !== undefined && readable === undefined ? percentile : undefined;

  const scopeParts = [
    `Ámbito: ${RAINFALL_SCOPE_LABELS[snapshot.scope.kind]}`,
    snapshot.regional_estimate ? 'estimación regional' : null,
    `comparación hasta el ${snapshot.comparison_end}`,
  ].filter((part): part is string => part !== null);

  return (
    <Stack gap={4} data-testid="rainfall-answer-card">
      {headline !== null && (
        <Text size="xl" fw={700} lh={1.1} data-testid="rainfall-headline">
          {headline}
        </Text>
      )}

      {wetness !== null && readable !== undefined && (
        // The colour ACCOMPANIES the word; it never replaces it. The full
        // sentence — adjective, percentile and baseline — is always rendered,
        // so greyscale, colour-blindness and a screen reader all still deliver
        // the whole fact.
        <Text size="sm" c={wetnessColor(wetness)} data-testid="rainfall-wetness">
          {`Año ${wetnessLabel(wetness)} · categoría derivada del percentil ${Math.round(
            readable.value ?? 0
          )} de ${snapshot.baseline}`}
        </Text>
      )}

      {/* The rank, in words a reader can check. Same ROUNDED value as the
          headline — one fact, one number, on every always-visible surface. */}
      {gloss !== null && (
        <Text size="xs" c="dimmed" data-testid="rainfall-percentile-gloss">
          {gloss}
        </Text>
      )}

      {withheld !== undefined && (
        <Text size="xs" c="dimmed">
          {`${metricLabel('percentile')}: ${describeMetricState(withheld)}`}
        </Text>
      )}

      <AnnualText snapshot={snapshot} freshness={freshness} />

      {/* The freshness of the STORED ANALYSIS, named as such. The chart below
          states the freshness of the SERIES it drew — a different object, and
          when the two disagree `rainfall-series-stale` says so rather than
          averaging them into one number (D1a). */}
      <Text
        size="xs"
        c="dimmed"
        data-testid="rainfall-freshness"
        title={freshness.reason ?? undefined}
        aria-label={
          freshness.reason !== null ? `${freshness.sentence} (${freshness.reason})` : undefined
        }
      >
        {freshness.sentence}
      </Text>

      {/* R1: this analysis is a ZONE or BASIN estimate. The public monthly
          normal beside it is a parcel clip, and the two must never be readable
          as the same pipeline. */}
      <Text size="xs" c="dimmed">
        {scopeParts.join(' · ')}
      </Text>

      {/* What "Estimación regional" MEANS for the parcel the reader clicked.
          The badge alone names a property of the number and leaves the reader
          to guess which region produced it; this names it. */}
      {snapshot.regional_estimate && (
        <Text size="xs" c="dimmed">
          {`Estimación para ${scopeSentence(snapshot.scope)}, que contiene esta parcela.`}
        </Text>
      )}

      {source !== null && (
        <Text size="xs" c="dimmed" data-testid="rainfall-source">
          {`Fuente: ${source}`}
        </Text>
      )}
    </Stack>
  );
}
