/**
 * FloodFlowPanel — Estimación de caudal pico por zona operativa.
 *
 * Kirpich (Tc) + Método Racional (Q = CIA/3.6).
 */

import '@mantine/dates/styles.css';
import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Collapse,
  Divider,
  Grid,
  Group,
  MultiSelect,
  Paper,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  Tooltip,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { notifications } from '@mantine/notifications';
import {
  computeFloodFlow,
  getFloodFlowHistory,
  listZonasOperativas,
  type FloodFlowHistoryResponse,
  type FloodFlowResponse,
  type ZonaFloodFlowResult,
  type ZonaOperativaItem,
} from '../../lib/api/floodFlow';
import {
  IconAlertCircle,
  IconAlertTriangle,
  IconChartBar,
  IconChartLine,
  IconCheck,
  IconDroplet,
  IconHistory,
  IconInfoCircle,
  IconWaveSine,
} from '../ui/icons';

// ─── types ──────────────────────────────────────────────────────────────────

type RiskLevel = ZonaFloodFlowResult['nivel_riesgo'];

// ─── constants ───────────────────────────────────────────────────────────────

const RISK_CONFIG: Record<RiskLevel, { color: string; label: string; rowBg: string }> = {
  bajo:          { color: 'green',  label: 'Bajo',      rowBg: 'var(--mantine-color-green-0)'  },
  moderado:      { color: 'yellow', label: 'Moderado',  rowBg: 'var(--mantine-color-yellow-0)' },
  alto:          { color: 'orange', label: 'Alto',      rowBg: 'var(--mantine-color-orange-0)' },
  critico:       { color: 'red',    label: 'Crítico',   rowBg: 'var(--mantine-color-red-0)'    },
  sin_capacidad: { color: 'gray',   label: 'Sin cap.',  rowBg: 'transparent'                   },
};

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '—';
  return n.toFixed(decimals);
}

function yesterday(): Date {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d;
}

function toISODate(d: Date): string {
  return d.toISOString().split('T')[0];
}

// ─── sub-components ──────────────────────────────────────────────────────────

function StatCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <Card withBorder radius="md" p="md">
      <Group gap="sm">
        <ThemeIcon color={color} variant="light" size="lg" radius="md">
          {icon}
        </ThemeIcon>
        <Box>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.5}>
            {label}
          </Text>
          <Text fw={700} size="xl" lh={1.2}>
            {value}
          </Text>
        </Box>
      </Group>
    </Card>
  );
}

function RiskBadge({ nivel }: { nivel: RiskLevel }) {
  const cfg = RISK_CONFIG[nivel];
  return (
    <Badge color={cfg.color} variant="filled" size="sm" radius="sm">
      {cfg.label}
    </Badge>
  );
}

function ResultsTable({
  results,
  onHistory,
  historyZona,
  historyLoading,
}: {
  results: ZonaFloodFlowResult[];
  onHistory: (id: string) => void;
  historyZona: string | null;
  historyLoading: boolean;
}) {
  return (
    <Box style={{ overflowX: 'auto' }}>
      <Table
        striped={false}
        highlightOnHover
        withTableBorder
        withColumnBorders
        verticalSpacing="sm"
        style={{ minWidth: 860 }}
      >
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Zona</Table.Th>
            <Table.Th>
              <Tooltip label="Tiempo de concentración (Kirpich)" position="top">
                <span>Tc (min)</span>
              </Tooltip>
            </Table.Th>
            <Table.Th>
              <Tooltip label="Coeficiente de escorrentía" position="top">
                <span>C</span>
              </Tooltip>
            </Table.Th>
            <Table.Th>
              <Tooltip label="Fuente del coeficiente C" position="top">
                <span>Fuente C</span>
              </Tooltip>
            </Table.Th>
            <Table.Th>I (mm/h)</Table.Th>
            <Table.Th>Área (km²)</Table.Th>
            <Table.Th fw={700}>Q (m³/s)</Table.Th>
            <Table.Th>Cap. (m³/s)</Table.Th>
            <Table.Th>% Cap.</Table.Th>
            <Table.Th>Riesgo</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {results.map((r) => (
            <Table.Tr
              key={r.zona_id}
              style={{ backgroundColor: RISK_CONFIG[r.nivel_riesgo].rowBg }}
            >
              <Table.Td>
                <Text size="sm" fw={500}>
                  {r.zona_nombre ?? r.zona_id.slice(0, 8)}
                </Text>
              </Table.Td>
              <Table.Td>{fmt(r.tc_minutos, 1)}</Table.Td>
              <Table.Td>{fmt(r.c_escorrentia)}</Table.Td>
              <Table.Td>
                <Badge
                  variant="outline"
                  size="xs"
                  color={
                    r.c_source === 'landcover' ? 'blue' :
                    r.c_source === 'ndvi_sentinel2' ? 'green' : 'gray'
                  }
                >
                  {r.c_source === 'landcover' ? 'Land Cover' :
                   r.c_source === 'ndvi_sentinel2' ? 'Sentinel-2' : 'Fallback'}
                </Badge>
              </Table.Td>
              <Table.Td>
                {r.intensidad_mm_h === 20 ? (
                  <Tooltip label="Dato fallback — sin registro CHIRPS" position="top">
                    <Text size="sm" c="dimmed">
                      {fmt(r.intensidad_mm_h, 1)} *
                    </Text>
                  </Tooltip>
                ) : (
                  fmt(r.intensidad_mm_h, 1)
                )}
              </Table.Td>
              <Table.Td>{fmt(r.area_km2)}</Table.Td>
              <Table.Td>
                <Text fw={700} size="sm">
                  {fmt(r.caudal_m3s)}
                </Text>
              </Table.Td>
              <Table.Td>{fmt(r.capacidad_m3s)}</Table.Td>
              <Table.Td>
                {r.porcentaje_capacidad != null ? (
                  <Text
                    fw={600}
                    size="sm"
                    c={
                      r.porcentaje_capacidad > 100
                        ? 'red'
                        : r.porcentaje_capacidad > 75
                          ? 'orange'
                          : 'inherit'
                    }
                  >
                    {fmt(r.porcentaje_capacidad, 1)}%
                  </Text>
                ) : (
                  '—'
                )}
              </Table.Td>
              <Table.Td>
                <RiskBadge nivel={r.nivel_riesgo} />
              </Table.Td>
              <Table.Td>
                <Button
                  size="xs"
                  variant="subtle"
                  leftSection={<IconHistory size={13} />}
                  loading={historyLoading && historyZona === r.zona_id}
                  onClick={() => onHistory(r.zona_id)}
                >
                  Historial
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Box>
  );
}

// ─── main component ───────────────────────────────────────────────────────────

export default function FloodFlowPanel() {
  const [zonas, setZonas] = useState<ZonaOperativaItem[]>([]);
  const [selectedZonaIds, setSelectedZonaIds] = useState<string[]>([]);
  const [fechaLluvia, setFechaLluvia] = useState<Date | null>(yesterday());
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FloodFlowResponse | null>(null);
  const [history, setHistory] = useState<FloodFlowHistoryResponse | null>(null);
  const [historyZona, setHistoryZona] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

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

  const zonaOptions = zonas.map((z) => ({
    value: z.id,
    label: `${z.nombre} — ${z.cuenca}`,
  }));

  // ── derived stats ──────────────────────────────────────────────────────────
  const maxQ = result ? Math.max(...result.results.map((r) => r.caudal_m3s), 0) : null;
  const zonasEnRiesgo = result
    ? result.results.filter((r) => r.nivel_riesgo === 'alto' || r.nivel_riesgo === 'critico').length
    : null;
  const usandoFallback = result?.results.some((r) => r.intensidad_mm_h === 20) ?? false;

  async function handleCalcular() {
    if (!fechaLluvia || selectedZonaIds.length === 0) {
      notifications.show({
        title: 'Faltan datos',
        message: 'Seleccioná al menos una zona y una fecha de lluvia.',
        color: 'red',
      });
      return;
    }

    setLoading(true);
    setResult(null);
    setHistory(null);
    setShowHistory(false);

    try {
      const res = await computeFloodFlow({
        zona_ids: selectedZonaIds,
        fecha_lluvia: toISODate(fechaLluvia),
      });
      setResult(res);

      if (res.results.length > 0) {
        notifications.show({
          title: 'Cálculo completado',
          message: `${res.results.length} zona(s) procesada(s).`,
          color: 'green',
          icon: <IconCheck size={16} />,
        });
      }
    } catch (err) {
      notifications.show({
        title: 'Error al calcular',
        message: err instanceof Error ? err.message : 'Error desconocido.',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleVerHistorial(zonaId: string) {
    setHistoryLoading(true);
    setHistoryZona(zonaId);
    setShowHistory(false);

    try {
      const h = await getFloodFlowHistory(zonaId, 10);
      setHistory(h);
      setShowHistory(true);
    } catch {
      notifications.show({
        title: 'Error',
        message: 'No se pudo cargar el historial.',
        color: 'red',
      });
    } finally {
      setHistoryLoading(false);
    }
  }

  const historyZonaName =
    result?.results.find((r) => r.zona_id === historyZona)?.zona_nombre ?? historyZona?.slice(0, 8);

  return (
    <Stack gap="lg" p="md">
      {/* ── Header ── */}
      <Group gap="sm">
        <ThemeIcon size="xl" radius="md" variant="light" color="blue">
          <IconWaveSine size={22} />
        </ThemeIcon>
        <Box>
          <Title order={2} lh={1.2}>
            Estimación de Caudal
          </Title>
          <Text size="sm" c="dimmed">
            Método Racional · Tiempo de concentración Kirpich · GEE SRTM + Sentinel-2
          </Text>
        </Box>
      </Group>

      <Divider />

      {/* ── Inputs ── */}
      <Paper withBorder p="lg" radius="md">
        <Grid gutter="md" align="flex-end">
          <Grid.Col span={{ base: 12, sm: 7 }}>
            <MultiSelect
              label="Zonas operativas"
              description="Seleccioná las zonas a analizar"
              placeholder="Buscar zona..."
              data={zonaOptions}
              value={selectedZonaIds}
              onChange={setSelectedZonaIds}
              searchable
              clearable
              disabled={loading}
              maxDropdownHeight={280}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 3 }}>
            <DatePickerInput
              label="Fecha del evento"
              description="Fecha de lluvia a analizar"
              placeholder="Seleccioná la fecha"
              value={fechaLluvia}
              onChange={setFechaLluvia}
              maxDate={new Date()}
              disabled={loading}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 2 }}>
            <Button
              fullWidth
              leftSection={<IconChartLine size={16} />}
              loading={loading}
              onClick={handleCalcular}
              disabled={selectedZonaIds.length === 0 || !fechaLluvia}
            >
              Calcular
            </Button>
          </Grid.Col>
        </Grid>
      </Paper>

      {/* ── Fallback warning ── */}
      {usandoFallback && (
        <Alert
          icon={<IconInfoCircle size={16} />}
          color="yellow"
          variant="light"
          title="Intensidad estimada"
        >
          Una o más zonas usaron el fallback de <strong>20 mm/h</strong> porque no hay
          registros CHIRPS para esa fecha. Los resultados son orientativos.
        </Alert>
      )}

      {/* ── Errors ── */}
      {result && result.errors.length > 0 && (
        <Alert
          icon={<IconAlertTriangle size={16} />}
          title={`${result.errors.length} zona(s) con error`}
          color="orange"
          variant="light"
        >
          <Stack gap={4}>
            {result.errors.map((e) => (
              <Text key={e.zona_id} size="sm">
                <Text span fw={600}>
                  {e.zona_id.slice(0, 8)}…
                </Text>{' '}
                — {e.error}
              </Text>
            ))}
          </Stack>
        </Alert>
      )}

      {/* ── Summary stats ── */}
      {result && result.results.length > 0 && (
        <>
          <Grid gutter="md">
            <Grid.Col span={{ base: 6, sm: 3 }}>
              <StatCard
                icon={<IconChartBar size={18} />}
                label="Zonas procesadas"
                value={result.results.length}
                color="blue"
              />
            </Grid.Col>
            <Grid.Col span={{ base: 6, sm: 3 }}>
              <StatCard
                icon={<IconWaveSine size={18} />}
                label="Q máximo"
                value={`${fmt(maxQ)} m³/s`}
                color="indigo"
              />
            </Grid.Col>
            <Grid.Col span={{ base: 6, sm: 3 }}>
              <StatCard
                icon={<IconAlertCircle size={18} />}
                label="En riesgo alto/crítico"
                value={zonasEnRiesgo ?? 0}
                color={zonasEnRiesgo ? 'red' : 'green'}
              />
            </Grid.Col>
            <Grid.Col span={{ base: 6, sm: 3 }}>
              <StatCard
                icon={<IconDroplet size={18} />}
                label="Fecha analizada"
                value={result.fecha_lluvia}
                color="cyan"
              />
            </Grid.Col>
          </Grid>

          {/* ── Results table ── */}
          <Paper withBorder radius="md" p="md">
            <Group justify="space-between" mb="sm">
              <Text fw={600} size="sm">
                Resultados detallados
              </Text>
              <Text size="xs" c="dimmed">
                * Intensidad con fallback (sin dato CHIRPS)
              </Text>
            </Group>
            <ResultsTable
              results={result.results}
              onHistory={handleVerHistorial}
              historyZona={historyZona}
              historyLoading={historyLoading}
            />
          </Paper>
        </>
      )}

      {/* ── History ── */}
      <Collapse in={showHistory}>
        {history && history.records.length > 0 && (
          <Paper withBorder radius="md" p="md">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <IconHistory size={16} />
                <Text fw={600} size="sm">
                  Historial — {historyZonaName}
                </Text>
                <Badge variant="light" size="sm">
                  {history.total} registros
                </Badge>
              </Group>
              <Button
                size="xs"
                variant="subtle"
                color="gray"
                onClick={() => setShowHistory(false)}
              >
                Cerrar
              </Button>
            </Group>
            <Table withTableBorder withColumnBorders verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Fecha lluvia</Table.Th>
                  <Table.Th>Fecha cálculo</Table.Th>
                  <Table.Th>Tc (min)</Table.Th>
                  <Table.Th>C</Table.Th>
                  <Table.Th>Q (m³/s)</Table.Th>
                  <Table.Th>Riesgo</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {history.records.map((r, i) => (
                  <Table.Tr
                    key={`${r.fecha_lluvia}-${i}`}
                    style={{ backgroundColor: RISK_CONFIG[r.nivel_riesgo].rowBg }}
                  >
                    <Table.Td>{r.fecha_lluvia}</Table.Td>
                    <Table.Td>{r.fecha_calculo}</Table.Td>
                    <Table.Td>{fmt(r.tc_minutos, 1)}</Table.Td>
                    <Table.Td>{fmt(r.c_escorrentia)}</Table.Td>
                    <Table.Td fw={600}>{fmt(r.caudal_m3s)}</Table.Td>
                    <Table.Td>
                      <RiskBadge nivel={r.nivel_riesgo} />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        )}
      </Collapse>
    </Stack>
  );
}
