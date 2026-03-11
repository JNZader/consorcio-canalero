// @ts-nocheck
import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  Card,
  Container,
  FileInput,
  Group,
  Modal,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { LoadingState } from '../../ui';
import {
  IconArrowDownRight,
  IconArrowUpRight,
  IconCoin,
  IconEdit,
  IconPlus,
  IconReceipt,
  IconReportMoney,
  IconUpload,
} from '../../ui/icons';

interface Gasto {
  id: string;
  fecha: string;
  descripcion: string;
  monto: number;
  categoria: string;
  comprobante_url?: string;
  infraestructura?: { nombre: string };
}

interface Balance {
  total_ingresos: number;
  total_gastos: number;
  balance: number;
}

interface Ingreso {
  id: string;
  fecha: string;
  descripcion: string;
  monto: number;
  fuente: string;
  comprobante_url?: string;
  pagador?: string;
}

export default function FinanzasPanel() {
  const DEFAULT_CATEGORIES = [
    'obras',
    'combustible',
    'maquinaria',
    'sueldos',
    'administrativo',
    'otros',
  ];
  const DEFAULT_INCOME_SOURCES = ['cuotas_extra', 'subsidio', 'alquiler', 'otros'];
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [ingresos, setIngresos] = useState<Ingreso[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string | null>('balance');
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [editingGasto, setEditingGasto] = useState<Gasto | null>(null);
  const [editingIngreso, setEditingIngreso] = useState<Ingreso | null>(null);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [sourceOptions, setSourceOptions] = useState<string[]>([]);
  const [newSourceName, setNewSourceName] = useState('');
  const [gastoComprobanteFile, setGastoComprobanteFile] = useState<File | null>(null);
  const [gastoEditComprobanteFile, setGastoEditComprobanteFile] = useState<File | null>(null);
  const [ingresoComprobanteFile, setIngresoComprobanteFile] = useState<File | null>(null);
  const [ingresoEditComprobanteFile, setIngresoEditComprobanteFile] = useState<File | null>(null);
  const [uploadingComprobante, setUploadingComprobante] = useState(false);

  const [opened, { open, close }] = useDisclosure(false);
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure(false);
  const [ingresoOpened, { open: openIngreso, close: closeIngreso }] = useDisclosure(false);
  const [editIngresoOpened, { open: openEditIngreso, close: closeEditIngreso }] = useDisclosure(false);
  const [categoryOpened, { open: openCategory, close: closeCategory }] = useDisclosure(false);
  const [sourceOpened, { open: openSource, close: closeSource }] = useDisclosure(false);

  const fetchFinanzas = useCallback(async () => {
    setLoading(true);
    try {
      const [gastosData, ingresosData, balanceData, categories, fuentes] = await Promise.all([
        apiFetch<Gasto[]>('/finance/gastos'),
        apiFetch<Ingreso[]>('/finance/ingresos'),
        apiFetch<Balance>(`/finance/balance-summary/${new Date().getFullYear()}`),
        apiFetch<string[]>('/finance/categorias'),
        apiFetch<string[]>('/finance/fuentes'),
      ]);
      setGastos(gastosData);
      setIngresos(ingresosData);
      setBalance(balanceData);
      setCategoryOptions(categories.length > 0 ? categories : DEFAULT_CATEGORIES);
      setSourceOptions(fuentes.length > 0 ? fuentes : DEFAULT_INCOME_SOURCES);
    } catch (err) {
      logger.error('Error fetching finanzas:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFinanzas();
  }, [fetchFinanzas]);

  const form = useForm({
    initialValues: {
      descripcion: '',
      monto: 0,
      categoria: '',
      comprobante_url: '',
      fecha: new Date().toISOString().split('T')[0],
    },
  });

  const editCategoryForm = useForm({
    initialValues: {
      categoria: '',
    },
  });

  const ingresoForm = useForm({
    initialValues: {
      descripcion: '',
      monto: 0,
      fuente: '',
      pagador: '',
      comprobante_url: '',
      fecha: new Date().toISOString().split('T')[0],
    },
  });

  const editIngresoForm = useForm({
    initialValues: {
      descripcion: '',
      monto: 0,
      fuente: '',
      pagador: '',
      comprobante_url: '',
      fecha: '',
    },
  });

  const categoryData = categoryOptions.map((cat) => ({ value: cat, label: cat }));
  const sourceData = sourceOptions.map((source) => ({ value: source, label: source }));

  const handleAddCategory = () => {
    const normalized = newCategoryName.trim().toLowerCase();
    if (!normalized) return;

    const exists = categoryOptions.some((cat) => cat.toLowerCase() === normalized);
    if (!exists) {
      setCategoryOptions((prev) => [...prev, normalized].sort((a, b) => a.localeCompare(b)));
    }

    if (opened) {
      form.setFieldValue('categoria', normalized);
    }
    if (editOpened) {
      editCategoryForm.setFieldValue('categoria', normalized);
    }

    setNewCategoryName('');
    closeCategory();
  };

  const handleAddSource = () => {
    const normalized = newSourceName.trim().toLowerCase();
    if (!normalized) return;

    const exists = sourceOptions.some((source) => source.toLowerCase() === normalized);
    if (!exists) {
      setSourceOptions((prev) => [...prev, normalized].sort((a, b) => a.localeCompare(b)));
    }

    ingresoForm.setFieldValue('fuente', normalized);
    if (editIngresoOpened) {
      editIngresoForm.setFieldValue('fuente', normalized);
    }
    setNewSourceName('');
    closeSource();
  };

  const handleCreateGasto = async (values: typeof form.values) => {
    try {
      let comprobanteUrl = values.comprobante_url;
      if (gastoComprobanteFile) {
        comprobanteUrl = await uploadComprobante(gastoComprobanteFile, 'gasto');
      }

      await apiFetch('/finance/gastos', {
        method: 'POST',
        body: JSON.stringify({
          ...values,
          comprobante_url: comprobanteUrl || undefined,
        }),
      });
      close();
      fetchFinanzas();
      form.reset();
      setGastoComprobanteFile(null);
      notifications.show({
        title: 'Gasto registrado',
        message: 'El gasto fue guardado correctamente',
        color: 'green',
      });
    } catch (err) {
      logger.error('Error creating gasto:', err);
    }
  };

  const handleOpenEditCategory = (gasto: Gasto) => {
    setEditingGasto(gasto);
    editCategoryForm.setFieldValue('categoria', gasto.categoria);
    setGastoEditComprobanteFile(null);
    openEdit();
  };

  const handleUpdateCategory = async (values: typeof editCategoryForm.values) => {
    if (!editingGasto) return;

    try {
      let comprobanteUrl = editingGasto.comprobante_url || '';
      if (gastoEditComprobanteFile) {
        comprobanteUrl = await uploadComprobante(gastoEditComprobanteFile, 'gasto');
      }

      await apiFetch(`/finance/gastos/${editingGasto.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          categoria: values.categoria,
          comprobante_url: comprobanteUrl || undefined,
        }),
      });
      closeEdit();
      setEditingGasto(null);
      setGastoEditComprobanteFile(null);
      fetchFinanzas();
      notifications.show({
        title: 'Categoria actualizada',
        message: 'La categoria del gasto fue actualizada',
        color: 'green',
      });
    } catch (err) {
      logger.error('Error updating category:', err);
    }
  };

  const handleCreateIngreso = async (values: typeof ingresoForm.values) => {
    try {
      let comprobanteUrl = values.comprobante_url;
      if (ingresoComprobanteFile) {
        comprobanteUrl = await uploadComprobante(ingresoComprobanteFile, 'ingreso');
      }

      await apiFetch('/finance/ingresos', {
        method: 'POST',
        body: JSON.stringify({
          ...values,
          comprobante_url: comprobanteUrl || undefined,
        }),
      });
      closeIngreso();
      ingresoForm.reset();
      setIngresoComprobanteFile(null);
      fetchFinanzas();
      notifications.show({
        title: 'Ingreso registrado',
        message: 'El ingreso fue guardado correctamente',
        color: 'green',
      });
    } catch (err) {
      logger.error('Error creating ingreso:', err);
    }
  };

  const handleOpenEditIngreso = (ingreso: Ingreso) => {
    setEditingIngreso(ingreso);
    editIngresoForm.setValues({
      descripcion: ingreso.descripcion,
      monto: ingreso.monto,
      fuente: ingreso.fuente,
      pagador: ingreso.pagador || '',
      comprobante_url: ingreso.comprobante_url || '',
      fecha: ingreso.fecha,
    });
    setIngresoEditComprobanteFile(null);
    openEditIngreso();
  };

  const handleUpdateIngreso = async (values: typeof editIngresoForm.values) => {
    if (!editingIngreso) return;

    try {
      let comprobanteUrl = values.comprobante_url;
      if (ingresoEditComprobanteFile) {
        comprobanteUrl = await uploadComprobante(ingresoEditComprobanteFile, 'ingreso');
      }

      await apiFetch(`/finance/ingresos/${editingIngreso.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          ...values,
          comprobante_url: comprobanteUrl || undefined,
        }),
      });
      closeEditIngreso();
      setEditingIngreso(null);
      setIngresoEditComprobanteFile(null);
      fetchFinanzas();
      notifications.show({
        title: 'Ingreso actualizado',
        message: 'Los datos del ingreso fueron actualizados',
        color: 'green',
      });
    } catch (err) {
      logger.error('Error updating ingreso:', err);
    }
  };

  const uploadComprobante = async (file: File, tipo: 'gasto' | 'ingreso'): Promise<string> => {
    setUploadingComprobante(true);
    try {
      const formData = new FormData();
      formData.append('tipo', tipo);
      formData.append('file', file);

      const result = await apiFetch<{ url: string }>('/finance/comprobantes/upload', {
        method: 'POST',
        body: formData,
      });
      return result.url;
    } finally {
      setUploadingComprobante(false);
    }
  };

  if (loading && !balance) return <LoadingState />;

  const currentYear = new Date().getFullYear();

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>Administracion Financiera</Title>
          <Text c="dimmed">Seguimiento de gastos y ejecucion presupuestaria</Text>
        </div>
        <Button leftSection={<IconPlus size={18} />} onClick={open} color="red">
          Registrar Gasto
        </Button>
        <Button leftSection={<IconPlus size={18} />} onClick={openIngreso} color="green">
          Registrar Ingreso
        </Button>
      </Group>

      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List mb="lg">
          <Tabs.Tab value="balance" leftSection={<IconCoin size={16} />}>
            Balance y Presupuesto
          </Tabs.Tab>
          <Tabs.Tab value="gastos" leftSection={<IconReceipt size={16} />}>
            Libro de Gastos
          </Tabs.Tab>
          <Tabs.Tab value="ingresos" leftSection={<IconArrowUpRight size={16} />}>
            Libro de Ingresos
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="balance">
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
            <Card withBorder padding="lg" radius="md">
              <Group justify="space-between">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                  Ingresos Totales
                </Text>
                <ThemeIcon color="green" variant="light">
                  <IconArrowUpRight size={16} />
                </ThemeIcon>
              </Group>
              <Text size="xl" fw={700} mt="md">
                ${balance?.total_ingresos.toLocaleString()}
              </Text>
              <Text size="xs" c="dimmed">
                Cuotas e ingresos operativos ano {currentYear}
              </Text>
            </Card>

            <Card withBorder padding="lg" radius="md">
              <Group justify="space-between">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                  Gastos Operativos
                </Text>
                <ThemeIcon color="red" variant="light">
                  <IconArrowDownRight size={16} />
                </ThemeIcon>
              </Group>
              <Text size="xl" fw={700} mt="md">
                ${balance?.total_gastos.toLocaleString()}
              </Text>
              <Text size="xs" c="dimmed">
                Obras, sueldos y mantenimiento
              </Text>
            </Card>

            <Card
              withBorder
              padding="lg"
              radius="md"
              bg={balance && balance.balance < 0 ? 'red.0' : 'blue.0'}
            >
              <Group justify="space-between">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                  Caja Actual
                </Text>
                <ThemeIcon color="blue" variant="light">
                  <IconReportMoney size={16} />
                </ThemeIcon>
              </Group>
              <Text size="xl" fw={700} mt="md">
                ${balance?.balance.toLocaleString()}
              </Text>
              <Text size="xs" c="dimmed">
                Saldo disponible en cuenta
              </Text>
            </Card>
          </SimpleGrid>

          <Paper withBorder p="xl" radius="md" mt="xl">
            <Group justify="space-between" mb="xl">
              <Title order={4}>Presupuesto Asamblea {currentYear}</Title>
              <Button variant="outline">Generar PDF Asamblea</Button>
            </Group>
            <Text c="dimmed" ta="center" py="xl">
              Area de planificacion presupuestaria en desarrollo...
            </Text>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="gastos">
          <Paper withBorder radius="md">
            <Table verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Fecha</Table.Th>
                  <Table.Th>Descripcion</Table.Th>
                  <Table.Th>Categoria</Table.Th>
                  <Table.Th>Monto</Table.Th>
                  <Table.Th>Activo Vinculado</Table.Th>
                  <Table.Th>Comprobante</Table.Th>
                  <Table.Th>Acciones</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {gastos.map((g) => (
                  <Table.Tr key={g.id}>
                    <Table.Td>
                      <Text size="sm">{new Date(g.fecha).toLocaleDateString()}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {g.descripcion}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light" color="gray">
                        {g.categoria.toUpperCase()}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text fw={700} c="red.7">
                        -${g.monto.toLocaleString()}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" c="dimmed">
                        {g.infraestructura?.nombre || '-'}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      {g.comprobante_url ? (
                        <Anchor href={g.comprobante_url} target="_blank" rel="noreferrer" size="sm">
                          Ver archivo
                        </Anchor>
                      ) : (
                        <Text size="xs" c="dimmed">
                          -
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <ActionIcon variant="subtle" onClick={() => handleOpenEditCategory(g)}>
                        <IconEdit size={16} />
                      </ActionIcon>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="ingresos">
          <Paper withBorder radius="md">
            <Table verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Fecha</Table.Th>
                  <Table.Th>Descripcion</Table.Th>
                  <Table.Th>Fuente</Table.Th>
                  <Table.Th>Monto</Table.Th>
                  <Table.Th>Pagador</Table.Th>
                  <Table.Th>Comprobante</Table.Th>
                  <Table.Th>Acciones</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {ingresos.map((ingreso) => (
                  <Table.Tr key={ingreso.id}>
                    <Table.Td>{new Date(ingreso.fecha).toLocaleDateString()}</Table.Td>
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {ingreso.descripcion}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light" color="green">
                        {ingreso.fuente.toUpperCase()}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text fw={700} c="green.7">
                        +${ingreso.monto.toLocaleString()}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" c="dimmed">
                        {ingreso.pagador || '-'}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      {ingreso.comprobante_url ? (
                        <Anchor href={ingreso.comprobante_url} target="_blank" rel="noreferrer" size="sm">
                          Ver archivo
                        </Anchor>
                      ) : (
                        <Text size="xs" c="dimmed">
                          -
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <ActionIcon variant="subtle" onClick={() => handleOpenEditIngreso(ingreso)}>
                        <IconEdit size={16} />
                      </ActionIcon>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        </Tabs.Panel>
      </Tabs>

      {/* Modal Nuevo Gasto */}
      <Modal opened={opened} onClose={close} title="Registrar Gasto de Caja">
        <form onSubmit={form.onSubmit(handleCreateGasto)}>
          <Stack gap="sm">
            <TextInput
              label="Descripcion del Gasto"
              placeholder="Ej: Compra de 500L gasoil"
              required
              {...form.getInputProps('descripcion')}
            />
            <SimpleGrid cols={2}>
              <NumberInput
                label="Monto ($)"
                placeholder="0.00"
                required
                hideControls
                {...form.getInputProps('monto')}
              />
              <Select
                label="Categoria"
                placeholder="Selecciona una categoria"
                data={categoryData}
                searchable
                required
                {...form.getInputProps('categoria')}
              />
            </SimpleGrid>
            <Group justify="space-between" gap="xs">
              <Text size="xs" c="dimmed">
                No aparece la categoria?
              </Text>
              <Button variant="subtle" size="xs" onClick={openCategory}>
                Agregar categoria
              </Button>
            </Group>
            <TextInput type="date" label="Fecha" {...form.getInputProps('fecha')} />
            <TextInput
              label="Comprobante (URL foto/PDF)"
              placeholder="https://..."
              {...form.getInputProps('comprobante_url')}
            />
            <FileInput
              label="O subir comprobante"
              placeholder="Imagen o PDF"
              value={gastoComprobanteFile}
              onChange={setGastoComprobanteFile}
              accept="image/jpeg,image/png,image/webp,application/pdf"
              leftSection={<IconUpload size={16} />}
              clearable
            />
            <Button type="submit" fullWidth mt="md" color="red" loading={uploadingComprobante}>
              Guardar Gasto
            </Button>
          </Stack>
        </form>
      </Modal>

      <Modal opened={editOpened} onClose={closeEdit} title="Editar categoria de gasto">
        <form onSubmit={editCategoryForm.onSubmit(handleUpdateCategory)}>
          <Stack gap="sm">
            <Select
              label="Categoria"
              placeholder="Selecciona categoria"
              data={categoryData}
              searchable
              required
              {...editCategoryForm.getInputProps('categoria')}
            />
            <Button variant="subtle" size="xs" onClick={openCategory}>
              Agregar categoria
            </Button>
            <TextInput
              label="Comprobante URL"
              placeholder="https://..."
              defaultValue={editingGasto?.comprobante_url || ''}
              onChange={(event) => {
                if (!editingGasto) return;
                setEditingGasto({ ...editingGasto, comprobante_url: event.currentTarget.value });
              }}
            />
            <FileInput
              label="Reemplazar comprobante"
              placeholder="Imagen o PDF"
              value={gastoEditComprobanteFile}
              onChange={setGastoEditComprobanteFile}
              accept="image/jpeg,image/png,image/webp,application/pdf"
              leftSection={<IconUpload size={16} />}
              clearable
            />
            <Button type="submit" fullWidth mt="md" loading={uploadingComprobante}>
              Actualizar categoria
            </Button>
          </Stack>
        </form>
      </Modal>

      <Modal opened={categoryOpened} onClose={closeCategory} title="Nueva categoria">
        <Stack gap="sm">
          <TextInput
            label="Nombre"
            placeholder="Ej: viaticos"
            value={newCategoryName}
            onChange={(event) => setNewCategoryName(event.currentTarget.value)}
          />
          <Button onClick={handleAddCategory}>Guardar categoria</Button>
        </Stack>
      </Modal>

      <Modal opened={ingresoOpened} onClose={closeIngreso} title="Registrar Ingreso">
        <form onSubmit={ingresoForm.onSubmit(handleCreateIngreso)}>
          <Stack gap="sm">
            <TextInput
              label="Descripcion"
              placeholder="Ej: Subsidio provincial"
              required
              {...ingresoForm.getInputProps('descripcion')}
            />
            <SimpleGrid cols={2}>
              <NumberInput
                label="Monto ($)"
                placeholder="0.00"
                required
                hideControls
                {...ingresoForm.getInputProps('monto')}
              />
              <Select
                label="Fuente"
                placeholder="Selecciona una fuente"
                data={sourceData}
                searchable
                required
                {...ingresoForm.getInputProps('fuente')}
              />
            </SimpleGrid>
            <Group justify="space-between" gap="xs">
              <Text size="xs" c="dimmed">
                No aparece la fuente?
              </Text>
              <Button variant="subtle" size="xs" onClick={openSource}>
                Agregar fuente
              </Button>
            </Group>
            <SimpleGrid cols={2}>
              <TextInput
                label="Pagador"
                placeholder="Ej: Ministerio de Produccion"
                {...ingresoForm.getInputProps('pagador')}
              />
              <TextInput type="date" label="Fecha" {...ingresoForm.getInputProps('fecha')} />
            </SimpleGrid>
            <TextInput
              label="Comprobante (URL foto/PDF)"
              placeholder="https://..."
              {...ingresoForm.getInputProps('comprobante_url')}
            />
            <FileInput
              label="O subir comprobante"
              placeholder="Imagen o PDF"
              value={ingresoComprobanteFile}
              onChange={setIngresoComprobanteFile}
              accept="image/jpeg,image/png,image/webp,application/pdf"
              leftSection={<IconUpload size={16} />}
              clearable
            />
            <Button type="submit" fullWidth mt="md" color="green" loading={uploadingComprobante}>
              Guardar Ingreso
            </Button>
          </Stack>
        </form>
      </Modal>

      <Modal opened={editIngresoOpened} onClose={closeEditIngreso} title="Editar ingreso">
        <form onSubmit={editIngresoForm.onSubmit(handleUpdateIngreso)}>
          <Stack gap="sm">
            <TextInput label="Descripcion" required {...editIngresoForm.getInputProps('descripcion')} />
            <SimpleGrid cols={2}>
              <NumberInput label="Monto ($)" required hideControls {...editIngresoForm.getInputProps('monto')} />
              <Select
                label="Fuente"
                placeholder="Selecciona fuente"
                data={sourceData}
                searchable
                required
                {...editIngresoForm.getInputProps('fuente')}
              />
            </SimpleGrid>
            <Button variant="subtle" size="xs" onClick={openSource}>
              Agregar fuente
            </Button>
            <SimpleGrid cols={2}>
              <TextInput label="Pagador" {...editIngresoForm.getInputProps('pagador')} />
              <TextInput type="date" label="Fecha" {...editIngresoForm.getInputProps('fecha')} />
            </SimpleGrid>
            <TextInput
              label="Comprobante (URL foto/PDF)"
              placeholder="https://..."
              {...editIngresoForm.getInputProps('comprobante_url')}
            />
            <FileInput
              label="Reemplazar comprobante"
              placeholder="Imagen o PDF"
              value={ingresoEditComprobanteFile}
              onChange={setIngresoEditComprobanteFile}
              accept="image/jpeg,image/png,image/webp,application/pdf"
              leftSection={<IconUpload size={16} />}
              clearable
            />
            <Button type="submit" fullWidth mt="md" loading={uploadingComprobante}>
              Actualizar ingreso
            </Button>
          </Stack>
        </form>
      </Modal>

      <Modal opened={sourceOpened} onClose={closeSource} title="Nueva fuente de ingreso">
        <Stack gap="sm">
          <TextInput
            label="Nombre"
            placeholder="Ej: convenio"
            value={newSourceName}
            onChange={(event) => setNewSourceName(event.currentTarget.value)}
          />
          <Button onClick={handleAddSource}>Guardar fuente</Button>
        </Stack>
      </Modal>
    </Container>
  );
}
