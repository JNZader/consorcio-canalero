/**
 * InformesTerritorialesPanel — Informe territorial del consorcio.
 *
 * Muestra km de canales y hectáreas/porcentaje de tipos de suelo
 * para tres ámbitos: todo el consorcio, por cuenca, por subcuenca (zona operativa).
 *
 * Los geodatos (suelos + canales) se importan desde GeoJSON al backend (PostGIS)
 * y se pre-calculan en vistas materializadas para máxima performance.
 */

import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Paper,
  Progress,
  Select,
  Stack,
  Table,
  Tabs,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { useEffect, useState } from 'react';
import { notifications } from '@mantine/notifications';
import {
  getTerritorialReport,
  getTerritorialStatus,
  listCuencas,
  syncGeodata,
  type TerritorialReportResponse,
  type TerritorialStatus,
} from '../../lib/api/territorial';
import { listZonasOperativas, type ZonaOperativaItem } from '../../lib/api/floodFlow';
import { IconAlertTriangle, IconInfoCircle, IconLeaf, IconMap } from '../ui/icons';

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmtNum(n: number, decimals = 1): string {
  return n.toLocaleString('es-AR', { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
}

function capColor(cap: string | null): string {
  const map: Record<string, string> = {
    I: 'green', II: 'teal', III: 'cyan', IV: 'blue',
    V: 'yellow', VI: 'orange', VII: 'red', VIII: 'dark',
  };
  return cap ? (map[cap] ?? 'gray') : 'gray';
}

// ─── ReportTable ─────────────────────────────────────────────────────────────

function ReportView({ report }: { report: TerritorialReportResponse }) {
  return (
    <Stack gap="md">
      <Group gap="xl">
        <Paper p="md" radius="md" withBorder style={{ flex: 1 }}>
          <Text size="xs" c="dimmed" mb={4}>Canales de riego</Text>
          <Text fw={700} size="xl">{fmtNum(report.km_canales, 2)} km</Text>
        </Paper>
        <Paper p="md" radius="md" withBorder style={{ flex: 1 }}>
          <Text size="xs" c="dimmed" mb={4}>Caminos</Text>
          <Text fw={700} size="xl">{fmtNum(report.total_km_caminos, 2)} km</Text>
        </Paper>
        <Paper p="md" radius="md" withBorder style={{ flex: 1 }}>
          <Text size="xs" c="dimmed" mb={4}>Área analizada</Text>
          <Text fw={700} size="xl">{fmtNum(report.total_ha_analizada)} ha</Text>
        </Paper>
        <Paper p="md" radius="md" withBorder style={{ flex: 1 }}>
          <Text size="xs" c="dimmed" mb={4}>Tipos de suelo</Text>
          <Text fw={700} size="xl">{report.suelos.length}</Text>
        </Paper>
      </Group>

      {report.caminos_por_consorcio.length > 0 && (
        <>
          <Divider label="Caminos por consorcio caminero" labelPosition="left" />
          <Table striped withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Consorcio Caminero</Table.Th>
                <Table.Th ta="right">km</Table.Th>
                <Table.Th ta="right">%</Table.Th>
                <Table.Th>Distribución</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {report.caminos_por_consorcio.map((c) => (
                <Table.Tr key={c.consorcio_codigo}>
                  <Table.Td>
                    <Text fw={600} size="sm">{c.consorcio_nombre}</Text>
                  </Table.Td>
                  <Table.Td ta="right">{fmtNum(c.km, 2)}</Table.Td>
                  <Table.Td ta="right">{fmtNum(c.pct)}%</Table.Td>
                  <Table.Td style={{ minWidth: 120 }}>
                    <Progress value={c.pct} color="orange" size="sm" radius="xl" />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </>
      )}

      <Divider label="Distribución de suelos" labelPosition="left" />

      <Table striped withTableBorder withColumnBorders>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Símbolo</Table.Th>
            <Table.Th>CAP</Table.Th>
            <Table.Th ta="right">Hectáreas</Table.Th>
            <Table.Th ta="right">%</Table.Th>
            <Table.Th>Distribución</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {report.suelos.map((s) => (
            <Table.Tr key={s.simbolo}>
              <Table.Td>
                <Text fw={600} ff="monospace">{s.simbolo}</Text>
              </Table.Td>
              <Table.Td>
                {s.cap ? (
                  <Badge color={capColor(s.cap)} variant="light" size="sm">
                    Clase {s.cap}
                  </Badge>
                ) : (
                  <Text c="dimmed" size="sm">—</Text>
                )}
              </Table.Td>
              <Table.Td ta="right">{fmtNum(s.ha)}</Table.Td>
              <Table.Td ta="right">{fmtNum(s.pct)}%</Table.Td>
              <Table.Td style={{ minWidth: 120 }}>
                <Progress value={s.pct} color={capColor(s.cap)} size="sm" radius="xl" />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

// ─── ImportSection ────────────────────────────────────────────────────────────

function SyncSection({
  status,
  onSynced,
}: {
  status: TerritorialStatus;
  onSynced: () => void;
}) {
  const [syncing, setSyncing] = useState(false);

  async function handleSync() {
    setSyncing(true);
    try {
      const res = await syncGeodata();
      notifications.show({
        title: 'Sincronización exitosa',
        message: res.message,
        color: 'green',
      });
      onSynced();
    } catch (err) {
      notifications.show({
        title: 'Error al sincronizar',
        message: err instanceof Error ? err.message : 'Error desconocido',
        color: 'red',
      });
    } finally {
      setSyncing(false);
    }
  }

  return (
    <Card withBorder radius="md" p="md">
      <Group justify="space-between">
        <Group>
          <ThemeIcon color="teal" variant="light" size="lg">
            <IconMap size={18} />
          </ThemeIcon>
          <div>
            <Text fw={600}>Geodatos territoriales</Text>
            <Text size="xs" c="dimmed">
              Suelos, canales y caminos — sincroniza desde las capas del sistema
            </Text>
          </div>
        </Group>

        <Group gap="md">
          <Group gap={6}>
            <Badge size="xs" color={status.has_suelos ? 'green' : 'gray'} variant="dot">
              Suelos
            </Badge>
            <Badge size="xs" color={status.has_canales ? 'green' : 'gray'} variant="dot">
              Canales
            </Badge>
            <Badge size="xs" color={status.has_caminos ? 'green' : 'gray'} variant="dot">
              Caminos
            </Badge>
          </Group>

          <Button
            size="xs"
            variant="light"
            color="teal"
            loading={syncing}
            onClick={handleSync}
            leftSection={<IconLeaf size={14} />}
          >
            Sincronizar geodatos
          </Button>
        </Group>
      </Group>
    </Card>
  );
}

// ─── Main panel ───────────────────────────────────────────────────────────────

export default function InformesTerritorialesPanel() {
  const [status, setStatus] = useState<TerritorialStatus>({ has_suelos: false, has_canales: false, has_caminos: false });
  const [cuencas, setCuencas] = useState<string[]>([]);
  const [zonas, setZonas] = useState<ZonaOperativaItem[]>([]);

  const [consorciReport, setConsorcioReport] = useState<TerritorialReportResponse | null>(null);
  const [cuencaSelected, setCuencaSelected] = useState<string | null>(null);
  const [cuencaReport, setCuencaReport] = useState<TerritorialReportResponse | null>(null);
  const [zonaSelected, setZonaSelected] = useState<string | null>(null);
  const [zonaReport, setZonaReport] = useState<TerritorialReportResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [noData, setNoData] = useState(false);

  useEffect(() => {
    loadInitialData();
  }, []);

  async function loadInitialData() {
    try {
      const [st, zs] = await Promise.all([getTerritorialStatus(), listZonasOperativas()]);
      setStatus(st);
      setZonas(zs);
      if (!st.has_suelos && !st.has_canales && !st.has_caminos) {
        setNoData(true);
        return;
      }
      const [cs, rep] = await Promise.all([listCuencas(), getTerritorialReport('consorcio')]);
      setCuencas(cs);
      setConsorcioReport(rep);
    } catch {
      setNoData(true);
    }
  }

  async function loadCuencaReport(cuenca: string) {
    setCuencaSelected(cuenca);
    setCuencaReport(null);
    setLoading(true);
    try {
      const rep = await getTerritorialReport('cuenca', cuenca);
      setCuencaReport(rep);
    } catch (err) {
      notifications.show({
        title: 'Error',
        message: err instanceof Error ? err.message : 'No se pudo cargar el informe',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  }

  async function loadZonaReport(zonaId: string) {
    setZonaSelected(zonaId);
    setZonaReport(null);
    setLoading(true);
    try {
      const rep = await getTerritorialReport('zona', zonaId);
      setZonaReport(rep);
    } catch (err) {
      notifications.show({
        title: 'Error',
        message: err instanceof Error ? err.message : 'No se pudo cargar el informe',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  }

  const hasData = status.has_suelos || status.has_canales || status.has_caminos;

  return (
    <Stack gap="lg">
      {/* Header */}
      <Group>
        <ThemeIcon color="teal" variant="light" size="xl" radius="md">
          <IconLeaf size={24} />
        </ThemeIcon>
        <div>
          <Title order={2}>Informe Territorial</Title>
          <Text c="dimmed" size="sm">
            Km de canales y distribución de suelos por unidad territorial
          </Text>
        </div>
      </Group>

      <SyncSection status={status} onSynced={loadInitialData} />

      {noData && !hasData && (
        <Alert icon={<IconAlertTriangle size={16} />} color="yellow" title="Sin datos importados">
          Importá los archivos GeoJSON de suelos y canales para generar informes. Los archivos ya
          existen en <Text span ff="monospace" size="xs">public/data/suelos_cu.geojson</Text> y{' '}
          <Text span ff="monospace" size="xs">public/waterways/canales_existentes.geojson</Text>.
        </Alert>
      )}

      {hasData && (
        <>
          <Alert icon={<IconInfoCircle size={16} />} color="blue" variant="light">
            Cálculos realizados en UTM 20S (EPSG:32720) sobre intersecciones PostGIS pre-computadas.
            Los porcentajes son sobre el área de suelos analizada dentro de cada unidad.
          </Alert>

          <Tabs defaultValue="consorcio">
            <Tabs.List>
              <Tabs.Tab value="consorcio" leftSection={<IconMap size={14} />}>
                Todo el Consorcio
              </Tabs.Tab>
              <Tabs.Tab value="cuenca" leftSection={<IconLeaf size={14} />}>
                Por Cuenca
              </Tabs.Tab>
              <Tabs.Tab value="zona" leftSection={<IconLeaf size={14} />}>
                Por Subcuenca
              </Tabs.Tab>
            </Tabs.List>

            {/* Tab: Consorcio */}
            <Tabs.Panel value="consorcio" pt="md">
              {consorciReport ? (
                <ReportView report={consorciReport} />
              ) : (
                <Text c="dimmed" size="sm">Cargando...</Text>
              )}
            </Tabs.Panel>

            {/* Tab: Por cuenca */}
            <Tabs.Panel value="cuenca" pt="md">
              <Stack gap="md">
                <Select
                  label="Cuenca"
                  placeholder="Seleccioná una cuenca"
                  data={cuencas}
                  value={cuencaSelected}
                  onChange={(v) => v && loadCuencaReport(v)}
                  searchable
                  clearable={false}
                />
                {loading && !cuencaReport && <Text c="dimmed" size="sm">Cargando...</Text>}
                {cuencaReport && <ReportView report={cuencaReport} />}
                {!cuencaSelected && (
                  <Text c="dimmed" size="sm">Seleccioná una cuenca para ver el informe.</Text>
                )}
              </Stack>
            </Tabs.Panel>

            {/* Tab: Por zona (subcuenca) */}
            <Tabs.Panel value="zona" pt="md">
              <Stack gap="md">
                <Select
                  label="Zona operativa (subcuenca)"
                  placeholder="Seleccioná una zona"
                  data={zonas.map((z) => ({ value: z.id, label: `${z.nombre} — ${z.cuenca}` }))}
                  value={zonaSelected}
                  onChange={(v) => v && loadZonaReport(v)}
                  searchable
                  clearable={false}
                />
                {loading && !zonaReport && <Text c="dimmed" size="sm">Cargando...</Text>}
                {zonaReport && <ReportView report={zonaReport} />}
                {!zonaSelected && (
                  <Text c="dimmed" size="sm">Seleccioná una zona operativa para ver el informe.</Text>
                )}
              </Stack>
            </Tabs.Panel>
          </Tabs>
        </>
      )}
    </Stack>
  );
}
