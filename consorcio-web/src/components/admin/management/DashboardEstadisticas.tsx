import { Grid, Paper, Text, Group, Stack, Title, RingProgress, Badge } from '@mantine/core';
import { BarChart, LineChart, DonutChart } from '@mantine/charts';
import { 
  IconReportMoney, 
  IconAlertTriangle, 
  IconDroplet, 
  IconCheck,
  IconChartBar,
  IconChartLine,
  IconPieChart
} from '../../ui/icons';
import { memo } from 'react';

// Mock data for initial preview (to be replaced with actual API calls)
const financeData = [
  { rubro: 'Combustible', proyectado: 1200000, real: 950000 },
  { rubro: 'Sueldos', proyectado: 2500000, real: 2500000 },
  { rubro: 'Reparaciones', proyectado: 800000, real: 1100000 },
  { rubro: 'Administración', proyectado: 400000, real: 320000 },
  { rubro: 'Insumos', proyectado: 600000, real: 450000 },
];

const floodHistoryData = [
  { fecha: 'Ago 25', anegamiento: 5 },
  { fecha: 'Sep 25', anegamiento: 8 },
  { fecha: 'Oct 25', anegamiento: 15 },
  { fecha: 'Nov 25', anegamiento: 22 },
  { fecha: 'Dic 25', anegamiento: 18 },
  { fecha: 'Ene 26', anegamiento: 12 },
];

const reportStats = [
  { name: 'Pendientes', value: 12, color: 'red.6' },
  { name: 'En Proceso', value: 8, color: 'orange.6' },
  { name: 'Resueltos', value: 25, color: 'green.6' },
];

export const DashboardEstadisticas = memo(function DashboardEstadisticas() {
  return (
    <Stack gap="lg">
      <Title order={2} size="h3">Resumen de Gestión</Title>

      <Grid>
        {/* KPI Cards */}
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" radius="md" withBorder>
            <Group justify="space-between">
              <Stack gap={0}>
                <Text size="xs" c="dimmed" fw={700} tt="uppercase">Presupuesto Ejecutado</Text>
                <Text size="xl" fw={700}>$5.32M / $5.5M</Text>
              </Stack>
              <IconReportMoney size={32} color="var(--mantine-color-blue-6)" />
            </Group>
            <Text size="sm" mt="sm">
              <Text span c="green" fw={700}>96%</Text> del total anual
            </Text>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" radius="md" withBorder>
            <Group justify="space-between">
              <Stack gap={0}>
                <Text size="xs" c="dimmed" fw={700} tt="uppercase">Anegamiento Promedio</Text>
                <Text size="xl" fw={700}>12.4%</Text>
              </Stack>
              <IconDroplet size={32} color="var(--mantine-color-cyan-6)" />
            </Group>
            <Text size="sm" mt="sm">
              <Text span c="red" fw={700}>+2.1%</Text> vs mes anterior
            </Text>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" radius="md" withBorder>
            <Group justify="space-between">
              <Stack gap={0}>
                <Text size="xs" c="dimmed" fw={700} tt="uppercase">Reportes Activos</Text>
                <Text size="xl" fw={700}>20</Text>
              </Stack>
              <IconAlertTriangle size={32} color="var(--mantine-color-orange-6)" />
            </Group>
            <Text size="sm" mt="sm">
              <Text span c="blue" fw={700}>5</Text> nuevos esta semana
            </Text>
          </Paper>
        </Grid.Col>

        {/* Charts */}
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper p="md" radius="md" withBorder>
            <Group mb="lg">
              <IconChartBar size={20} />
              <Title order={4} size="h4">Ejecución Presupuestaria por Rubro</Title>
            </Group>
            <BarChart
              h={300}
              data={financeData}
              dataKey="rubro"
              type="grouped"
              series={[
                { name: 'proyectado', color: 'gray.4', label: 'Proyectado' },
                { name: 'real', color: 'blue.6', label: 'Real' },
              ]}
              tickLine="y"
              gridAxis="xy"
              valueFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
            />
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" radius="md" withBorder h="100%">
            <Group mb="lg">
              <IconPieChart size={20} />
              <Title order={4} size="h4">Estado de Reportes</Title>
            </Group>
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
              {reportStats.map(s => (
                <Group key={s.name} justify="space-between">
                  <Group gap="xs">
                    <Badge color={s.color.split('.')[0]} variant="filled" size="xs" circle />
                    <Text size="xs">{s.name}</Text>
                  </Group>
                  <Text size="xs" fw={700}>{s.value}</Text>
                </Group>
              ))}
            </Stack>
          </Paper>
        </Grid.Col>

        <Grid.Col span={12}>
          <Paper p="md" radius="md" withBorder>
            <Group mb="lg">
              <IconChartLine size={20} />
              <Title order={4} size="h4">Evolución de Anegamiento Satelital (%)</Title>
            </Group>
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
          </Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  );
});
