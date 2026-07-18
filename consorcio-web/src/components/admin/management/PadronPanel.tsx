import {
  Button,
  Container,
  FileInput,
  Group,
  Modal,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/api';
import { handleError } from '../../../lib/errorHandler';
import { isValidCUIT } from '../../../lib/validators';
import { LoadingState } from '../../ui/LoadingState';
import { IconPlus, IconSearch, IconUser } from '../../ui/icons';

const PADRON_NOMBRE_ERROR_ID = 'padron-nombre-error';
const PADRON_APELLIDO_ERROR_ID = 'padron-apellido-error';
const PADRON_CUIT_ERROR_ID = 'padron-cuit-error';

// Types for this panel
interface Consorcista {
  id: string;
  nombre: string;
  apellido: string;
  cuit: string;
  email?: string;
  telefono?: string;
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

  const [opened, { open, close }] = useDisclosure(false);
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

  useEffect(() => {
    const timer = setTimeout(() => fetchConsorcistas(), 300);
    return () => clearTimeout(timer);
  }, [fetchConsorcistas]);

  const form = useForm({
    initialValues: {
      nombre: '',
      apellido: '',
      cuit: '',
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
          <Text c="dimmed">Administración de socios y datos del padrón</Text>
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

      <Paper withBorder p="sm" radius="md" mb="md">
        <Text size="sm" c="dimmed">
          La gestion de pagos y cuotas no esta disponible en esta version.
        </Text>
      </Paper>

      <Paper withBorder radius="md">
        <Table.ScrollContainer minWidth={680} type="native">
          <Table verticalSpacing="sm" highlightOnHover aria-label="Tabla de consorcistas">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Consorcista</Table.Th>
                <Table.Th>CUIT</Table.Th>
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
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>

      {/* Modal Nuevo Consorcista */}
      <Modal opened={opened} onClose={close} title="Registrar Nuevo Consorcista" size="lg">
        <form onSubmit={form.onSubmit(handleCreate)} noValidate>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            <TextInput
              label="Nombre"
              placeholder="Ej: Juan"
              required
              {...form.getInputProps('nombre')}
              errorProps={{
                id: PADRON_NOMBRE_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />
            <TextInput
              label="Apellido"
              placeholder="Ej: Perez"
              required
              {...form.getInputProps('apellido')}
              errorProps={{
                id: PADRON_APELLIDO_ERROR_ID,
                role: 'alert',
                'aria-live': 'assertive',
              }}
            />
          </SimpleGrid>
          <TextInput
            label="CUIT"
            placeholder="20-XXXXXXXX-X"
            required
            mt="sm"
            {...form.getInputProps('cuit')}
            errorProps={{
              id: PADRON_CUIT_ERROR_ID,
              role: 'alert',
              'aria-live': 'assertive',
            }}
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
