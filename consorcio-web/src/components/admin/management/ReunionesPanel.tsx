import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Container,
  Divider,
  Group,
  Modal,
  MultiSelect,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { useCallback, useEffect, useState } from 'react';
import { API_URL, apiFetch, getAuthToken } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { LoadingState } from '../../ui';
import { IconCalendar, IconLink, IconMessageDots, IconPlus, IconTrash } from '../../ui/icons';

interface Reunion {
  id: string;
  titulo: string;
  fecha_reunion: string;
  lugar: string;
  estado: string;
}

interface AgendaItem {
  id: string;
  titulo: string;
  descripcion: string;
  referencias: Array<{
    entidad_tipo: string;
    entidad_id: string;
    metadata?: {
      label?: string;
      [key: string]: unknown;
    };
  }>;
}

interface EntityOption {
  value: string;
  label: string;
  group: string;
  type: string;
}

export default function ReunionesPanel() {
  const [reuniones, setReuniones] = useState<Reunion[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [selectedReunion, setSelectedReunion] = useState<Reunion | null>(null);
  const [agenda, setAgenda] = useState<AgendaItem[]>([]);

  // Entidades disponibles para referenciar
  const [availableEntities, setAvailableEntities] = useState<EntityOption[]>([]);
  const [loadingEntities, setLoadingEntities] = useState(false);

  const [_opened, { open: _open, close: _close }] = useDisclosure(false);
  const [agendaOpened, { open: openAgenda, close: closeAgenda }] = useDisclosure(false);

  const fetchReuniones = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<Reunion[]>('/management/reuniones');
      setReuniones(data);
    } catch (err) {
      logger.error('Error fetching reuniones:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleExportPDF = async () => {
    if (!selectedReunion) return;
    setExporting(true);
    try {
      const token = await getAuthToken();
      const response = await fetch(
        `${API_URL}/api/v1/management/reuniones/${selectedReunion.id}/export-pdf`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!response.ok) throw new Error('Error al generar PDF');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Agenda_${selectedReunion.titulo.replace(/\s+/g, '_')}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (error) {
      logger.error('Export error:', error);
    } finally {
      setExporting(false);
    }
  };

  const fetchAgenda = async (reunionId: string) => {
    try {
      const data = await apiFetch<AgendaItem[]>(`/management/reuniones/${reunionId}/agenda`);
      setAgenda(data);
    } catch (err) {
      logger.error('Error fetching agenda:', err);
    }
  };

  // Cargar todas las cosas que se pueden "arrobar"
  const fetchReferrables = useCallback(async () => {
    setLoadingEntities(true);
    try {
      const [reports, tramites, assets] = await Promise.all([
        apiFetch<Array<{ id: string; tipo: string; ubicacion_texto?: string }>>(
          '/reports?limit=50'
        ),
        apiFetch<Array<{ id: string; titulo: string; numero_expediente?: string }>>(
          '/management/tramites'
        ),
        apiFetch<Array<{ id: string; nombre: string; tipo: string }>>('/infrastructure/assets'),
      ]);

      const options: EntityOption[] = [
        ...reports.map((r) => ({
          value: r.id,
          label: `${r.tipo.replace('_', ' ')} - ${r.ubicacion_texto || r.id.slice(0, 5)}`,
          group: 'Reportes',
          type: 'reporte',
        })),
        ...tramites.map((t) => ({
          value: t.id,
          label: `${t.titulo} (${t.numero_expediente || 'S/N'})`,
          group: 'Tramites',
          type: 'tramite',
        })),
        ...assets.map((a) => ({
          value: a.id,
          label: `${a.nombre} (${a.tipo})`,
          group: 'Infraestructura',
          type: 'infraestructura',
        })),
      ];
      setAvailableEntities(options);
    } catch (err) {
      logger.error('Error fetching referrables:', err);
    } finally {
      setLoadingEntities(false);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      await fetchReuniones();
      await fetchReferrables();
    };
    loadData();
  }, [fetchReuniones, fetchReferrables]);

  const handleViewAgenda = (reunion: Reunion) => {
    setSelectedReunion(reunion);
    fetchAgenda(reunion.id);
    openAgenda();
  };

  const itemForm = useForm({
    initialValues: {
      titulo: '',
      descripcion: '',
      referencias: [] as string[], // IDs de las entidades seleccionadas
    },
  });

  const handleAddTopic = async (values: typeof itemForm.values) => {
    if (!selectedReunion) return;

    // Preparar payload con metadata para la tabla de referencias
    const selectedRefs = values.referencias.map((id) => {
      const entity = availableEntities.find((e) => e.value === id);
      return {
        entidad_id: id,
        entidad_tipo: entity?.type || 'otro',
        metadata: { label: entity?.label },
      };
    });

    try {
      await apiFetch(`/management/reuniones/${selectedReunion.id}/agenda`, {
        method: 'POST',
        body: JSON.stringify({
          item: {
            titulo: values.titulo,
            descripcion: values.descripcion,
            orden: agenda.length + 1,
          },
          referencias: selectedRefs,
        }),
      });

      itemForm.reset();
      fetchAgenda(selectedReunion.id);
    } catch (err) {
      logger.error('Error adding agenda topic:', err);
    }
  };

  if (loading) return <LoadingState />;

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>Reuniones de Comision</Title>
          <Text c="dimmed">Planificacion de orden del dia y actas</Text>
        </div>
        <Button leftSection={<IconCalendar size={18} />} onClick={_open} color="violet">
          Nueva Reunion
        </Button>
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
        {reuniones.map((r) => (
          <Card key={r.id} shadow="sm" padding="lg" radius="md" withBorder>
            <Group justify="space-between" mb="xs">
              <Badge color={r.estado === 'planificada' ? 'blue' : 'green'} variant="light">
                {r.estado.toUpperCase()}
              </Badge>
              <Text size="xs" c="dimmed">
                {new Date(r.fecha_reunion).toLocaleDateString()}
              </Text>
            </Group>

            <Text fw={700} mb="xs">
              {r.titulo}
            </Text>
            <Text size="sm" c="dimmed" mb="md">
              Lugar: {r.lugar}
            </Text>

            <Button
              fullWidth
              variant="light"
              color="violet"
              onClick={() => handleViewAgenda(r)}
              leftSection={<IconMessageDots size={16} />}
            >
              Gestionar Agenda
            </Button>
          </Card>
        ))}
      </SimpleGrid>

      {/* Modal Agenda / Orden del Dia */}
      <Modal opened={agendaOpened} onClose={closeAgenda} title="Orden del Dia" size="xl">
        {selectedReunion && (
          <Stack gap="md">
            <Group justify="space-between">
              <div>
                <Text fw={700} size="lg">
                  {selectedReunion.titulo}
                </Text>
                <Text size="sm" c="dimmed">
                  {new Date(selectedReunion.fecha_reunion).toLocaleString()}
                </Text>
              </div>
              <Button size="xs" variant="outline" onClick={handleExportPDF} loading={exporting}>
                Exportar PDF
              </Button>
            </Group>

            <Divider label="Temas a Tratar" labelPosition="center" />

            {agenda.length === 0 ? (
              <Paper p="xl" withBorder style={{ borderStyle: 'dashed' }}>
                <Text ta="center" c="dimmed">
                  No hay temas en la agenda todavia.
                </Text>
              </Paper>
            ) : (
              <Stack gap="sm">
                {agenda.map((item, index) => (
                  <Paper key={item.id} p="md" withBorder radius="md">
                    <Group justify="space-between" align="flex-start">
                      <div style={{ flex: 1 }}>
                        <Text fw={600}>
                          {index + 1}. {item.titulo}
                        </Text>
                        <Text size="sm" c="dimmed" mb="xs">
                          {item.descripcion}
                        </Text>

                        {/* Referencias (Los @arrobados) */}
                        {item.referencias && item.referencias.length > 0 && (
                          <Group gap="xs" mt="xs">
                            {item.referencias.map((ref, i) => (
                              <Badge
                                key={i}
                                size="xs"
                                variant="outline"
                                color={
                                  ref.entidad_tipo === 'reporte'
                                    ? 'red'
                                    : ref.entidad_tipo === 'tramite'
                                      ? 'blue'
                                      : ref.entidad_tipo === 'infraestructura'
                                        ? 'green'
                                        : 'gray'
                                }
                                leftSection={<IconLink size={10} />}
                              >
                                {ref.metadata?.label ||
                                  `${ref.entidad_tipo.toUpperCase()} #${ref.entidad_id.slice(0, 5)}`}
                              </Badge>
                            ))}
                          </Group>
                        )}
                      </div>
                      <ActionIcon color="red" variant="subtle">
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            )}

            <Paper p="md" bg="gray.0" radius="md">
              <Text fw={600} size="sm" mb="sm">
                Agregar Tema a la Agenda
              </Text>
              <form onSubmit={itemForm.onSubmit(handleAddTopic)}>
                <Stack gap="xs">
                  <TextInput
                    placeholder="Titulo del tema (Ej: Reparacion Puente FFCC)"
                    size="sm"
                    required
                    {...itemForm.getInputProps('titulo')}
                  />
                  <Textarea
                    placeholder="Descripcion o puntos a discutir..."
                    size="sm"
                    {...itemForm.getInputProps('descripcion')}
                  />

                  {/* Selector de Referencias Cruzadas */}
                  <MultiSelect
                    label="Vincular con (@)"
                    placeholder="Escribe para buscar reportes, tramites o activos..."
                    data={availableEntities}
                    searchable
                    nothingFoundMessage="No se encontro nada..."
                    clearable
                    size="sm"
                    {...itemForm.getInputProps('referencias')}
                  />

                  <Group justify="flex-end" mt="xs">
                    <Button
                      type="submit"
                      size="xs"
                      leftSection={<IconPlus size={14} />}
                      loading={loadingEntities}
                    >
                      Anadir Tema
                    </Button>
                  </Group>
                </Stack>
              </form>
            </Paper>
          </Stack>
        )}
      </Modal>
    </Container>
  );
}
