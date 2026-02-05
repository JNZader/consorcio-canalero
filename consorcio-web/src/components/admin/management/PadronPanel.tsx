import {
  Badge,
  Box,
  Button,
  Card,
  Container,
  Divider,
  Group,
  Stack,
  Table,
  Text,
  Title,
  Paper,
  ActionIcon,
  Modal,
  TextInput,
  Textarea,
  Select,
  NumberInput,
  SimpleGrid,
  Tooltip
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/api';
import { handleError } from '../../../lib/errorHandler';
import { isValidCUIT } from '../../../lib/validators';
import { IconPlus, IconSearch, IconUser, IconCreditCard, IconHistory } from '../../ui/icons';
import { LoadingState } from '../../ui';

// Types for this panel
interface Consorcista {
  id: string;
  nombre: string;
  apellido: string;
  cuit: string;
  representa_a?: string;
  email?: string;
  telefono?: string;
}

interface Pago {
  id: string;
  anio: number;
  monto: number;
  estado: 'pagado' | 'pendiente';
  fecha_pago?: string;
}

export default function PadronPanel() {
  const [consorcistas, setConsorcistas] = useState<Consorcista[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  
  const [selectedConsorcista, setSelectedConsorcista] = useState<Consorcista | null>(null);
  const [pagos, setPagos] = useState<Pago[]>([]);
  
  const [opened, { open, close }] = useDisclosure(false);
  const [pagoOpened, { open: openPago, close: closePago }] = useDisclosure(false);

  const fetchConsorcistas = async () => {
    setLoading(true);
    try {
      const data = await apiFetch<Consorcista[]>(`/padron/consorcistas?search=${search}`);
      setConsorcistas(data);
    } catch (err) {
      handleError(err, {
        title: 'Error al cargar consorcistas',
        context: 'PadronPanel.fetchConsorcistas',
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchPagos = async (id: string) => {
    try {
      const data = await apiFetch<Pago[]>(`/padron/consorcistas/${id}/pagos`);
      setPagos(data);
    } catch (err) {
      handleError(err, {
        title: 'Error al cargar pagos',
        context: 'PadronPanel.fetchPagos',
      });
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => fetchConsorcistas(), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const handleViewPagos = (c: Consorcista) => {
    setSelectedConsorcista(c);
    fetchPagos(c.id);
    openPago();
  };

  const form = useForm({
    initialValues: {
      nombre: '',
      apellido: '',
      cuit: '',
      representa_a: '',
      email: '',
      telefono: ''
    },
    validate: {
      cuit: (value) => (!isValidCUIT(value) ? 'CUIT invalido' : null),
      nombre: (value) => (value.length < 2 ? 'Nombre requerido' : null),
      apellido: (value) => (value.length < 2 ? 'Apellido requerido' : null),
    }
  });

  const handleCreate = async (values: typeof form.values) => {
    try {
      await apiFetch('/padron/consorcistas', {
        method: 'POST',
        body: JSON.stringify(values)
      });
      notifications.show({
        title: 'Consorcista registrado',
        message: `${values.apellido}, ${values.nombre} fue agregado al padron`,
        color: 'green',
      });
      close();
      fetchConsorcistas();
      form.reset();
    } catch (err) {
      handleError(err, {
        title: 'Error al crear consorcista',
        context: 'PadronPanel.handleCreate',
      });
    }
  };

  if (loading && consorcistas.length === 0) return <LoadingState />;

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>Padrón de Consorcistas</Title>
          <Text c="dimmed">Administración de socios y recaudación de cuotas anuales</Text>
        </div>
        <Button leftSection={<IconPlus size={18} />} onClick={open} color="blue">
          Nuevo Consorcista
        </Button>
      </Group>

      <Paper shadow="sm" p="md" radius="md" mb="md">
        <TextInput 
          placeholder="Buscar por Nombre, Apellido o CUIT..." 
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </Paper>

      <Paper withBorder radius="md">
        <Table verticalSpacing="sm" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Consorcista</Table.Th>
              <Table.Th>CUIT</Table.Th>
              <Table.Th>Representación</Table.Th>
              <Table.Th>Acciones</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {consorcistas.map((c) => (
              <Table.Tr key={c.id}>
                <Table.Td>
                  <Group gap="sm">
                    <IconUser size={16} color="gray" />
                    <Text fw={500} size="sm">{c.apellido}, {c.nombre}</Text>
                  </Group>
                </Table.Td>
                <Table.Td><Text size="sm">{c.cuit}</Text></Table.Td>
                <Table.Td>
                  <Text size="sm" italic c="dimmed">{c.representa_a || '-'}</Text>
                </Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <Tooltip label="Ver Pagos / Cuotas">
                      <ActionIcon variant="light" color="green" onClick={() => handleViewPagos(c)}>
                        <IconCreditCard size={16} />
                      </ActionIcon>
                    </Tooltip>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>

      {/* Modal Nuevo Consorcista */}
      <Modal opened={opened} onClose={close} title="Registrar Nuevo Consorcista" size="lg">
        <form onSubmit={form.onSubmit(handleCreate)}>
          <SimpleGrid cols={2} spacing="sm">
            <TextInput label="Nombre" placeholder="Ej: Juan" required {...form.getInputProps('nombre')} />
            <TextInput label="Apellido" placeholder="Ej: Perez" required {...form.getInputProps('apellido')} />
          </SimpleGrid>
          <TextInput label="CUIT" placeholder="20-XXXXXXXX-X" required mt="sm" {...form.getInputProps('cuit')} />
          <TextInput 
            label="En representación de..." 
            placeholder="Empresa, Sucesión o Establecimiento" 
            mt="sm" 
            {...form.getInputProps('representa_a')} 
          />
          <SimpleGrid cols={2} mt="sm">
            <TextInput label="Email" placeholder="email@ejemplo.com" {...form.getInputProps('email')} />
            <TextInput label="Teléfono" placeholder="+54..." {...form.getInputProps('telefono')} />
          </SimpleGrid>
          <Button type="submit" fullWidth mt="xl">Guardar en Padrón</Button>
        </form>
      </Modal>

      {/* Modal Pagos */}
      <Modal opened={pagoOpened} onClose={closePago} title="Estado de Cuotas Anuales" size="lg">
        {selectedConsorcista && (
          <Stack gap="md">
            <Box>
              <Text fw={700} size="lg">{selectedConsorcista.apellido}, {selectedConsorcista.nombre}</Text>
              <Text size="sm" c="dimmed">CUIT: {selectedConsorcista.cuit}</Text>
            </Box>
            
            <Table withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Año</Table.Th>
                  <Table.Th>Monto</Table.Th>
                  <Table.Th>Estado</Table.Th>
                  <Table.Th>Fecha Pago</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {[2026, 2025, 2024].map(anio => {
                  const pago = pagos.find(p => p.anio === anio);
                  return (
                    <Table.Tr key={anio}>
                      <Table.Td fw={600}>{anio}</Table.Td>
                      <Table.Td>${pago?.monto || '-'}</Table.Td>
                      <Table.Td>
                        <Badge color={pago?.estado === 'pagado' ? 'green' : 'red'} variant="light">
                          {pago?.estado || 'PENDIENTE'}
                        </Badge>
                      </Table.Td>
                      <Table.Td>{pago?.fecha_pago ? new Date(pago.fecha_pago).toLocaleDateString() : '-'}</Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
            
            <Divider label="Registrar Nuevo Pago" labelPosition="center" />
            <Paper p="sm" bg="gray.0">
              <Group grow align="flex-end">
                <NumberInput label="Año" defaultValue={2026} hideControls />
                <NumberInput label="Monto" placeholder="$" hideControls />
                <Button color="green" leftSection={<IconCreditCard size={14} />}>Registrar</Button>
              </Group>
            </Paper>
          </Stack>
        )}
      </Modal>
    </Container>
  );
}
