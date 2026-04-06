/**
 * ReturnPeriodsPanel — Períodos de retorno por distribución Gumbel EV-I.
 *
 * Usa los máximos anuales diarios de precipitación (CHIRPS/IMERG) para
 * ajustar la distribución de Gumbel y estimar precipitaciones para T5 a T100.
 */

import '@mantine/charts/styles.css';
import {
  Alert,
  Badge,
  Box,
  Card,
  Divider,
  Grid,
  Group,
  Paper,
  Select,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { BarChart } from '@mantine/charts';
import { useEffect, useState } from 'react';
import { notifications } from '@mantine/notifications';
import {
  getReturnPeriods,
  listZonasOperativas,
  type ReturnPeriodsResponse,
  type ZonaOperativaItem,
} from '../../lib/api/floodFlow';
import {
  IconAlertTriangle,
  IconChartBar,
  IconDroplet,
  IconInfoCircle,
} from '../ui/icons';

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, decimals = 1): string {
  if (n == null) return '—';
  return n.toFixed(decimals);
}

// Color ramp: from blue (low risk) to red (extreme)
const PERIOD_COLORS: Record<number, string> = {
  5:   '#60a5fa', // blue-400
  10:  '#34d399', // emerald-400
  25:  '#fbbf24', // amber-400
  50:  '#f97316', // orange-500
  100: '#ef4444', // red-500
};

// ─── sub-components ──────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  unit,
  color = 'blue',
}: {
  label: string;
  value: string;
  unit?: string;
  color?: string;
}) {
  return (
    <Card withBorder radius="md" p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.5} mb={4}>
        {label}
      </Text>
      <Group gap={4} align="baseline">
        <Text fw={700} size="lg" c={`${color}.7`}>
          {value}
        </Text>
        {unit && (
          <Text size="sm" c="dimmed">
            {unit}
          </Text>
        )}
      </Group>
    </Card>
  );
}

// ─── main component ───────────────────────────────────────────────────────────

export default function ReturnPeriodsPanel() {
  const [zonas, setZonas] = useState<ZonaOperativaItem[]>([]);
  const [selectedZona, setSelectedZona] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ReturnPeriodsResponse | null>(null);

  useEffect(() => {
    listZonasOperativas()
      .then(setZonas)
      .catch(() =>
        notifications.show({
          title: 'Aviso',
          message: 'No se pudieron cargar las zonas operativas.',
          color: 'yellow',
        })
      );
  }, []);

  useEffect(() => {
    if (!selectedZona) return;

    setLoading(true);
    setResult(null);

    getReturnPeriods(selectedZona)
      .then(setResult)
      .catch((err) => {
        notifications.show({
          title: 'Error',
          message: err instanceof Error ? err.message : 'No se pudieron calcular los períodos de retorno.',
          color: 'red',
        });
      })
      .finally(() => setLoading(false));
  }, [selectedZona]);

  const zonaOptions = zonas.map((z) => ({
    value: z.id,
    label: `${z.nombre} — ${z.cuenca}`,
  }));

  // Prepare chart data
  const chartData = result?.return_periods.map((rp) => ({
    periodo: `T${rp.return_period_years}`,
    'Precipitación (mm)': rp.precipitation_mm,
    color: PERIOD_COLORS[rp.return_period_years] ?? '#6366f1',
  })) ?? [];

  const hasData = result && result.return_periods.length > 0;
  const insufficientData = result && result.years_of_data < 5;

  return (
    <Stack gap="lg" p="md">
      {/* ── Header ── */}
      <Group gap="sm">
        <ThemeIcon size="xl" radius="md" variant="light" color="violet">
          <IconChartBar size={22} />
        </ThemeIcon>
        <Box>
          <Title order={2} lh={1.2}>
            Períodos de Retorno
          </Title>
          <Text size="sm" c="dimmed">
            Distribución Gumbel EV-I · Máximos anuales CHIRPS/IMERG · T5 a T100
          </Text>
        </Box>
      </Group>

      <Divider />

      {/* ── Zona selector ── */}
      <Paper withBorder p="lg" radius="md">
        <Select
          label="Zona operativa"
          description="Seleccioná la zona para calcular los períodos de retorno"
          placeholder="Buscar zona..."
          data={zonaOptions}
          value={selectedZona}
          onChange={setSelectedZona}
          searchable
          clearable
          disabled={loading}
          maxDropdownHeight={280}
          style={{ maxWidth: 500 }}
        />
      </Paper>

      {/* ── Method info ── */}
      <Alert
        icon={<IconInfoCircle size={16} />}
        color="violet"
        variant="light"
        title="Método estadístico"
      >
        Se ajusta la distribución de valores extremos <strong>Gumbel EV-I</strong> por método de
        momentos a los máximos anuales de precipitación diaria. IMERG tiene prioridad sobre CHIRPS
        para fechas con ambos registros. Se requieren al menos <strong>5 años</strong> de datos.
      </Alert>

      {/* ── Insufficient data warning ── */}
      {insufficientData && (
        <Alert
          icon={<IconAlertTriangle size={16} />}
          color="orange"
          variant="light"
          title="Datos insuficientes"
        >
          Solo hay <strong>{result.years_of_data}</strong> año(s) de datos para esta zona.
          Se necesitan al menos 5 para ajustar la distribución Gumbel.
        </Alert>
      )}

      {/* ── Stats summary ── */}
      {result && (
        <Grid gutter="md">
          <Grid.Col span={{ base: 6, sm: 3 }}>
            <StatCard
              label="Años de datos"
              value={String(result.years_of_data)}
              color="violet"
            />
          </Grid.Col>
          <Grid.Col span={{ base: 6, sm: 3 }}>
            <StatCard
              label="Media anual máx."
              value={fmt(result.mean_annual_max_mm)}
              unit="mm"
              color="blue"
            />
          </Grid.Col>
          <Grid.Col span={{ base: 6, sm: 3 }}>
            <StatCard
              label="Desvío estándar"
              value={fmt(result.std_annual_max_mm)}
              unit="mm"
              color="cyan"
            />
          </Grid.Col>
          <Grid.Col span={{ base: 6, sm: 3 }}>
            <StatCard
              label="Registros anuales"
              value={String(result.annual_maxima_count)}
              color="teal"
            />
          </Grid.Col>
        </Grid>
      )}

      {/* ── Bar chart ── */}
      {hasData && (
        <Paper withBorder radius="md" p="md">
          <Group justify="space-between" mb="md">
            <Text fw={600} size="sm">
              Precipitación estimada por período de retorno
            </Text>
            <Badge variant="light" color="violet">
              Gumbel EV-I
            </Badge>
          </Group>
          <BarChart
            h={300}
            data={chartData}
            dataKey="periodo"
            series={[{ name: 'Precipitación (mm)', color: 'violet.6' }]}
            tickLine="y"
            gridAxis="y"
            withLegend={false}
            yAxisLabel="mm"
          />
        </Paper>
      )}

      {/* ── Table ── */}
      {hasData && (
        <Paper withBorder radius="md" p="md">
          <Group gap="xs" mb="sm">
            <IconDroplet size={16} />
            <Text fw={600} size="sm">
              Tabla de períodos de retorno
            </Text>
          </Group>
          <Table withTableBorder withColumnBorders verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Período de retorno</Table.Th>
                <Table.Th>Probabilidad anual de excedencia</Table.Th>
                <Table.Th>Precipitación estimada</Table.Th>
                <Table.Th>Referencia</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {result.return_periods.map((rp) => (
                <Table.Tr key={rp.return_period_years}>
                  <Table.Td>
                    <Badge
                      size="sm"
                      variant="filled"
                      style={{ backgroundColor: PERIOD_COLORS[rp.return_period_years] ?? '#6366f1' }}
                    >
                      T{rp.return_period_years} años
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {(100 / rp.return_period_years).toFixed(1)}%
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text fw={700} size="sm">
                      {fmt(rp.precipitation_mm)} mm
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {rp.return_period_years === 5
                        ? 'Diseño menor'
                        : rp.return_period_years === 10
                          ? 'Diseño estándar'
                          : rp.return_period_years === 25
                            ? 'Diseño mayor'
                            : rp.return_period_years === 50
                              ? 'Emergencia'
                              : 'Extremo / regulatorio'}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}

      {/* ── Empty state ── */}
      {!selectedZona && (
        <Paper withBorder radius="md" p="xl" ta="center">
          <ThemeIcon size="xl" radius="xl" variant="light" color="violet" mx="auto" mb="sm">
            <IconChartBar size={24} />
          </ThemeIcon>
          <Text c="dimmed" size="sm">
            Seleccioná una zona operativa para calcular los períodos de retorno.
          </Text>
        </Paper>
      )}

      {loading && (
        <Paper withBorder radius="md" p="xl" ta="center">
          <Text c="dimmed" size="sm">
            Calculando distribución Gumbel...
          </Text>
        </Paper>
      )}
    </Stack>
  );
}
