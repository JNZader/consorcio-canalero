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

/**
 * The groups this frontend has a Spanish title for, in the order they render.
 *
 * A TITLE TABLE, not a whitelist — that distinction is the whole of R6. The
 * renderer iterates the SNAPSHOT's own keys and looks a title up here; a key
 * absent from this table still renders, under its raw name. `intensity` used to
 * be listed and is not any more: `build_snapshot` cannot emit it
 * (`compute.py:476-656`), and dead-code-as-documentation is what produced
 * exploration finding #10. If it ever comes back it renders under `intensity`
 * with raw metric keys — visible, not dropped.
 */
const GROUP_TITLES: Readonly<Record<string, string>> = {
  annual: 'Anual',
  antecedents: 'Antecedentes',
};

/** Known groups first, in the published order, so the vocabulary a reader has
 *  learned does not get reshuffled by whatever the server adds next. */
const KNOWN_GROUP_ORDER: readonly string[] = ['annual', 'antecedents'];

/**
 * Root keys that are NOT metric groups and already have their own renderer.
 *
 * Not belt-and-braces. `source_health` is `unknown` on the wire
 * (`lib/api/rainfall.ts:94`), so a future shape like `{chirps: {metric, state}}`
 * would PASS the guard below and render as a metric group on top of the single
 * analysis-level line D9 gives it — the double-rendering the enumerated floor
 * forbids. `metric_policy` is allow-listed at the server's root
 * (`service.SNAPSHOT_ROOT_KEYS`) and copied through by `normalize_snapshot`
 * even though `RainfallAnalysisSnapshot` does not declare it; the guard rejects
 * it today, and "we know this key and it is not a group" is a stronger
 * guarantee than "the guard happens to reject it".
 */
const NON_GROUP_ROOT_KEYS: ReadonlySet<string> = new Set([
  'analysis_revision_id',
  'data_revision',
  'scope',
  'regional_estimate',
  'year',
  'comparison_end',
  'baseline',
  'summary',
  'source_health',
  'metric_policy',
]);

/**
 * Whether a served root value is a group of metrics — TOTAL over `unknown`.
 *
 * Both `typeof` checks come BEFORE any `in`: `'metric' in "texto"` throws
 * `TypeError: Cannot use 'in' operator`, so a server that starts emitting a
 * scalar under a new root key would take the whole panel down instead of being
 * ignored — the exact opposite of what R6 asks for. The e2e fixture already
 * serves a string `summary` and an object-of-scalars `source_health` at the
 * root, so the crash is reachable, not theoretical.
 *
 * `Array.isArray` is excluded deliberately: a JSON array is an object whose
 * entries could each look metric-shaped, and rendering one as a keyed group
 * would invent metric names out of array indices.
 */
function isMetricGroup(value: unknown): value is Record<string, RainfallMetric> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const entries = Object.values(value);
  return (
    entries.length > 0 &&
    entries.every(
      (entry) =>
        entry !== null && typeof entry === 'object' && 'metric' in entry && 'state' in entry
    )
  );
}

interface RenderedGroup {
  readonly key: string;
  readonly title: string;
  readonly group: Record<string, RainfallMetric>;
}

/** Every metric group the snapshot actually carries: the known ones in their
 *  published order, then anything else that passes the guard, titled with its
 *  raw key. */
function renderedGroups(snapshot: RainfallAnalysisSnapshot): RenderedGroup[] {
  const entries = Object.entries(snapshot as unknown as Record<string, unknown>);
  const known = KNOWN_GROUP_ORDER.map(
    (key) => entries.find(([entryKey]) => entryKey === key) ?? [key, undefined]
  );
  const unknown = entries.filter(
    ([key]) => !KNOWN_GROUP_ORDER.includes(key) && !NON_GROUP_ROOT_KEYS.has(key)
  );
  return [...known, ...unknown]
    .filter((entry): entry is [string, Record<string, RainfallMetric>] => isMetricGroup(entry[1]))
    .map(([key, group]) => ({ key, title: GROUP_TITLES[key] ?? key, group }));
}

/** Every metric of every rendered group, which is the set the shared
 *  provenance block speaks for — BOTH folds, not just this list's own. */
export function snapshotMetrics(snapshot: RainfallAnalysisSnapshot): RainfallMetric[] {
  return renderedGroups(snapshot).flatMap(({ group }) => Object.values(group));
}

/**
 * The chip a row shows — or `null`, which is the common case.
 *
 * EXCEPTION-ONLY, and that is the whole rule. A chip on every row is a row of
 * chips: the reader stops reading them, and in a 380 px panel they truncate
 * into fragments (`PROVISIO… FALLB… DISPONI…`). So a metric that is simply
 * available and definitive shows NOTHING, and the chip is reserved for the
 * rows where the state is the point.
 *
 * Full Spanish words, never a wire token: `Dato provisorio`, not `FALLBACK`.
 * And the chip is PRESENTATION — the state, the reason, the temporal state and
 * `fallback_used` all remain in the row's text below it, which is where the
 * disclosure floor is actually discharged (D9). Dropping a chip never drops a
 * fact.
 */
function stateChip(metric: RainfallMetric): { label: string; color: string } | null {
  if (metric.state !== 'available') {
    return { label: metricStateLabel(metric), color: STATE_COLORS[metric.state] };
  }
  if (metric.temporal_state === 'provisional' || metric.fallback_used) {
    return { label: 'Dato provisorio', color: 'violet' };
  }
  return null;
}

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
  const chip = stateChip(metric);
  return (
    <Stack gap={2} data-testid={`rainfall-metric-${name}`}>
      <Group gap="xs" wrap="wrap" justify="space-between">
        <Text size="xs">{metricLabel(name, baseline)}</Text>
        <Group gap={6} wrap="nowrap">
          {chip !== null && (
            <Badge size="xs" variant="light" color={chip.color} data-metric-state={metric.state}>
              {chip.label}
            </Badge>
          )}
          <Text size="xs" fw={600}>
            {formatMetricValue(metric)}
          </Text>
        </Group>
      </Group>
      {/* The state, ALWAYS, in text. The chip above is exception-only — it is
          presentation — so this is where the disclosure floor is actually
          discharged: an available metric shows no chip, and its state is still
          a served field the fold must render (D9). Dropping a chip must never
          drop a fact. */}
      <Text size="xs" c="dimmed">
        {`Estado: ${metricStateLabel(metric)}`}
      </Text>
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
            Fuente alternativa
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
   * unrecognised group lands there by default (R6) — which is now literally
   * true of the renderer below, not just of this prop: it iterates the
   * snapshot's own keys and titles an unknown one with its raw name.
   */
  readonly exclude?: readonly string[];
}

export function RainfallMetricList({ snapshot, exclude }: RainfallMetricListProps) {
  return (
    <Stack gap="xs" data-testid="rainfall-metrics">
      {renderedGroups(snapshot)
        .filter(({ key }) => !exclude?.includes(key))
        .map(({ key, title, group }) => (
          <RainfallMetricGroup key={key} group={group} baseline={snapshot.baseline} title={title} />
        ))}
      {typeof snapshot.summary === 'string' && snapshot.summary.length > 0 && (
        <Text size="xs" fs="italic" data-testid="rainfall-summary">
          {snapshot.summary}
        </Text>
      )}
    </Stack>
  );
}
