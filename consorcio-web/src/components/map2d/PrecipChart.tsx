/**
 * PrecipChart.tsx
 *
 * Renders the `precipitacion_mensual` dataset of a ficha as a COMPACT
 * INTA-style block: an annual headline stat, a 12-bar chart in calendar order
 * with the millimetres printed on top of each bar, and a one-line provenance
 * footer.
 *
 * WHY THE mes/mm TABLE IS GONE (owner review, 2026-08-04, INTA reference
 * screenshot). The block used to render the chart AND a 13-row table (Ene..Dic +
 * Anual) of the same twelve numbers. In the ficha panel — a floating card on top
 * of the map, and a bottom sheet on a phone — that duplicate cost more than half
 * the block's height and pushed the chart out of view (measured: 535px → 233px).
 * The numbers are NOT lost: every value the table carried is now printed above
 * its own bar, so the block stays a full data readout. The contract is the
 * VALUES, not the `<table>`.
 *
 * THIS SUPERSEDES JD-A-012 FOR PRECIPITATION ONLY. That judgment-day finding
 * made the per-dataset table the contract and charts a mere complement, and it
 * still binds the clase/ha/% datasets (`SuelosBreakdown`, `RiesgoBins`). Its
 * actual concern — no number may be lost to a chart — is satisfied here by the
 * on-bar labels. The spec carries the delta; do not "restore" the table from the
 * older clause above it.
 *
 * @see spec `ficha-frontend` › "Card rendering — tables plus monthly chart",
 *      delta 2026-08-04 (supersedes the JD-A-012 clause for this block)
 * @see spec `ficha-frontend` › "A covered month with zero rainfall"
 * @see `openspec/changes/ficha-territorial/tasks.md` › B2.2-bis
 *
 * Monthly normals are mean millimetres, not a class partition — so this was
 * never a `RiesgoBins`-style clase/ha/% table to begin with. Values come
 * straight from the server; only the display is ours. That now includes the
 * provenance footer: `dataset.fuente` / `dataset.periodo` are served, and this
 * component prints them (see {@link PRECIP_FUENTE_LEGACY} for the fallback).
 *
 * `cobertura === 'sin_cobertura'` renders an explicit "sin datos de precipitación"
 * state — never an empty/broken chart and never fabricated `0 mm` bars (spec
 * "Zone outside precipitation coverage").
 *
 * `cobertura === 'parcial'` renders a one-line caveat ABOVE the numbers. Partial
 * coverage was previously served and rendered silently: the reader got a chart
 * that looks exactly like a full-coverage one while the mean spoke for only part
 * of the zone. That is the same defect class as the fake zeros the backend fix
 * closed — a number presented as more authoritative than it is — so the state the
 * payload already carried now has to be visible.
 */

import { Box, Group, Stack, Text } from '@mantine/core';
import { memo } from 'react';
import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis } from 'recharts';

import type { FichaPrecipitacion } from '../../lib/api/ficha';
import { LowConfidenceBadge } from './fichaShared';
import styles from '../../styles/components/map.module.css';

/** Short calendar-month labels, index 0 = January. Display only. */
const MESES = [
  'Ene',
  'Feb',
  'Mar',
  'Abr',
  'May',
  'Jun',
  'Jul',
  'Ago',
  'Sep',
  'Oct',
  'Nov',
  'Dic',
] as const;

/**
 * Legacy provenance label — the FALLBACK, not the contract.
 *
 * The contract is server-driven: the payload carries `fuente` (product) and
 * `periodo` (normals period), read backend-side off the `metadata_extra` of the
 * rasters that actually answered, and {@link procedencia} prints whatever
 * arrives. Regenerating the normals over a different period therefore changes
 * this line by itself — no frontend release, nothing left asserting a period the
 * data no longer has.
 *
 * This string survives for ONE case: a payload with no provenance, i.e. a
 * browser talking to a backend older than that change. It states the period the
 * pipeline was pinned to at the time (`CHIRPS_NORMAL_START_YEAR = 1991` /
 * `CHIRPS_NORMAL_END_YEAR = 2020` over `UCSB-CHG/CHIRPS/DAILY`), which is what
 * such a backend is serving. Do not read it as the current period, and do not
 * reintroduce it as the primary source: that is exactly the defect (RISK-001)
 * the served fields closed.
 */
const PRECIP_FUENTE_LEGACY = 'Normales CHIRPS 1991-2020';

/**
 * The provenance line, server-driven with a legacy fallback.
 *
 * BOTH fields or neither: a half-populated payload would render "Normales
 * CHIRPS " or "Normales  1991-2020", which reads as a rendering bug rather than
 * as the missing datum it is. Whitespace-only counts as absent for the same
 * reason.
 */
function procedencia(dataset: FichaPrecipitacion): string {
  const fuente = dataset.fuente?.trim();
  const periodo = dataset.periodo?.trim();
  return fuente && periodo ? `Normales ${fuente} ${periodo}` : PRECIP_FUENTE_LEGACY;
}

function mesLabel(mes: number): string {
  return MESES[mes - 1] ?? String(mes);
}

/**
 * Millimetres as a WHOLE number.
 *
 * Twelve bars inside a ~330px-wide panel leave about 25px per label: "126.7"
 * does not fit, and the tenth of a millimetre in a thirty-year mean is noise
 * anyway. The one decimal survives in the hover tooltip, where there is room.
 */
function fmtMmEntero(value: number): string {
  return String(Math.round(value));
}

/** Millimetres at full precision — tooltip and the annual headline. */
function fmtMm(value: number): string {
  return `${value.toFixed(1)} mm`;
}

export const PrecipChart = memo(function PrecipChart({
  dataset,
}: {
  readonly dataset: FichaPrecipitacion;
}) {
  const hasData = dataset.cobertura !== 'sin_cobertura' && dataset.serie.length > 0;
  const esParcial = dataset.cobertura === 'parcial';

  const chartData = dataset.serie.map((punto) => ({
    mes: mesLabel(punto.mes),
    mm: punto.mm,
  }));

  return (
    <Stack gap={6} data-testid="ficha-precipitacion">
      <Group gap="xs" justify="space-between" wrap="nowrap">
        <Text size="sm" fw={600}>
          Precipitación mensual (normal)
        </Text>
        {dataset.low_confidence && <LowConfidenceBadge pixelCount={dataset.pixel_count} />}
      </Group>

      {!hasData ? (
        <Text size="xs" c="dimmed" fs="italic" data-testid="ficha-precipitacion-sin-cobertura">
          Sin datos de precipitación para esta zona.
        </Text>
      ) : (
        <>
          {/* ABOVE the numbers on purpose: a caveat printed under the chart is
              read after the reader has already taken the figures at face value.
              Same dimmed-italic treatment as the no-data line, because it is the
              same kind of statement — what the payload does NOT say. */}
          {esParcial && (
            <Text
              size="xs"
              c="dimmed"
              fs="italic"
              data-testid="ficha-precipitacion-cobertura-parcial"
            >
              Cobertura parcial: el promedio usa sólo la parte de la zona con datos.
            </Text>
          )}

          {/* The annual total was the table's footer row — the single number a
              reader actually leaves with. Promoted to a headline above the
              chart so it survives the table's removal AND reads first. */}
          {dataset.anual_mm != null && (
            <Text size="sm" fw={600} data-testid="precip-anual">
              Anual (normal): {fmtMm(dataset.anual_mm)}
            </Text>
          )}

          {/* 132px, down from 160: the axis/grid furniture below went away, so
              the bars themselves keep their old drawing height. */}
          <Box h={132} data-testid="precip-chart">
            <ResponsiveContainer width="100%" height="100%">
              {/* No `YAxis` and no `CartesianGrid`: with the value printed on
                  every bar, a scale to read them AGAINST is redundant furniture,
                  and dropping it buys back the width the labels need. `top: 16`
                  reserves the row those labels are drawn into — without it the
                  tallest bar's label is clipped by the container. */}
              <BarChart data={chartData} margin={{ top: 16, right: 4, bottom: 0, left: 4 }}>
                <XAxis dataKey="mes" fontSize={10} tickLine={false} axisLine={false} interval={0} />
                <Tooltip formatter={(value) => fmtMm(Number(value))} />
                {/* `minPointSize` is LOAD-BEARING, not cosmetic. recharts skips
                    a zero-height rectangle entirely, and `LabelList` labels
                    rectangles — so a month served as `0 mm` rendered NO bar and
                    NO label: eleven columns and a silent gap where July should
                    be, indistinguishable from missing data. The old mes/mm table
                    printed "0.0 mm" and never had that hole; dropping the table
                    is what exposed it. A 2px floor gives every served value a
                    rectangle to carry its own label, so a genuinely dry month
                    reads as "0" instead of vanishing. (No-coverage is a separate
                    state that renders no chart at all, so there is no ambiguity
                    between "0" and "unknown".) */}
                <Bar
                  dataKey="mm"
                  fill="#1c7ed6"
                  radius={[2, 2, 0, 0]}
                  isAnimationActive={false}
                  minPointSize={2}
                >
                  {/* Recharts' own label layer, so the text tracks each bar's
                      computed geometry instead of us re-deriving it. `fontSize
                      9` is what fits three digits in a 12-bar row at the ficha
                      panel's narrowest (a ~360px phone sheet). */}
                  {/* `className`, NOT `fill="var(...)"`: recharts forwards
                      `fill` verbatim as an SVG PRESENTATION ATTRIBUTE, where
                      CSS custom properties are never substituted — the value
                      is dropped and the text falls back to black, invisible
                      on the dark ficha panel. A stylesheet rule (see
                      `.precipBarLabels` in map.module.css) is how var() gets
                      resolved — same approach @mantine/charts uses. */}
                  <LabelList
                    dataKey="mm"
                    position="top"
                    fontSize={9}
                    className={styles.precipBarLabels}
                    formatter={(value: unknown) => fmtMmEntero(Number(value))}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Box>

          <Text size="xs" c="dimmed" data-testid="precip-fuente">
            {procedencia(dataset)}
          </Text>
        </>
      )}
    </Stack>
  );
});
