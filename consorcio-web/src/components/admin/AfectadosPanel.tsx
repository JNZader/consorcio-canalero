/**
 * AfectadosPanel - Consorcistas affected by flood risk zones.
 *
 * Two views:
 * - Por Zona: select a zona operativa → list affected consorcistas via ST_Intersects
 * - Por Evento: select a flood event → grouped results per flooded zona
 *
 * Includes admin-only catastro import from the static IDECOR GeoJSON.
 */

import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Paper,
  Select,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';

import { floodCalibrationApi } from '../../lib/api/floodCalibration';
import type {
  AfectadosResponse,
  EventoAfectadosResponse,
  FloodEventListItem,
} from '../../lib/api/floodCalibration';
import { logger } from '../../lib/logger';
import {
  IconAlertTriangle,
  IconCheck,
  IconRefresh,
  IconUpload,
  IconUsers,
} from '../ui/icons';

// ─── Helpers ──────────────────────────────────────────────────────────────

function SummaryCards({ totalConsorcistas, totalHa }: { totalConsorcistas: number; totalHa: number }) {
  return (
    <Group grow>
      <Card withBorder radius="md" p="md">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Consorcistas afectados</Text>
        <Text size="2rem" fw={700} c="red.6">{totalConsorcistas}</Text>
      </Card>
      <Card withBorder radius="md" p="md">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Hectáreas afectadas</Text>
        <Text size="2rem" fw={700} c="orange.6">
          {totalHa.toLocaleString('es-AR', { maximumFractionDigits: 1 })}
        </Text>
      </Card>
    </Group>
  );
}

function AfectadosTable({ data }: { data: AfectadosResponse }) {
  if (data.afectados.length === 0) {
    return (
      <Text c="dimmed" size="sm" ta="center" py="md">
        No se encontraron consorcistas con parcelas en esta zona.
      </Text>
    );
  }
  return (
    <Table striped highlightOnHover withTableBorder fz="sm">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Nombre</Table.Th>
          <Table.Th>Nomenclatura</Table.Th>
          <Table.Th>Hectáreas</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {data.afectados.map((a) => (
          <Table.Tr key={`${a.consorcista_id}-${a.nomenclatura}`}>
            <Table.Td fw={500}>{a.nombre}</Table.Td>
            <Table.Td>
              <Text size="xs" ff="monospace" c="dimmed">{a.nomenclatura}</Text>
            </Table.Td>
            <Table.Td>
              {a.hectareas != null
                ? a.hectareas.toLocaleString('es-AR', { maximumFractionDigits: 1 })
                : '—'}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────

export default function AfectadosPanel() {
  // ── Zona tab state
  const [zonas, setZonas] = useState<{ value: string; label: string }[]>([]);
  const [selectedZona, setSelectedZona] = useState<string | null>(null);
  const [zonaResult, setZonaResult] = useState<AfectadosResponse | null>(null);
  const [zonaLoading, setZonaLoading] = useState(false);

  // ── Event tab state
  const [events, setEvents] = useState<FloodEventListItem[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [eventoResult, setEventoResult] = useState<EventoAfectadosResponse | null>(null);
  const [eventoLoading, setEventoLoading] = useState(false);

  // ── Import state
  const [importing, setImporting] = useState(false);

  // ── Load zonas and events on mount
  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL ?? ''}/api/v2/geo/basins`)
      .then((r) => r.json())
      .then((fc) => {
        if (!fc?.features) return;
        const opts = (fc.features as Array<{ properties: { id: string; nombre: string } }>)
          .map((f) => ({ value: f.properties.id, label: f.properties.nombre }))
          .sort((a, b) => a.label.localeCompare(b.label));
        setZonas(opts);
      })
      .catch((err) => logger.warn('Error cargando zonas:', err));

    floodCalibrationApi
      .listEvents()
      .then(setEvents)
      .catch((err) => logger.warn('Error cargando eventos:', err));
  }, []);

  // ── Query by zona
  const handleQueryZona = useCallback(async () => {
    if (!selectedZona) return;
    setZonaLoading(true);
    setZonaResult(null);
    try {
      const data = await floodCalibrationApi.getAfectadosByZona(selectedZona);
      setZonaResult(data);
    } catch (err) {
      notifications.show({
        title: 'Error',
        message: err instanceof Error ? err.message : 'No se pudo consultar la zona',
        color: 'red',
      });
    } finally {
      setZonaLoading(false);
    }
  }, [selectedZona]);

  // ── Query by event
  const handleQueryEvento = useCallback(async () => {
    if (!selectedEvent) return;
    setEventoLoading(true);
    setEventoResult(null);
    try {
      const data = await floodCalibrationApi.getAfectadosByEvento(selectedEvent);
      setEventoResult(data);
    } catch (err) {
      notifications.show({
        title: 'Error',
        message: err instanceof Error ? err.message : 'No se pudo consultar el evento',
        color: 'red',
      });
    } finally {
      setEventoLoading(false);
    }
  }, [selectedEvent]);

  // ── Import catastro from static GeoJSON
  const handleImport = useCallback(async () => {
    setImporting(true);
    try {
      const res = await fetch('/data/catastro_rural_cu.geojson');
      if (!res.ok) throw new Error('No se pudo cargar el archivo de catastro');
      const geojson = await res.json();
      const result = await floodCalibrationApi.importCatastro(geojson);
      notifications.show({
        title: 'Catastro importado',
        message: `${result.imported.toLocaleString()} parcelas importadas, ${result.skipped} omitidas de ${result.total.toLocaleString()} totales.`,
        color: 'green',
        icon: <IconCheck size={16} />,
        autoClose: 8000,
      });
    } catch (err) {
      notifications.show({
        title: 'Error en importación',
        message: err instanceof Error ? err.message : 'Error desconocido',
        color: 'red',
      });
    } finally {
      setImporting(false);
    }
  }, []);

  const eventOptions = events.map((e) => ({
    value: e.id,
    label: `${e.event_date}${e.description ? ` — ${e.description}` : ''}`,
  }));

  return (
    <Stack gap="lg">
      {/* Header */}
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={3}>
            <Group gap="xs">
              <IconUsers size={22} />
              Afectados por Zona de Riesgo
            </Group>
          </Title>
          <Text c="dimmed" size="sm" mt={4}>
            Consorcistas cuyas parcelas catastrales intersectan zonas de riesgo o eventos de inundación.
          </Text>
        </div>
        <Tooltip label="Importar geometrías del catastro IDECOR a PostGIS (necesario la primera vez)">
          <Button
            variant="light"
            color="teal"
            leftSection={<IconUpload size={16} />}
            loading={importing}
            onClick={handleImport}
            size="sm"
          >
            Importar Catastro IDECOR
          </Button>
        </Tooltip>
      </Group>

      <Alert icon={<IconAlertTriangle size={16} />} color="yellow" variant="light">
        Requiere que el catastro IDECOR esté importado en la base de datos. Usá el botón "Importar Catastro IDECOR" la primera vez (proceso único, luego se actualiza automáticamente al re-importar).
      </Alert>

      {/* Tabs */}
      <Tabs defaultValue="zona">
        <Tabs.List>
          <Tabs.Tab value="zona">Por Zona Operativa</Tabs.Tab>
          <Tabs.Tab value="evento">Por Evento de Inundación</Tabs.Tab>
        </Tabs.List>

        {/* ── Tab: Por Zona ── */}
        <Tabs.Panel value="zona" pt="md">
          <Stack gap="md">
            <Group align="flex-end">
              <Select
                label="Zona operativa"
                placeholder="Seleccioná una zona..."
                data={zonas}
                value={selectedZona}
                onChange={setSelectedZona}
                searchable
                clearable
                style={{ flex: 1 }}
              />
              <Button
                leftSection={<IconRefresh size={16} />}
                onClick={handleQueryZona}
                disabled={!selectedZona}
                loading={zonaLoading}
              >
                Consultar
              </Button>
            </Group>

            {zonaLoading && (
              <Group justify="center" py="xl">
                <Loader size="sm" />
                <Text c="dimmed" size="sm">Ejecutando consulta espacial...</Text>
              </Group>
            )}

            {!zonaLoading && zonaResult && (
              <Stack gap="md">
                <SummaryCards
                  totalConsorcistas={zonaResult.total_consorcistas}
                  totalHa={zonaResult.total_ha}
                />
                <Paper withBorder p="md" radius="md">
                  <AfectadosTable data={zonaResult} />
                </Paper>
              </Stack>
            )}
          </Stack>
        </Tabs.Panel>

        {/* ── Tab: Por Evento ── */}
        <Tabs.Panel value="evento" pt="md">
          <Stack gap="md">
            {events.length === 0 && (
              <Text c="dimmed" size="sm">
                No hay eventos de inundación guardados. Crealos en el panel de Calibración.
              </Text>
            )}

            {events.length > 0 && (
              <Group align="flex-end">
                <Select
                  label="Evento de inundación"
                  placeholder="Seleccioná un evento..."
                  data={eventOptions}
                  value={selectedEvent}
                  onChange={setSelectedEvent}
                  searchable
                  clearable
                  style={{ flex: 1 }}
                />
                <Button
                  leftSection={<IconRefresh size={16} />}
                  onClick={handleQueryEvento}
                  disabled={!selectedEvent}
                  loading={eventoLoading}
                >
                  Consultar
                </Button>
              </Group>
            )}

            {eventoLoading && (
              <Group justify="center" py="xl">
                <Loader size="sm" />
                <Text c="dimmed" size="sm">Ejecutando consulta espacial...</Text>
              </Group>
            )}

            {!eventoLoading && eventoResult && (
              <Stack gap="md">
                <SummaryCards
                  totalConsorcistas={eventoResult.total_consorcistas}
                  totalHa={eventoResult.total_ha}
                />

                <Text size="xs" c="dimmed">
                  Evento: {eventoResult.event_date} —{' '}
                  {eventoResult.zonas_afectadas.length} zona{eventoResult.zonas_afectadas.length !== 1 ? 's' : ''} inundada{eventoResult.zonas_afectadas.length !== 1 ? 's' : ''}
                </Text>

                {eventoResult.zonas_afectadas.map((zona) => (
                  <Paper key={zona.zona_id} withBorder p="md" radius="md">
                    <Group justify="space-between" mb="sm">
                      <Text fw={600}>{zona.zona_nombre}</Text>
                      <Group gap="xs">
                        <Badge color="red" variant="light">
                          {zona.total_consorcistas} consorcistas
                        </Badge>
                        <Badge color="orange" variant="light">
                          {zona.total_ha.toLocaleString('es-AR', { maximumFractionDigits: 1 })} ha
                        </Badge>
                      </Group>
                    </Group>
                    <Divider mb="sm" />
                    <AfectadosTable data={zona} />
                  </Paper>
                ))}
              </Stack>
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
