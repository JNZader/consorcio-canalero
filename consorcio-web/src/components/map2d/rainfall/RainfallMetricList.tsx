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
import {
  formatMetricValue,
  hoistProvenance,
  metricEvidenceLine,
  metricLabel,
  metricStateLabel,
  PROVENANCE_FIELD,
  PROVENANCE_FIELDS,
  type ProvenanceField,
  provenanceFieldValue,
  type RainfallProvenanceHoist,
  stringifyUnknownFields,
} from './rainfallFormat';

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

/** How each hoistable field is NAMED, in the block and on the row alike — one
 *  vocabulary, so a field that moves between the two does not change words on
 *  the way. */
const PROVENANCE_FIELD_LABELS: Record<ProvenanceField, string> = {
  [PROVENANCE_FIELD.SOURCE_ID]: 'Fuente',
  [PROVENANCE_FIELD.SOURCE_CLASS]: 'Clase de fuente',
  [PROVENANCE_FIELD.METHOD]: 'Método',
  [PROVENANCE_FIELD.NOMINAL_RESOLUTION]: 'Resolución nominal',
  [PROVENANCE_FIELD.AGGREGATION]: 'Agregación',
  [PROVENANCE_FIELD.SPATIAL_SCOPE]: 'Ámbito espacial',
  [PROVENANCE_FIELD.FRESHNESS]: 'Frescura',
  [PROVENANCE_FIELD.REVISION]: 'Revisión',
};

/** A dimmed metadata line — or nothing at all when the snapshot served nothing
 *  to put in it. There is no `—` branch on purpose: D9a rule 3 forbids proving
 *  a field was considered by printing a placeholder for it. */
function MetadataLine({ text }: { readonly text: string | null }) {
  if (text === null || text.length === 0) return null;
  return (
    <Text size="xs" c="dimmed">
      {text}
    </Text>
  );
}

/** `Cobertura: 92% · Completitud: 88%` — each half bound only when served, so
 *  a metric carrying one of the two prints one of the two. Never hoisted (D5):
 *  they are the metric's OWN quality, and stating them once for a set would
 *  make a claim about metrics that do not share it. */
function qualityCoverageLine(metric: RainfallMetric): string | null {
  const parts: string[] = [];
  if (typeof metric.coverage === 'number') {
    parts.push(`Cobertura: ${Math.round(metric.coverage * 100)}%`);
  }
  if (typeof metric.completeness === 'number') {
    parts.push(`Completitud: ${Math.round(metric.completeness * 100)}%`);
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

/** The window this metric was computed over, AS SERVED. Never hoisted: the
 *  intervals are what makes d7 a different metric from d90, and inside `annual`
 *  they are equal only by accident. */
function intervalLine(metric: RainfallMetric): string | null {
  const { interval_start: start, interval_end: end } = metric;
  if (
    typeof start !== 'string' ||
    typeof end !== 'string' ||
    start.length === 0 ||
    end.length === 0
  )
    return null;
  return `Intervalo: ${start} → ${end}`;
}

/** Provisional-or-final and fallback use, in TEXT, on every row that serves
 *  them. The coloured markers above are presentation and only appear in the
 *  exceptional case; this line is the contract, and the enumerated floor asks
 *  for both fields whenever the snapshot carries them. Same discipline as
 *  `Estado: {word}` beside the exception-only chip (OWN-010). */
function temporalOriginLine(metric: RainfallMetric): string | null {
  const parts: string[] = [];
  if (typeof metric.temporal_state === 'string') {
    parts.push(`Estado temporal: ${metric.temporal_state}`);
  }
  if (typeof metric.fallback_used === 'boolean') {
    parts.push(`Origen: ${metric.fallback_used ? 'fuente alternativa' : 'fuente primaria'}`);
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

export interface RainfallMetricRowProps {
  readonly name: string;
  readonly metric: RainfallMetric;
  /** Served period, so the `normal` row names the SAME baseline as the phrase
   *  above it — never a constant frozen in the frontend (LI4-004). */
  readonly baseline: string;
  /**
   * What the shared provenance block already said for the whole displayed set.
   *
   * The row prints exactly the fields that DIVERGED (`hoist.perMetric`), so the
   * reader gets `shared ∪ row` and never six identical provenance blocks. With
   * no hoist supplied the row prints every field it carries — a group rendered
   * outside the technical fold with no block above it must not lose provenance
   * just because nobody consolidated it.
   */
  readonly hoist?: RainfallProvenanceHoist;
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
export function RainfallMetricRow({ name, metric, baseline, hoist }: RainfallMetricRowProps) {
  const chip = stateChip(metric);
  // Exactly the provenance fields the shared block did NOT already state. With
  // no block above, every field this metric carries.
  const ownFields = hoist?.perMetric ?? PROVENANCE_FIELDS;
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
      </Group>
      {/* `shared ∪ row`: whatever diverged from the block above, named with the
          same words the block uses. A metric served in the stripped four-field
          shape carries none of these, so it prints none of them — and that is
          the whole of D9a rule 3, not a degradation of it. */}
      {ownFields.map((field) => (
        <MetadataLine
          key={field}
          text={
            provenanceFieldValue(metric, field) === undefined
              ? null
              : `${PROVENANCE_FIELD_LABELS[field]}: ${provenanceFieldValue(metric, field)}`
          }
        />
      ))}
      <MetadataLine text={qualityCoverageLine(metric)} />
      <MetadataLine text={intervalLine(metric)} />
      {/* The metric's OWN evidence statement, gated on the metric's OWN fields
          (D9a rule 2). Not `evidenceFooter`, which says "en este análisis" and
          is a claim about the whole envelope (UXJA-205). */}
      <MetadataLine text={metricEvidenceLine(metric)} />
      <MetadataLine
        text={
          stringifyUnknownFields(metric.quality).length > 0
            ? `Calidad: ${stringifyUnknownFields(metric.quality)}`
            : null
        }
      />
      <MetadataLine
        text={
          Array.isArray(metric.discrepancies) && metric.discrepancies.length > 0
            ? `Discrepancias: ${metric.discrepancies.join('; ')}`
            : null
        }
      />
      <MetadataLine text={temporalOriginLine(metric)} />
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
  /** Passed straight through to the rows: what the shared block already said
   *  for the whole displayed set, so these rows print only what diverges. */
  readonly hoist?: RainfallProvenanceHoist;
}

/**
 * ONE metric group. Renders nothing at all for an absent or empty group: the
 * antecedents fold mounts this directly, and a heading over zero rows would
 * claim a section the snapshot never served.
 */
export function RainfallMetricGroup({ group, baseline, title, hoist }: RainfallMetricGroupProps) {
  if (!group || Object.keys(group).length === 0) return null;
  return (
    <Stack gap={4}>
      {title !== undefined && (
        <Text size="xs" fw={600} c="dimmed">
          {title}
        </Text>
      )}
      {Object.entries(group).map(([name, metric]) => (
        <RainfallMetricRow
          key={name}
          name={name}
          metric={metric}
          baseline={baseline}
          hoist={hoist}
        />
      ))}
    </Stack>
  );
}

/**
 * What the shared block may honestly claim, in one sentence, DERIVED from what
 * was actually compared and from what is actually on screen (S2R3-001).
 *
 * Two independent axes, and both of them used to be asserted rather than
 * derived:
 *
 *   - `everyDisplayedCompared` — `hoistProvenance` compares only metrics that
 *     CARRY provenance (UXJB-110, `rainfallFormat.ts:661`). A metric served in
 *     the stripped four-field shape (`service.py:479-518`) is DISPLAYED in the
 *     folds this sentence names and was never in the comparison set, so
 *     "todas las métricas mostradas" over-claims membership for it. The
 *     over-claim is the sentence's, not the hoist's: excluding such a metric is
 *     the right rule (comparing it would collapse the hoist to zero), and the
 *     row itself is value-less and self-identifying. So the SENTENCE narrows —
 *     "solo … con procedencia servida" — and the comparison set is untouched.
 *     This is the resolution of the UXJB-110 (exclusion) ↔ UXJA-107 (universal
 *     wording) contradiction: universal wording holds only when the exclusion
 *     removed nothing.
 *   - `namesAntecedents` — the antecedents fold mounts only for a non-empty
 *     `antecedents` group (`RainfallDetailPanel.tsx:570`). Naming a fold that
 *     is not on screen points the reader at a control that does not exist.
 */
function sharedProvenanceScope(everyDisplayedCompared: boolean, namesAntecedents: boolean): string {
  const where = namesAntecedents ? 'en este plegable y en Antecedentes' : 'en este plegable';
  return everyDisplayedCompared
    ? `Vale para todas las métricas mostradas${namesAntecedents ? ', ' : ' '}${where}.`
    : `Vale solo para las métricas con procedencia servida, ${where}.`;
}

/**
 * The provenance every COMPARED metric agreed on, stated ONCE.
 *
 * ITS SCOPE IS BOTH FOLDS, and the wording says so — never "de esta sección"
 * (UXJA-107). The antecedents live in a different fold, and a block scoped to
 * this one would have left their provenance homeless while the delta requires
 * every field to be reachable by operating at most ONE disclosure control. It
 * need not be the SAME control for every field: opening this fold alone exposes
 * the shared provenance of the antecedents too, and opening the antecedents
 * alone exposes their values, states and whatever diverged.
 *
 * The sentence is BUILT, not hardcoded: see {@link sharedProvenanceScope} for
 * why a fixed universal sentence was a claim the hoist did not support.
 *
 * Renders nothing when nothing is shared — an empty comparison set (every
 * metric served stripped) or a set that agrees on no field at all. There is no
 * empty block and no placeholder: the rows then carry everything themselves.
 */
function SharedProvenance({
  hoist,
  scope,
}: {
  readonly hoist: RainfallProvenanceHoist;
  readonly scope: string;
}) {
  const fields = PROVENANCE_FIELDS.filter((field) => hoist.shared[field] !== undefined);
  if (fields.length === 0) return null;
  return (
    <Stack gap={2} data-testid="rainfall-provenance-shared">
      <Text size="xs" fw={600} c="dimmed">
        Procedencia común
      </Text>
      <Text size="xs" c="dimmed">
        {scope}
      </Text>
      {fields.map((field) => (
        <Text key={field} size="xs" c="dimmed">
          {`${PROVENANCE_FIELD_LABELS[field]}: ${hoist.shared[field]}`}
        </Text>
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
  // The hoist is computed over EVERY displayed metric of the snapshot, not just
  // the groups this list renders: the block speaks for both folds, so it must
  // be compared over both (D5).
  const displayed = snapshotMetrics(snapshot);
  const hoist = hoistProvenance(displayed);
  // Both halves of what the block may claim, read off the SAME sources the
  // renderers use: the comparison set's own membership rule, and whether the
  // antecedents group renders in a fold of its own (it is a group of this
  // snapshot AND this list was told not to render it).
  const scope = sharedProvenanceScope(
    displayed.every((metric) => metric.provenance !== undefined),
    renderedGroups(snapshot).some(({ key }) => key === 'antecedents') &&
      exclude?.includes('antecedents') === true
  );
  const sourceHealth = stringifyUnknownFields(snapshot.source_health);
  return (
    <Stack gap="xs" data-testid="rainfall-metrics">
      <SharedProvenance hoist={hoist} scope={scope} />
      {/* The narrative sits UNDER the block: it summarises the metrics below
          it, and a summary above the provenance it summarises reads as the
          fold's own heading. */}
      {typeof snapshot.summary === 'string' && snapshot.summary.length > 0 && (
        <Text size="xs" fs="italic" data-testid="rainfall-summary">
          {snapshot.summary}
        </Text>
      )}
      {renderedGroups(snapshot)
        .filter(({ key }) => !exclude?.includes(key))
        .map(({ key, title, group }) => (
          <RainfallMetricGroup
            key={key}
            group={group}
            baseline={snapshot.baseline}
            title={title}
            hoist={hoist}
          />
        ))}
      {/* `source_health` is a ROOT key of the snapshot (`lib/api/rainfall.ts:94`),
          not a member of `RainfallMetric`: ONE line for the analysis, at the
          foot, never repeated per metric — that would attribute one
          analysis-wide fact to six metrics that never carried it. Through the
          same stringify guard `quality` uses, and absent entirely when the
          guard yields nothing (D9a rules 3 and 4). */}
      {sourceHealth.length > 0 && (
        <Text size="xs" c="dimmed" data-testid="rainfall-source-health">
          {`Estado de fuentes: ${sourceHealth}`}
        </Text>
      )}
    </Stack>
  );
}
