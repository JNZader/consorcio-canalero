import '@mantine/dates/styles.css';
import { Alert, Box, Button, Divider, Grid, Group, MultiSelect, Paper, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import {
  IconAlertCircle,
  IconAlertTriangle,
  IconChartBar,
  IconChartLine,
  IconDroplet,
  IconInfoCircle,
  IconWaveSine,
} from '../ui/icons';
import { FloodFlowHistoryPanel } from './flood-flow/components/FloodFlowHistoryPanel';
import { FloodFlowResultsTable } from './flood-flow/components/FloodFlowResultsTable';
import { FloodFlowStatCard } from './flood-flow/components/FloodFlowStatCard';
import { fmt } from './flood-flow/floodFlowUtils';
import { useFloodFlowController } from './flood-flow/useFloodFlowController';

export default function FloodFlowPanel() {
  const controller = useFloodFlowController();

  return (
    <Stack gap="lg" p="md">
      <Group gap="sm">
        <ThemeIcon size="xl" radius="md" variant="light" color="blue">
          <IconWaveSine size={22} />
        </ThemeIcon>
        <Box>
          <Title order={2} lh={1.2}>Estimación de Caudal</Title>
          <Text size="sm" c="dimmed">
            Método Racional · Tiempo de concentración Kirpich · GEE SRTM + Sentinel-2
          </Text>
        </Box>
      </Group>

      <Divider />

      <Paper withBorder p="lg" radius="md">
        <Grid gutter="md" align="flex-end">
          <Grid.Col span={{ base: 12, sm: 7 }}>
            <MultiSelect
              label="Zonas operativas"
              description="Seleccioná las zonas a analizar"
              placeholder="Buscar zona..."
              data={controller.zonaOptions}
              value={controller.selectedZonaIds}
              onChange={controller.setSelectedZonaIds}
              searchable
              clearable
              disabled={controller.loading}
              maxDropdownHeight={280}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 3 }}>
            <DatePickerInput
              label="Fecha del evento"
              description="Fecha de lluvia a analizar"
              placeholder="Seleccioná la fecha"
              value={controller.fechaLluvia}
              onChange={controller.setFechaLluvia}
              maxDate={new Date()}
              disabled={controller.loading}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 2 }}>
            <Button
              fullWidth
              leftSection={<IconChartLine size={16} />}
              loading={controller.loading}
              onClick={controller.handleCalcular}
              disabled={controller.selectedZonaIds.length === 0 || !controller.fechaLluvia}
            >
              Calcular
            </Button>
          </Grid.Col>
        </Grid>
      </Paper>

      {controller.stats.usandoFallback && (
        <Alert icon={<IconInfoCircle size={16} />} color="yellow" variant="light" title="Intensidad estimada">
          Una o más zonas usaron el fallback de <strong>20 mm/h</strong> porque no hay
          registros CHIRPS para esa fecha. Los resultados son orientativos.
        </Alert>
      )}

      {controller.result && controller.result.errors.length > 0 && (
        <Alert icon={<IconAlertTriangle size={16} />} title={`${controller.result.errors.length} zona(s) con error`} color="orange" variant="light">
          <Stack gap={4}>
            {controller.result.errors.map((error) => (
              <Text key={error.zona_id} size="sm">
                <Text span fw={600}>{error.zona_id.slice(0, 8)}…</Text> — {error.error}
              </Text>
            ))}
          </Stack>
        </Alert>
      )}

      {controller.result && controller.result.results.length > 0 && (
        <>
          <Grid gutter="md">
            <Grid.Col span={{ base: 6, sm: 3 }}>
              <FloodFlowStatCard icon={<IconChartBar size={18} />} label="Zonas procesadas" value={controller.result.results.length} color="blue" />
            </Grid.Col>
            <Grid.Col span={{ base: 6, sm: 3 }}>
              <FloodFlowStatCard icon={<IconWaveSine size={18} />} label="Q máximo" value={`${fmt(controller.stats.maxQ)} m³/s`} color="indigo" />
            </Grid.Col>
            <Grid.Col span={{ base: 6, sm: 3 }}>
              <FloodFlowStatCard icon={<IconAlertCircle size={18} />} label="En riesgo alto/crítico" value={controller.stats.zonasEnRiesgo ?? 0} color={controller.stats.zonasEnRiesgo ? 'red' : 'green'} />
            </Grid.Col>
            <Grid.Col span={{ base: 6, sm: 3 }}>
              <FloodFlowStatCard icon={<IconDroplet size={18} />} label="Fecha analizada" value={controller.result.fecha_lluvia} color="cyan" />
            </Grid.Col>
          </Grid>

          <Paper withBorder radius="md" p="md">
            <Group justify="space-between" mb="sm">
              <Text fw={600} size="sm">Resultados detallados</Text>
              <Text size="xs" c="dimmed">* Intensidad con fallback (sin dato CHIRPS)</Text>
            </Group>
            <FloodFlowResultsTable
              results={controller.result.results}
              onHistory={controller.handleVerHistorial}
              historyZona={controller.historyZona}
              historyLoading={controller.historyLoading}
            />
          </Paper>
        </>
      )}

      <FloodFlowHistoryPanel
        showHistory={controller.showHistory}
        history={controller.history}
        historyZonaName={controller.historyZonaName}
        onClose={() => controller.setShowHistory(false)}
      />
    </Stack>
  );
}
