/**
 * RainfallAccumulationChart.tsx (Lluvia insights — slice 4, design.md D8)
 *
 * The comparison the owner asked for: "si selecciono un año podría mostrarse
 * además en el gráfico de arriba como comparando con el histórico". The
 * selected year's accumulated rainfall and the normal curve of the SERVED
 * baseline (`snapshot.baseline`, never a period frozen here — LI4-004), drawn
 * from `GET /rainfall/analyses/{revision}/series` — the SAME builder the xlsx
 * "Serie diaria" sheet uses, so the screen and the workbook cannot tell
 * different stories.
 *
 * `recharts` directly rather than `@mantine/charts` (design D8): the Lluvia tab
 * already loads the `vendor-charts` chunk, while `vendor-mantine-charts` is
 * admin-only — zero incremental vendor bytes on the ficha route.
 *
 * WHAT THIS COMPONENT REFUSES TO DO
 * ─────────────────────────────────
 * · Redraw silently when the daily data moved under the analysis. The server
 *   pin (`consistent_with_snapshot`) is authoritative and the echoed
 *   `data_revision` is the client cross-check that also catches a snapshot left
 *   open in a tab; either one renders the curve PLUS an alert (design D3).
 * · Offer a re-request button beside that alert. It was there, and it was a
 *   FAKE REMEDY (JDA-003 ≡ JDB-003): the only path that enqueues a rebuild is
 *   a superseded policy revision (`router.read_analysis` →
 *   `_requeue_stale_revision`), never a moved `data_revision`, and revisions
 *   are immutable — so re-POSTing `/analyses` returned the same revision every
 *   time. A control that reliably does nothing is worse than none: it turns an
 *   accurate disclosure into an instruction the reader follows and blames
 *   themselves for. The disclosure stays; the button is gone. The panel's own
 *   poll is what eventually moves this tab to a newer analysis.
 * · Read `available_through` as an inclusive day. It is the EXCLUSIVE end of
 *   the disclosure window — see {@link lastEvidenceDay}, which is the single
 *   place that conversion happens, and which both footer sentences use.
 * · Claim evidence the series does not carry. `available_through` exists even
 *   for an analysis that published nothing (the window falls back to
 *   `comparison_end + 1 day`), so the evidence sentence and the lag notice are
 *   gated on there being at least one point with an accumulation — see
 *   {@link evidenceFooter}.
 * · Collapse `suppressed` and `integrity_refused` into "there is no line".
 *   Both arrive with every `normal_accumulated: null`, so the wire cannot tell
 *   them apart by shape — only by `normal_curve_state` (backend LI3A-001).
 *   An honest absence and a curve that was computed and thrown away for
 *   contradicting the card beside it are different facts, and the difference is
 *   carried in the COPY and in a state attribute, never in colour alone.
 * · Turn the campaign preset into a request. It is a display window over the
 *   same calendar-year series (spec "Campaign Display Preset"): no `/analyses`
 *   call, no re-read of the series, and the accumulations stay counted from
 *   January 1 — re-basing them would make it a different measurement wearing a
 *   display preset's clothes.
 */

import { Alert, Box, Group, SegmentedControl, Stack, Text } from '@mantine/core';
import { IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { useRainfallSeries } from '../../../hooks/useRainfallAnalysis';
import {
  RAINFALL_NORMAL_CURVE_STATE,
  type RainfallAnalysisSnapshot,
  type RainfallNormalCurveState,
  type RainfallSeriesPoint,
} from '../../../lib/api/rainfall';
import { evidenceFooter, formatAccumulated, isoDay, lastEvidenceDay } from './rainfallFormat';

/** Display window over one calendar-year series. Never a request parameter. */
export const CAMPAIGN_PRESET = {
  CALENDAR: 'calendario',
  CAMPAIGN: 'campana',
} as const;

export type CampaignPreset = (typeof CAMPAIGN_PRESET)[keyof typeof CAMPAIGN_PRESET];

/** spec "Campaign Display Preset": the preset is defined as *since September 1*. */
const CAMPAIGN_START_MONTH_DAY = '09-01';

/**
 * How the normal is NAMED inside a sentence, with the SERVED period.
 *
 * `metricLabel`'s rule in prose form (LI4-004): the period is server-driven, so
 * it comes from `snapshot.baseline`, and with none served the phrase names the
 * metric without a period rather than asserting one. The chart title and the
 * legend beside this notice already read the same field — a constant here would
 * put two different periods on one screen, in the one state where there is no
 * curve for the reader to check the claim against.
 */
function normalPhrase(baseline: string | null | undefined): string {
  return baseline ? `normal ${baseline}` : 'normal de referencia';
}

/**
 * What a reader is told when there is no normal line, per state.
 *
 * The two entries MUST stay different sentences. They describe different
 * facts and the operator who needs the second one is reading a screenshot or a
 * printout where a colour never survives.
 *
 * `body` takes the phrase from {@link normalPhrase} rather than being a plain
 * string, so the period cannot be re-frozen here by the next editor. The
 * refusal copy ignores its argument on purpose: it is about an inconsistency
 * between two computed curves, not about which period they cover.
 */
const NORMAL_CURVE_NOTICE: Record<
  Exclude<RainfallNormalCurveState, 'available'>,
  { readonly title: string; readonly body: (normal: string) => string }
> = {
  suppressed: {
    title: 'Sin línea normal',
    body: (normal) =>
      `No hay ${normal} para este análisis, así que no hay línea histórica con la cual comparar el año.`,
  },
  integrity_refused: {
    title: 'Línea normal descartada',
    body: () =>
      'La línea normal se calculó y se descartó por una inconsistencia de datos: no ' +
      'coincidía con la normal del análisis. No es una ausencia de datos. El motivo ' +
      'exacto queda en el evento rainfall.series.normal_curve_refused.',
  },
};

/**
 * The notice for a state with no normal line — with an honest fallback.
 *
 * The map above is keyed by the states this client knows TODAY, but
 * `normal_curve_state` is the BACKEND's field to extend. A state added there
 * and not here indexes to `undefined`, and reading `.title` off it is a
 * TypeError that unmounts the whole panel subtree — a reader loses the chart,
 * the metrics and the provenance over one footnote (LI4-005).
 *
 * So an unmodelled state degrades to the untranslated fact: the title states
 * what is true of EVERY non-`available` state (there is no line), and the body
 * carries the raw state so an operator can name what the server actually said.
 * Same rule as `metricLabel`'s raw-key fallback and `export._label` — show it,
 * never disappear. The cast is confined here: widening the map to a `Partial`
 * would trade this one guarded lookup for the loss of the compile-time check
 * that every KNOWN state has copy.
 */
function normalCurveNotice(
  state: RainfallNormalCurveState,
  baseline?: string | null
): {
  readonly title: string;
  readonly body: string;
} {
  const known = NORMAL_CURVE_NOTICE[state as Exclude<RainfallNormalCurveState, 'available'>] as
    | { readonly title: string; readonly body: (normal: string) => string }
    | undefined;
  return known === undefined
    ? { title: 'Sin línea normal', body: state }
    : { title: known.title, body: known.body(normalPhrase(baseline)) };
}

/**
 * A tooltip value — with the null guard BEFORE the numeric coercion.
 *
 * recharts hands the formatter the raw datum, `null` included, and
 * `Number(null)` is `0`: coercing first turns "no evidence" into a measured
 * 0.0 mm. Two real shapes carry `null` here — February 29, which the backend
 * omits from the normal curve by construction, and any day before the first
 * published one — so this is the same rule `formatAccumulated` exists to
 * enforce, applied one step earlier than the coercion that would defeat it.
 */
function tooltipValue(value: unknown, unit: string): string {
  if (value === null || value === undefined) return formatAccumulated(null, unit);
  return formatAccumulated(Number(value), unit);
}

/** The last point that actually carries a value for `key`, or undefined. */
function lastValued(
  points: readonly RainfallSeriesPoint[],
  key: 'accumulated' | 'normal_accumulated'
): number | undefined {
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const value = points[index]?.[key];
    if (value !== null && value !== undefined) return value;
  }
  return undefined;
}

/**
 * The chart's textual equivalent.
 *
 * A screen reader gets nothing from an SVG of axis ticks, and `AnnualText`
 * (`RainfallMetricList`) describes the CARD, not the plotted window — which the
 * campaign preset moves. So this names the window and both end values, and when
 * there is no normal line it says which kind of "no line" this is rather than
 * staying silent about it.
 */
function describePlottedWindow(
  points: readonly RainfallSeriesPoint[],
  {
    year,
    baseline,
    unit,
    curveAvailable,
    curveTitle,
  }: {
    readonly year: number;
    readonly baseline: string;
    readonly unit: string;
    readonly curveAvailable: boolean;
    readonly curveTitle: string | null;
  }
): string {
  const first = points[0]?.date;
  const last = points[points.length - 1]?.date;
  if (!first || !last) return 'Sin serie diaria para este análisis.';
  const accumulated = formatAccumulated(lastValued(points, 'accumulated') ?? null, unit);
  const normal = curveAvailable
    ? `Normal ${baseline} a la misma fecha: ${formatAccumulated(lastValued(points, 'normal_accumulated') ?? null, unit)}.`
    : `${curveTitle ?? 'Sin línea normal'}.`;
  return `Lluvia acumulada entre el ${first} y el ${last}. Acumulado del año ${year} al ${last}: ${accumulated}. ${normal}`;
}

/**
 * Why there is no normal line — and WHICH of the two reasons it is.
 *
 * `suppressed` and `integrity_refused` arrive with byte-identical
 * `normal_accumulated: null` columns (backend D3), so this notice is the only
 * thing that keeps an honest absence distinguishable from a curve that was
 * computed and thrown away. The difference is carried by the TITLE, the BODY
 * and `data-normal-curve-state` — never by the colour alone, which does not
 * survive a printed screenshot or a colour-blind reader.
 */
function NormalCurveNotice({
  state,
  baseline,
}: {
  readonly state: RainfallNormalCurveState | undefined;
  /** Served period, so this notice names the SAME baseline as the chart title
   *  and the legend beside it — never a constant (LI4-004). */
  readonly baseline: string;
}) {
  if (state === undefined || state === RAINFALL_NORMAL_CURVE_STATE.AVAILABLE) return null;
  const notice = normalCurveNotice(state, baseline);
  const refused = state === RAINFALL_NORMAL_CURVE_STATE.INTEGRITY_REFUSED;
  return (
    <Alert
      color={refused ? 'red' : 'gray'}
      variant="light"
      icon={refused ? <IconAlertTriangle size={16} /> : <IconInfoCircle size={16} />}
      title={notice.title}
      data-testid="rainfall-normal-curve-state"
      data-normal-curve-state={state}
    >
      <Text size="xs">{notice.body}</Text>
    </Alert>
  );
}

export interface RainfallAccumulationChartProps {
  readonly snapshot: RainfallAnalysisSnapshot;
  /**
   * The display window, owned by `RainfallDetailPanel` (design D6).
   *
   * REQUIRED, with no uncontrolled fallback. The first draft made these
   * optional and kept an internal `useState` for callers that passed neither —
   * two behaviours in one component of which only one would ever ship, and the
   * untested path is the one that rots. An optional prop would also let a
   * future caller silently acquire a SECOND source of truth for the same
   * window.
   */
  readonly preset: CampaignPreset;
  readonly onPresetChange: (preset: CampaignPreset) => void;
}

export function RainfallAccumulationChart({
  snapshot,
  preset,
  onPresetChange,
}: RainfallAccumulationChartProps) {
  const series = useRainfallSeries(snapshot.analysis_revision_id);

  const unit = series.data?.unit ?? 'mm';
  const campaignStart = `${snapshot.year}-${CAMPAIGN_START_MONTH_DAY}`;
  const visible =
    preset === CAMPAIGN_PRESET.CAMPAIGN
      ? series.points.filter((point) => point.date >= campaignStart)
      : series.points;

  const curveState = series.normalCurveState;
  const curveAvailable = curveState === RAINFALL_NORMAL_CURVE_STATE.AVAILABLE;
  const curveTitle =
    curveState !== undefined && !curveAvailable
      ? normalCurveNotice(curveState, snapshot.baseline).title
      : null;

  // The pin is authoritative; the echo comparison is the cheap cross-check that
  // ALSO catches a snapshot this tab has been holding while the server moved on
  // (design D3). Different causes, so different sentences.
  const pinInconsistent = series.consistentWithSnapshot === false;
  const echoMismatch =
    series.data !== undefined && series.data.data_revision !== snapshot.data_revision;
  const stale = pinInconsistent || echoMismatch;

  const comparisonEndDay = isoDay(series.data?.comparison_end ?? snapshot.comparison_end);
  // The claim is about the SERIES, not about the campaign window: a preset
  // that hides January does not unpublish it, so the gate reads every point
  // the response carried, not the visible slice.
  const hasEvidence = series.points.some((point) => point.accumulated !== null);
  const evidenceDay =
    series.data && hasEvidence ? lastEvidenceDay(series.data.available_through) : null;
  const lagging = evidenceDay !== null && evidenceDay < comparisonEndDay;

  const chartLabel = describePlottedWindow(visible, {
    year: snapshot.year,
    baseline: snapshot.baseline,
    unit,
    curveAvailable,
    curveTitle,
  });

  if (series.isLoading) {
    return (
      <Text size="xs" c="dimmed" data-testid="rainfall-accumulation-loading">
        Cargando la serie diaria…
      </Text>
    );
  }

  if (series.isError) {
    return (
      <Text size="xs" c="red" data-testid="rainfall-accumulation-error">
        {series.error?.message ?? 'No se pudo obtener la serie diaria de este análisis.'}
      </Text>
    );
  }

  return (
    <Stack gap={6} data-testid="rainfall-accumulation">
      <Group gap="xs" justify="space-between" wrap="nowrap">
        <Text size="sm" fw={600}>
          Acumulado {snapshot.year} vs. normal {snapshot.baseline}
        </Text>
        <SegmentedControl
          size="xs"
          value={preset}
          onChange={(value) => onPresetChange(value as CampaignPreset)}
          data={[
            { value: CAMPAIGN_PRESET.CALENDAR, label: 'Año calendario' },
            { value: CAMPAIGN_PRESET.CAMPAIGN, label: 'Campaña' },
          ]}
          aria-label="Ventana de visualización"
          data-testid="rainfall-campaign-preset"
        />
      </Group>

      {stale && (
        <Alert
          color="yellow"
          variant="light"
          icon={<IconAlertTriangle size={16} />}
          title={
            pinInconsistent
              ? 'Los datos diarios cambiaron'
              : 'Esta pestaña puede estar desactualizada'
          }
          data-testid="rainfall-series-stale"
        >
          <Text size="xs">
            {pinInconsistent
              ? `Los datos diarios se corrigieron después de que se guardó este análisis (${series.consistencyReason}). La serie de abajo es la evidencia más fresca; los números de la ficha son los del análisis guardado.`
              : 'La serie que sirve el servidor pertenece a otra revisión de los datos que la del análisis anterior que está mostrando esta pestaña.'}
          </Text>
        </Alert>
      )}

      <NormalCurveNotice state={curveState} baseline={snapshot.baseline} />

      {visible.length === 0 ? (
        <Text size="xs" c="dimmed" fs="italic" data-testid="rainfall-accumulation-empty">
          Sin días publicados en esta ventana; no hay serie para dibujar.
        </Text>
      ) : (
        <Box h={180} role="img" aria-label={chartLabel} data-testid="rainfall-accumulation-chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={visible} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} opacity={0.25} />
              <XAxis dataKey="date" fontSize={9} tickLine={false} minTickGap={28} />
              <YAxis fontSize={9} width={36} tickLine={false} axisLine={false} />
              <Tooltip
                formatter={(value: unknown) => tooltipValue(value, unit)}
                isAnimationActive={false}
              />
              <Legend
                verticalAlign="bottom"
                height={18}
                iconSize={8}
                wrapperStyle={{ fontSize: 10 }}
              />
              {/* Where the analysis says the comparison ends. Under provider
                  lag this day is outside the plotted window, so it draws
                  nothing — which is why the footer states both dates in text
                  and never relies on this mark alone. */}
              <ReferenceLine
                x={comparisonEndDay}
                stroke="#868e96"
                strokeDasharray="4 4"
                ifOverflow="hidden"
              />
              {/* SOLID vs DASHED, not just two colours: the two lines have to
                  stay distinguishable in greyscale and for a colour-blind
                  reader. */}
              <Line
                type="monotone"
                dataKey="accumulated"
                name={`Año ${snapshot.year}`}
                stroke="#1c7ed6"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              {curveAvailable && (
                // `connectNulls` is load-bearing here and nowhere else: Feb 29
                // carries NO curve key by construction (the backend keys the
                // normal by month/day and omits it), so without this the normal
                // line breaks in two every leap year.
                <Line
                  type="monotone"
                  dataKey="normal_accumulated"
                  name={`Normal ${snapshot.baseline}`}
                  stroke="#f08c00"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </Box>
      )}

      {preset === CAMPAIGN_PRESET.CAMPAIGN && (
        <Text size="xs" c="dimmed" data-testid="rainfall-campaign-note">
          Vista de campaña desde el 1 de septiembre de {snapshot.year}. Reformatea el mismo análisis
          del año calendario {snapshot.year} — el período analizado no cambió — y los acumulados
          siguen contados desde el 1 de enero de {snapshot.year}.
        </Text>
      )}

      <Text size="xs" c="dimmed" data-testid="rainfall-accumulation-dates">
        Comparación hasta el {comparisonEndDay} ·{' '}
        {evidenceFooter(evidenceDay, series.data !== undefined)}
      </Text>

      {lagging && (
        <Text size="xs" c="dimmed" fs="italic" data-testid="rainfall-accumulation-lag">
          El proveedor todavía no publicó los días posteriores al {evidenceDay}: la serie termina
          donde termina la evidencia, no en un período sin lluvia.
        </Text>
      )}
    </Stack>
  );
}
