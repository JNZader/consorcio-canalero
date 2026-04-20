import {
  Button,
  Container,
  Group,
  Paper,
  SimpleGrid,
  Text,
  Title,
} from '@mantine/core';
import { useDebouncedCallback, useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { type Sugerencia, type SugerenciasStats, sugerenciasApi, apiFetch } from '../../../lib/api';
import { useCanales } from '../../../hooks/useCanales';
import { formatDate } from '../../../lib/formatters';
import { logger } from '../../../lib/logger';
import { LiveRegionProvider, useLiveRegion } from '../../ui/accessibility';
import {
  IconCheck,
  IconPlus,
  IconCalendar,
  IconTrash,
  IconClock,
  IconUsers,
  IconBuilding,
} from '../../ui/icons';
import { ITEMS_PER_PAGE } from './constants';
import type { SeguimientoEntry } from './sugerenciasPanelTypes';
import { filterSugerenciasByQuery, getStatusBadge } from './sugerenciasPanelUtils';
import { StatsCard } from './components/StatsCard';
import { SugerenciasTableContent } from './components/SugerenciasTableContent';
import { CreateInternalModal } from './components/CreateInternalModal';
import { SuggestionDetailModal } from './components/SuggestionDetailModal';
import { ProximaReunionSection } from './components/ProximaReunionSection';
import { SugerenciasFilters } from './components/SugerenciasFilters';

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
  const [incorporating, setIncorporating] = useState(false);

  // Agendar state
  const [agendarFecha, setAgendarFecha] = useState<Date | null>(null);
  const [agendando, setAgendando] = useState(false);

  // Historial state
  const [historial, setHistorial] = useState<SeguimientoEntry[]>([]);
  const [loadingHistorial, setLoadingHistorial] = useState(false);
  const [showHistorial, setShowHistorial] = useState(false);
  // Batch 5 (2026-04-20): migrated from `useWaterways` to `useCanales`. The
  // reference-map backdrop in `SuggestionDetailModal` now renders the 23
  // relevados from the Pilar Azul static dataset instead of the retired
  // `canales_existentes` waterway. When the relevados FeatureCollection is
  // absent (first deploy before ETL runs), we pass an empty array — the
  // modal still mounts gracefully.
  const { relevados: relevadosFC } = useCanales();
  const canales = useMemo(
    () =>
      relevadosFC
        ? [
            {
              id: 'canales_relevados',
              data: relevadosFC as import('geojson').FeatureCollection,
              // Match the default relevados palette used by Pilar Azul's map
              // paint factory (see `canalesLayers.ts::CANALES_COLORS`).
              style: { color: '#1D4ED8', weight: 3, opacity: 0.9 },
            },
          ]
        : [],
    [relevadosFC],
  );

  useLiveRegion();

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
      // TODO: v2 uses sugerencias/{id} with historial included, or a dedicated historial endpoint
      const response = await apiFetch<SeguimientoEntry[] | { items: SeguimientoEntry[] }>(`/sugerencias/${id}/historial`).catch(() => [] as SeguimientoEntry[]);
      const data = Array.isArray(response) ? response : (response.items ?? []);
      setHistorial(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingHistorial(false);
    }
  };

  const handleViewDetail = async (sug: Sugerencia) => {
    try {
      const full = await sugerenciasApi.get(sug.id).catch(() => sug);
      const merged = { ...sug, ...full };
      setSelectedSugerencia(merged);
      setNewEstado(merged.estado);
      setAdminNotes('');
      setPublicComment('');
      setAgendarFecha(merged.fecha_reunion ? new Date(merged.fecha_reunion) : null);
      setHistorial([]);
      setShowHistorial(false);
      loadHistory(merged.id);
      openDetail();
    } catch (error) {
      logger.error('Error loading sugerencia detail:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo cargar el detalle de la sugerencia',
        color: 'red',
      });
    }
  };

  const handleUpdate = async () => {
    if (!selectedSugerencia) return;

    setUpdating(true);
    try {
      // 1. Create tracking entry (this updates suggestion status in backend via universal management service)
      // In v2, update sugerencia status via PATCH /sugerencias/{id}
      await apiFetch(`/sugerencias/${selectedSugerencia.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          estado: newEstado,
          notas_comision: adminNotes,
          resolucion: publicComment,
        }),
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

  const handleIncorporateChannel = async () => {
    if (!selectedSugerencia) return;

    setIncorporating(true);
    try {
      const updated = await sugerenciasApi.incorporateChannel(selectedSugerencia.id);
      const merged = { ...selectedSugerencia, ...updated };
      setSelectedSugerencia(merged);
      setNewEstado('tratado');
      notifications.show({
        title: 'Canal incorporado',
        message: 'La geometría ya se suma visualmente a la capa de Canales existentes',
        color: 'green',
        icon: <IconCheck size={16} />,
      });
      refreshAll();
    } catch (error) {
      logger.error('Error incorporating suggestion channel:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo incorporar la sugerencia a Canales existentes',
        color: 'red',
      });
    } finally {
      setIncorporating(false);
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

  // Filter sugerencias by search query
  const filteredSugerencias = useMemo(() => {
    return filterSugerenciasByQuery(sugerencias, searchQuery);
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

        <ProximaReunionSection
          proximaReunion={proximaReunion}
          onViewDetail={handleViewDetail}
        />

        <SugerenciasFilters
          searchInputValue={searchInputValue}
          onSearchInputChange={(value) => {
            setSearchInputValue(value);
            debouncedSetSearch(value);
          }}
          filterEstado={filterEstado}
          setFilterEstado={setFilterEstado}
          filterTipo={filterTipo}
          setFilterTipo={setFilterTipo}
          onRefresh={refreshAll}
        />

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

        <SuggestionDetailModal
          opened={detailOpened}
          onClose={closeDetail}
          selectedSugerencia={selectedSugerencia}
          canales={canales}
          historial={historial}
          loadingHistorial={loadingHistorial}
          showHistorial={showHistorial}
          setShowHistorial={setShowHistorial}
          newEstado={newEstado}
          setNewEstado={setNewEstado}
          publicComment={publicComment}
          setPublicComment={setPublicComment}
          adminNotes={adminNotes}
          setAdminNotes={setAdminNotes}
          agendarFecha={agendarFecha}
          setAgendarFecha={setAgendarFecha}
          onAgendar={handleAgendar}
          agendando={agendando}
          onIncorporateChannel={handleIncorporateChannel}
          incorporating={incorporating}
          onDelete={handleDelete}
          deleting={deleting}
          onUpdate={handleUpdate}
          updating={updating}
        />

        <CreateInternalModal
          opened={createOpened}
          onClose={closeCreate}
          newTitulo={newTitulo}
          setNewTitulo={setNewTitulo}
          newDescripcion={newDescripcion}
          setNewDescripcion={setNewDescripcion}
          newCategoria={newCategoria}
          setNewCategoria={setNewCategoria}
          newPrioridad={newPrioridad}
          setNewPrioridad={setNewPrioridad}
          creating={creating}
          onCreate={handleCreateInternal}
        />
      </Container>
    </LiveRegionProvider>
  );
}
