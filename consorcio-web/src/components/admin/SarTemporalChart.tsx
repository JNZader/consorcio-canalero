/**
 * SarTemporalChart - Line chart for VV backscatter time series
 * with anomaly detection visualization.
 *
 * Uses recharts for custom rendering (baseline line, anomaly dots).
 */

import {
  Alert,
  Badge,
  Group,
  Paper,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { SarTemporalResultado } from '../../lib/api/sarTemporal';
import { IconAlertTriangle } from '../ui/icons';

interface SarTemporalChartProps {
  readonly data: SarTemporalResultado;
}

interface ChartDataPoint {
  date: string;
  vv: number;
  isAnomaly: boolean;
}

export default function SarTemporalChart({ data }: SarTemporalChartProps) {
  if (data.dates.length === 0) {
    return (
      <Alert color="yellow" title="Sin datos">
        {data.warning || 'No se encontraron imagenes Sentinel-1 en el rango de fechas.'}
      </Alert>
    );
  }

  // Build chart data
  const anomalyDates = new Set(data.anomalies.map((a) => a.date));
  const chartData: ChartDataPoint[] = data.dates.map((date, i) => ({
    date,
    vv: data.vv_mean[i],
    isAnomaly: anomalyDates.has(date),
  }));

  const anomalyPoints = chartData.filter((d) => d.isAnomaly);

  // Y-axis domain with some padding
  const vvMin = Math.min(...data.vv_mean);
  const vvMax = Math.max(...data.vv_mean);
  const yPadding = (vvMax - vvMin) * 0.15 || 2;

  return (
    <Stack gap="md">
      {/* Chart */}
      <Paper p="md" radius="md" withBorder>
        <Title order={5} mb="sm">
          Retrodispersion VV (dB) - Serie Temporal
        </Title>
        <Text size="xs" c="dimmed" mb="md">
          {data.image_count} imagenes Sentinel-1 | {data.start_date} a {data.end_date} | Escala:{' '}
          {data.scale_m}m
        </Text>

        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              angle={-45}
              textAnchor="end"
              height={60}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[Math.floor(vvMin - yPadding), Math.ceil(vvMax + yPadding)]}
              tick={{ fontSize: 11 }}
              label={{ value: 'VV (dB)', angle: -90, position: 'insideLeft', fontSize: 12 }}
            />
            <Tooltip
              formatter={(value: number) => [`${value.toFixed(2)} dB`, 'VV Mean']}
              labelFormatter={(label: string) => `Fecha: ${label}`}
            />

            {/* VV time series line */}
            <Line
              type="monotone"
              dataKey="vv"
              stroke="var(--mantine-color-blue-6)"
              strokeWidth={2}
              dot={{ r: 3, fill: 'var(--mantine-color-blue-6)' }}
              activeDot={{ r: 5 }}
              name="VV Mean"
            />

            {/* Baseline reference line */}
            {data.baseline != null && (
              <ReferenceLine
                y={data.baseline}
                stroke="var(--mantine-color-green-6)"
                strokeDasharray="5 5"
                label={{
                  value: `Baseline: ${data.baseline.toFixed(1)} dB`,
                  position: 'right',
                  fontSize: 10,
                  fill: 'var(--mantine-color-green-6)',
                }}
              />
            )}

            {/* Threshold reference line */}
            {data.threshold != null && (
              <ReferenceLine
                y={data.threshold}
                stroke="var(--mantine-color-red-6)"
                strokeDasharray="8 4"
                label={{
                  value: `Umbral: ${data.threshold.toFixed(1)} dB`,
                  position: 'right',
                  fontSize: 10,
                  fill: 'var(--mantine-color-red-6)',
                }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>

        {/* Anomaly scatter overlay */}
        {anomalyPoints.length > 0 && (
          <Text size="xs" c="red" mt="xs">
            {anomalyPoints.length} anomalia(s) detectada(s) por debajo del umbral
          </Text>
        )}
      </Paper>

      {/* Statistics summary */}
      <Group grow>
        <Paper p="sm" radius="md" withBorder>
          <Text size="xs" c="dimmed">
            Baseline
          </Text>
          <Text fw={600}>{data.baseline != null ? `${data.baseline.toFixed(2)} dB` : 'N/A'}</Text>
        </Paper>
        <Paper p="sm" radius="md" withBorder>
          <Text size="xs" c="dimmed">
            Desviacion Estandar
          </Text>
          <Text fw={600}>{data.std != null ? `${data.std.toFixed(2)} dB` : 'N/A'}</Text>
        </Paper>
        <Paper p="sm" radius="md" withBorder>
          <Text size="xs" c="dimmed">
            Umbral Anomalia
          </Text>
          <Text fw={600} c="red">
            {data.threshold != null ? `${data.threshold.toFixed(2)} dB` : 'N/A'}
          </Text>
        </Paper>
        <Paper p="sm" radius="md" withBorder>
          <Text size="xs" c="dimmed">
            Imagenes
          </Text>
          <Text fw={600}>{data.image_count}</Text>
        </Paper>
      </Group>

      {/* Anomalies table */}
      {data.anomalies.length > 0 && (
        <Paper p="md" radius="md" withBorder>
          <Group mb="sm">
            <IconAlertTriangle size={18} color="var(--mantine-color-red-6)" />
            <Title order={5}>Anomalias Detectadas</Title>
            <Badge color="red" size="sm">
              {data.anomalies.length}
            </Badge>
          </Group>
          <Text size="xs" c="dimmed" mb="sm">
            Fechas con VV por debajo del umbral (baseline - 2*std). Indica posible anegamiento.
          </Text>
          <Table verticalSpacing="xs" striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Fecha</Table.Th>
                <Table.Th>VV (dB)</Table.Th>
                <Table.Th>Desviacion</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.anomalies.map((anomaly) => {
                const deviation =
                  data.baseline != null ? (anomaly.vv - data.baseline).toFixed(2) : 'N/A';
                return (
                  <Table.Tr key={anomaly.date}>
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {anomaly.date}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="red" fw={600}>
                        {anomaly.vv.toFixed(2)} dB
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="red">
                        {deviation} dB
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Paper>
      )}
    </Stack>
  );
}
