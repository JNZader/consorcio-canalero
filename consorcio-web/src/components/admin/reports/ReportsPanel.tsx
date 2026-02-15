import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Container,
  Group,
  Image,
  Loader,
  Modal,
  Pagination,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Timeline,
  Title,
  Tooltip,
} from '@mantine/core';
import { useDebouncedCallback, useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { STATUS_OPTIONS, CATEGORY_OPTIONS } from '../../../constants';
import { type Report, reportsApi, apiFetch } from '../../../lib/api';
import { formatDate } from '../../../lib/formatters';
import { logger } from '../../../lib/logger';
import { LiveRegionProvider, useLiveRegion } from '../../ui/accessibility';
import { EmptyState } from '../../ui';
import { IconInfoCircle, IconMap, IconHistory } from '../../ui/icons';

interface SeguimientoEntry {
  id: string;
  estado_anterior: string;
  estado_nuevo: string;
  comentario_publico: string;
  comentario_interno: string;
  fecha: string;
}

/** Items per page constant - defined outside component to avoid recreating on each render */
const ITEMS_PER_PAGE = 10;

/**
 * Component to render the reports table content based on loading state and data.
 * Avoids nested ternary operators (SonarQube S3358).
 */
interface ReportsTableContentProps {
  readonly loading: boolean;
  readonly filteredReports: Report[];
  readonly totalPages: number;
  readonly page: number;
  readonly onPageChange: (page: number) => void;
  readonly onViewDetail: (report: Report) => void;
  readonly getStatusBadge: (status: string) => React.ReactNode;
}

function ReportsTableContent({
  loading,
  filteredReports,
  totalPages,
  page,
  onPageChange,
  onViewDetail,
  getStatusBadge,
}: ReportsTableContentProps) {
  if (loading) {
    return (
      <Center py="xl" aria-busy="true" aria-live="polite">
        <Stack align="center" gap="md">
          <Loader aria-hidden="true" />
          <Text size="sm" c="gray.6">
            Cargando denuncias...
          </Text>
        </Stack>
      </Center>
    );
  }

  if (filteredReports.length > 0) {
    return (
      <Box aria-live="polite">
        <Table striped highlightOnHover aria-label="Tabla de denuncias">
          <caption
            style={{
              position: 'absolute',
              width: 1,
              height: 1,
              padding: 0,
              margin: -1,
              overflow: 'hidden',
              clip: 'rect(0, 0, 0, 0)',
              whiteSpace: 'nowrap',
              border: 0,
            }}
          >
            Lista de denuncias ciudadanas con fecha, categoria, descripcion, ubicacion, estado y
            acciones disponibles
          </caption>
          <Table.Thead>
            <Table.Tr>
              <Table.Th scope="col">Fecha</Table.Th>
              <Table.Th scope="col">Categoria</Table.Th>
              <Table.Th scope="col">Descripcion</Table.Th>
              <Table.Th scope="col">Ubicacion</Table.Th>
              <Table.Th scope="col">Estado</Table.Th>
              <Table.Th scope="col">Acciones</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filteredReports.map((report) => (
              <Table.Tr key={report.id}>
                <Table.Td>
                  <Text size="sm">{formatDate(report.created_at, { includeTime: true })}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge variant="outline">
                    {CATEGORY_OPTIONS.find((c) => c.value === report.categoria)?.label ||
                      report.categoria}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" lineClamp={2} style={{ maxWidth: 300 }}>
                    {report.descripcion}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="gray.6" lineClamp={1} style={{ maxWidth: 200 }}>
                    {report.ubicacion_texto || 'Sin direccion'}
                  </Text>
                </Table.Td>
                <Table.Td>{getStatusBadge(report.estado)}</Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <Tooltip label="Ver detalle">
                      <ActionIcon
                        variant="light"
                        onClick={() => onViewDetail(report)}
                        aria-label={`Ver detalle de denuncia del ${formatDate(report.created_at)}`}
                      >
                        <IconInfoCircle size={18} />
                      </ActionIcon>
                    </Tooltip>
                    {report.latitud != null && report.longitud != null && (
                      <Tooltip label="Ver en mapa">
                        <ActionIcon
                          variant="light"
                          color="blue"
                          component="a"
                          href={`/mapa?lat=${report.latitud}&lng=${report.longitud}&zoom=15`}
                          aria-label={`Ver ubicacion de denuncia en el mapa, coordenadas ${report.latitud}, ${report.longitud}`}
                        >
                          <IconMap size={18} />
                        </ActionIcon>
                      </Tooltip>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>

        {totalPages > 1 && (
          <Group justify="center" mt="md">
            <Pagination
              total={totalPages}
              value={page}
              onChange={onPageChange}
              aria-label="Paginacion de denuncias"
              getItemProps={(page) => ({
                'aria-label': `Ir a pagina ${page}`,
              })}
              getControlProps={(control) => {
                if (control === 'first') {
                  return { 'aria-label': 'Ir a primera pagina' };
                }
                if (control === 'last') {
                  return { 'aria-label': 'Ir a ultima pagina' };
                }
                if (control === 'next') {
                  return { 'aria-label': 'Ir a siguiente pagina' };
                }
                if (control === 'previous') {
                  return { 'aria-label': 'Ir a pagina anterior' };
                }
                return {};
              }}
            />
          </Group>
        )}
      </Box>
    );
  }

  return (
    <EmptyState
      title="No hay denuncias"
      description="No se encontraron denuncias con los filtros aplicados"
    />
  );
}

export default function ReportsPanel() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [detailOpened, { open: openDetail, close: closeDetail }] = useDisclosure(false);
  const [history, setHistory] = useState<SeguimientoEntry[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Filters
  const [filterStatus, setFilterStatus] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInputValue, setSearchInputValue] = useState('');

  // Debounced search to avoid excessive API calls
  const debouncedSetSearch = useDebouncedCallback((value: string) => {
    setSearchQuery(value);
  }, 300);

  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Edit state
  const [newStatus, setNewStatus] = useState<string>('');
  const [adminNotes, setAdminNotes] = useState('');
  const [publicComment, setPublicComment] = useState('');
  const [updating, setUpdating] = useState(false);

  // Hook para anuncios de accesibilidad
  const { announce } = useLiveRegion();
  // Use ref to avoid recreating loadReports on announce changes
  const announceRef = useRef(announce);
  announceRef.current = announce;

  const loadReports = useCallback(async () => {
    setLoading(true);
    announceRef.current('Cargando reportes...');
    try {
      const data = await reportsApi.getAll(page, ITEMS_PER_PAGE, filterStatus || undefined);
      setReports(data.items);
      setTotalPages(Math.ceil(data.total / ITEMS_PER_PAGE));
      announceRef.current(`${data.items.length} reportes cargados`);
    } catch (error) {
      logger.error('Error loading reports:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudieron cargar los reportes',
        color: 'red',
      });
      announceRef.current('Error al cargar los reportes');
    } finally {
      setLoading(false);
    }
  }, [page, filterStatus]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  const loadHistory = async (id: string) => {
    setLoadingHistory(true);
    try {
      const data = await apiFetch<SeguimientoEntry[]>(`/management/seguimiento/reporte/${id}`);
      setHistory(data);
    } catch (err) {
      logger.error('Error loading report history:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleViewDetail = (report: Report) => {
    setSelectedReport(report);
    setNewStatus(report.estado);
    setAdminNotes('');
    setPublicComment('');
    loadHistory(report.id);
    openDetail();
  };

  const handleUpdateStatus = async () => {
    if (!selectedReport) return;

    setUpdating(true);
    try {
      // 1. Create tracking entry (this also updates report status in backend)
      await apiFetch('/management/seguimiento', {
        method: 'POST',
        body: JSON.stringify({
          entidad_tipo: 'reporte',
          entidad_id: selectedReport.id,
          estado_anterior: selectedReport.estado,
          estado_nuevo: newStatus,
          comentario_interno: adminNotes,
          comentario_publico: publicComment
        })
      });

      notifications.show({
        title: 'Reporte actualizado',
        message: 'El historial de gestion ha sido registrado',
        color: 'green',
      });
      announceRef.current('Reporte actualizado correctamente');
      closeDetail();
      loadReports();
    } catch (error) {
      logger.error('Error al actualizar reporte:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo actualizar el reporte',
        color: 'red',
      });
      announceRef.current('Error al actualizar el reporte');
    } finally {
      setUpdating(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const option = STATUS_OPTIONS.find((o) => o.value === status);
    return (
      <Badge color={option?.color || 'gray'} variant="light">
        {option?.label || status}
      </Badge>
    );
  };

  // Memoized filtering and stats calculation (single pass)
  const { filteredReports, pendingCount, inReviewCount } = useMemo(() => {
    let pending = 0;
    let inReview = 0;

    const filtered = reports.filter((report) => {
      // Count stats during filtering (single iteration)
      if (report.estado === 'pendiente') pending++;
      if (report.estado === 'en_revision') inReview++;

      // Apply filters
      if (filterCategory && report.categoria !== filterCategory) return false;
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        return (
          report.descripcion.toLowerCase().includes(query) ||
          report.ubicacion_texto?.toLowerCase().includes(query)
        );
      }
      return true;
    });

    return { filteredReports: filtered, pendingCount: pending, inReviewCount: inReview };
  }, [reports, filterCategory, searchQuery]);

  return (
    <LiveRegionProvider>
      <Container size="xl" py="md">
        <Group justify="space-between" mb="xl">
          <div>
            <Title order={2}>Gestion de Denuncias</Title>
            <Text c="gray.6">Administra las denuncias ciudadanas</Text>
          </div>
          <Group>
            <Badge size="lg" color="yellow" variant="light">
              {pendingCount} pendientes
            </Badge>
            <Badge size="lg" color="blue" variant="light">
              {inReviewCount} en revision
            </Badge>
          </Group>
        </Group>

        {/* Filters */}
        <Paper shadow="sm" p="md" radius="md" mb="md">
          <Group role="search" aria-label="Filtros de busqueda de denuncias">
            <TextInput
              placeholder="Buscar..."
              value={searchInputValue}
              onChange={(e) => {
                setSearchInputValue(e.target.value);
                debouncedSetSearch(e.target.value);
              }}
              style={{ flex: 1 }}
              aria-label="Buscar denuncias por descripcion o ubicacion"
            />
            <Select
              placeholder="Estado"
              data={[{ value: '', label: 'Todos' }, ...STATUS_OPTIONS]}
              value={filterStatus}
              onChange={setFilterStatus}
              clearable
              w={150}
              aria-label="Filtrar por estado de la denuncia"
            />
            <Select
              placeholder="Categoria"
              data={[{ value: '', label: 'Todas' }, ...CATEGORY_OPTIONS]}
              value={filterCategory}
              onChange={setFilterCategory}
              clearable
              w={150}
              aria-label="Filtrar por categoria de la denuncia"
            />
            <Button variant="light" onClick={loadReports} aria-label="Actualizar lista de denuncias">
              Actualizar
            </Button>
          </Group>
        </Paper>

        {/* Reports Table */}
        <Paper shadow="sm" p="lg" radius="md">
          <ReportsTableContent
            loading={loading}
            filteredReports={filteredReports}
            totalPages={totalPages}
            page={page}
            onPageChange={setPage}
            onViewDetail={handleViewDetail}
            getStatusBadge={getStatusBadge}
          />
        </Paper>

        {/* Detail Modal */}
        <Modal
          opened={detailOpened}
          onClose={closeDetail}
          title="Detalle de Denuncia"
          size="lg"
          aria-labelledby="modal-title-detail"
        >
          {selectedReport && (
            <Stack gap="md">
              {/* Report info */}
              <SimpleGrid cols={2}>
                <div>
                  <Text size="sm" fw={500}>
                    Fecha
                  </Text>
                  <Text size="sm" c="gray.6">
                    {formatDate(selectedReport.created_at, { includeTime: true })}
                  </Text>
                </div>
                <div>
                  <Text size="sm" fw={500}>
                    Categoria
                  </Text>
                  <Badge variant="outline">
                    {CATEGORY_OPTIONS.find((c) => c.value === selectedReport.categoria)?.label ||
                      selectedReport.categoria}
                  </Badge>
                </div>
              </SimpleGrid>

              <div>
                <Text size="sm" fw={500} id="descripcion-label">
                  Descripcion
                </Text>
                <Paper
                  p="sm"
                  style={{
                    background:
                      'light-dark(var(--mantine-color-gray-1), var(--mantine-color-dark-6))',
                  }}
                  radius="sm"
                  aria-labelledby="descripcion-label"
                >
                  <Text size="sm">{selectedReport.descripcion}</Text>
                </Paper>
              </div>

              {selectedReport.ubicacion_texto && (
                <div>
                  <Text size="sm" fw={500}>
                    Ubicacion
                  </Text>
                  <Text size="sm" c="gray.6">
                    {selectedReport.ubicacion_texto}
                  </Text>
                  {selectedReport.latitud != null && selectedReport.longitud != null && (
                    <Text size="xs" c="gray.6">
                      Coordenadas: {selectedReport.latitud}, {selectedReport.longitud}
                    </Text>
                  )}
                </div>
              )}

              {/* Images */}
              {selectedReport.imagenes && selectedReport.imagenes.length > 0 && (
                <div>
                  <Text size="sm" fw={500} mb="xs" id="imagenes-label">
                    Imagenes adjuntas
                  </Text>
                  <SimpleGrid cols={3} aria-labelledby="imagenes-label">
                    {selectedReport.imagenes.map((url) => (
                      <Card key={url} padding={0} radius="sm">
                        <Image
                          src={url}
                          alt={`Imagen de la denuncia sobre ${selectedReport.categoria || 'problema reportado'} en ${selectedReport.ubicacion_texto || 'ubicacion no especificada'}`}
                          height={100}
                          fit="cover"
                        />
                      </Card>
                    ))}
                  </SimpleGrid>
                </div>
              )}

              {/* Contact info */}
              {(selectedReport.contacto_nombre || selectedReport.contacto_telefono) && (
                <div>
                  <Text size="sm" fw={500}>
                    Contacto
                  </Text>
                  <Text size="sm" c="gray.6">
                    {selectedReport.contacto_nombre}
                    {selectedReport.contacto_telefono && ` - ${selectedReport.contacto_telefono}`}
                  </Text>
                </div>
              )}

              {/* Admin section */}
              <Paper
                p="md"
                style={{
                  background: 'light-dark(var(--mantine-color-blue-0), var(--mantine-color-dark-5))',
                }}
                radius="md"
              >
                <Title order={6} mb="md" id="admin-section-label">
                  Gestion del reporte
                </Title>

                <Stack gap="sm" aria-labelledby="admin-section-label">
                  <Select
                    label="Cambiar Estado"
                    data={STATUS_OPTIONS}
                    value={newStatus}
                    onChange={(v) => setNewStatus(v || 'pendiente')}
                  />

                  <Textarea
                    label="Comentario Publico"
                    placeholder="Lo que el ciudadano vera..."
                    value={publicComment}
                    onChange={(e) => setPublicComment(e.target.value)}
                    minRows={2}
                  />

                  <Textarea
                    label="Notas Internas (Consorcio)"
                    placeholder="Detalles tecnicos, costos, etc..."
                    value={adminNotes}
                    onChange={(e) => setAdminNotes(e.target.value)}
                    minRows={2}
                  />
                </Stack>
              </Paper>

              {/* Trazabilidad / Timeline */}
              <div>
                <Group gap="xs" mb="sm">
                  <IconHistory size={18} />
                  <Text fw={600} size="sm">Historial de Seguimiento</Text>
                </Group>

                {loadingHistory ? <Loader size="sm" /> : (
                  <Timeline active={0} lineWidth={2}>
                    {history.map((entry) => (
                      <Timeline.Item
                        key={entry.id}
                        title={`Cambio a ${entry.estado_nuevo.replace('_', ' ').toUpperCase()}`}
                      >
                        <Text size="xs" fw={500}>{entry.comentario_publico}</Text>
                        {entry.comentario_interno && (
                          <Text size="xs" c="blue" fs="italic">Interno: {entry.comentario_interno}</Text>
                        )}
                        <Text size="xs" c="dimmed" mt={2}>{formatDate(entry.fecha, { includeTime: true })}</Text>
                      </Timeline.Item>
                    ))}
                    <Timeline.Item title="Reporte Creado">
                      <Text size="xs" mt={2}>Ingresado al sistema</Text>
                    </Timeline.Item>
                  </Timeline>
                )}
              </div>

              <Group justify="flex-end">
                <Button variant="light" onClick={closeDetail}>
                  Cancelar
                </Button>
                <Button onClick={handleUpdateStatus} loading={updating}>
                  Registrar Gestion
                </Button>
              </Group>
            </Stack>
          )}
        </Modal>
      </Container>
    </LiveRegionProvider>
  );
}
