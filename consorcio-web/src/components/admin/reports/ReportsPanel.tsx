import { Badge, Button, Container, Group, Paper } from '@mantine/core';
import { useDebouncedCallback, useDisclosure } from '@mantine/hooks';
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, type Report, reportsApi } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { showError, showSuccess } from '../../../lib/notifications';
import { erroresUi, textoError } from '../../../lib/userFacingError';
import { useLiveRegion } from '../../ui/accessibility';
import { ConfirmDialog } from '../../ui/ConfirmDialog';
import { ReportDetailModal } from './components/ReportDetailModal';
import { ReportsFilters } from './components/ReportsFilters';
import { ReportsTableContent } from './components/ReportsTableContent';
import { ITEMS_PER_PAGE } from './constants';
import type { SeguimientoEntry } from './reportsPanelTypes';
import { countReportStatuses, getStatusBadge, type ReportStatusCounts } from './reportsPanelUtils';

function readBandejaQuery() {
  if (typeof window === 'undefined') {
    return {
      q: '',
      estado: null as string | null,
      categoria: null as string | null,
      page: 1,
      sort: 'created_at',
      order: 'desc' as 'asc' | 'desc',
    };
  }
  const params = new URLSearchParams(window.location.search);
  const page = Number(params.get('page') || '1');
  return {
    q: params.get('q') ?? '',
    estado: params.get('estado'),
    categoria: params.get('categoria'),
    page: Number.isFinite(page) && page > 0 ? page : 1,
    sort: params.get('sort') || 'created_at',
    // Cualquier valor no reconocido cae en el default del backend.
    order: params.get('order') === 'asc' ? ('asc' as const) : ('desc' as const),
  };
}

export default function ReportsPanel() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [detailOpened, { open: openDetail, close: closeDetail }] = useDisclosure(false);
  const [history, setHistory] = useState<SeguimientoEntry[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Filters
  const initialQuery = readBandejaQuery();
  const [filterStatus, setFilterStatus] = useState<string | null>(initialQuery.estado);
  const [filterCategory, setFilterCategory] = useState<string | null>(initialQuery.categoria);
  const [searchQuery, setSearchQuery] = useState(initialQuery.q);
  const [searchInputValue, setSearchInputValue] = useState(initialQuery.q);
  const [sort, setSort] = useState(initialQuery.sort);
  const [order, setOrder] = useState<'asc' | 'desc'>(initialQuery.order);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [globalStats, setGlobalStats] = useState<ReportStatusCounts | null>(null);

  // Debounced search to avoid excessive API calls; resets pagination to page 1
  const debouncedSetSearch = useDebouncedCallback((value: string) => {
    setSearchQuery(value);
    setPage(1);
  }, 300);

  // Pagination
  const [page, setPage] = useState(initialQuery.page);
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

  /**
   * Encabezado clicable: mismo key invierte la dirección; key nuevo
   * arranca en 'desc' (predecible). Siempre vuelve a la página 1.
   */
  const handleSortChange = useCallback(
    (sortKey: string) => {
      setPage(1);
      if (sortKey === sort) {
        setOrder((current) => (current === 'desc' ? 'asc' : 'desc'));
        return;
      }
      setSort(sortKey);
      setOrder('desc');
    },
    [sort]
  );

  // El selector "Ordenar" de la vista móvil entrega key+dirección ya
  // elegidos por el usuario; solo aplica y resetea la paginación.
  const handleSortSelect = useCallback((nextSort: string, nextOrder: 'asc' | 'desc') => {
    setSort(nextSort);
    setOrder(nextOrder);
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
          searchQuery || undefined,
          sort,
          order
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
        setGlobalStats(countReportStatuses(data.items));
      }
      setLoadError(null);
      announceRef.current(`${data.items.length} reportes cargados`);
    } catch (error) {
      logger.error('Error loading reports:', error);
      setReports([]);
      setLoadError(textoError(erroresUi.cargarDenuncias));
      showError(erroresUi.cargarDenuncias.titulo, erroresUi.cargarDenuncias.detalle);
      announceRef.current(textoError(erroresUi.cargarDenuncias));
    } finally {
      setLoading(false);
    }
  }, [page, filterStatus, filterCategory, searchQuery, sort, order]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const put = (key: string, value: string | null) => {
      if (value) params.set(key, value);
      else params.delete(key);
    };
    put('q', searchQuery || null);
    put('estado', filterStatus);
    put('categoria', filterCategory);
    put('sort', sort === 'created_at' ? null : sort);
    put('order', order === 'desc' ? null : order);
    if (page > 1) params.set('page', String(page));
    else params.delete('page');
    const query = params.toString();
    const next = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`;
    window.history.replaceState(window.history.state, '', next);
  }, [searchQuery, filterStatus, filterCategory, page, sort, order]);

  const runBulk = async () => {
    setBulkRunning(true);
    try {
      const result = await reportsApi.bulkUpdate(selectedIds, 'en_revision', crypto.randomUUID());
      const failed = result.resultados.filter((row) => !row.ok);
      if (failed.length === 0) showSuccess('Listo', 'Se actualizaron las denuncias seleccionadas');
      else
        showError(
          'Algunas no se actualizaron',
          failed
            .map((row) => row.error)
            .filter(Boolean)
            .join(' ')
        );
      setSelectedIds([]);
      setBulkOpen(false);
      await loadReports();
    } finally {
      setBulkRunning(false);
    }
  };

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

  /** AssigneeField auto-PATCHes; keep list + selectedReport in sync for reopen. */
  const handleAssigneeChange = useCallback((denunciaId: string, asignadoA: string | null) => {
    // Report.asignado_a is optional string; clearable Select yields null → undefined.
    const next = asignadoA ?? undefined;
    setReports((current) =>
      current.map((row) => (row.id === denunciaId ? { ...row, asignado_a: next } : row))
    );
    setSelectedReport((current) =>
      current && current.id === denunciaId ? { ...current, asignado_a: next } : current
    );
  }, []);

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

  const pendingCount = globalStats?.pendiente ?? 0;
  const inReviewCount = globalStats?.en_revision ?? 0;

  return (
    <Container size="xl" py="md">
      {/* El titulo vive en el contenedor (`ParticipacionPanel`); aca solo
          quedan los contadores propios de la bandeja de denuncias. */}
      <Group justify="flex-end" mb="md">
        <Badge
          size="lg"
          color="yellow"
          variant="light"
          styles={{ label: { color: 'var(--cc-color-warning)' } }}
        >
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
        sort={sort}
        order={order}
        onSortChange={handleSortSelect}
        onRefresh={loadReports}
      />

      {/* Reports Table */}
      {selectedIds.length > 0 ? (
        <Group mb="sm">
          <Button onClick={() => setBulkOpen(true)}>
            Pasar {selectedIds.length} a en revisión
          </Button>
        </Group>
      ) : null}
      <ConfirmDialog
        opened={bulkOpen}
        title="Cambiar estado"
        message="Las denuncias seleccionadas pasan a en revisión. Cada una se valida por separado."
        confirmLabel="Confirmar"
        onClose={() => setBulkOpen(false)}
        loading={bulkRunning}
        onConfirm={() => void runBulk()}
      />
      <Paper shadow="sm" p="lg" radius="md">
        <ReportsTableContent
          loading={loading}
          loadError={loadError}
          onRetry={() => void loadReports()}
          selectedIds={selectedIds}
          onToggleSelected={(id) =>
            setSelectedIds((current) =>
              current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
            )
          }
          filteredReports={reports}
          totalPages={totalPages}
          page={page}
          onPageChange={setPage}
          onViewDetail={handleViewDetail}
          getStatusBadge={getStatusBadge}
          sorting={{ active: sort, direction: order, onChange: handleSortChange }}
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
        onAssigneeChange={handleAssigneeChange}
      />
    </Container>
  );
}
