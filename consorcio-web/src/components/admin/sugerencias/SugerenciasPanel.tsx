import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Center,
  Collapse,
  Container,
  Divider,
  Group,
  Loader,
  Modal,
  Pagination,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Timeline,
  Title,
  Tooltip,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useDebouncedCallback, useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { type Sugerencia, type SugerenciasStats, sugerenciasApi, apiFetch } from '../../../lib/api';
import { formatDate } from '../../../lib/formatters';
import { logger } from '../../../lib/logger';
import { LiveRegionProvider, useLiveRegion } from '../../ui/accessibility';
import { EmptyState } from '../../ui';
import {
  IconCheck,
  IconInfoCircle,
  IconHistory,
  IconPlus,
  IconArrowRight,
  IconCalendar,
  IconCircleCheck,
  IconTrash,
  IconClock,
  IconUsers,
  IconBuilding,
} from '../../ui/icons';

interface SeguimientoEntry {
  id: string;
  estado_anterior: string;
  estado_nuevo: string;
  comentario_publico: string;
  comentario_interno: string;
  fecha: string;
}

const ITEMS_PER_PAGE = 10;

const ESTADO_OPTIONS = [
  { value: 'pendiente', label: 'Pendiente', color: 'yellow' },
  { value: 'en_agenda', label: 'En Agenda', color: 'blue' },
  { value: 'tratado', label: 'Tratado', color: 'green' },
  { value: 'descartado', label: 'Descartado', color: 'gray' },
];

const CATEGORIA_OPTIONS = [
  { value: 'infraestructura', label: 'Infraestructura' },
  { value: 'servicios', label: 'Servicios' },
  { value: 'administrativo', label: 'Administrativo' },
  { value: 'ambiental', label: 'Ambiental' },
  { value: 'otro', label: 'Otro' },
];

const PRIORIDAD_OPTIONS = [
  { value: 'baja', label: 'Baja', color: 'gray' },
  { value: 'normal', label: 'Normal', color: 'blue' },
  { value: 'alta', label: 'Alta', color: 'orange' },
  { value: 'urgente', label: 'Urgente', color: 'red' },
];

interface SugerenciasTableContentProps {
  readonly loading: boolean;
  readonly sugerencias: Sugerencia[];
  readonly totalPages: number;
  readonly page: number;
  readonly onPageChange: (page: number) => void;
  readonly onViewDetail: (sugerencia: Sugerencia) => void;
  readonly getStatusBadge: (status: string) => React.ReactNode;
}

function SugerenciasTableContent({
  loading,
  sugerencias,
  totalPages,
  page,
  onPageChange,
  onViewDetail,
  getStatusBadge,
}: SugerenciasTableContentProps) {
  if (loading) {
    return (
      <Center py="xl">
        <Stack align="center" gap="md">
          <Loader />
          <Text size="sm" c="gray.6">Cargando sugerencias...</Text>
        </Stack>
      </Center>
    );
  }

  if (sugerencias.length === 0) {
    return (
      <EmptyState
        title="No hay sugerencias"
        description="No se encontraron sugerencias con los filtros aplicados"
      />
    );
  }

  return (
    <>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Fecha</Table.Th>
            <Table.Th>Titulo</Table.Th>
            <Table.Th>Categoria</Table.Th>
            <Table.Th>Tipo</Table.Th>
            <Table.Th>Estado</Table.Th>
            <Table.Th>Acciones</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sugerencias.map((sug) => (
            <Table.Tr key={sug.id}>
              <Table.Td>
                <Text size="sm">{formatDate(sug.created_at)}</Text>
              </Table.Td>
              <Table.Td>
                <Text size="sm" lineClamp={1} style={{ maxWidth: 250 }}>
                  {sug.titulo}
                </Text>
              </Table.Td>
              <Table.Td>
                <Badge variant="outline" size="sm">
                  {CATEGORIA_OPTIONS.find((c) => c.value === sug.categoria)?.label || sug.categoria || 'Sin categoria'}
                </Badge>
              </Table.Td>
              <Table.Td>
                <Badge color={sug.tipo === 'ciudadana' ? 'blue' : 'violet'} size="sm" variant="light">
                  {sug.tipo === 'ciudadana' ? 'Ciudadana' : 'Interna'}
                </Badge>
              </Table.Td>
              <Table.Td>{getStatusBadge(sug.estado)}</Table.Td>
              <Table.Td>
                <Tooltip label="Ver detalle">
                  <ActionIcon variant="light" onClick={() => onViewDetail(sug)}>
                    <IconInfoCircle size={18} />
                  </ActionIcon>
                </Tooltip>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      {totalPages > 1 && (
        <Group justify="center" mt="md">
          <Pagination total={totalPages} value={page} onChange={onPageChange} />
        </Group>
      )}
    </>
  );
}

// Stats Card Component
function StatsCard({
  label,
  value,
  color,
  icon: Icon
}: {
  label: string;
  value: number;
  color: string;
  icon: React.ComponentType<{ size?: number }>;
}) {
  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      <Group justify="space-between">
        <div>
          <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
            {label}
          </Text>
          <Text size="xl" fw={700}>
            {value}
          </Text>
        </div>
        <ThemeIcon color={color} size="lg" radius="md" variant="light">
          <Icon size={20} />
        </ThemeIcon>
      </Group>
    </Card>
  );
}

export default function SugerenciasPanel() {
  const [sugerencias, setSugerencias] = useState<Sugerencia[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSugerencia, setSelectedSugerencia] = useState<Sugerencia | null>(null);
  const [detailOpened, { open: openDetail, close: closeDetail }] = useDisclosure(false);

  // Stats from API
  const [stats, setStats] = useState<SugerenciasStats | null>(null);
  const [_loadingStats, setLoadingStats] = useState(true);

  // Proxima reunion
  const [proximaReunion, setProximaReunion] = useState<Sugerencia[]>([]);
  const [_loadingProxima, setLoadingProxima] = useState(true);

  // Create internal modal
  const [createOpened, { open: openCreate, close: closeCreate }] = useDisclosure(false);
  const [newTitulo, setNewTitulo] = useState('');
  const [newDescripcion, setNewDescripcion] = useState('');
  const [newCategoria, setNewCategoria] = useState<string | null>(null);
  const [newPrioridad, setNewPrioridad] = useState<string>('normal');
  const [creating, setCreating] = useState(false);

  // Filters
  const [filterEstado, setFilterEstado] = useState<string | null>(null);
  const [filterTipo, setFilterTipo] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInputValue, setSearchInputValue] = useState('');

  const debouncedSetSearch = useDebouncedCallback((value: string) => {
    setSearchQuery(value);
  }, 300);

  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Edit state
  const [newEstado, setNewEstado] = useState<string>('');
  const [adminNotes, setAdminNotes] = useState('');
  const [publicComment, setPublicComment] = useState('');
  const [updating, setUpdating] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Agendar state
  const [agendarFecha, setAgendarFecha] = useState<Date | null>(null);
  const [agendando, setAgendando] = useState(false);

  // Historial state
  const [historial, setHistorial] = useState<SeguimientoEntry[]>([]);
  const [loadingHistorial, setLoadingHistorial] = useState(false);
  const [showHistorial, setShowHistorial] = useState(false);

  const { announce } = useLiveRegion();
  const announceRef = useRef(announce);
  announceRef.current = announce;

  // Load stats
  const loadStats = useCallback(async () => {
    setLoadingStats(true);
    try {
      const data = await sugerenciasApi.getStats();
      setStats(data);
    } catch (error) {
      logger.error('Error loading stats:', error);
    } finally {
      setLoadingStats(false);
    }
  }, []);

  // Load proxima reunion
  const loadProximaReunion = useCallback(async () => {
    setLoadingProxima(true);
    try {
      const data = await sugerenciasApi.getProximaReunion();
      setProximaReunion(data);
    } catch (error) {
      logger.error('Error loading proxima reunion:', error);
    } finally {
      setLoadingProxima(false);
    }
  }, []);

  const loadSugerencias = useCallback(async () => {
    setLoading(true);
    try {
      const data = await sugerenciasApi.getAll({
        page,
        limit: ITEMS_PER_PAGE,
        estado: filterEstado || undefined,
        tipo: filterTipo || undefined,
      });
      setSugerencias(data.items);
      setTotalPages(Math.ceil(data.total / ITEMS_PER_PAGE));
    } catch (error) {
      logger.error('Error loading sugerencias:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudieron cargar las sugerencias',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  }, [page, filterEstado, filterTipo]);

  // Load all data on mount
  useEffect(() => {
    loadStats();
    loadProximaReunion();
  }, [loadStats, loadProximaReunion]);

  useEffect(() => {
    loadSugerencias();
  }, [loadSugerencias]);

  const refreshAll = useCallback(() => {
    loadSugerencias();
    loadStats();
    loadProximaReunion();
  }, [loadSugerencias, loadStats, loadProximaReunion]);

  const loadHistory = async (id: string) => {
    setLoadingHistorial(true);
    try {
      const data = await apiFetch<SeguimientoEntry[]>(`/management/seguimiento/sugerencia/${id}`);
      setHistorial(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingHistorial(false);
    }
  };

  const handleViewDetail = (sug: Sugerencia) => {
    setSelectedSugerencia(sug);
    setNewEstado(sug.estado);
    setAdminNotes('');
    setPublicComment('');
    setAgendarFecha(sug.fecha_reunion ? new Date(sug.fecha_reunion) : null);
    setHistorial([]);
    setShowHistorial(false);
    loadHistory(sug.id);
    openDetail();
  };

  const handleUpdate = async () => {
    if (!selectedSugerencia) return;

    setUpdating(true);
    try {
      // 1. Create tracking entry (this updates suggestion status in backend via universal management service)
      await apiFetch('/management/seguimiento', {
        method: 'POST',
        body: JSON.stringify({
          entidad_tipo: 'sugerencia',
          entidad_id: selectedSugerencia.id,
          estado_anterior: selectedSugerencia.estado,
          estado_nuevo: newEstado,
          comentario_interno: adminNotes,
          comentario_publico: publicComment
        })
      });

      notifications.show({
        title: 'Sugerencia actualizada',
        message: 'El historial de gestión ha sido registrado',
        color: 'green',
        icon: <IconCheck size={16} />,
      });
      closeDetail();
      refreshAll();
    } catch (error) {
      logger.error('Error updating sugerencia:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo actualizar la sugerencia',
        color: 'red',
      });
    } finally {
      setUpdating(false);
    }
  };

  const handleAgendar = async () => {
    if (!selectedSugerencia || !agendarFecha) return;

    setAgendando(true);
    try {
      const fechaStr = agendarFecha.toISOString().split('T')[0];
      await sugerenciasApi.agendar(selectedSugerencia.id, fechaStr);
      notifications.show({
        title: 'Sugerencia agendada',
        message: `Agendada para el ${formatDate(fechaStr)}`,
        color: 'blue',
        icon: <IconCalendar size={16} />,
      });
      closeDetail();
      refreshAll();
    } catch (error) {
      logger.error('Error agendando sugerencia:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo agendar la sugerencia',
        color: 'red',
      });
    } finally {
      setAgendando(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedSugerencia) return;

    setDeleting(true);
    try {
      await sugerenciasApi.delete(selectedSugerencia.id);
      notifications.show({
        title: 'Sugerencia eliminada',
        message: 'La sugerencia fue eliminada correctamente',
        color: 'green',
        icon: <IconTrash size={16} />,
      });
      closeDetail();
      refreshAll();
    } catch (error) {
      logger.error('Error deleting sugerencia:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo eliminar la sugerencia',
        color: 'red',
      });
    } finally {
      setDeleting(false);
    }
  };

  const handleCreateInternal = async () => {
    if (!newTitulo.trim() || !newDescripcion.trim()) {
      notifications.show({
        title: 'Error',
        message: 'Titulo y descripcion son requeridos',
        color: 'red',
      });
      return;
    }

    setCreating(true);
    try {
      await sugerenciasApi.createInternal({
        titulo: newTitulo.trim(),
        descripcion: newDescripcion.trim(),
        categoria: newCategoria || undefined,
        prioridad: newPrioridad,
      });
      notifications.show({
        title: 'Tema creado',
        message: 'El tema interno fue creado correctamente',
        color: 'green',
        icon: <IconCheck size={16} />,
      });
      closeCreate();
      setNewTitulo('');
      setNewDescripcion('');
      setNewCategoria(null);
      setNewPrioridad('normal');
      refreshAll();
    } catch (error) {
      logger.error('Error creating internal:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo crear el tema interno',
        color: 'red',
      });
    } finally {
      setCreating(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const option = ESTADO_OPTIONS.find((o) => o.value === status);
    return (
      <Badge color={option?.color || 'gray'} variant="light">
        {option?.label || status}
      </Badge>
    );
  };

  const _getHistorialIcon = (_accion: string) => {
    switch (_accion) {
      case 'creado':
        return <IconPlus size={14} />;
      case 'agendado':
        return <IconCalendar size={14} />;
      case 'resuelto':
        return <IconCircleCheck size={14} />;
      default:
        return <IconArrowRight size={14} />;
    }
  };

  const _getHistorialColor = (_accion: string): string => {
    switch (_accion) {
      case 'creado':
        return 'blue';
      case 'agendado':
        return 'violet';
      case 'resuelto':
        return 'green';
      default:
        return 'gray';
    }
  };

  const _getAccionLabel = (_accion: string): string => {
    switch (_accion) {
      case 'creado':
        return 'Sugerencia creada';
      case 'agendado':
        return 'Agendada para reunion';
      case 'resuelto':
        return 'Marcada como resuelta';
      case 'estado_cambiado':
        return 'Estado actualizado';
      default:
        return _accion;
    }
  };

  // Filter sugerencias by search query
  const filteredSugerencias = useMemo(() => {
    if (!searchQuery) return sugerencias;
    const query = searchQuery.toLowerCase();
    return sugerencias.filter(
      (sug) =>
        sug.titulo.toLowerCase().includes(query) ||
        sug.descripcion.toLowerCase().includes(query)
    );
  }, [sugerencias, searchQuery]);

  return (
    <LiveRegionProvider>
      <Container size="xl" py="md">
        <Group justify="space-between" mb="xl">
          <div>
            <Title order={2}>Gestion de Sugerencias</Title>
            <Text c="gray.6">Administra las sugerencias ciudadanas y de la comision</Text>
          </div>
          <Button leftSection={<IconPlus size={16} />} onClick={openCreate}>
            Nuevo Tema Interno
          </Button>
        </Group>

        {/* Stats Cards */}
        <SimpleGrid cols={{ base: 2, sm: 4 }} mb="xl">
          <StatsCard
            label="Pendientes"
            value={stats?.pendiente ?? 0}
            color="yellow"
            icon={IconClock}
          />
          <StatsCard
            label="En Agenda"
            value={stats?.en_agenda ?? 0}
            color="blue"
            icon={IconCalendar}
          />
          <StatsCard
            label="Ciudadanas"
            value={stats?.ciudadanas ?? 0}
            color="cyan"
            icon={IconUsers}
          />
          <StatsCard
            label="Internas"
            value={stats?.internas ?? 0}
            color="violet"
            icon={IconBuilding}
          />
        </SimpleGrid>

        {/* Proxima Reunion Section */}
        {proximaReunion.length > 0 && (
          <Paper shadow="sm" p="lg" radius="md" mb="xl" withBorder style={{ borderColor: 'var(--mantine-color-blue-3)' }}>
            <Group gap="xs" mb="md">
              <ThemeIcon color="blue" size="md" variant="light">
                <IconCalendar size={16} />
              </ThemeIcon>
              <Title order={4}>Temas para Proxima Reunion</Title>
              <Badge color="blue" variant="light">{proximaReunion.length} temas</Badge>
            </Group>
            <Stack gap="xs">
              {proximaReunion.map((sug) => (
                <Paper
                  key={sug.id}
                  p="sm"
                  radius="sm"
                  style={{ background: 'light-dark(var(--mantine-color-blue-0), var(--mantine-color-dark-6))', cursor: 'pointer' }}
                  onClick={() => handleViewDetail(sug)}
                >
                  <Group justify="space-between">
                    <div style={{ flex: 1 }}>
                      <Group gap="xs">
                        <Text size="sm" fw={500}>{sug.titulo}</Text>
                        <Badge size="xs" color={sug.tipo === 'ciudadana' ? 'blue' : 'violet'} variant="light">
                          {sug.tipo === 'ciudadana' ? 'Ciudadana' : 'Interna'}
                        </Badge>
                        {sug.prioridad !== 'normal' && (
                          <Badge size="xs" color={PRIORIDAD_OPTIONS.find(p => p.value === sug.prioridad)?.color || 'gray'} variant="dot">
                            {PRIORIDAD_OPTIONS.find(p => p.value === sug.prioridad)?.label || sug.prioridad}
                          </Badge>
                        )}
                      </Group>
                      <Text size="xs" c="dimmed" lineClamp={1}>{sug.descripcion}</Text>
                    </div>
                    {sug.fecha_reunion && (
                      <Badge color="blue" variant="outline" size="sm">
                        {formatDate(sug.fecha_reunion)}
                      </Badge>
                    )}
                  </Group>
                </Paper>
              ))}
            </Stack>
          </Paper>
        )}

        {/* Filters */}
        <Paper shadow="sm" p="md" radius="md" mb="md">
          <Group>
            <TextInput
              placeholder="Buscar..."
              value={searchInputValue}
              onChange={(e) => {
                setSearchInputValue(e.target.value);
                debouncedSetSearch(e.target.value);
              }}
              style={{ flex: 1 }}
            />
            <Select
              placeholder="Estado"
              data={[{ value: '', label: 'Todos' }, ...ESTADO_OPTIONS]}
              value={filterEstado}
              onChange={setFilterEstado}
              clearable
              w={150}
            />
            <Select
              placeholder="Tipo"
              data={[
                { value: '', label: 'Todos' },
                { value: 'ciudadana', label: 'Ciudadana' },
                { value: 'interna', label: 'Interna' },
              ]}
              value={filterTipo}
              onChange={setFilterTipo}
              clearable
              w={150}
            />
            <Button variant="light" onClick={refreshAll}>
              Actualizar
            </Button>
          </Group>
        </Paper>

        {/* Table */}
        <Paper shadow="sm" p="lg" radius="md">
          <SugerenciasTableContent
            loading={loading}
            sugerencias={filteredSugerencias}
            totalPages={totalPages}
            page={page}
            onPageChange={setPage}
            onViewDetail={handleViewDetail}
            getStatusBadge={getStatusBadge}
          />
        </Paper>

        {/* Detail Modal */}
        <Modal opened={detailOpened} onClose={closeDetail} title="Detalle de Sugerencia" size="lg">
          {selectedSugerencia && (
            <Stack gap="md">
              <div>
                <Text size="sm" fw={500}>Titulo</Text>
                <Text>{selectedSugerencia.titulo}</Text>
              </div>

              <div>
                <Text size="sm" fw={500}>Descripcion</Text>
                <Paper p="sm" style={{ background: 'light-dark(var(--mantine-color-gray-1), var(--mantine-color-dark-6))' }} radius="sm">
                  <Text size="sm">{selectedSugerencia.descripcion}</Text>
                </Paper>
              </div>

              <Group>
                <div>
                  <Text size="sm" fw={500}>Categoria</Text>
                  <Badge variant="outline">
                    {CATEGORIA_OPTIONS.find((c) => c.value === selectedSugerencia.categoria)?.label || 'Sin categoria'}
                  </Badge>
                </div>
                <div>
                  <Text size="sm" fw={500}>Tipo</Text>
                  <Badge color={selectedSugerencia.tipo === 'ciudadana' ? 'blue' : 'violet'} variant="light">
                    {selectedSugerencia.tipo === 'ciudadana' ? 'Ciudadana' : 'Interna'}
                  </Badge>
                </div>
                <div>
                  <Text size="sm" fw={500}>Fecha</Text>
                  <Text size="sm" c="gray.6">{formatDate(selectedSugerencia.created_at)}</Text>
                </div>
              </Group>

              {selectedSugerencia.contacto_nombre && (
                <div>
                  <Text size="sm" fw={500}>Contacto</Text>
                  <Text size="sm" c="gray.6">
                    {selectedSugerencia.contacto_nombre}
                    {selectedSugerencia.contacto_email && ` - ${selectedSugerencia.contacto_email}`}
                    {selectedSugerencia.contacto_telefono && ` - ${selectedSugerencia.contacto_telefono}`}
                  </Text>
                </div>
              )}

              {/* Historial section */}
              <Paper p="md" style={{ background: 'light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-6))' }} radius="md">
                <Group justify="space-between" mb="sm">
                  <Group gap="xs">
                    <IconHistory size={18} />
                    <Text size="sm" fw={600}>Historial de Gestión</Text>
                  </Group>
                  <Button
                    variant="subtle"
                    size="xs"
                    onClick={() => setShowHistorial(!showHistorial)}
                    loading={loadingHistorial}
                  >
                    {showHistorial ? 'Ocultar' : 'Mostrar'} ({historial.length})
                  </Button>
                </Group>

                <Collapse in={showHistorial}>
                  {historial.length === 0 ? (
                    <Text size="sm" c="dimmed" ta="center" py="md">
                      {loadingHistorial ? 'Cargando historial...' : 'Sin historial disponible'}
                    </Text>
                  ) : (
                    <Timeline active={0} lineWidth={2}>
                      {historial.map((entry) => (
                        <Timeline.Item 
                          key={entry.id} 
                          title={`Cambio a ${entry.estado_nuevo.replace('_', ' ').toUpperCase()}`}
                        >
                          <Text size="xs" fw={500}>{entry.comentario_publico}</Text>
                          {entry.comentario_interno && (
                            <Text size="xs" c="blue" fs="italic">Interno: {entry.comentario_interno}</Text>
                          )}
                          <Text size="xs" c="dimmed" mt={2}>{formatDate(entry.fecha)}</Text>
                        </Timeline.Item>
                      ))}
                      <Timeline.Item title="Sugerencia Creada">
                        <Text size="xs" mt={2}>Ingresada al sistema</Text>
                      </Timeline.Item>
                    </Timeline>
                  )}
                </Collapse>
              </Paper>

              {/* Agendar section */}
              {selectedSugerencia.estado === 'pendiente' && (
                <Paper p="md" style={{ background: 'light-dark(var(--mantine-color-violet-0), var(--mantine-color-dark-5))' }} radius="md">
                  <Text size="sm" fw={600} mb="md">Agendar para Reunion</Text>
                  <Group>
                    <DatePickerInput
                      label="Fecha de reunion"
                      placeholder="Seleccionar fecha"
                      value={agendarFecha}
                      onChange={setAgendarFecha}
                      minDate={new Date()}
                      style={{ flex: 1 }}
                    />
                    <Button
                      color="violet"
                      onClick={handleAgendar}
                      loading={agendando}
                      disabled={!agendarFecha}
                      mt={24}
                    >
                      Agendar
                    </Button>
                  </Group>
                </Paper>
              )}

              {/* Admin section */}
              <Paper p="md" style={{ background: 'light-dark(var(--mantine-color-blue-0), var(--mantine-color-dark-5))' }} radius="md">
                <Title order={6} size="sm" fw={600} mb="md">Gestión de la sugerencia</Title>
                <Stack gap="sm">
                  <Select
                    label="Cambiar Estado"
                    data={ESTADO_OPTIONS}
                    value={newEstado}
                    onChange={(v) => setNewEstado(v || 'pendiente')}
                  />
                  
                  <Textarea
                    label="Comentario Público"
                    placeholder="Lo que el vecino verá en su seguimiento..."
                    value={publicComment}
                    onChange={(e) => setPublicComment(e.target.value)}
                    minRows={2}
                  />

                  <Textarea
                    label="Notas Internas (Consorcio)"
                    placeholder="Detalles de la discusión en comisión, presupuesto, etc..."
                    value={adminNotes}
                    onChange={(e) => setAdminNotes(e.target.value)}
                    minRows={2}
                  />
                </Stack>
              </Paper>

              <Divider />

              <Group justify="space-between">
                <Button
                  variant="light"
                  color="red"
                  leftSection={<IconTrash size={16} />}
                  onClick={handleDelete}
                  loading={deleting}
                >
                  Eliminar
                </Button>
                <Group>
                  <Button variant="light" onClick={closeDetail}>Cancelar</Button>
                  <Button onClick={handleUpdate} loading={updating}>Registrar Gestión</Button>
                </Group>
              </Group>
            </Stack>
          )}
        </Modal>

        {/* Create Internal Modal */}
        <Modal opened={createOpened} onClose={closeCreate} title="Nuevo Tema Interno" size="md">
          <Stack gap="md">
            <TextInput
              label="Titulo"
              placeholder="Titulo del tema"
              value={newTitulo}
              onChange={(e) => setNewTitulo(e.target.value)}
              required
            />
            <Textarea
              label="Descripcion"
              placeholder="Describe el tema a tratar..."
              value={newDescripcion}
              onChange={(e) => setNewDescripcion(e.target.value)}
              minRows={4}
              required
            />
            <Group grow>
              <Select
                label="Categoria"
                placeholder="Seleccionar"
                data={CATEGORIA_OPTIONS}
                value={newCategoria}
                onChange={setNewCategoria}
                clearable
              />
              <Select
                label="Prioridad"
                data={PRIORIDAD_OPTIONS}
                value={newPrioridad}
                onChange={(v) => setNewPrioridad(v || 'normal')}
              />
            </Group>
            <Group justify="flex-end" mt="md">
              <Button variant="light" onClick={closeCreate}>Cancelar</Button>
              <Button onClick={handleCreateInternal} loading={creating}>
                Crear Tema
              </Button>
            </Group>
          </Stack>
        </Modal>
      </Container>
    </LiveRegionProvider>
  );
}
