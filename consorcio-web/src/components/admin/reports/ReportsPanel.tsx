import { Badge, Container, Group, Paper } from '@mantine/core';
import { useDebouncedCallback, useDisclosure } from '@mantine/hooks';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, type Report, reportsApi } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { showError, showSuccess } from '../../../lib/notifications';
import { erroresUi, textoError } from '../../../lib/userFacingError';
import { useLiveRegion } from '../../ui/accessibility';
import { ReportDetailModal } from './components/ReportDetailModal';
import { ReportsFilters } from './components/ReportsFilters';
import { ReportsTableContent } from './components/ReportsTableContent';
import { ITEMS_PER_PAGE } from './constants';
import type { SeguimientoEntry } from './reportsPanelTypes';
import { filterReports, getStatusBadge, type ReportStatusCounts } from './reportsPanelUtils';

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
  const [globalStats, setGlobalStats] = useState<ReportStatusCounts | null>(null);

  // Debounced search to avoid excessive API calls; resets pagination to page 1
  const debouncedSetSearch = useDebouncedCallback((value: string) => {
    setSearchQuery(value);
    setPage(1);
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

  const handleFilterStatusChange = useCallback((value: string | null) => {
    setFilterStatus(value);
    setPage(1);
  }, []);

  const handleFilterCategoryChange = useCallback((value: string | null) => {
    setFilterCategory(value);
    setPage(1);
  }, []);

  const loadReports = useCallback(async () => {
    setLoading(true);
    announceRef.current('Cargando reportes...');
    try {
      const getStatsFn = (reportsApi as { getStats?: () => Promise<ReportStatusCounts> }).getStats;
      const [data, statsResponse] = await Promise.all([
        reportsApi.getAll(
          page,
          ITEMS_PER_PAGE,
          filterStatus || undefined,
          filterCategory || undefined,
          searchQuery || undefined
        ),
        typeof getStatsFn === 'function' ? getStatsFn().catch(() => null) : Promise.resolve(null),
      ]);
      setReports(data.items);
      setTotalPages(Math.max(1, Math.ceil(data.total / ITEMS_PER_PAGE)));
      if (
        statsResponse &&
        typeof statsResponse.pendiente === 'number' &&
        typeof statsResponse.en_revision === 'number'
      ) {
        setGlobalStats({
          pendiente: statsResponse.pendiente,
          en_revision: statsResponse.en_revision,
        });
      } else if (!filterStatus && !filterCategory && !searchQuery) {
        const unfilteredCounts = filterReports(data.items, null, '');
        setGlobalStats({
          pendiente: unfilteredCounts.pendingCount,
          en_revision: unfilteredCounts.inReviewCount,
        });
      }
      announceRef.current(`${data.items.length} reportes cargados`);
    } catch (error) {
      logger.error('Error loading reports:', error);
      showError(erroresUi.cargarDenuncias.titulo, erroresUi.cargarDenuncias.detalle);
      announceRef.current(textoError(erroresUi.cargarDenuncias));
    } finally {
      setLoading(false);
    }
  }, [page, filterStatus, filterCategory, searchQuery]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  /**
   * Pull the audit log for a denuncia. The backend returns it nested
   * inside `GET /denuncias/{id}.historial` — there is NO separate
   * `/management/seguimiento` endpoint (that one only existed in an
   * old OpenAPI snapshot left in `schema.d.ts`; calling it returned 404
   * and the modal showed an empty timeline forever).
   */
  const loadHistory = async (id: string) => {
    setLoadingHistory(true);
    try {
      const denuncia = await apiFetch<{ historial?: SeguimientoEntry[] }>(`/denuncias/${id}`);
      setHistory(denuncia.historial ?? []);
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
    // Pre-fill the public comment textarea with whatever the operator has
    // already published as `respuesta` so editing means SEEING the prior
    // answer instead of typing into a blank field. Empty if none yet.
    setPublicComment(report.respuesta ?? '');
    loadHistory(report.id);
    openDetail();
  };

  /**
   * Update a denuncia's estado / respuesta via `PATCH /denuncias/{id}`.
   * The previous version POSTed to `/management/seguimiento` (404) with a
   * payload shaped for an `entidad_tipo`/`entidad_id` audit row that the
   * current backend does not have — that's what was throwing the
   * el toast genérico de actualización cuando el endpoint no existía.
   *
   * Mapping:
   *   newStatus      → estado
   *   publicComment  → respuesta   (visible to the citizen on /reportes/<id>)
   *   adminNotes     → comentario  (free-text note saved into the historial entry)
   *
   * The backend records the historial entry automatically when estado
   * changes (see `denuncias.service.update`).
   */
  const handleUpdateStatus = async () => {
    if (!selectedReport) return;

    setUpdating(true);
    try {
      await apiFetch(`/denuncias/${selectedReport.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          estado: newStatus,
          respuesta: publicComment || undefined,
          comentario: adminNotes || undefined,
        }),
      });

      showSuccess('Reporte actualizado', 'El historial de gestión ha sido registrado');
      announceRef.current('Reporte actualizado correctamente');
      closeDetail();
      loadReports();
    } catch (error) {
      logger.error(erroresUi.actualizarDenuncia.titulo, error);
      showError(erroresUi.actualizarDenuncia.titulo, erroresUi.actualizarDenuncia.detalle);
      announceRef.current(textoError(erroresUi.actualizarDenuncia));
    } finally {
      setUpdating(false);
    }
  };

  // Memoized filtering and stats calculation (single pass)
  const { filteredReports, pendingCount, inReviewCount } = useMemo(() => {
    return filterReports(reports, filterCategory, searchQuery, globalStats);
  }, [reports, filterCategory, searchQuery, globalStats]);

  return (
    <Container size="xl" py="md">
      {/* El titulo vive en el contenedor (`ParticipacionPanel`); aca solo
          quedan los contadores propios de la bandeja de denuncias. */}
      <Group justify="flex-end" mb="md">
        <Badge size="lg" color="yellow" variant="light" styles={{ label: { color: '#7a4100' } }}>
          {pendingCount} pendientes
        </Badge>
        <Badge size="lg" color="blue" variant="light">
          {inReviewCount} en revision
        </Badge>
      </Group>

      <ReportsFilters
        searchInputValue={searchInputValue}
        onSearchInputChange={(value) => {
          setSearchInputValue(value);
          debouncedSetSearch(value);
        }}
        filterStatus={filterStatus}
        setFilterStatus={handleFilterStatusChange}
        filterCategory={filterCategory}
        setFilterCategory={handleFilterCategoryChange}
        onRefresh={loadReports}
      />

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

      <ReportDetailModal
        opened={detailOpened}
        onClose={closeDetail}
        selectedReport={selectedReport}
        history={history}
        loadingHistory={loadingHistory}
        newStatus={newStatus}
        setNewStatus={setNewStatus}
        publicComment={publicComment}
        setPublicComment={setPublicComment}
        adminNotes={adminNotes}
        setAdminNotes={setAdminNotes}
        onUpdate={handleUpdateStatus}
        updating={updating}
      />
    </Container>
  );
}
