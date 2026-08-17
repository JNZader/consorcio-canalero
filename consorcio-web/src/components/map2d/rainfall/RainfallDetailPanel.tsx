/**
 * RainfallDetailPanel.tsx (Lluvia v2 — Phase 3)
 *
 * Authenticated Rainfall v2 technical detail, mounted in the ficha's Lluvia
 * tab under the public PrecipChart (untouched). RENDER GATE only — the backend
 * is the authorization boundary; anonymous visitors and non-staff never see
 * the control (anti-flash criterion as `useAnalysisToolsGate`). A queued (202)
 * answer is a LABELLED pending state that polls with a bounded budget; once
 * the budget is exhausted the panel shows an honest terminal "no disponible
 * aún" state with a manual retry — never an auto-update promise that cannot be
 * kept (RESILIENCE-001/002). All state changes go through an aria-live region;
 * parcel-originated results keep the "Estimación regional" label (spec
 * "Supported Analysis Scope and Parcel Semantics").
 *
 * ANSWER-FIRST HIERARCHY (design D1/D2/D6, spec delta "Answer-First Rainfall
 * Presentation Hierarchy"). This is the ONLY stateful node of the surface —
 * scope, year, campaign preset, export, announcer, render gate — and the only
 * place a derived fact is computed. Everything below it is a pure function of
 * its props, which is what makes a future `/lluvia` page a re-mount rather than
 * a rewrite.
 *
 * The order is the hierarchy: announcer, header, the two controls that
 * RE-QUERY, the answer card, the chart, the export row — and only then two
 * collapsed folds. `CollapsibleSection` UNMOUNTS its body when closed
 * (`CollapsibleSection.tsx:113`), so anything a reader must keep is above the
 * first fold, never inside one.
 */

import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  NativeSelect,
  SegmentedControl,
  Stack,
  Text,
  VisuallyHidden,
} from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useEffect, useRef, useState } from 'react';

import { useRainfallAnalysis, useRainfallScopes } from '../../../hooks/useRainfallAnalysis';
import {
  type RainfallAnalysisResponse,
  type RainfallMetric,
  type RainfallScopeChoice,
  downloadRainfallCsv,
  downloadRainfallXlsx,
} from '../../../lib/api/rainfall';
import { useCanAccess } from '../../../stores/authStore';
import { CollapsibleSection } from '../../ui/CollapsibleSection';
import {
  CAMPAIGN_PRESET,
  type CampaignPreset,
  RainfallAccumulationChart,
} from './RainfallAccumulationChart';
import { RainfallAnswerCard } from './RainfallAnswerCard';
import { RainfallMetricGroup, RainfallMetricList, snapshotMetrics } from './RainfallMetricList';
import {
  RAINFALL_SCOPE_LABELS,
  compactAntecedent,
  deriveFreshness,
  describeMetricState,
  hoistProvenance,
  scopeChoiceLabels,
  shouldUseSegmentedScope,
} from './rainfallFormat';

const CURRENT_YEAR = new Date().getFullYear();
/** The oldest year the selector offers — and the floor the fallback stops at. */
const EARLIEST_YEAR = 1991;
const YEAR_OPTIONS = Array.from({ length: CURRENT_YEAR - 1990 }, (_, i) =>
  String(CURRENT_YEAR - i)
);

/**
 * What a reader is told while the analysis is being built (OWN-002).
 *
 * ONE sentence, stated identically by the alert and by the `aria-live` region.
 * It still does the job the queued state exists for — it names what is
 * happening and promises the update the poll actually delivers, so this is a
 * LABELLED pending state and never a silent spinner. What it no longer does is
 * paste the backend's job identifiers into user copy.
 */
const QUEUED_SENTENCE = 'Análisis en preparación — se actualiza automáticamente en unos minutos.';

const DETAIL_PLACEMENT = {
  PRIORITY: 'priority',
  STANDARD: 'standard',
} as const;

type DetailPlacement = (typeof DETAIL_PLACEMENT)[keyof typeof DETAIL_PLACEMENT];

function PlacedDetail({
  prioritizeAnswer,
  placement,
  children,
}: {
  readonly prioritizeAnswer: boolean;
  readonly placement: DetailPlacement;
  readonly children: ReactNode;
}) {
  const active = prioritizeAnswer ? DETAIL_PLACEMENT.PRIORITY : DETAIL_PLACEMENT.STANDARD;
  return active === placement ? children : null;
}

/**
 * What a reader is told when polling gave up WHILE the previous year is on
 * screen (R3-001 / R4-001).
 *
 * The substitution notice cannot disappear just because the poll budget ran
 * out: the panel is still showing `previousYear` under a selector reading
 * `year`, and "which year am I looking at" stays the question a reader cannot
 * answer from the numbers. Terminal form — it names both years and promises
 * nothing, because auto-refresh is over.
 */
function fallbackTerminalSentence(previousYear: number, year: number): string {
  return `Mostrando el análisis ${previousYear}. El análisis ${year} no está disponible aún.`;
}

/** The antecedent windows, in the order the collapsed header states them. A
 *  FIXED order: a header whose items move with the data is a header nobody can
 *  learn to scan. */
const ANTECEDENT_ORDER: ReadonlyArray<{ readonly key: string; readonly label: string }> = [
  { key: 'd7', label: '7d' },
  { key: 'd30', label: '30d' },
  { key: 'd90', label: '90d' },
];

function scopeKey(scope: RainfallScopeChoice): string {
  return `${scope.kind}:${scope.id}:${scope.version}`;
}

/**
 * The collapsed `Antecedentes` header's values (design D2a).
 *
 * The spec delta makes this a CONTRACT, not a decoration: "a collapsed section
 * MUST show its key values in the collapsed header". So:
 *
 *  - whole millimetres through `compactAntecedent` — `formatAccumulated` would
 *    yield `31.0 mm`, a decimal nobody reads off a header and a unit repeated
 *    once per value inside a ~26-character string at 348 px;
 *  - the unit stated ONCE, at the END. Dropping it when the last item is
 *    unavailable would make its POSITION depend on the data, so `… 90d — mm`
 *    reads oddly and is accepted deliberately;
 *  - a non-available antecedent prints `—`, never `0`, and carries its reason
 *    in `title` + `aria-label`, so what a screen reader hears is the STATE, not
 *    a dash — and the state is reachable without expanding anything.
 */
function AntecedentAccessory({ group }: { readonly group: Record<string, RainfallMetric> }) {
  const items: ReadonlyArray<{ key: string; label: string; metric: RainfallMetric }> =
    ANTECEDENT_ORDER.flatMap(({ key, label }) => {
      const metric = group[key];
      return metric === undefined ? [] : [{ key, label, metric }];
    });
  if (items.length === 0) return null;

  return (
    <Text size="xs" c="dimmed" truncate data-testid="rainfall-antecedents-summary">
      {items.map(({ key, label, metric }, index) => {
        const value = compactAntecedent(metric);
        const reason = value === '—' ? (metric.reason ?? describeMetricState(metric)) : null;
        return (
          <Text
            component="span"
            key={key}
            size="xs"
            title={reason ?? undefined}
            aria-label={reason !== null ? `${label}: ${describeMetricState(metric)}` : undefined}
          >
            {`${index > 0 ? ' · ' : ''}${label} ${value}`}
          </Text>
        );
      })}
      {' mm'}
    </Text>
  );
}

/**
 * The regional scope picker — named options, and the RIGHT control for how
 * many there are (OWN-001).
 *
 * Labelling by kind alone offered a real parcel `Zona | Zona | Cuenca | Cuenca
 * | Cuenca`: five options, three identical, a control that can only be guessed
 * at. And five segments do not fit the panel's 348 px, so above the budget the
 * control becomes the same `NativeSelect` the year uses beside it — a
 * segmented control that does not fit is the badge-truncation defect one level
 * up, with the whole label set as its victim.
 *
 * Its own component so the panel keeps ONE control-flow branch instead of two
 * nested ternaries around large JSX. Pure — the panel still owns the state.
 */
function ScopeControl({
  choices,
  selected,
  onSelect,
}: {
  readonly choices: readonly RainfallScopeChoice[];
  readonly selected: RainfallScopeChoice | null;
  readonly onSelect: (key: string) => void;
}) {
  if (choices.length <= 1) return null;

  const labels = scopeChoiceLabels(choices);
  const data = choices.map((choice, index) => ({
    value: scopeKey(choice),
    label: labels[index] ?? RAINFALL_SCOPE_LABELS[choice.kind],
  }));
  const value = selected ? scopeKey(selected) : undefined;

  if (shouldUseSegmentedScope(labels)) {
    return (
      <SegmentedControl
        size="xs"
        fullWidth
        value={value}
        onChange={onSelect}
        data={data}
        aria-label="Ámbito regional"
        data-testid="rainfall-scope-switch"
      />
    );
  }

  return (
    <NativeSelect
      size="xs"
      label="Ámbito regional"
      aria-label="Ámbito regional"
      value={value}
      onChange={(event) => onSelect(event.currentTarget.value)}
      data={data}
      data-testid="rainfall-scope-switch"
      style={{ flex: '1 1 160px', minWidth: 0 }}
    />
  );
}

/**
 * Terminal: polling gave up without a ready snapshot (RESILIENCE-001/002).
 *
 * Honest labelled failure with a manual retry that re-runs the fetch with a
 * fresh budget — auto-refresh is over and the UI never promises it.
 *
 * When the previous year is on screen this alert INHERITS the queued block's
 * two jobs (R3-001), because that block unmounts at `gaveUp`: it states the
 * substitution in TERMINAL form and it carries `data-showing-year`. Without
 * that, the panel rendered a full Y-1 card, chart and export row under a
 * selector reading Y, beside an alert naming neither year.
 *
 * Its own component for the same reason `ScopeControl` is one: the panel stays
 * under the cognitive-complexity gate by extraction, never by raising it. Pure.
 */
function UnavailableAlert({
  showingFallback,
  year,
  previousYear,
  onRetry,
}: {
  readonly showingFallback: boolean;
  readonly year: number;
  readonly previousYear: number;
  readonly onRetry: () => void;
}) {
  return (
    <Alert
      color="yellow"
      variant="light"
      data-testid="rainfall-unavailable"
      data-showing-year={showingFallback ? String(previousYear) : undefined}
    >
      <Text size="xs">
        {showingFallback
          ? fallbackTerminalSentence(previousYear, year)
          : 'Análisis no disponible aún. Se agotó el tiempo de espera automático.'}
      </Text>
      <Button size="xs" variant="light" mt="xs" onClick={onRetry} data-testid="rainfall-retry">
        Reintentar
      </Button>
    </Alert>
  );
}

function LoadingRow({ label }: { readonly label: string }) {
  return (
    <Group gap="xs">
      <Loader size="xs" />
      <Text size="xs" c="dimmed">
        {label}
      </Text>
    </Group>
  );
}

function AnalysisStatus({
  data,
  gaveUp,
  isError,
  showingFallback,
  previousYear,
  year,
  onRetry,
}: {
  readonly data: RainfallAnalysisResponse | undefined;
  readonly gaveUp: boolean;
  readonly isError: boolean;
  readonly showingFallback: boolean;
  readonly previousYear: number;
  readonly year: number;
  readonly onRetry: () => void;
}) {
  if (data?.type === 'queued' && !gaveUp && !isError) {
    return (
      <Alert
        color="blue"
        variant="light"
        data-testid="rainfall-queued"
        data-queued-labels={data.queued.labels.length > 0 ? data.queued.labels.join(', ') : undefined}
        data-showing-year={showingFallback ? String(previousYear) : undefined}
      >
        <Text size="xs">
          {showingFallback
            ? `Mostrando ${previousYear} — el análisis ${year} se está preparando y se actualizará solo.`
            : QUEUED_SENTENCE}
        </Text>
      </Alert>
    );
  }

  if (gaveUp) {
    return (
      <UnavailableAlert
        showingFallback={showingFallback}
        year={year}
        previousYear={previousYear}
        onRetry={onRetry}
      />
    );
  }

  return null;
}

export function RainfallDetailPanel({
  nomenclatura,
  pollIntervalMs,
  maxQueuedPolls,
  prioritizeAnswer = false,
}: {
  readonly nomenclatura: string;
  /** Test seam: forwarded to `useRainfallAnalysis` (see the hook options). */
  readonly pollIntervalMs?: number;
  /** Test seam: forwarded to `useRainfallAnalysis` (see the hook options). */
  readonly maxQueuedPolls?: number;
  /**
   * Mobile-sheet layout seam. The ficha already owns the dataset selector, so
   * its short `medio` stage must put the answer before this panel's secondary
   * header and re-query controls. Desktop keeps the controls-first hierarchy.
   */
  readonly prioritizeAnswer?: boolean;
}) {
  const canAccess = useCanAccess(['admin', 'operador']);
  const queryClient = useQueryClient();
  const previousNomenclatura = useRef(nomenclatura);
  useEffect(() => {
    if (previousNomenclatura.current !== nomenclatura) {
      previousNomenclatura.current = nomenclatura;
      if (canAccess) {
        queryClient.invalidateQueries({ queryKey: ['rainfall-analysis'] });
      }
    }
  }, [nomenclatura, canAccess, queryClient]);
  const scopes = useRainfallScopes(canAccess ? nomenclatura : null);
  const choices =
    scopes.data?.kind === 'choices'
      ? scopes.data.choices
      : scopes.data?.kind === 'scope'
        ? [scopes.data.scope]
        : [];
  const regionalEstimate = scopes.data?.regional_estimate === true;

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [year, setYear] = useState(CURRENT_YEAR);
  // The chart's display window, owned HERE (design D6): the chart is
  // controlled-only, so there is one source of truth for it and a URL could
  // carry it the day this content moves to a page.
  const [preset, setPreset] = useState<CampaignPreset>(CAMPAIGN_PRESET.CALENDAR);
  const selected = choices.find((c) => scopeKey(c) === selectedKey) ?? choices[0] ?? null;

  const analysis = useRainfallAnalysis(canAccess ? selected : null, year, {
    pollIntervalMs,
    maxQueuedPolls,
  });
  const primarySnapshot = analysis.data?.type === 'ready' ? analysis.data.snapshot : null;

  // ONE step back, never a cascade. While the selected year is being prepared
  // the reader is handed the previous year rather than an empty panel — the
  // year they would have compared against anyway. If THAT one is also queued
  // the ladder stops here: a fallback that keeps walking backwards turns one
  // slow answer into a queue of them.
  const previousYear = year - 1;
  const canFallBack =
    analysis.data?.type === 'queued' && !analysis.isError && previousYear >= EARLIEST_YEAR;
  const fallback = useRainfallAnalysis(canAccess && canFallBack ? selected : null, previousYear, {
    pollIntervalMs,
    maxQueuedPolls,
  });
  const fallbackSnapshot = fallback.data?.type === 'ready' ? fallback.data.snapshot : null;

  // What the panel is actually SHOWING. The export buttons, the chart and the
  // folds all read this, so they describe the revision on screen rather than
  // the one that has not been built yet.
  const showingFallback = primarySnapshot === null && fallbackSnapshot !== null;
  const snapshot = primarySnapshot ?? fallbackSnapshot;

  const [announcement, setAnnouncement] = useState('');
  useEffect(() => {
    if (showingFallback) {
      // The INTERSECTION is explicit (R3-001/R4-001). This branch is tested
      // FIRST, so the `gaveUp` case below was unreachable while a previous year
      // was on screen: the region kept saying "se está preparando" after
      // polling had permanently stopped — the auto-update promise this file's
      // header forbids. Both cases name BOTH years, and the terminal one states
      // the same fact the visible alert states (the contract above).
      setAnnouncement(
        analysis.gaveUp
          ? `${fallbackTerminalSentence(previousYear, year)} Puede reintentar manualmente.`
          : `Mostrando el análisis ${previousYear}. El análisis ${year} se está preparando.`
      );
    } else if (analysis.data?.type === 'queued') {
      if (analysis.gaveUp) {
        setAnnouncement('Análisis no disponible aún. Puede reintentar manualmente.');
      } else {
        // The SAME sentence the alert prints. The served labels are internal
        // job identifiers (`role:daily`, `analysis_missing`) and a screen
        // reader must not be the one reader who gets handed them (OWN-002).
        setAnnouncement(QUEUED_SENTENCE);
      }
    } else if (snapshot) {
      // Two dimensions, separated. "…disponible para Zona 2026" ran the scope
      // and the year together into something that reads like a place called
      // "Zona 2026"; a listener has no layout to disambiguate it with.
      setAnnouncement(
        `Análisis de lluvia ${year} disponible · Alcance: ${RAINFALL_SCOPE_LABELS[snapshot.scope.kind]}`
      );
    } else if (analysis.isError) {
      setAnnouncement('No se pudo obtener el análisis de lluvia.');
    }
  }, [
    analysis.data,
    analysis.gaveUp,
    analysis.isError,
    showingFallback,
    previousYear,
    snapshot,
    year,
  ]);

  // One in-flight export at a time, tracked by FORMAT: two independent
  // booleans would let both buttons spin at once and a shared one would spin
  // the wrong button.
  const [exportingFormat, setExportingFormat] = useState<'csv' | 'xlsx' | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  async function exportAnalysis(revisionId: string, format: 'csv' | 'xlsx') {
    setExportingFormat(format);
    setExportError(null);
    try {
      await (format === 'csv' ? downloadRainfallCsv(revisionId) : downloadRainfallXlsx(revisionId));
    } catch (error) {
      setExportError(
        error instanceof Error
          ? error.message
          : `No se pudo exportar el ${format === 'csv' ? 'CSV' : 'Excel'}.`
      );
    } finally {
      setExportingFormat(null);
    }
  }

  if (!canAccess) return null;

  return (
    <Stack gap="xs" data-testid="rainfall-detail">
      {/* Every state change is announced, so queued → ready is perceivable
          without watching the panel.
          VISUALLY HIDDEN, and that is a fix, not a downgrade: this region
          restates whatever is ALREADY on screen — the queued alert, the
          terminal alert, the error, the card — so rendering it visibly printed
          "Análisis en preparación" twice, one line apart. It stays in the
          accessibility tree, still `aria-live="polite"`, still carrying the
          same sentence; it simply stops being a second visible copy of the
          state it announces. */}
      <VisuallyHidden aria-live="polite" data-testid="rainfall-live">
        {announcement}
      </VisuallyHidden>

      {/* A fallback disclosure must still precede the answer it qualifies.
          Normal ready analyses have no status block, so `prioritizeAnswer`
          makes the card the first visible content in the mobile sheet without
          hiding or duplicating any control. */}
      <PlacedDetail prioritizeAnswer={prioritizeAnswer} placement={DETAIL_PLACEMENT.PRIORITY}>
        <AnalysisStatus
          data={analysis.data}
          gaveUp={analysis.gaveUp}
          isError={analysis.isError}
          showingFallback={showingFallback}
          previousYear={previousYear}
          year={year}
          onRetry={() => analysis.retry()}
        />
        {snapshot && (
          <RainfallAnswerCard snapshot={snapshot} freshness={deriveFreshness(snapshot)} />
        )}
      </PlacedDetail>

      <Group gap="xs" justify="space-between" wrap="nowrap">
        <Text size="sm" fw={600}>
          Detalle técnico de lluvia
        </Text>
        {regionalEstimate && (
          <Badge size="xs" variant="light" color="blue" data-testid="rainfall-regional-estimate">
            Estimación regional
          </Badge>
        )}
      </Group>

      {scopes.isLoading && <LoadingRow label="Resolviendo ámbito regional…" />}
      {scopes.isError && (
        <Text size="xs" c="red">
          {scopes.error?.message ?? 'No se pudo resolver el ámbito regional.'}
        </Text>
      )}

      {/* The two controls that RE-QUERY, together, directly under the header
          and OUTSIDE the snapshot gate — they are how a reader moves while the
          analysis is loading, queued or unavailable. The campaign preset is
          NOT here on purpose (D6): it windows a series, so it lives with the
          chart, inside the gate, where it cannot become a live control over a
          series that does not exist yet. */}
      <Stack gap="xs" data-testid="rainfall-controls">
        {/* The scope options are named so they can be TOLD APART (OWN-001):
            labelling by kind alone offered a real parcel `Zona | Zona | Cuenca
            | Cuenca | Cuenca`, three of them identical. And five segments do
            not fit 348 px, so above the budget the control becomes the same
            select the year uses — a segmented control that does not fit is the
            badge-truncation defect one level up. */}
        <ScopeControl choices={choices} selected={selected} onSelect={setSelectedKey} />

        {selected && (
          <Group gap="xs" wrap="wrap">
            <NativeSelect
              size="xs"
              label="Año de análisis"
              aria-label="Año de análisis"
              value={String(year)}
              onChange={(event) => setYear(Number(event.currentTarget.value))}
              data={YEAR_OPTIONS}
              data-testid="rainfall-year-select"
              // Container-driven, never viewport-driven: Mantine breakpoints
              // read the VIEWPORT, and inside a 380 px card on a 1920 px screen
              // they would claim columns that do not fit. This degrades by
              // stacking, never by overflowing.
              style={{ flex: '1 1 160px', minWidth: 0 }}
            />
          </Group>
        )}
      </Stack>

      {analysis.isLoading && <LoadingRow label="Consultando análisis…" />}
      {analysis.isError && (
        <Stack gap="xs">
          <Text size="xs" c="red">
            {analysis.error?.message ?? 'No se pudo obtener el análisis de lluvia.'}
          </Text>
          <Button
            size="xs"
            variant="light"
            onClick={() => analysis.retry()}
            data-testid="rainfall-retry"
          >
            Reintentar
          </Button>
        </Stack>
      )}

      <PlacedDetail prioritizeAnswer={prioritizeAnswer} placement={DETAIL_PLACEMENT.STANDARD}>
        <AnalysisStatus
          data={analysis.data}
          gaveUp={analysis.gaveUp}
          isError={analysis.isError}
          showingFallback={showingFallback}
          previousYear={previousYear}
          year={year}
          onRetry={() => analysis.retry()}
        />
      </PlacedDetail>

      {snapshot && (
        <>
          {/* THE ANSWER, always visible: percentile headline, derived
              adjective, the textual equivalent and the freshness of THIS
              analysis — derived ONCE, here, and passed down (D1a). Nothing
              below re-derives it. */}
          <PlacedDetail prioritizeAnswer={prioritizeAnswer} placement={DETAIL_PLACEMENT.STANDARD}>
            <RainfallAnswerCard snapshot={snapshot} freshness={deriveFreshness(snapshot)} />
          </PlacedDetail>
          {/* The year-vs-normal comparison the owner asked for. Mounted here
              rather than inside the metric list because it owns its own
              request (`/series`) and its own disclosures; the card's
              `AnnualText` above stays its textual equivalent. */}
          <RainfallAccumulationChart
            snapshot={snapshot}
            preset={preset}
            onPresetChange={setPreset}
          />
          <Group gap="xs" wrap="nowrap">
            <Button
              size="xs"
              variant="light"
              loading={exportingFormat === 'csv'}
              onClick={() => void exportAnalysis(snapshot.analysis_revision_id, 'csv')}
              data-testid="rainfall-export-csv"
            >
              Exportar CSV
            </Button>
            <Button
              size="xs"
              variant="light"
              loading={exportingFormat === 'xlsx'}
              onClick={() => void exportAnalysis(snapshot.analysis_revision_id, 'xlsx')}
              data-testid="rainfall-export-xlsx"
            >
              Exportar Excel
            </Button>
          </Group>
          {exportError && (
            <Text size="xs" c="red" data-testid="rainfall-export-error">
              {exportError}
            </Text>
          )}

          {/* Below here the reader has to ask. Both folds start CLOSED at every
              size (owner-ratified 2026-08-11) and both keep their key values
              reachable while closed: the antecedents in the header itself, the
              technical detail one click away. */}
          {snapshot.antecedents && Object.keys(snapshot.antecedents).length > 0 && (
            <CollapsibleSection
              title="Antecedentes"
              defaultOpen={false}
              testId="rainfall-antecedents"
              titleSize="xs"
              rightAccessory={<AntecedentAccessory group={snapshot.antecedents} />}
            >
              {/* The SAME hoist the technical fold's shared block was built
                  from, so these rows print only what diverges from it (D5).
                  Without it the antecedents would repeat a block that already
                  covers them — the six-identical-provenance-blocks defect the
                  hoist exists to remove, reintroduced one fold over. */}
              <RainfallMetricGroup
                group={snapshot.antecedents}
                baseline={snapshot.baseline}
                hoist={hoistProvenance(snapshotMetrics(snapshot))}
              />
            </CollapsibleSection>
          )}

          <CollapsibleSection
            title="Detalle técnico"
            defaultOpen={false}
            testId="rainfall-technical"
            titleSize="xs"
          >
            {/* `exclude`, not `include`: this fold means "everything the card
                and the antecedents fold did not already show", so a group the
                server starts serving tomorrow lands HERE instead of nowhere.
                Since slice 2 that is the RENDERER's behaviour and not just this
                prop's intent — the list iterates the snapshot's own root keys
                behind a total group guard and titles an unrecognised one with
                its raw key (R2-001: this comment used to promise it a slice
                early). */}
            <RainfallMetricList snapshot={snapshot} exclude={['antecedents']} />
          </CollapsibleSection>
        </>
      )}
    </Stack>
  );
}
