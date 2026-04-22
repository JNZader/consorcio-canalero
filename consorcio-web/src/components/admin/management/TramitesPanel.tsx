import {
  ActionIcon,
  Badge,
  Button,
  Container,
  Divider,
  Group,
  Modal,
  Paper,
  Select,
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
import { useCallback, useEffect, useState } from 'react';
import { type TramiteEstadoCanonico, formatTramiteEstado } from '../../../constants/tramites';
import { API_URL, apiFetch, getAuthToken } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { LoadingState } from '../../ui/LoadingState';
import { IconDownload, IconExternalLink, IconHistory, IconPlus } from '../../ui/icons';
import { type RawTramiteItem, filterCanonicalTramites } from './tramitesCanonical';

interface Tramite {
  id: string;
  titulo: string;
  numero_expediente: string;
  estado: TramiteEstadoCanonico;
  ultima_actualizacion: string;
}

interface Avance {
  id: string;
  fecha: string;
  titulo_avance: string;
  comentario: string;
}

export default function TramitesPanel() {
  const [tramites, setTramites] = useState<Tramite[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [selectedTramite, setSelectedTramite] = useState<(Tramite & { avances: Avance[] }) | null>(
    null
  );
  const [opened, { open, close }] = useDisclosure(false);
  const [historyOpened, { open: openHistory, close: closeHistory }] = useDisclosure(false);

  const fetchTramites = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch<{ items: RawTramiteItem[]; total: number }>('/tramites');
      const data = response.items ?? [];
      const { canonical, discarded } = filterCanonicalTramites(data);

      for (const tramite of discarded) {
        logger.warn('Discarding tramite with non-canonical state', {
          tramiteId: tramite.id,
          estado: tramite.estado,
        });
      }

      setTramites(canonical as Tramite[]);
    } catch (err) {
      logger.error('Error fetching tramites:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleExport = async (id: string) => {
    setExporting(true);
    try {
      const token = await getAuthToken();
      // TODO: v2 does not have a dedicated tramite export-pdf endpoint yet
      const response = await fetch(`${API_URL}/api/v2/tramites/${id}/export-pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Resumen_Expediente_${id.slice(0, 8)}.pdf`;
      a.click();
    } catch (err) {
      logger.error('Error exporting tramite:', err);
    } finally {
      setExporting(false);
    }
  };

  const fetchDetalle = async (id: string) => {
    try {
      const data = await apiFetch<Tramite & { avances: Avance[] }>(`/tramites/${id}`);
      setSelectedTramite(data);
      openHistory();
    } catch (err) {
      logger.error('Error fetching tramite detail:', err);
    }
  };

  useEffect(() => {
    fetchTramites();
  }, [fetchTramites]);

  const form = useForm({
    initialValues: {
      titulo: '',
      numero_expediente: '',
      descripcion: '',
      prioridad: 'normal',
    },
  });

  const handleCreate = async (values: typeof form.values) => {
    try {
      await apiFetch('/tramites', {
        method: 'POST',
        body: JSON.stringify(values),
      });
      close();
      fetchTramites();
      form.reset();
    } catch (err) {
      logger.error('Error creating tramite:', err);
    }
  };

  if (loading) return <LoadingState />;

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>Gestion de Expedientes</Title>
          <Text c="dimmed">Seguimiento de tramites en Recursos Hidricos de la Provincia</Text>
        </div>
        <Button leftSection={<IconPlus size={18} />} onClick={open}>
          Nuevo Expediente
        </Button>
      </Group>

      <Paper withBorder radius="md">
        <Table verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Titulo / Expediente</Table.Th>
              <Table.Th>Estado</Table.Th>
              <Table.Th>Ultima Actualizacion</Table.Th>
              <Table.Th>Acciones</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {tramites.map((t) => (
              <Table.Tr key={t.id}>
                <Table.Td>
                  <Stack gap={0}>
                    <Text fw={500} size="sm">
                      {t.titulo}
                    </Text>
                    <Text size="xs" c="dimmed">
                      Nro: {t.numero_expediente || 'S/N'}
                    </Text>
                  </Stack>
                </Table.Td>
                <Table.Td>
                  <Badge variant="light">{formatTramiteEstado(t.estado)}</Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{new Date(t.ultima_actualizacion).toLocaleDateString()}</Text>
                </Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <ActionIcon variant="light" color="blue" onClick={() => fetchDetalle(t.id)}>
                      <IconHistory size={16} />
                    </ActionIcon>
                    <ActionIcon variant="light" color="gray">
                      <IconExternalLink size={16} />
                    </ActionIcon>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>

      {/* Modal Nuevo Expediente */}
      <Modal opened={opened} onClose={close} title="Registrar Nuevo Expediente Provincial">
        <form onSubmit={form.onSubmit(handleCreate)}>
          <Stack gap="sm">
            <TextInput
              label="Titulo del Tramite"
              placeholder="Ej: Obra Canal San Marcos"
              required
              {...form.getInputProps('titulo')}
            />
            <TextInput
              label="Numero de Expediente"
              placeholder="Ej: 0416-00123/2026"
              {...form.getInputProps('numero_expediente')}
            />
            <Textarea
              label="Descripcion Inicial"
              placeholder="Objetivo del tramite..."
              {...form.getInputProps('descripcion')}
            />
            <Select
              label="Prioridad"
              data={['baja', 'normal', 'alta', 'urgente']}
              {...form.getInputProps('prioridad')}
            />
            <Button type="submit" fullWidth mt="md">
              Crear Expediente
            </Button>
          </Stack>
        </form>
      </Modal>

      {/* Modal Historial de Avances */}
      <Modal
        opened={historyOpened}
        onClose={closeHistory}
        title="Linea de Tiempo del Expediente"
        size="lg"
      >
        {selectedTramite && (
          <Stack gap="md">
            <Group justify="space-between">
              <div>
                <Text fw={700} size="lg">
                  {selectedTramite.titulo}
                </Text>
                <Text size="sm" c="dimmed">
                  Expediente: {selectedTramite.numero_expediente}
                </Text>
              </div>
              <Button
                size="xs"
                variant="outline"
                leftSection={<IconDownload size={14} />}
                onClick={() => handleExport(selectedTramite.id)}
                loading={exporting}
              >
                Exportar Resumen
              </Button>
            </Group>
            <Divider />
            <Timeline active={0} lineWidth={2}>
              {selectedTramite.avances.map((a) => (
                <Timeline.Item key={a.id} title={a.titulo_avance}>
                  <Text c="dimmed" size="sm">
                    {a.comentario}
                  </Text>
                  <Text size="xs" mt={4}>
                    {new Date(a.fecha).toLocaleString()}
                  </Text>
                </Timeline.Item>
              ))}
              <Timeline.Item title="Inicio de Tramite">
                <Text size="xs" mt={4}>
                  Expediente creado en el sistema
                </Text>
              </Timeline.Item>
            </Timeline>
            <Button variant="light" fullWidth>
              Agregar Nuevo Avance
            </Button>
          </Stack>
        )}
      </Modal>
    </Container>
  );
}
