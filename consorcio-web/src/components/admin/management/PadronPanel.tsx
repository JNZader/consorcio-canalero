import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Container,
  Divider,
  FileInput,
  Group,
  Modal,
  NumberInput,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/api';
import { handleError } from '../../../lib/errorHandler';
import { isValidCUIT } from '../../../lib/validators';
import { LoadingState } from '../../ui/LoadingState';
import { IconCreditCard, IconPlus, IconSearch, IconUser } from '../../ui/icons';

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

interface PadronImportResult {
  filename: string;
  processed: number;
  upserted: number;
  skipped: number;
  errors: Array<{ row: number; error: string }>;
}

export default function PadronPanel() {
  const [consorcistas, setConsorcistas] = useState<Consorcista[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const [selectedConsorcista, setSelectedConsorcista] = useState<Consorcista | null>(null);
  const [pagos, setPagos] = useState<Pago[]>([]);
  const [nuevoPagoAnio, setNuevoPagoAnio] = useState<number>(new Date().getFullYear());
  const [nuevoPagoMonto, setNuevoPagoMonto] = useState<number | ''>('');

  const [opened, { open, close }] = useDisclosure(false);
  const [pagoOpened, { open: openPago, close: closePago }] = useDisclosure(false);
  const [importOpened, { open: openImport, close: closeImport }] = useDisclosure(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState<PadronImportResult | null>(null);

  const fetchConsorcistas = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiFetch<Consorcista[] | { items: Consorcista[] }>(
        `/padron?search=${search}`
      );
      const data = Array.isArray(response) ? response : (response.items ?? []);
      setConsorcistas(data);
    } catch (err) {
      handleError(err, {
        title: 'Error al cargar consorcistas',
        context: 'PadronPanel.fetchConsorcistas',
      });
    } finally {
      setLoading(false);
    }
  }, [search]);

  const fetchPagos = async (id: string) => {
    try {
      // TODO: Pagos endpoint not implemented in v2 padron yet
      const response = await apiFetch<Pago[] | { items: Pago[] }>(`/padron/${id}/pagos`).catch(
        () => [] as Pago[]
      );
      const data = Array.isArray(response) ? response : (response.items ?? []);
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
  }, [fetchConsorcistas]);

  const handleViewPagos = (c: Consorcista) => {
    setSelectedConsorcista(c);
    setNuevoPagoAnio(new Date().getFullYear());
    setNuevoPagoMonto('');
    fetchPagos(c.id);
    openPago();
  };

  const handleRegistrarPago = async () => {
    if (!selectedConsorcista || !nuevoPagoMonto || nuevoPagoMonto <= 0) {
      notifications.show({
        title: 'Datos incompletos',
        message: 'Ingrese anio y monto validos para registrar el pago',
        color: 'yellow',
      });
      return;
    }

    try {
      // TODO: Pagos creation not implemented in v2 padron yet
      await apiFetch('/padron/pagos', {
        method: 'POST',
        body: JSON.stringify({
          consorcista_id: selectedConsorcista.id,
          anio: nuevoPagoAnio,
          monto: Number(nuevoPagoMonto),
          estado: 'pagado',
          fecha_pago: new Date().toISOString().slice(0, 10),
        }),
      });

      notifications.show({
        title: 'Pago registrado',
        message: `Cuota ${nuevoPagoAnio} registrada para ${selectedConsorcista.apellido}, ${selectedConsorcista.nombre}`,
        color: 'green',
      });

      await fetchPagos(selectedConsorcista.id);
      setNuevoPagoMonto('');
    } catch (err) {
      handleError(err, {
        title: 'Error al registrar pago',
        context: 'PadronPanel.handleRegistrarPago',
      });
    }
  };

  const form = useForm({
    initialValues: {
      nombre: '',
      apellido: '',
      cuit: '',
      representa_a: '',
      email: '',
      telefono: '',
    },
    validate: {
      cuit: (value) => (!isValidCUIT(value) ? 'CUIT invalido' : null),
      nombre: (value) => (value.length < 2 ? 'Nombre requerido' : null),
      apellido: (value) => (value.length < 2 ? 'Apellido requerido' : null),
    },
  });

  const handleCreate = async (values: typeof form.values) => {
    try {
      await apiFetch('/padron', {
        method: 'POST',
        body: JSON.stringify(values),
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

  const handleImportPadron = async () => {
    if (!importFile) {
      notifications.show({
        title: 'Archivo requerido',
        message: 'Selecciona un archivo CSV, XLS o XLSX para importar',
        color: 'yellow',
      });
      return;
    }

    setImportLoading(true);
    setImportResult(null);
    try {
      const formData = new FormData();
      formData.append('file', importFile);

      const result = await apiFetch<PadronImportResult>('/padron/import', {
        method: 'POST',
        body: formData,
      });

      setImportResult(result);
      await fetchConsorcistas();

      notifications.show({
        title: 'Importacion completada',
        message: `Procesadas ${result.processed} filas, ${result.upserted} aplicadas`,
        color: result.errors.length > 0 ? 'yellow' : 'green',
      });
    } catch (err) {
      handleError(err, {
        title: 'Error al importar padron',
        context: 'PadronPanel.handleImportPadron',
      });
    } finally {
      setImportLoading(false);
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
        <Button variant="outline" onClick={openImport}>
          Importar CSV/XLS
        </Button>
      </Group>

      <Paper shadow="sm" p="md" radius="md" mb="md">
        <TextInput
          aria-label="Buscar consorcistas"
          placeholder="Buscar por Nombre, Apellido o CUIT..."
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </Paper>

      <Paper withBorder radius="md">
        <Table.ScrollContainer minWidth={680} type="native">
          <Table verticalSpacing="sm" highlightOnHover aria-label="Tabla de consorcistas">
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
                    <Group gap="sm" wrap="nowrap">
                      <IconUser size={16} color="gray" aria-hidden="true" />
                      <Text fw={500} size="sm">
                        {c.apellido}, {c.nombre}
                      </Text>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{c.cuit}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" fs="italic" c="dimmed">
                      {c.representa_a || '-'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs" wrap="nowrap">
                      <Tooltip label="Ver Pagos / Cuotas">
                        <ActionIcon
                          variant="light"
                          color="green"
                          onClick={() => handleViewPagos(c)}
                          aria-label={`Ver pagos y cuotas de ${c.apellido}, ${c.nombre}`}
                        >
                          <IconCreditCard size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>

      {/* Modal Nuevo Consorcista */}
      <Modal opened={opened} onClose={close} title="Registrar Nuevo Consorcista" size="lg">
        <form onSubmit={form.onSubmit(handleCreate)}>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            <TextInput
              label="Nombre"
              placeholder="Ej: Juan"
              required
              {...form.getInputProps('nombre')}
            />
            <TextInput
              label="Apellido"
              placeholder="Ej: Perez"
              required
              {...form.getInputProps('apellido')}
            />
          </SimpleGrid>
          <TextInput
            label="CUIT"
            placeholder="20-XXXXXXXX-X"
            required
            mt="sm"
            {...form.getInputProps('cuit')}
          />
          <TextInput
            label="En representación de..."
            placeholder="Empresa, Sucesión o Establecimiento"
            mt="sm"
            {...form.getInputProps('representa_a')}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }} mt="sm">
            <TextInput
              label="Email"
              placeholder="email@ejemplo.com"
              {...form.getInputProps('email')}
            />
            <TextInput label="Teléfono" placeholder="+54..." {...form.getInputProps('telefono')} />
          </SimpleGrid>
          <Button type="submit" fullWidth mt="xl">
            Guardar en Padrón
          </Button>
        </form>
      </Modal>

      {/* Modal Pagos */}
      <Modal opened={pagoOpened} onClose={closePago} title="Estado de Cuotas Anuales" size="lg">
        {selectedConsorcista && (
          <Stack gap="md">
            <Box>
              <Text fw={700} size="lg">
                {selectedConsorcista.apellido}, {selectedConsorcista.nombre}
              </Text>
              <Text size="sm" c="dimmed">
                CUIT: {selectedConsorcista.cuit}
              </Text>
            </Box>

            <Table.ScrollContainer minWidth={520} type="native">
              <Table
                withColumnBorders
                aria-label={`Cuotas anuales de ${selectedConsorcista.apellido}, ${selectedConsorcista.nombre}`}
              >
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Año</Table.Th>
                    <Table.Th>Monto</Table.Th>
                    <Table.Th>Estado</Table.Th>
                    <Table.Th>Fecha Pago</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {[2026, 2025, 2024].map((anio) => {
                    const pago = pagos.find((p) => p.anio === anio);
                    return (
                      <Table.Tr key={anio}>
                        <Table.Td fw={600}>{anio}</Table.Td>
                        <Table.Td>${pago?.monto || '-'}</Table.Td>
                        <Table.Td>
                          <Badge
                            color={pago?.estado === 'pagado' ? 'green' : 'red'}
                            variant="light"
                          >
                            {pago?.estado || 'PENDIENTE'}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          {pago?.fecha_pago ? new Date(pago.fecha_pago).toLocaleDateString() : '-'}
                        </Table.Td>
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>

            <Divider label="Registrar Nuevo Pago" labelPosition="center" />
            <Paper p="sm" bg="gray.0">
              <Group grow align="flex-end" wrap="wrap">
                <NumberInput
                  label="Año"
                  value={nuevoPagoAnio}
                  onChange={(value) => setNuevoPagoAnio(Number(value) || new Date().getFullYear())}
                  hideControls
                  min={2000}
                  max={2100}
                />
                <NumberInput
                  label="Monto"
                  placeholder="$"
                  hideControls
                  value={nuevoPagoMonto}
                  onChange={(value) => {
                    if (typeof value === 'number') {
                      setNuevoPagoMonto(value);
                      return;
                    }
                    setNuevoPagoMonto('');
                  }}
                  min={0}
                />
                <Button
                  color="green"
                  leftSection={<IconCreditCard size={14} />}
                  onClick={handleRegistrarPago}
                >
                  Registrar
                </Button>
              </Group>
            </Paper>
          </Stack>
        )}
      </Modal>

      <Modal
        opened={importOpened}
        onClose={closeImport}
        title="Importar padron desde archivo"
        size="lg"
      >
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            Formatos soportados: CSV, XLS y XLSX. El sistema actualiza o crea consorcistas por CUIT.
          </Text>
          <FileInput
            label="Archivo"
            placeholder="Selecciona un archivo"
            value={importFile}
            onChange={setImportFile}
            accept=".csv,.xls,.xlsx"
            clearable
          />
          <Button loading={importLoading} onClick={handleImportPadron}>
            Procesar importacion
          </Button>

          {importResult && (
            <Paper withBorder p="sm" radius="md">
              <Text size="sm">Archivo: {importResult.filename}</Text>
              <Text size="sm">Filas procesadas: {importResult.processed}</Text>
              <Text size="sm">Upserts aplicados: {importResult.upserted}</Text>
              <Text size="sm">Filas omitidas: {importResult.skipped}</Text>
              {importResult.errors.length > 0 && (
                <Text size="xs" c="red.7" mt="xs">
                  {`Errores: ${importResult.errors
                    .slice(0, 5)
                    .map((item) => `fila ${item.row}: ${item.error}`)
                    .join(' | ')}`}
                </Text>
              )}
            </Paper>
          )}
        </Stack>
      </Modal>
    </Container>
  );
}
