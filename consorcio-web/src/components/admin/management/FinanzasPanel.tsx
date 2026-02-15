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
  Paper,
  Modal,
  TextInput,
  Select,
  NumberInput,
  SimpleGrid,
  Tabs,
  ThemeIcon
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { IconPlus, IconCoin, IconArrowUpRight, IconArrowDownRight, IconReceipt, IconReportMoney } from '../../ui/icons';
import { LoadingState } from '../../ui';

interface Gasto {
  id: string;
  fecha: string;
  descripcion: string;
  monto: number;
  categoria: string;
  infraestructura?: { nombre: string };
}

interface Balance {
  total_ingresos: number;
  total_gastos: number;
  balance: number;
}

export default function FinanzasPanel() {
  const [gastos, setGastos] = useState<Gasto[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string | null>('balance');

  const [opened, { open, close }] = useDisclosure(false);

  const fetchFinanzas = useCallback(async () => {
    setLoading(true);
    try {
      const [gastosData, balanceData] = await Promise.all([
        apiFetch<Gasto[]>('/finance/gastos'),
        apiFetch<Balance>(`/finance/balance-summary/${new Date().getFullYear()}`)
      ]);
      setGastos(gastosData);
      setBalance(balanceData);
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
      categoria: 'obras',
      fecha: new Date().toISOString().split('T')[0]
    }
  });

  const handleCreateGasto = async (values: typeof form.values) => {
    try {
      await apiFetch('/finance/gastos', {
        method: 'POST',
        body: JSON.stringify(values)
      });
      close();
      fetchFinanzas();
      form.reset();
    } catch (err) {
      logger.error('Error creating gasto:', err);
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
          <Tabs.Tab value="balance" leftSection={<IconCoin size={16} />}>Balance y Presupuesto</Tabs.Tab>
          <Tabs.Tab value="gastos" leftSection={<IconReceipt size={16} />}>Libro de Gastos</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="balance">
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
            <Card withBorder padding="lg" radius="md">
              <Group justify="space-between">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>Recaudacion (Cuotas)</Text>
                <ThemeIcon color="green" variant="light"><IconArrowUpRight size={16} /></ThemeIcon>
              </Group>
              <Text size="xl" fw={700} mt="md">${balance?.total_ingresos.toLocaleString()}</Text>
              <Text size="xs" c="dimmed">Ingresos confirmados ano {currentYear}</Text>
            </Card>

            <Card withBorder padding="lg" radius="md">
              <Group justify="space-between">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>Gastos Operativos</Text>
                <ThemeIcon color="red" variant="light"><IconArrowDownRight size={16} /></ThemeIcon>
              </Group>
              <Text size="xl" fw={700} mt="md">${balance?.total_gastos.toLocaleString()}</Text>
              <Text size="xs" c="dimmed">Obras, sueldos y mantenimiento</Text>
            </Card>

            <Card withBorder padding="lg" radius="md" bg={balance && balance.balance < 0 ? 'red.0' : 'blue.0'}>
              <Group justify="space-between">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>Caja Actual</Text>
                <ThemeIcon color="blue" variant="light"><IconReportMoney size={16} /></ThemeIcon>
              </Group>
              <Text size="xl" fw={700} mt="md">${balance?.balance.toLocaleString()}</Text>
              <Text size="xs" c="dimmed">Saldo disponible en cuenta</Text>
            </Card>
          </SimpleGrid>

          <Paper withBorder p="xl" radius="md" mt="xl">
            <Group justify="space-between" mb="xl">
              <Title order={4}>Presupuesto Asamblea {currentYear}</Title>
              <Button variant="outline">Generar PDF Asamblea</Button>
            </Group>
            <Text c="dimmed" ta="center" py="xl">Area de planificacion presupuestaria en desarrollo...</Text>
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
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {gastos.map((g) => (
                  <Table.Tr key={g.id}>
                    <Table.Td><Text size="sm">{new Date(g.fecha).toLocaleDateString()}</Text></Table.Td>
                    <Table.Td><Text size="sm" fw={500}>{g.descripcion}</Text></Table.Td>
                    <Table.Td>
                      <Badge variant="light" color="gray">{g.categoria.toUpperCase()}</Badge>
                    </Table.Td>
                    <Table.Td><Text fw={700} c="red.7">-${g.monto.toLocaleString()}</Text></Table.Td>
                    <Table.Td>
                      <Text size="xs" c="dimmed">{g.infraestructura?.nombre || '-'}</Text>
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
            <TextInput label="Descripcion del Gasto" placeholder="Ej: Compra de 500L gasoil" required {...form.getInputProps('descripcion')} />
            <SimpleGrid cols={2}>
              <NumberInput label="Monto ($)" placeholder="0.00" required hideControls {...form.getInputProps('monto')} />
              <Select
                label="Categoria"
                data={[
                  { value: 'combustible', label: 'Combustible' },
                  { value: 'maquinaria', label: 'Maquinaria' },
                  { value: 'sueldos', label: 'Sueldos' },
                  { value: 'obras', label: 'Obras' },
                  { value: 'administrativo', label: 'Administrativo' },
                ]}
                {...form.getInputProps('categoria')}
              />
            </SimpleGrid>
            <TextInput type="date" label="Fecha" {...form.getInputProps('fecha')} />
            <Button type="submit" fullWidth mt="md" color="red">Guardar Gasto</Button>
          </Stack>
        </form>
      </Modal>
    </Container>
  );
}
