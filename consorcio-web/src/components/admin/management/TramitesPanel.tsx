import { 
  Badge, 
  Button, 
  Card, 
  Container, 
  Group, 
  Stack, 
  Table, 
  Text, 
  Title, 
  Timeline,
  Paper,
  ActionIcon,
  Modal,
  TextInput,
  Textarea,
  Select
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { useEffect, useState } from 'react';
import { apiFetch, API_URL, getAuthToken } from '../../../lib/api';
import { IconPlus, IconExternalLink, IconHistory, IconDownload } from '../../ui/icons';
import { LoadingState } from '../../ui';

interface Tramite {
  id: string;
  titulo: string;
  numero_expediente: string;
  estado: string;
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
  const [selectedTramite, setSelectedTramite] = useState<(Tramite & { avances: Avance[] }) | null>(null);
  const [opened, { open, close }] = useDisclosure(false);
  const [historyOpened, { open: openHistory, close: closeHistory }] = useDisclosure(false);

  const fetchTramites = async () => {
    setLoading(true);
    try {
      const data = await apiFetch<Tramite[]>('/management/tramites');
      setTramites(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (id: string) => {
    setExporting(true);
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/api/v1/management/tramites/${id}/export-pdf`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Resumen_Expediente_${id.slice(0,8)}.pdf`;
      a.click();
    } catch (err) {
      console.error(err);
    } finally {
      setExporting(false);
    }
  };

  const fetchDetalle = async (id: string) => {
    try {
      const data = await apiFetch<Tramite & { avances: Avance[] }>(`/management/tramites/${id}`);
      setSelectedTramite(data);
      openHistory();
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchTramites();
  }, []);

  const form = useForm({
    initialValues: {
      titulo: '',
      numero_expediente: '',
      descripcion: '',
      prioridad: 'normal'
    }
  });

  const handleCreate = async (values: typeof form.values) => {
    try {
      await apiFetch('/management/tramites', {
        method: 'POST',
        body: JSON.stringify(values)
      });
      close();
      fetchTramites();
      form.reset();
    } catch (err) {
      console.error(err);
    }
  };

  if (loading) return <LoadingState />;

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>Gestión de Expedientes</Title>
          <Text c="dimmed">Seguimiento de trámites en Recursos Hídricos de la Provincia</Text>
        </div>
        <Button leftSection={<IconPlus size={18} />} onClick={open}>
          Nuevo Expediente
        </Button>
      </Group>

      <Paper withBorder radius="md">
        <Table verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Título / Expediente</Table.Th>
              <Table.Th>Estado</Table.Th>
              <Table.Th>Última Actualización</Table.Th>
              <Table.Th>Acciones</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {tramites.map((t) => (
              <Table.Tr key={t.id}>
                <Table.Td>
                  <Stack gap={0}>
                    <Text fw={500} size="sm">{t.titulo}</Text>
                    <Text size="xs" c="dimmed">Nro: {t.numero_expediente || 'S/N'}</Text>
                  </Stack>
                </Table.Td>
                <Table.Td>
                  <Badge variant="light">{t.estado.replace('_', ' ').toUpperCase()}</Badge>
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
            <TextInput label="Título del Trámite" placeholder="Ej: Obra Canal San Marcos" required {...form.getInputProps('titulo')} />
            <TextInput label="Número de Expediente" placeholder="Ej: 0416-00123/2026" {...form.getInputProps('numero_expediente')} />
            <Textarea label="Descripción Inicial" placeholder="Objetivo del trámite..." {...form.getInputProps('descripcion')} />
            <Select 
              label="Prioridad" 
              data={['baja', 'normal', 'alta', 'urgente']} 
              {...form.getInputProps('prioridad')} 
            />
            <Button type="submit" fullWidth mt="md">Crear Expediente</Button>
          </Stack>
        </form>
      </Modal>

      {/* Modal Historial de Avances */}
      <Modal opened={historyOpened} onClose={closeHistory} title="Línea de Tiempo del Expediente" size="lg">
        {selectedTramite && (
          <Stack gap="md">
            <Group justify="space-between">
              <div>
                <Text fw={700} size="lg">{selectedTramite.titulo}</Text>
                <Text size="sm" c="dimmed">Expediente: {selectedTramite.numero_expediente}</Text>
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
            <Timeline active={0} bulletSize={24} lineWidth={2}>
              {selectedTramite.avances.map((a) => (
                <Timeline.Item key={a.id} title={a.titulo_avance}>
                  <Text c="dimmed" size="sm">{a.comentario}</Text>
                  <Text size="xs" mt={4}>{new Date(a.fecha).toLocaleString()}</Text>
                </Timeline.Item>
              ))}
              <Timeline.Item title="Inicio de Trámite" bulletSize={12}>
                <Text size="xs" mt={4}>Expediente creado en el sistema</Text>
              </Timeline.Item>
            </Timeline>
            <Button variant="light" fullWidth>Agregar Nuevo Avance</Button>
          </Stack>
        )}
      </Modal>
    </Container>
  );
}
