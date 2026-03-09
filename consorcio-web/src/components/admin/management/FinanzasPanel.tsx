import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  Card,
  Container,
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

export default function FinanzasPanel() {
  const DEFAULT_CATEGORIES = [
    'obras',
    'combustible',
    'maquinaria',
    'sueldos',
    'administrativo',
    'otros',
  ];
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string | null>('balance');
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [editingGasto, setEditingGasto] = useState<Gasto | null>(null);
  const [newCategoryName, setNewCategoryName] = useState('');

  const [opened, { open, close }] = useDisclosure(false);
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure(false);
  const [categoryOpened, { open: openCategory, close: closeCategory }] = useDisclosure(false);

  const fetchFinanzas = useCallback(async () => {
    setLoading(true);
    try {
      const [gastosData, balanceData] = await Promise.all([
        apiFetch<Gasto[]>('/finance/gastos'),
        apiFetch<Balance>(`/finance/balance-summary/${new Date().getFullYear()}`),
      ]);
      setGastos(gastosData);
      setBalance(balanceData);
      const categories = await apiFetch<string[]>('/finance/categorias');
      setCategoryOptions(categories.length > 0 ? categories : DEFAULT_CATEGORIES);
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

  const categoryData = categoryOptions.map((cat) => ({ value: cat, label: cat }));

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

  const handleCreateGasto = async (values: typeof form.values) => {
    try {
      await apiFetch('/finance/gastos', {
        method: 'POST',
        body: JSON.stringify(values),
      });
      close();
      fetchFinanzas();
      form.reset();
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
    openEdit();
  };

  const handleUpdateCategory = async (values: typeof editCategoryForm.values) => {
    if (!editingGasto) return;

    try {
      await apiFetch(`/finance/gastos/${editingGasto.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ categoria: values.categoria }),
      });
      closeEdit();
      setEditingGasto(null);
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
      </Group>

      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List mb="lg">
          <Tabs.Tab value="balance" leftSection={<IconCoin size={16} />}>
            Balance y Presupuesto
          </Tabs.Tab>
          <Tabs.Tab value="gastos" leftSection={<IconReceipt size={16} />}>
            Libro de Gastos
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="balance">
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
            <Card withBorder padding="lg" radius="md">
              <Group justify="space-between">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                  Recaudacion (Cuotas)
                </Text>
                <ThemeIcon color="green" variant="light">
                  <IconArrowUpRight size={16} />
                </ThemeIcon>
              </Group>
              <Text size="xl" fw={700} mt="md">
                ${balance?.total_ingresos.toLocaleString()}
              </Text>
              <Text size="xs" c="dimmed">
                Ingresos confirmados ano {currentYear}
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
            <Button type="submit" fullWidth mt="md" color="red">
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
            <Button type="submit" fullWidth mt="md">
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
    </Container>
  );
}
