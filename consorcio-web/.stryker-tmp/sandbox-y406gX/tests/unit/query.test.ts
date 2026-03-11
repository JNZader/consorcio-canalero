// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  useQueryMock,
  useMutationMock,
  useQueryClientMock,
  invalidateQueriesMock,
  prefetchQueryMock,
  useAuthStoreMock,
  statsApiMock,
  monitoringApiMock,
  reportsApiMock,
  layersApiMock,
} = vi.hoisted(() => ({
  useQueryMock: vi.fn(),
  useMutationMock: vi.fn(),
  useQueryClientMock: vi.fn(),
  invalidateQueriesMock: vi.fn(),
  prefetchQueryMock: vi.fn(),
  useAuthStoreMock: vi.fn(),
  statsApiMock: { getDashboard: vi.fn() },
  monitoringApiMock: { getDashboard: vi.fn() },
  reportsApiMock: {
    getAll: vi.fn(),
    get: vi.fn(),
    updateStatus: vi.fn(),
    update: vi.fn(),
  },
  layersApiMock: { getAll: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}));

vi.mock('@tanstack/react-query', () => ({
  QueryClient: class QueryClient {
    invalidateQueries = invalidateQueriesMock;
    prefetchQuery = prefetchQueryMock;
  },
  useQuery: useQueryMock,
  useMutation: useMutationMock,
  useQueryClient: useQueryClientMock,
}));

vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: useAuthStoreMock,
}));

vi.mock('../../src/lib/api', () => ({
  statsApi: statsApiMock,
  monitoringApi: monitoringApiMock,
  reportsApi: reportsApiMock,
  layersApi: layersApiMock,
}));

import {
  QueryError,
  invalidateAll,
  invalidateDashboardStats,
  invalidateLayers,
  invalidateReports,
  prefetchDashboardStats,
  prefetchReports,
  queryKeys,
  useCreateLayer,
  useDashboardStats,
  useDeleteLayer,
  useLayers,
  useMonitoringDashboard,
  useReport,
  useReports,
  useUpdateLayer,
  useUpdateReport,
  useUpdateReportStatus,
} from '../../src/lib/query';

describe('query helpers and hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    useQueryClientMock.mockReturnValue({ invalidateQueries: invalidateQueriesMock });
    useMutationMock.mockImplementation((options) => options);
    useQueryMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    useAuthStoreMock.mockReturnValue({ user: { id: 'u1' }, loading: false, initialized: true });

    prefetchQueryMock.mockResolvedValue(undefined);
    invalidateQueriesMock.mockResolvedValue(undefined);
  });

  it('builds query keys and preserves QueryError metadata', () => {
    expect(queryKeys.dashboardStats('7d')).toEqual(['dashboard-stats', '7d']);
    expect(queryKeys.reports({ page: 2, status: 'pendiente' })).toEqual([
      'reports',
      { page: 2, status: 'pendiente' },
    ]);

    const err = new QueryError('boom', 500, '/reports');
    expect(err.name).toBe('QueryError');
    expect(err.statusCode).toBe(500);
    expect(err.endpoint).toBe('/reports');
  });

  it('maps dashboard, monitoring and reports query state', () => {
    const refetch = vi.fn();
    useQueryMock.mockReturnValueOnce({
      data: { denuncias_nuevas_semana: 4 },
      isLoading: false,
      isFetching: true,
      error: null,
      refetch,
    });

    const dashboard = useDashboardStats('30d');
    expect(dashboard.stats).toEqual({ denuncias_nuevas_semana: 4 });
    expect(dashboard.isValidating).toBe(true);
    expect(dashboard.refetch).toBe(refetch);
    expect(useQueryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ['dashboard-stats', '30d'],
        enabled: true,
      })
    );

    useQueryMock.mockReturnValueOnce({
      data: undefined,
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    const monitoring = useMonitoringDashboard();
    expect(monitoring.rankingCuencas).toEqual([]);

    useQueryMock.mockReturnValueOnce({
      data: { items: [{ id: 'rep-1' }], total: 1, page: 3 },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    const reports = useReports({ page: 3, limit: 5, status: 'pendiente' });
    expect(reports.reports).toEqual([{ id: 'rep-1' }]);
    expect(reports.total).toBe(1);
    expect(reports.currentPage).toBe(3);
  });

  it('disables auth-aware hooks when user is not authenticated', () => {
    useAuthStoreMock.mockReturnValue({ user: null, loading: false, initialized: true });

    useDashboardStats();
    expect(useQueryMock).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }));

    useReport(null);
    expect(useQueryMock).toHaveBeenLastCalledWith(expect.objectContaining({ enabled: false }));
  });

  it('maps layers query and mutation invalidation callbacks', async () => {
    useQueryMock.mockReturnValueOnce({
      data: [{ id: 'layer-1' }],
      isLoading: false,
      isFetching: true,
      error: null,
      refetch: vi.fn(),
    });
    const layers = useLayers(true);
    expect(layers.layers).toEqual([{ id: 'layer-1' }]);
    expect(layers.isValidating).toBe(true);

    const statusMutation = useUpdateReportStatus();
    await statusMutation.onSuccess();
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['reports'] });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['dashboard-stats'] });

    const reportMutation = useUpdateReport();
    await reportMutation.onSuccess(undefined, { id: 'rep-9', data: {} });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['report', 'rep-9'] });

    const createLayer = useCreateLayer();
    await createLayer.onSuccess();
    const updateLayer = useUpdateLayer();
    await updateLayer.onSuccess();
    const deleteLayer = useDeleteLayer();
    await deleteLayer.onSuccess();
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['layers'] });
  });

  it('invalidates and prefetches through shared query client', async () => {
    await invalidateDashboardStats();
    await invalidateReports();
    await invalidateLayers();
    await invalidateAll();

    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['dashboard-stats'] });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['reports'] });
    expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['layers'] });
    expect(invalidateQueriesMock).toHaveBeenCalledWith();

    await prefetchDashboardStats('15d');
    await prefetchReports({ page: 2, limit: 20, status: 'en_revision', cuenca: 'sur', tipo: 'canal' });

    expect(prefetchQueryMock).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['dashboard-stats', '15d'] })
    );
    expect(prefetchQueryMock).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ['reports', { page: 2, limit: 20, status: 'en_revision', cuenca: 'sur', tipo: 'canal' }],
      })
    );
  });
});
