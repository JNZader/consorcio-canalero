import { Container, Paper, SimpleGrid } from '@mantine/core';
import { useDebouncedCallback, useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useCanales } from '../../../hooks/useCanales';
import { apiFetch, type Sugerencia, type SugerenciasStats, sugerenciasApi } from '../../../lib/api';
import { formatDate } from '../../../lib/formatters';
import { logger } from '../../../lib/logger';
import { mapColorTokens } from '../../../lib/mapColorTokens';
import { useLiveRegion } from '../../ui/accessibility';
import { IconBuilding, IconCalendar, IconCheck, IconClock, IconUsers } from '../../ui/icons';
import { ProximaReunionSection } from './components/ProximaReunionSection';
import { StatsCard } from './components/StatsCard';
import { SugerenciasFilters } from './components/SugerenciasFilters';
import { SugerenciasTableContent } from './components/SugerenciasTableContent';
import { SuggestionDetailModal } from './components/SuggestionDetailModal';
import { ITEMS_PER_PAGE } from './constants';
import { filterSugerenciasByQuery, getStatusBadge } from './sugerenciasPanelUtils';

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

  // Filters
  const [filterEstado, setFilterEstado] = useState<string | null>(null);
  const [filterTipo, setFilterTipo] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInputValue, setSearchInputValue] = useState('');

  const debouncedSetSearch = useDebouncedCallback((value: string) => {
    setSearchQuery(value);
    setPage(1);
  }, 300);

  const handleFilterEstadoChange = useCallback((value: string | null) => {
    setFilterEstado(value);
    setPage(1);
  }, []);

  const handleFilterTipoChange = useCallback((value: string | null) => {
    setFilterTipo(value);
    setPage(1);
  }, []);

  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Edit state
  const [newEstado, setNewEstado] = useState<string>('');
  const [adminNotes, setAdminNotes] = useState('');
  const [publicComment, setPublicComment] = useState('');
  const [updating, setUpdating] = useState(false);

  // Agendar state
  const [agendarFecha, setAgendarFecha] = useState<Date | null>(null);
  const [agendando, setAgendando] = useState(false);

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
              style: { color: mapColorTokens.h1D4ED8, weight: 3, opacity: 0.9 },
            },
          ]
        : [],
    [relevadosFC]
  );

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
      logger.error('Error loading próxima reunion:', error);
    } finally {
      setLoadingProxima(false);
    }
  }, []);

  const loadSugerencias = useCallback(async () => {
    setLoading(true);
    announceRef.current('Cargando sugerencias...');
    try {
      const data = await sugerenciasApi.getAll({
        page,
        limit: ITEMS_PER_PAGE,
        estado: filterEstado || undefined,
        tipo: filterTipo || undefined,
        ...(searchQuery ? { search: searchQuery } : {}),
      });
      setSugerencias(data.items);
      setTotalPages(Math.max(1, Math.ceil(data.total / ITEMS_PER_PAGE)));
      announceRef.current(`${data.items.length} sugerencias cargadas`);
    } catch (error) {
      logger.error('Error loading sugerencias:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudieron cargar las sugerencias',
        color: 'red',
      });
      announceRef.current('No se pudieron cargar las sugerencias');
    } finally {
      setLoading(false);
    }
  }, [page, filterEstado, filterTipo, searchQuery]);

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

  const handleViewDetail = async (sug: Sugerencia) => {
    try {
      const full = await sugerenciasApi.get(sug.id).catch(() => sug);
      const merged = { ...sug, ...full };
      setSelectedSugerencia(merged);
      setNewEstado(merged.estado);
      // Precargar lo guardado: si el operador entra al modal por
      // segunda vez, ve lo que escribió antes — antes los textareas
      // arrancaban vacíos aunque la base tuviera contenido (otra cara
      // del bug del schema mismatch).
      setAdminNotes(merged.notas_internas ?? '');
      setPublicComment(merged.respuesta ?? '');
      setAgendarFecha(merged.fecha_reunion ? new Date(merged.fecha_reunion) : null);
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
      // PATCH /sugerencias/{id}. El backend acepta `respuesta` (público,
      // visible al ciudadano) y `notas_internas` (privado, sólo operador).
      // Antes mandábamos `resolucion` y `notas_comision` que NO EXISTEN
      // en el schema — Pydantic los descartaba en silencio y la "gestión"
      // no se persistía nunca. Por eso el ciudadano veía vacío en
      // `/perfil > Mis sugerencias`.
      await apiFetch(`/sugerencias/${selectedSugerencia.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          estado: newEstado,
          notas_internas: adminNotes,
          respuesta: publicComment,
        }),
      });

      notifications.show({
        title: 'Sugerencia actualizada',
        message: 'Los cambios de la sugerencia fueron guardados correctamente',
        color: 'green',
        icon: <IconCheck size={16} />,
      });
      announceRef.current('Sugerencia actualizada correctamente');
      closeDetail();
      refreshAll();
    } catch (error) {
      logger.error('Error updating sugerencia:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo actualizar la sugerencia',
        color: 'red',
      });
      announceRef.current('No se pudo actualizar la sugerencia');
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
      announceRef.current(`Sugerencia agendada para el ${formatDate(fechaStr)}`);
      closeDetail();
      refreshAll();
    } catch (error) {
      logger.error('Error agendando sugerencia:', error);
      notifications.show({
        title: 'Error',
        message: 'No se pudo agendar la sugerencia',
        color: 'red',
      });
      announceRef.current('No se pudo agendar la sugerencia');
    } finally {
      setAgendando(false);
    }
  };

  // The "Incorporar a Canales existentes" workflow was retired on
  // 2026-04-29: it mutated a static GeoJSON file at runtime and the
  // operator can express the same intent by setting estado=implementada
  // + writing a respuesta. The state setter `setIncorporating` and the
  // related backend endpoint were removed in the same pass.

  // Filter sugerencias by search query
  const filteredSugerencias = useMemo(() => {
    return filterSugerenciasByQuery(sugerencias, searchQuery);
  }, [sugerencias, searchQuery]);

  return (
    <Container size="xl" py="md">
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

      <ProximaReunionSection proximaReunion={proximaReunion} onViewDetail={handleViewDetail} />

      <SugerenciasFilters
        searchInputValue={searchInputValue}
        onSearchInputChange={(value) => {
          setSearchInputValue(value);
          debouncedSetSearch(value);
        }}
        filterEstado={filterEstado}
        setFilterEstado={handleFilterEstadoChange}
        filterTipo={filterTipo}
        setFilterTipo={handleFilterTipoChange}
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
        onUpdate={handleUpdate}
        updating={updating}
      />
    </Container>
  );
}
