/**
 * RainfallMetricList.tsx (Lluvia v2 — Phase 3)
 *
 * Metric groups of one snapshot as state-badged rows with full provenance.
 * Nominal grid resolution is stated as such — never as parcel-level accuracy
 * (spec "Metric Provenance and State Metadata").
 *
 * `AnnualText` — the chart's accessible textual equivalent — used to live here
 * and now lives on `RainfallAnswerCard`. It had to move: this list renders
 * inside a COLLAPSED `CollapsibleSection`, which unmounts its body, so an
 * equivalent left here would disappear from the accessibility tree for exactly
 * the readers it exists for (proposal R7).
 */

import { Badge, Group, Stack, Text } from '@mantine/core';

import type { RainfallAnalysisSnapshot, RainfallMetric } from '../../../lib/api/rainfall';
import { formatMetricValue, metricLabel, metricStateLabel } from './rainfallFormat';

const STATE_COLORS: Record<RainfallMetric['state'], string> = {
  available: 'green',
  partial: 'yellow',
  suppressed: 'orange',
  unavailable: 'gray',
};

const GROUP_TITLES: ReadonlyArray<{ key: 'annual' | 'antecedents' | 'intensity'; title: string }> =
  [
    { key: 'annual', title: 'Anual' },
    { key: 'antecedents', title: 'Antecedentes' },
    { key: 'intensity', title: 'Intensidad y evento' },
  ];

export interface RainfallMetricRowProps {
  readonly name: string;
  readonly metric: RainfallMetric;
  /** Served period, so the `normal` row names the SAME baseline as the phrase
   *  above it — never a constant frozen in the frontend (LI4-004). */
  readonly baseline: string;
}

/**
 * ONE metric: name, state, value, and the facts underneath.
 *
 * EXACTLY ONE BADGE, carrying the state WORD (OWN-003). The row used to carry
 * three — `Provisional`, `Fallback` and a state badge holding
 * `describeMetricState`, i.e. the state AND its reason — all competing for one
 * `nowrap` row inside a 380 px panel, which is how the owner's screenshot came
 * to read `PROVISIO… FALLB… DISPONI…`. A truncated badge is worse than no
 * badge: unreadable, and still looking like data.
 *
 * Nothing was dropped to get there. The reason moved to its own line, and the
 * provisional/fallback flags became plain markers on the metadata line — they
 * are not states, they are qualifiers of one, and they never needed to shout
 * from the same row as the value. The row also WRAPS now: given too little
 * width it takes a second line instead of shaving letters off a word.
 */
export function RainfallMetricRow({ name, metric, baseline }: RainfallMetricRowProps) {
  const provenance = metric.provenance;
  return (
    <Stack gap={2} data-testid={`rainfall-metric-${name}`}>
      <Group gap="xs" wrap="wrap" justify="space-between">
        <Text size="xs">{metricLabel(name, baseline)}</Text>
        <Group gap={6} wrap="nowrap">
          <Badge
            size="xs"
            variant="light"
            color={STATE_COLORS[metric.state]}
            data-metric-state={metric.state}
          >
            {metricStateLabel(metric)}
          </Badge>
          <Text size="xs" fw={600}>
            {formatMetricValue(metric)}
          </Text>
        </Group>
      </Group>
      {/* The reason the badge no longer carries. Its own line, in full: a
          suppression a reader cannot read is a suppression nobody can act on. */}
      {metric.reason !== null && metric.reason.length > 0 && (
        <Text size="xs" c="dimmed">
          {`Motivo: ${metric.reason}`}
        </Text>
      )}
      <Group gap={6} wrap="wrap">
        {metric.temporal_state === 'provisional' && (
          <Text size="xs" c="violet" fw={500}>
            Provisional
          </Text>
        )}
        {metric.fallback_used && (
          <Text size="xs" c="cyan" fw={500}>
            Fallback
          </Text>
        )}
        <Text size="xs" c="dimmed">
          {`Fuente: ${provenance.source_id} · Resolución nominal: ${provenance.nominal_resolution} · Cobertura: ${Math.round(metric.coverage * 100)}% · Revisión: ${metric.revision}`}
        </Text>
      </Group>
    </Stack>
  );
}

export interface RainfallMetricGroupProps {
  /** The group's metrics, keyed by metric name exactly as the wire sent them. */
  readonly group: Record<string, RainfallMetric> | undefined;
  readonly baseline: string;
  /**
   * Optional heading. Omitted when the group is rendered as the whole body of
   * a `CollapsibleSection` whose header already names it — a second title
   * inside the fold is noise, not structure.
   */
  readonly title?: string;
}

/**
 * ONE metric group. Renders nothing at all for an absent or empty group: the
 * antecedents fold mounts this directly, and a heading over zero rows would
 * claim a section the snapshot never served.
 */
export function RainfallMetricGroup({ group, baseline, title }: RainfallMetricGroupProps) {
  if (!group || Object.keys(group).length === 0) return null;
  return (
    <Stack gap={4}>
      {title !== undefined && (
        <Text size="xs" fw={600} c="dimmed">
          {title}
        </Text>
      )}
      {Object.entries(group).map(([name, metric]) => (
        <RainfallMetricRow key={name} name={name} metric={metric} baseline={baseline} />
      ))}
    </Stack>
  );
}

export interface RainfallMetricListProps {
  readonly snapshot: RainfallAnalysisSnapshot;
  /**
   * Group keys this list must NOT render because another surface already
   * shows them (the antecedents have their own fold, with the values in its
   * collapsed header).
   *
   * `exclude`, never `include`, and that is the whole point: with an
   * include-list a group the server starts serving tomorrow would render
   * NOWHERE, silently. With an exclude-list the technical fold means
   * "everything the card and the other fold did not already show", so an
   * unrecognised group lands there by default (R6).
   */
  readonly exclude?: readonly string[];
}

export function RainfallMetricList({ snapshot, exclude }: RainfallMetricListProps) {
  return (
    <Stack gap="xs" data-testid="rainfall-metrics">
      {GROUP_TITLES.filter(({ key }) => !exclude?.includes(key)).map(({ key, title }) => (
        <RainfallMetricGroup
          key={key}
          group={snapshot[key]}
          baseline={snapshot.baseline}
          title={title}
        />
      ))}
      {typeof snapshot.summary === 'string' && snapshot.summary.length > 0 && (
        <Text size="xs" fs="italic" data-testid="rainfall-summary">
          {snapshot.summary}
        </Text>
      )}
    </Stack>
  );
}
