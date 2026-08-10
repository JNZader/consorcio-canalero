/**
 * RainfallAccumulationChart.tsx (Lluvia insights — slice 4, design.md D8)
 *
 * The comparison the owner asked for: "si selecciono un año podría mostrarse
 * además en el gráfico de arriba como comparando con el histórico". The
 * selected year's accumulated rainfall and the 1991-2020 normal curve, drawn
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
 *   open in a tab; either one renders the curve PLUS an alert and a re-request
 *   action (design D3).
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

import { Alert, Box, Button, Group, SegmentedControl, Stack, Text } from '@mantine/core';
import { IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
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

import { rainfallAnalysisQueryKey, useRainfallSeries } from '../../../hooks/useRainfallAnalysis';
import {
  RAINFALL_NORMAL_CURVE_STATE,
  type RainfallAnalysisSnapshot,
  type RainfallNormalCurveState,
  type RainfallSeriesPoint,
  fetchRainfallAnalysis,
} from '../../../lib/api/rainfall';
import { formatAccumulated } from './rainfallFormat';

/** Display window over one calendar-year series. Never a request parameter. */
const CAMPAIGN_PRESET = {
  CALENDAR: 'calendario',
  CAMPAIGN: 'campana',
} as const;

type CampaignPreset = (typeof CAMPAIGN_PRESET)[keyof typeof CAMPAIGN_PRESET];

/** spec "Campaign Display Preset": the preset is defined as *since September 1*. */
const CAMPAIGN_START_MONTH_DAY = '09-01';

/**
 * What a reader is told when there is no normal line, per state.
 *
 * The two entries MUST stay different sentences. They describe different
 * facts and the operator who needs the second one is reading a screenshot or a
 * printout where a colour never survives.
 */
const NORMAL_CURVE_NOTICE: Record<
  Exclude<RainfallNormalCurveState, 'available'>,
  { readonly title: string; readonly body: string }
> = {
  suppressed: {
    title: 'Sin línea normal',
    body:
      'No hay normal 1991-2020 para este análisis, así que no hay línea histórica ' +
      'con la cual comparar el año.',
  },
  integrity_refused: {
    title: 'Línea normal descartada',
    body:
      'La línea normal se calculó y se descartó por una inconsistencia de datos: no ' +
      'coincidía con la normal del análisis. No es una ausencia de datos. El motivo ' +
      'exacto queda en el evento rainfall.series.normal_curve_refused.',
  },
};

/** ISO day of a date or datetime string, without re-parsing it into a Date
 *  (a `new Date(...)` round trip is where a UTC day silently becomes the day
 *  before in a browser west of Greenwich). */
function isoDay(value: string): string {
  return value.slice(0, 10);
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
function NormalCurveNotice({ state }: { readonly state: RainfallNormalCurveState | undefined }) {
  if (state === undefined || state === RAINFALL_NORMAL_CURVE_STATE.AVAILABLE) return null;
  const notice = NORMAL_CURVE_NOTICE[state];
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

export function RainfallAccumulationChart({
  snapshot,
}: {
  readonly snapshot: RainfallAnalysisSnapshot;
}) {
  const series = useRainfallSeries(snapshot.analysis_revision_id);
  const queryClient = useQueryClient();
  const [preset, setPreset] = useState<CampaignPreset>(CAMPAIGN_PRESET.CALENDAR);
  const [rerequesting, setRerequesting] = useState(false);
  const [rerequestResult, setRerequestResult] = useState<string | null>(null);
  const [rerequestError, setRerequestError] = useState<string | null>(null);

  const unit = series.data?.unit ?? 'mm';
  const campaignStart = `${snapshot.year}-${CAMPAIGN_START_MONTH_DAY}`;
  const visible =
    preset === CAMPAIGN_PRESET.CAMPAIGN
      ? series.points.filter((point) => point.date >= campaignStart)
      : series.points;

  const curveState = series.normalCurveState;
  const curveAvailable = curveState === RAINFALL_NORMAL_CURVE_STATE.AVAILABLE;
  const curveTitle =
    curveState !== undefined && !curveAvailable ? NORMAL_CURVE_NOTICE[curveState].title : null;

  // The pin is authoritative; the echo comparison is the cheap cross-check that
  // ALSO catches a snapshot this tab has been holding while the server moved on
  // (design D3). Different causes, so different sentences.
  const pinInconsistent = series.consistentWithSnapshot === false;
  const echoMismatch =
    series.data !== undefined && series.data.data_revision !== snapshot.data_revision;
  const stale = pinInconsistent || echoMismatch;

  const comparisonEndDay = isoDay(series.data?.comparison_end ?? snapshot.comparison_end);
  const availableThroughDay = series.data ? isoDay(series.data.available_through) : null;
  const lagging = availableThroughDay !== null && availableThroughDay < comparisonEndDay;

  const chartLabel = describePlottedWindow(visible, {
    year: snapshot.year,
    baseline: snapshot.baseline,
    unit,
    curveAvailable,
    curveTitle,
  });

  async function rerequest() {
    setRerequesting(true);
    setRerequestResult(null);
    setRerequestError(null);
    try {
      const response = await fetchRainfallAnalysis(snapshot.scope, snapshot.year);
      // Written into the PANEL's own query rather than kept here: a newer
      // revision has to move the card, the metric list and this chart together,
      // and a labelled 202 has to land on the poll path `useRainfallAnalysis`
      // already owns instead of a second one growing here.
      queryClient.setQueryData(rainfallAnalysisQueryKey(snapshot.scope, snapshot.year), response);
      if (response.type === 'queued') {
        const labels = response.queued.labels.join(', ');
        setRerequestResult(
          `Se pidió un análisis nuevo${labels ? `: ${labels}` : ''}. El panel lo sigue automáticamente.`
        );
      } else if (response.snapshot.analysis_revision_id !== snapshot.analysis_revision_id) {
        setRerequestResult('Se actualizó al análisis más reciente.');
      } else {
        // Without this the button is indistinguishable from a broken one:
        // nothing on screen changes and the reader cannot tell whether the
        // request even happened.
        setRerequestResult(
          'El servidor sigue sirviendo este mismo análisis: todavía no hay una revisión más nueva.'
        );
      }
    } catch (error) {
      setRerequestError(
        error instanceof Error ? error.message : 'No se pudo volver a pedir el análisis.'
      );
    } finally {
      setRerequesting(false);
    }
  }

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
          onChange={(value) => setPreset(value as CampaignPreset)}
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
          <Stack gap={4}>
            <Text size="xs">
              {pinInconsistent
                ? `Los datos diarios se corrigieron después de que se guardó este análisis (${series.consistencyReason}). La serie de abajo es la evidencia más fresca; los números de la ficha son los del análisis guardado.`
                : 'La serie que sirve el servidor pertenece a otra revisión de los datos que la del análisis anterior que está mostrando esta pestaña.'}
            </Text>
            <Button
              size="xs"
              variant="light"
              loading={rerequesting}
              onClick={() => void rerequest()}
              data-testid="rainfall-series-rerequest"
            >
              Volver a pedir el análisis
            </Button>
            {rerequestResult && (
              <Text size="xs" data-testid="rainfall-series-rerequest-result">
                {rerequestResult}
              </Text>
            )}
            {rerequestError && (
              <Text size="xs" c="red" data-testid="rainfall-series-rerequest-error">
                {rerequestError}
              </Text>
            )}
          </Stack>
        </Alert>
      )}

      <NormalCurveNotice state={curveState} />

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
                formatter={(value: unknown) => formatAccumulated(Number(value), unit)}
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
        Comparación hasta el {comparisonEndDay} · Evidencia publicada hasta el{' '}
        {availableThroughDay ?? '—'}
      </Text>

      {lagging && (
        <Text size="xs" c="dimmed" fs="italic" data-testid="rainfall-accumulation-lag">
          El proveedor todavía no publicó los días posteriores al {availableThroughDay}: la serie
          termina donde termina la evidencia, no en un período sin lluvia.
        </Text>
      )}
    </Stack>
  );
}
