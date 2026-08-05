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
 * straight from the server; only the display is ours.
 *
 * `cobertura === 'sin_cobertura'` renders an explicit "sin datos de precipitación"
 * state — never an empty/broken chart and never fabricated `0 mm` bars (spec
 * "Zone outside precipitation coverage").
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
 * Provenance of the numbers, spelled out for the reader.
 *
 * NOT invented: the pipeline that produces them is
 * `gee-backend/app/domains/geo/etl/generate_chirps_normals.py`, driven by
 * `gee_service_analytics_support.py`, which pins
 * `CHIRPS_NORMAL_START_YEAR = 1991` / `CHIRPS_NORMAL_END_YEAR = 2020` over the
 * `UCSB-CHG/CHIRPS/DAILY` collection. Verified against those constants
 * 2026-08-04.
 *
 * FOLLOW-UP (accepted debt, RISK-001): this string is HARDCODED CLIENT-SIDE and
 * the wire carries no provenance — `FichaPrecipitacion` has `unidad` but no
 * `fuente` / `periodo`. If the pipeline is ever re-run over a different normal
 * period, the backend changes and this label keeps asserting 1991-2020, i.e. the
 * UI starts lying about the age of its own numbers with nothing to catch it. The
 * real fix is to serve `fuente` + `periodo` in the `precipitacion_mensual`
 * payload (`schemas_ficha.py`) and render whatever arrives; it is a backend
 * change and deliberately out of scope for this frontend-only branch.
 */
const PRECIP_FUENTE = 'Normales CHIRPS 1991-2020';

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
            {PRECIP_FUENTE}
          </Text>
        </>
      )}
    </Stack>
  );
});
