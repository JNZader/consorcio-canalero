import {
  ActionIcon,
  Badge,
  Button,
  Container,
  Group,
  Modal,
  NativeSelect,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Timeline,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { type TramiteEstadoCanonico, formatTramiteEstado } from '../../../constants/tramites';
import { API_URL, apiFetch, getAuthToken } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { LoadingState } from '../../ui/LoadingState';
import { IconDownload, IconHistory, IconPlus } from '../../ui/icons';

interface TramiteListItem {
  id: string;
  tipo: string;
  titulo: string;
  solicitante: string;
  estado: TramiteEstadoCanonico;
  prioridad: string;
  fecha_ingreso: string;
  fecha_resolucion: string | null;
  created_at: string;
}

interface Seguimiento {
  id: string;
  tramite_id: string;
  estado_anterior: string;
  estado_nuevo: string;
  comentario: string;
  usuario_id: string;
  created_at: string;
}

interface TramiteDetail extends TramiteListItem {
  descripcion: string;
  resolucion: string | null;
  usuario_id: string;
  updated_at: string;
  seguimiento: Seguimiento[];
}

interface TramiteFormValues {
  tipo: string;
  titulo: string;
  descripcion: string;
  solicitante: string;
  prioridad: string;
  fecha_ingreso: string;
}

const TRAMITE_TYPES = ['obra', 'permiso', 'habilitacion', 'reclamo', 'otro'];
const TRAMITE_PRIORITIES = ['baja', 'media', 'alta', 'urgente'];

function formatDate(value: string) {
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

export default function TramitesPanel() {
  const [tramites, setTramites] = useState<TramiteListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTramite, setSelectedTramite] = useState<TramiteDetail | null>(null);
  const [newSeguimiento, setNewSeguimiento] = useState('');
  const [addingSeguimiento, setAddingSeguimiento] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [opened, { open, close }] = useDisclosure(false);
  const [historyOpened, { open: openHistory, close: closeHistory }] = useDisclosure(false);

  const fetchTramites = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch<{ items: TramiteListItem[]; total: number }>('/tramites');
      setTramites(response.items ?? []);
    } catch (err) {
      logger.error('Error fetching tramites:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchDetalle = async (id: string) => {
    try {
      const detail = await apiFetch<TramiteDetail>(`/tramites/${id}`);
      setSelectedTramite({ ...detail, seguimiento: detail.seguimiento ?? [] });
      setNewSeguimiento('');
      openHistory();
    } catch (err) {
      logger.error('Error fetching tramite detail:', err);
    }
  };

  useEffect(() => {
    fetchTramites();
  }, [fetchTramites]);

  const form = useForm<TramiteFormValues>({
    initialValues: {
      tipo: '',
      titulo: '',
      descripcion: '',
      solicitante: '',
      prioridad: 'media',
      fecha_ingreso: '',
    },
    validate: {
      tipo: (value) => (value ? null : 'Tipo requerido'),
      titulo: (value) =>
        value.trim().length < 5 ? 'El titulo debe tener al menos 5 caracteres' : null,
      descripcion: (value) =>
        value.trim().length < 10 ? 'La descripcion debe tener al menos 10 caracteres' : null,
      solicitante: (value) =>
        value.trim().length < 2 ? 'El solicitante debe tener al menos 2 caracteres' : null,
    },
  });

  const handleCreate = async (values: TramiteFormValues) => {
    try {
      await apiFetch('/tramites', {
        method: 'POST',
        body: JSON.stringify({
          tipo: values.tipo,
          titulo: values.titulo.trim(),
          descripcion: values.descripcion.trim(),
          solicitante: values.solicitante.trim(),
          prioridad: values.prioridad,
          ...(values.fecha_ingreso ? { fecha_ingreso: values.fecha_ingreso } : {}),
        }),
      });
      close();
      form.reset();
      await fetchTramites();
    } catch (err) {
      logger.error('Error creating tramite:', err);
    }
  };

  const handleAddSeguimiento = async () => {
    if (!selectedTramite || newSeguimiento.trim().length < 5) return;

    setAddingSeguimiento(true);
    try {
      const seguimiento = await apiFetch<Seguimiento>(
        `/tramites/${selectedTramite.id}/seguimiento`,
        {
          method: 'POST',
          body: JSON.stringify({ comentario: newSeguimiento.trim() }),
        }
      );
      setSelectedTramite((current) =>
        current ? { ...current, seguimiento: [seguimiento, ...current.seguimiento] } : current
      );
      setNewSeguimiento('');
    } catch (err) {
      logger.error('Error adding tramite follow-up:', err);
    } finally {
      setAddingSeguimiento(false);
    }
  };

  const handleCloseHistory = () => {
    setSelectedTramite(null);
    setNewSeguimiento('');
    closeHistory();
  };

  const handleDownloadPdf = async () => {
    if (!selectedTramite) return;

    setDownloadingPdf(true);
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/api/v2/tramites/${selectedTramite.id}/export-pdf`, {
        headers: {
          Accept: 'application/pdf',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!response.ok) {
        throw new Error(`Error al descargar el tramite (${response.status})`);
      }

      const contentType = response.headers.get('content-type') ?? '';
      if (!contentType.includes('application/pdf')) {
        throw new Error('El servidor no devolvio un documento PDF');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `tramite-${selectedTramite.id}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);

      notifications.show({
        title: 'PDF descargado',
        message: `Se descargo el expediente de ${selectedTramite.titulo}`,
        color: 'green',
      });
    } catch (error) {
      logger.error('Error downloading tramite PDF:', error);
      notifications.show({
        title: 'No se pudo descargar el tramite',
        message: error instanceof Error ? error.message : 'Intenta nuevamente en unos minutos.',
        color: 'red',
      });
    } finally {
      setDownloadingPdf(false);
    }
  };

  if (loading) return <LoadingState />;

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>Gestion de Tramites</Title>
          <Text c="dimmed">Seguimiento de tramites del Consorcio Canalero</Text>
        </div>
        <Button leftSection={<IconPlus size={18} />} onClick={open}>
          Nuevo Tramite
        </Button>
      </Group>

      <Paper withBorder radius="md">
        <Table.ScrollContainer minWidth={680} type="native">
          <Table verticalSpacing="sm" aria-label="Tabla de tramites">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Tramite</Table.Th>
                <Table.Th>Estado</Table.Th>
                <Table.Th>Prioridad</Table.Th>
                <Table.Th>Fecha de ingreso</Table.Th>
                <Table.Th>Acciones</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {tramites.map((tramite) => (
                <Table.Tr key={tramite.id}>
                  <Table.Td>
                    <Stack gap={0}>
                      <Text fw={500} size="sm">
                        {tramite.titulo}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {tramite.tipo} · {tramite.solicitante}
                      </Text>
                    </Stack>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="light">{formatTramiteEstado(tramite.estado)}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{tramite.prioridad}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{formatDate(tramite.fecha_ingreso)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <ActionIcon
                      variant="light"
                      color="blue"
                      onClick={() => fetchDetalle(tramite.id)}
                      aria-label={`Ver seguimiento de ${tramite.titulo}`}
                    >
                      <IconHistory size={16} />
                    </ActionIcon>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>

      <Modal opened={opened} onClose={close} title="Registrar Nuevo Tramite">
        <form onSubmit={form.onSubmit(handleCreate)} noValidate>
          <Stack gap="sm">
            <NativeSelect
              label="Tipo"
              data={TRAMITE_TYPES}
              required
              {...form.getInputProps('tipo')}
            />
            <TextInput label="Titulo del Tramite" required {...form.getInputProps('titulo')} />
            <Textarea label="Descripcion" required {...form.getInputProps('descripcion')} />
            <TextInput label="Solicitante" required {...form.getInputProps('solicitante')} />
            <NativeSelect
              label="Prioridad"
              data={TRAMITE_PRIORITIES}
              required
              {...form.getInputProps('prioridad')}
            />
            <TextInput
              type="date"
              label="Fecha de ingreso"
              {...form.getInputProps('fecha_ingreso')}
            />
            <Button type="submit" fullWidth mt="md">
              Crear Tramite
            </Button>
          </Stack>
        </form>
      </Modal>

      <Modal
        opened={historyOpened}
        onClose={handleCloseHistory}
        title="Seguimiento del Tramite"
        size="lg"
      >
        {selectedTramite && (
          <Stack gap="md">
            <div>
              <Text fw={700} size="lg">
                {selectedTramite.titulo}
              </Text>
              <Text size="sm" c="dimmed">
                {selectedTramite.tipo} · {selectedTramite.solicitante}
              </Text>
            </div>

            <Button
              variant="outline"
              leftSection={<IconDownload size={16} />}
              onClick={handleDownloadPdf}
              loading={downloadingPdf}
            >
              Descargar PDF
            </Button>

            {selectedTramite.seguimiento.length > 0 ? (
              <Timeline active={selectedTramite.seguimiento.length} lineWidth={2}>
                {selectedTramite.seguimiento.map((item) => (
                  <Timeline.Item
                    key={item.id}
                    title={`${formatTramiteEstado(item.estado_anterior as TramiteEstadoCanonico)} → ${formatTramiteEstado(item.estado_nuevo as TramiteEstadoCanonico)}`}
                  >
                    <Text c="dimmed" size="sm">
                      {item.comentario}
                    </Text>
                    <Text size="xs" mt={4}>
                      {new Date(item.created_at).toLocaleString()}
                    </Text>
                  </Timeline.Item>
                ))}
              </Timeline>
            ) : (
              <Text c="dimmed" size="sm">
                Este tramite todavia no tiene entradas de seguimiento.
              </Text>
            )}

            <Textarea
              label="Nuevo seguimiento"
              value={newSeguimiento}
              onChange={(event) => setNewSeguimiento(event.currentTarget.value)}
              minRows={3}
            />
            <Button
              variant="light"
              fullWidth
              onClick={handleAddSeguimiento}
              loading={addingSeguimiento}
              disabled={newSeguimiento.trim().length < 5}
            >
              Agregar Seguimiento
            </Button>
          </Stack>
        )}
      </Modal>
    </Container>
  );
}
