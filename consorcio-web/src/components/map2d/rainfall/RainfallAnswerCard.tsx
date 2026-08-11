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
  percentilePhrase,
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
 */
function AnnualText({ snapshot }: { readonly snapshot: RainfallAnalysisSnapshot }) {
  const selected = snapshot.annual?.selected;
  const normal = snapshot.annual?.normal;
  // Task 4.8: the percentile is what answers "wet or dry against the record?"
  // — the question the chart's two lines answer visually. Without it here, a
  // reader who cannot see the chart gets two absolute numbers and no ranking.
  const percentile = snapshot.annual?.percentile;
  if (!selected && !normal && !percentile) return null;
  const parts: string[] = [];
  if (selected) parts.push(`Año ${snapshot.year}: ${formatMetricValue(selected)}`);
  if (normal) parts.push(`Normal ${snapshot.baseline}: ${formatMetricValue(normal)}`);
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

      {withheld !== undefined && (
        <Text size="xs" c="dimmed">
          {`${metricLabel('percentile')}: ${describeMetricState(withheld)}`}
        </Text>
      )}

      <AnnualText snapshot={snapshot} />

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
    </Stack>
  );
}
