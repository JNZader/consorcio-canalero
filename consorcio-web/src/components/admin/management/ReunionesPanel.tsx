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
import { notifications } from '@mantine/notifications';
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
  descripcion?: string;
  orden_del_dia_items?: string[];
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

function normalizeArrayResponse<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) {
    return payload as T[];
  }

  if (payload && typeof payload === 'object') {
    const wrapped = payload as Record<string, unknown>;
    const arrayLike = wrapped.items ?? wrapped.data ?? wrapped.results;

    if (Array.isArray(arrayLike)) {
      return arrayLike as T[];
    }
  }

  return [];
}

export default function ReunionesPanel() {
  const [reuniones, setReuniones] = useState<Reunion[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [selectedReunion, setSelectedReunion] = useState<Reunion | null>(null);
  const [agenda, setAgenda] = useState<AgendaItem[]>([]);
  const [newChecklistPoint, setNewChecklistPoint] = useState('');

  // Entidades disponibles para referenciar
  const [availableEntities, setAvailableEntities] = useState<EntityOption[]>([]);
  const [loadingEntities, setLoadingEntities] = useState(false);

  const [createOpened, { open: openCreate, close: closeCreate }] = useDisclosure(false);
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
        `${API_URL}/api/v2/management/reuniones/${selectedReunion.id}/export-pdf`,
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
      const [reportsRaw, tramitesRaw, assetsRaw] = await Promise.all([
        apiFetch<unknown>('/reports?limit=50'),
        apiFetch<unknown>('/management/tramites'),
        apiFetch<unknown>('/infrastructure/assets'),
      ]);

      const reports = normalizeArrayResponse<{
        id: string;
        tipo: string;
        ubicacion_texto?: string;
      }>(reportsRaw);
      const tramites = normalizeArrayResponse<{
        id: string;
        titulo: string;
        numero_expediente?: string;
      }>(tramitesRaw);
      const assets = normalizeArrayResponse<{ id: string; nombre: string; tipo: string }>(
        assetsRaw
      );

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

  const reunionForm = useForm({
    initialValues: {
      titulo: '',
      fecha_reunion: '',
      lugar: '',
      descripcion: '',
      orden_del_dia_items: [''],
      tipo: 'ordinaria',
    },
    validate: {
      titulo: (value) => (value.trim().length < 3 ? 'Titulo requerido' : null),
      fecha_reunion: (value) => (!value ? 'Fecha y hora requeridas' : null),
      orden_del_dia_items: (value) =>
        value.some((item) => item.trim().length > 0)
          ? null
          : 'Agrega al menos un punto al orden del dia',
    },
  });

  const handleCreateReunion = async (values: typeof reunionForm.values) => {
    try {
      const ordenDelDiaItems = values.orden_del_dia_items
        .map((item) => item.trim())
        .filter((item) => item.length > 0);

      const payload = {
        ...values,
        orden_del_dia_items: ordenDelDiaItems,
        fecha_reunion: new Date(values.fecha_reunion).toISOString(),
      };

      await apiFetch('/management/reuniones', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      notifications.show({
        title: 'Reunion creada',
        message: 'La reunion fue registrada correctamente',
        color: 'green',
      });

      reunionForm.reset();
      setNewChecklistPoint('');
      closeCreate();
      await fetchReuniones();
    } catch (err) {
      logger.error('Error creating reunion:', err);
      notifications.show({
        title: 'No se pudo crear la reunion',
        message: 'Revisa los datos e intenta nuevamente',
        color: 'red',
      });
    }
  };

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
        <Button leftSection={<IconCalendar size={18} />} onClick={openCreate} color="violet">
          Nueva Reunion
        </Button>
      </Group>

      <Modal opened={createOpened} onClose={closeCreate} title="Nueva Reunion" size="lg">
        <form onSubmit={reunionForm.onSubmit(handleCreateReunion)}>
          <Stack gap="sm">
            <TextInput
              label="Titulo"
              placeholder="Ej: Reunion de comision de marzo"
              required
              {...reunionForm.getInputProps('titulo')}
            />
            <TextInput
              type="datetime-local"
              label="Fecha y hora"
              required
              {...reunionForm.getInputProps('fecha_reunion')}
            />
            <TextInput
              label="Lugar"
              placeholder="Ej: Sede del consorcio"
              {...reunionForm.getInputProps('lugar')}
            />
            <Textarea
              label="Descripcion"
              placeholder="Temas generales a tratar"
              autosize
              minRows={2}
              {...reunionForm.getInputProps('descripcion')}
            />
            <Stack gap="xs">
              <Text fw={500} size="sm">
                Orden del dia (checklist)
              </Text>

              <Group align="flex-end" gap="xs">
                <TextInput
                  value={newChecklistPoint}
                  onChange={(event) => setNewChecklistPoint(event.currentTarget.value)}
                  placeholder="Escribe un punto y pulsa Anadir"
                  style={{ flex: 1 }}
                />
                <Button
                  type="button"
                  variant="light"
                  onClick={() => {
                    const newPoint = newChecklistPoint.trim();
                    if (!newPoint) return;

                    reunionForm.insertListItem('orden_del_dia_items', newPoint);
                    setNewChecklistPoint('');
                  }}
                >
                  Anadir punto
                </Button>
              </Group>

              <Stack gap="xs">
                {reunionForm.values.orden_del_dia_items.map((point, index) => (
                  <Group key={`orden-${index}`} align="flex-start" gap="xs">
                    <Text size="sm" mt={8}>
                      {index + 1}.
                    </Text>
                    <TextInput
                      value={point}
                      onChange={(event) =>
                        reunionForm.setFieldValue(
                          `orden_del_dia_items.${index}`,
                          event.currentTarget.value
                        )
                      }
                      placeholder={`Punto ${index + 1}`}
                      style={{ flex: 1 }}
                    />
                    <ActionIcon
                      type="button"
                      color="red"
                      variant="subtle"
                      onClick={() => reunionForm.removeListItem('orden_del_dia_items', index)}
                      aria-label={`Eliminar punto ${index + 1}`}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                ))}
              </Stack>

              {reunionForm.errors.orden_del_dia_items ? (
                <Text size="xs" c="red">
                  {reunionForm.errors.orden_del_dia_items}
                </Text>
              ) : null}
            </Stack>
            <Button type="submit" mt="xs">
              Crear Reunion
            </Button>
          </Stack>
        </form>
      </Modal>

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
            {r.orden_del_dia_items && r.orden_del_dia_items.length > 0 ? (
              <ol style={{ margin: 0, paddingLeft: 18, marginBottom: 16 }}>
                {r.orden_del_dia_items.map((item, index) => (
                  <li key={`${r.id}-orden-${index}`}>
                    <Text size="sm">{item}</Text>
                  </li>
                ))}
              </ol>
            ) : null}

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
                {selectedReunion.descripcion ? (
                  <Text size="sm" c="dimmed">
                    {selectedReunion.descripcion}
                  </Text>
                ) : null}
                {selectedReunion.orden_del_dia_items &&
                selectedReunion.orden_del_dia_items.length > 0 ? (
                  <ol style={{ margin: 0, paddingLeft: 18 }}>
                    {selectedReunion.orden_del_dia_items.map((item, index) => (
                      <li key={`${selectedReunion.id}-detalle-orden-${index}`}>
                        <Text size="sm">{item}</Text>
                      </li>
                    ))}
                  </ol>
                ) : null}
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
