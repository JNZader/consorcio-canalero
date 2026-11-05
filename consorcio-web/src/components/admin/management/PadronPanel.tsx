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
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/api';
import { handleError } from '../../../lib/errorHandler';
import { showNotification, showSuccess } from '../../../lib/notifications';
import { erroresUi } from '../../../lib/userFacingError';
import { isValidCUIT } from '../../../lib/validators';
import { useUserRole } from '../../../stores/authStore';
import { ConfirmDialog } from '../../ui/ConfirmDialog';
import { IconButton } from '../../ui/IconButton';
import { IconEdit, IconPlus, IconSearch, IconTrash, IconUser } from '../../ui/icons';
import { LoadingState } from '../../ui/LoadingState';
import { PageHeader } from '../../ui/PageHeader';

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
  created: number;
  skipped: number;
  errors: Array<{ row: number; error: string }>;
}

export default function PadronPanel() {
  const userRole = useUserRole();
  const canImportPadron = userRole === 'admin';
  const [consorcistas, setConsorcistas] = useState<Consorcista[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const [opened, { open, close }] = useDisclosure(false);
  const [editingConsorcista, setEditingConsorcista] = useState<Consorcista | null>(null);
  const [importOpened, { open: openImport, close: closeImport }] = useDisclosure(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState<PadronImportResult | null>(null);
  const [consorcistaPendingDelete, setConsorcistaPendingDelete] = useState<Consorcista | null>(
    null
  );
  const [deleting, setDeleting] = useState(false);

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
        title: erroresUi.cargarPadron.titulo,
        fallbackMessage: erroresUi.cargarPadron.detalle,
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
      cuit: (value) => (!isValidCUIT(value) ? 'CUIT inválido' : null),
      nombre: (value) => (value.length < 2 ? 'Nombre requerido' : null),
      apellido: (value) => (value.length < 2 ? 'Apellido requerido' : null),
    },
  });

  const handleOpenCreate = () => {
    setEditingConsorcista(null);
    form.reset();
    open();
  };

  const handleOpenEdit = (consorcista: Consorcista) => {
    setEditingConsorcista(consorcista);
    form.setValues({
      nombre: consorcista.nombre,
      apellido: consorcista.apellido,
      cuit: consorcista.cuit,
      email: consorcista.email ?? '',
      telefono: consorcista.telefono ?? '',
    });
    open();
  };

  const handleSave = async (values: typeof form.values) => {
    try {
      if (editingConsorcista) {
        await apiFetch(`/padron/${editingConsorcista.id}`, {
          method: 'PATCH',
          body: JSON.stringify(values),
        });
        showSuccess(
          'Consorcista actualizado',
          `${values.apellido}, ${values.nombre} fue actualizado en el padrón`
        );
      } else {
        await apiFetch('/padron', {
          method: 'POST',
          body: JSON.stringify(values),
        });
        showSuccess(
          'Consorcista registrado',
          `${values.apellido}, ${values.nombre} fue agregado al padrón`
        );
      }
      close();
      setEditingConsorcista(null);
      fetchConsorcistas();
      form.reset();
    } catch (err) {
      handleError(err, {
        title: erroresUi.crearConsorcista.titulo,
        fallbackMessage: erroresUi.crearConsorcista.detalle,
        context: 'PadronPanel.handleSave',
      });
    }
  };

  const requestDelete = (consorcista: Consorcista) => {
    setConsorcistaPendingDelete(consorcista);
  };

  const confirmDelete = async () => {
    const consorcista = consorcistaPendingDelete;
    if (!consorcista) return;
    setDeleting(true);
    try {
      await apiFetch(`/padron/${consorcista.id}`, {
        method: 'DELETE',
      });
      showSuccess(
        'Consorcista eliminado',
        `${consorcista.apellido}, ${consorcista.nombre} fue eliminado del padrón`
      );
      setConsorcistaPendingDelete(null);
      fetchConsorcistas();
    } catch (err) {
      handleError(err, {
        title: erroresUi.cargarPadron.titulo,
        fallbackMessage: erroresUi.cargarPadron.detalle,
        context: 'PadronPanel.handleDelete',
      });
    } finally {
      setDeleting(false);
    }
  };

  const handleImportPadron = async () => {
    if (!importFile) {
      showNotification(
        'Archivo requerido',
        'Seleccioná un archivo CSV, XLS o XLSX para importar',
        'yellow'
      );
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

      showNotification(
        'Importación completada',
        `Procesadas ${result.processed} filas; registros creados: ${result.created}; filas omitidas: ${result.skipped}`,
        result.errors.length > 0 ? 'yellow' : 'green'
      );
    } catch (err) {
      handleError(err, {
        title: erroresUi.importarPadron.titulo,
        fallbackMessage: erroresUi.importarPadron.detalle,
        context: 'PadronPanel.handleImportPadron',
      });
    } finally {
      setImportLoading(false);
    }
  };

  if (loading && consorcistas.length === 0) return <LoadingState />;

  return (
    <Container size="xl" py="md">
      <PageHeader
        title="Padrón de Consorcistas"
        subtitle="Administración de socios y datos del padrón"
        actions={
          <>
            <Button leftSection={<IconPlus size={18} />} onClick={handleOpenCreate}>
              Nuevo Consorcista
            </Button>
            {canImportPadron && (
              <Button variant="outline" onClick={openImport}>
                Importar CSV/XLS
              </Button>
            )}
          </>
        }
      />

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
          La gestión de pagos y cuotas no está disponible en esta versión.
        </Text>
      </Paper>

      <Paper withBorder radius="md">
        <Table.ScrollContainer minWidth={680} type="native">
          <Table verticalSpacing="sm" highlightOnHover aria-label="Tabla de consorcistas">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Consorcista</Table.Th>
                <Table.Th>CUIT</Table.Th>
                <Table.Th>Email</Table.Th>
                <Table.Th>Teléfono</Table.Th>
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
                    <Text size="sm" c={c.email ? undefined : 'dimmed'}>
                      {c.email || '—'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c={c.telefono ? undefined : 'dimmed'}>
                      {c.telefono || '—'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs" wrap="nowrap">
                      <IconButton
                        variant="subtle"
                        aria-label={`Editar consorcista ${c.apellido}, ${c.nombre}`}
                        onClick={() => handleOpenEdit(c)}
                      >
                        <IconEdit size={16} />
                      </IconButton>
                      <IconButton
                        variant="subtle"
                        color="red"
                        aria-label={`Eliminar consorcista ${c.apellido}, ${c.nombre}`}
                        onClick={() => requestDelete(c)}
                      >
                        <IconTrash size={16} />
                      </IconButton>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>

      {/* Modal Nuevo / Editar Consorcista */}
      <Modal
        opened={opened}
        onClose={() => {
          close();
          setEditingConsorcista(null);
        }}
        title={editingConsorcista ? 'Editar Consorcista' : 'Registrar Nuevo Consorcista'}
        size="lg"
      >
        <form onSubmit={form.onSubmit(handleSave)} noValidate>
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

      {canImportPadron && (
        <Modal
          opened={importOpened}
          onClose={closeImport}
          title="Importar padrón desde archivo"
          size="lg"
        >
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              Formatos soportados: CSV, XLS y XLSX. Los CUIT nuevos se crean; los existentes o
              duplicados se omiten sin modificar datos.
            </Text>
            <FileInput
              label="Archivo"
              placeholder="Seleccioná un archivo"
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
                <Text size="sm">Registros creados: {importResult.created}</Text>
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
      )}

      <ConfirmDialog
        opened={consorcistaPendingDelete !== null}
        title="Eliminar consorcista"
        message={
          consorcistaPendingDelete
            ? `¿Eliminar al consorcista "${consorcistaPendingDelete.apellido}, ${consorcistaPendingDelete.nombre}"? Esta acción no se puede deshacer.`
            : ''
        }
        confirmLabel="Eliminar"
        onConfirm={() => void confirmDelete()}
        onClose={() => {
          if (!deleting) setConsorcistaPendingDelete(null);
        }}
        loading={deleting}
      />
    </Container>
  );
}
