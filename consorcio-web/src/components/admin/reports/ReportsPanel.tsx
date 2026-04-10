import {
  Badge,
  Container,
  Group,
  Paper,
  Text,
  Title,
} from '@mantine/core';
import { useDebouncedCallback, useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { type Report, reportsApi, apiFetch } from '../../../lib/api';
import { logger } from '../../../lib/logger';
import { LiveRegionProvider, useLiveRegion } from '../../ui/accessibility';
import type { SeguimientoEntry } from './reportsPanelTypes';
import { ITEMS_PER_PAGE } from './constants';
import { filterReports, getStatusBadge } from './reportsPanelUtils';
import { ReportsFilters } from './components/ReportsFilters';
import { ReportsTableContent } from './components/ReportsTableContent';
import { ReportDetailModal } from './components/ReportDetailModal';

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
      const response = await apiFetch<SeguimientoEntry[] | { items: SeguimientoEntry[] }>(`/management/seguimiento/reporte/${id}`);
      const data = Array.isArray(response) ? response : (response.items ?? []);
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
          comentario_publico: publicComment,
        }),
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

  // Memoized filtering and stats calculation (single pass)
  const { filteredReports, pendingCount, inReviewCount } = useMemo(() => {
    return filterReports(reports, filterCategory, searchQuery);
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

        <ReportsFilters
          searchInputValue={searchInputValue}
          onSearchInputChange={(value) => {
            setSearchInputValue(value);
            debouncedSetSearch(value);
          }}
          filterStatus={filterStatus}
          setFilterStatus={setFilterStatus}
          filterCategory={filterCategory}
          setFilterCategory={setFilterCategory}
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
    </LiveRegionProvider>
  );
}
