/**
 * PrecipChart.tsx
 *
 * Renders the `precipitacion_mensual` dataset of a ficha: a 12-bar chart in
 * calendar order PLUS a mes/mm table and the annual total. The table is the
 * contract (JD-A-012, spec `ficha-frontend` › "Full ficha rendered"); the chart
 * is a visual complement over the SAME server numbers.
 *
 * Monthly normals are mean millimetres, not a class partition — so this is NOT a
 * `RiesgoBins`-style clase/ha/% table. Values come straight from the server; only
 * the display is ours.
 *
 * `cobertura === 'sin_cobertura'` renders an explicit "sin datos de precipitación"
 * state — never an empty/broken chart and never fabricated `0 mm` bars (spec
 * "Zone outside precipitation coverage").
 */

import { Box, Group, Stack, Table, Text } from '@mantine/core';
import { memo } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import type { FichaPrecipitacion } from '../../lib/api/ficha';
import { LowConfidenceBadge } from './fichaShared';

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

function mesLabel(mes: number): string {
  return MESES[mes - 1] ?? String(mes);
}

/** Millimetres at a fixed precision. The number is the server's; the format is ours. */
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
        <Text
          size="xs"
          c="dimmed"
          fs="italic"
          data-testid="ficha-precipitacion-sin-cobertura"
        >
          Sin datos de precipitación para esta zona.
        </Text>
      ) : (
        <>
          <Box h={160} data-testid="precip-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="mes" fontSize={10} tickLine={false} interval={0} />
                <YAxis fontSize={10} tickLine={false} width={32} unit="" />
                <Tooltip formatter={(value) => fmtMm(Number(value))} />
                <Bar dataKey="mm" fill="#1c7ed6" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Box>

          <Table
            withRowBorders={false}
            verticalSpacing={2}
            fz="xs"
            data-testid="precip-table"
          >
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Mes</Table.Th>
                <Table.Th ta="right">mm</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {dataset.serie.map((punto) => (
                <Table.Tr key={punto.mes}>
                  <Table.Td>{mesLabel(punto.mes)}</Table.Td>
                  <Table.Td ta="right">{fmtMm(punto.mm)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
            {dataset.anual_mm != null && (
              <Table.Tfoot>
                <Table.Tr>
                  <Table.Th>Anual</Table.Th>
                  <Table.Th ta="right" data-testid="precip-anual">
                    {fmtMm(dataset.anual_mm)}
                  </Table.Th>
                </Table.Tr>
              </Table.Tfoot>
            )}
          </Table>
        </>
      )}
    </Stack>
  );
});
