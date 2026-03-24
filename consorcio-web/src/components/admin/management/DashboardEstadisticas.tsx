import { Grid, Paper, Text, Group, Stack, Title, Badge } from '@mantine/core';
import { BarChart, LineChart, DonutChart } from '@mantine/charts';
import {
  IconReportMoney,
  IconAlertTriangle,
  IconDroplet,
  IconChartBar,
  IconChartLine,
  IconPieChart,
} from '../../ui/icons';
import { memo, useEffect, useMemo, useState } from 'react';
import { apiFetch, statsApi } from '../../../lib/api';
import { useDashboardStats, useMonitoringDashboard } from '../../../lib/query';

interface FinanceBalanceSummary {
  total_ingresos: number;
  total_gastos: number;
}

interface FinanceChartRow {
  rubro: string;
  proyectado: number;
  real: number;
}

interface FloodHistoryPoint {
  fecha: string;
  anegamiento: number;
}

interface HistoricalStatsResponse {
  items?: unknown[];
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatMonthLabel(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleDateString('es-AR', {
    month: 'short',
    year: '2-digit',
  });
}

function parseFinanceRows(payload: unknown): FinanceChartRow[] {
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload
    .map((entry) => {
      if (entry === null || typeof entry !== 'object') {
        return null;
      }

      const row = entry as Record<string, unknown>;
      const rubro =
        typeof row.rubro === 'string'
          ? row.rubro
          : typeof row.categoria === 'string'
            ? row.categoria
            : typeof row.nombre === 'string'
              ? row.nombre
              : null;
      const proyectado =
        asNumber(row.proyectado) ??
        asNumber(row.presupuestado) ??
        asNumber(row.monto_presupuestado);
      const real = asNumber(row.real) ?? asNumber(row.ejecutado) ?? asNumber(row.monto_ejecutado);

      if (!rubro || (proyectado === null && real === null)) {
        return null;
      }

      return {
        rubro,
        proyectado: proyectado ?? 0,
        real: real ?? 0,
      };
    })
    .filter((row): row is FinanceChartRow => row !== null);
}

function parseFloodHistory(payload: unknown): FloodHistoryPoint[] {
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload
    .map((entry) => {
      if (entry === null || typeof entry !== 'object') {
        return null;
      }

      const row = entry as Record<string, unknown>;
      const rawDate =
        typeof row.fecha === 'string'
          ? row.fecha
          : typeof row.date === 'string'
            ? row.date
            : typeof row.periodo === 'string'
              ? row.periodo
              : typeof row.mes === 'string'
                ? row.mes
                : typeof row.created_at === 'string'
                  ? row.created_at
                  : null;
      const anegamiento =
        asNumber(row.anegamiento) ??
        asNumber(row.porcentaje_area) ??
        asNumber(row.porcentaje_problematico) ??
        asNumber(row.valor) ??
        asNumber(row.value);

      if (!rawDate || anegamiento === null) {
        return null;
      }

      return {
        fecha: formatMonthLabel(rawDate),
        anegamiento,
      };
    })
    .filter((row): row is FloodHistoryPoint => row !== null)
    .slice(-6);
}

export const DashboardEstadisticas = memo(function DashboardEstadisticas() {
  const { stats } = useDashboardStats();
  const { data: monitoringData } = useMonitoringDashboard();
  const [financeSummary, setFinanceSummary] = useState<FinanceBalanceSummary | null>(null);
  const [financeData, setFinanceData] = useState<FinanceChartRow[]>([]);
  const [floodHistoryData, setFloodHistoryData] = useState<FloodHistoryPoint[]>([]);

  useEffect(() => {
    let mounted = true;

    async function fetchOptionalData() {
      const currentYear = new Date().getFullYear();

      const [balanceResult, budgetResult, historicalResult] = await Promise.allSettled([
        apiFetch<FinanceBalanceSummary>(`/finanzas/resumen/${currentYear}`),
        apiFetch<unknown>(`/finanzas/ejecucion/${currentYear}`),
        statsApi.getHistorical({ limit: 6 }),
      ]);

      if (!mounted) {
        return;
      }

      setFinanceSummary(balanceResult.status === 'fulfilled' ? balanceResult.value : null);
      setFinanceData(
        budgetResult.status === 'fulfilled' ? parseFinanceRows(budgetResult.value) : []
      );
      setFloodHistoryData(
        historicalResult.status === 'fulfilled'
          ? parseFloodHistory(
              (historicalResult.value as HistoricalStatsResponse)?.items ?? historicalResult.value
            )
          : []
      );
    }

    fetchOptionalData();

    return () => {
      mounted = false;
    };
  }, []);

  const reportStats = useMemo(() => {
    if (!stats?.denuncias) {
      return [] as Array<{ name: string; value: number; color: string }>;
    }

    return [
      { name: 'Pendientes', value: stats.denuncias.pendiente ?? 0, color: 'red.6' },
      { name: 'En Proceso', value: stats.denuncias.en_revision ?? 0, color: 'orange.6' },
      { name: 'Resueltos', value: stats.denuncias.resuelto ?? 0, color: 'green.6' },
    ];
  }, [stats]);

  const reportesActivos = stats?.denuncias
    ? (stats.denuncias.pendiente ?? 0) + (stats.denuncias.en_revision ?? 0)
    : null;
  const reportesNuevosSemana = asNumber(stats?.denuncias_nuevas_semana);

  const budgetRatio =
    financeSummary && financeSummary.total_ingresos > 0
      ? Math.round((financeSummary.total_gastos / financeSummary.total_ingresos) * 100)
      : null;

  const avgAnegamiento = useMemo(() => {
    if (floodHistoryData.length > 0) {
      const total = floodHistoryData.reduce((acc, item) => acc + item.anegamiento, 0);
      return total / floodHistoryData.length;
    }

    if (typeof monitoringData?.summary?.porcentaje_problematico === 'number') {
      return monitoringData.summary.porcentaje_problematico;
    }

    return null;
  }, [floodHistoryData, monitoringData]);

  const floodVariation = useMemo(() => {
    if (floodHistoryData.length < 2) {
      return null;
    }

    const previous = floodHistoryData[floodHistoryData.length - 2].anegamiento;
    const current = floodHistoryData[floodHistoryData.length - 1].anegamiento;
    return current - previous;
  }, [floodHistoryData]);

  const hasReportChartData = reportStats.some((item) => item.value > 0);

  return (
    <Stack gap="lg">
      <Title order={2} size="h3">
        Resumen de Gestión
      </Title>

      <Grid>
        {/* KPI Cards */}
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" radius="md" withBorder>
            <Group justify="space-between">
              <Stack gap={0}>
                <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                  Presupuesto Ejecutado
                </Text>
                <Text size="xl" fw={700}>
                  {financeSummary
                    ? `${formatCurrency(financeSummary.total_gastos)} / ${formatCurrency(financeSummary.total_ingresos)}`
                    : 'Sin datos'}
                </Text>
              </Stack>
              <IconReportMoney size={32} color="var(--mantine-color-blue-6)" />
            </Group>
            <Text size="sm" mt="sm">
              {budgetRatio === null ? (
                <Text span c="dimmed" fw={700}>
                  Sin datos
                </Text>
              ) : (
                <>
                  <Text span c="green" fw={700}>
                    {budgetRatio}%
                  </Text>{' '}
                  del total anual
                </>
              )}
            </Text>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" radius="md" withBorder>
            <Group justify="space-between">
              <Stack gap={0}>
                <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                  Anegamiento Promedio
                </Text>
                <Text size="xl" fw={700}>
                  {avgAnegamiento === null ? 'Sin datos' : `${avgAnegamiento.toFixed(1)}%`}
                </Text>
              </Stack>
              <IconDroplet size={32} color="var(--mantine-color-cyan-6)" />
            </Group>
            <Text size="sm" mt="sm">
              {floodVariation === null ? (
                <Text span c="dimmed" fw={700}>
                  Sin datos
                </Text>
              ) : (
                <>
                  <Text span c={floodVariation >= 0 ? 'red' : 'green'} fw={700}>
                    {floodVariation >= 0 ? '+' : ''}
                    {floodVariation.toFixed(1)}%
                  </Text>{' '}
                  vs mes anterior
                </>
              )}
            </Text>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" radius="md" withBorder>
            <Group justify="space-between">
              <Stack gap={0}>
                <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                  Reportes Activos
                </Text>
                <Text size="xl" fw={700}>
                  {reportesActivos === null ? 'Sin datos' : reportesActivos}
                </Text>
              </Stack>
              <IconAlertTriangle size={32} color="var(--mantine-color-orange-6)" />
            </Group>
            <Text size="sm" mt="sm">
              {reportesNuevosSemana === null ? (
                <Text span c="dimmed" fw={700}>
                  Sin datos
                </Text>
              ) : (
                <>
                  <Text span c="blue" fw={700}>
                    {reportesNuevosSemana}
                  </Text>{' '}
                  nuevos esta semana
                </>
              )}
            </Text>
          </Paper>
        </Grid.Col>

        {/* Charts */}
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper p="md" radius="md" withBorder>
            <Group mb="lg">
              <IconChartBar size={20} />
              <Title order={4} size="h4">
                Ejecución Presupuestaria por Rubro
              </Title>
            </Group>
            {financeData.length > 0 ? (
              <BarChart
                h={300}
                data={financeData}
                dataKey="rubro"
                series={[
                  { name: 'proyectado', color: 'gray.4', label: 'Proyectado' },
                  { name: 'real', color: 'blue.6', label: 'Real' },
                ]}
                tickLine="y"
                gridAxis="xy"
                valueFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
              />
            ) : (
              <Stack align="center" justify="center" h={300}>
                <Text c="dimmed">Sin datos de presupuesto por rubro</Text>
              </Stack>
            )}
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" radius="md" withBorder h="100%">
            <Group mb="lg">
              <IconPieChart size={20} />
              <Title order={4} size="h4">
                Estado de Reportes
              </Title>
            </Group>
            {hasReportChartData ? (
              <>
                <Stack align="center" justify="center" h={250}>
                  <DonutChart
                    size={180}
                    thickness={25}
                    data={reportStats}
                    withLabelsLine
                    labelsType="percent"
                    withLabels
                  />
                </Stack>
                <Stack gap={4} mt="md">
                  {reportStats.map((s) => (
                    <Group key={s.name} justify="space-between">
                      <Group gap="xs">
                        <Badge color={s.color.split('.')[0]} variant="filled" size="xs" circle />
                        <Text size="xs">{s.name}</Text>
                      </Group>
                      <Text size="xs" fw={700}>
                        {s.value}
                      </Text>
                    </Group>
                  ))}
                </Stack>
              </>
            ) : (
              <Stack align="center" justify="center" h={300}>
                <Text c="dimmed">Sin datos de estado de reportes</Text>
              </Stack>
            )}
          </Paper>
        </Grid.Col>

        <Grid.Col span={12}>
          <Paper p="md" radius="md" withBorder>
            <Group mb="lg">
              <IconChartLine size={20} />
              <Title order={4} size="h4">
                Evolución de Anegamiento Satelital (%)
              </Title>
            </Group>
            {floodHistoryData.length > 0 ? (
              <LineChart
                h={300}
                data={floodHistoryData}
                dataKey="fecha"
                series={[{ name: 'anegamiento', color: 'cyan.6', label: 'Anegamiento (%)' }]}
                curveType="monotone"
                tickLine="y"
                gridAxis="xy"
                valueFormatter={(value) => `${value}%`}
              />
            ) : (
              <Stack align="center" justify="center" h={300}>
                <Text c="dimmed">Sin datos de evolución satelital</Text>
              </Stack>
            )}
          </Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  );
});
