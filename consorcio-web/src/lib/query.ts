/**
 * TanStack Query configuration and hooks.
 * Replaces SWR with better TypeScript support and auth-aware fetching.
 */

import { QueryClient, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../stores/authStore';
import {
  type Layer,
  layersApi,
  monitoringApi,
  reportsApi,
  statsApi,
} from './api';

// ===========================================
// QUERY CLIENT
// ===========================================

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60, // 1 minute
      gcTime: 1000 * 60 * 5, // 5 minutes (formerly cacheTime)
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
    mutations: {
      retry: 1,
    },
  },
});

// ===========================================
// QUERY KEYS
// ===========================================

export const queryKeys = {
  dashboardStats: (period: string) => ['dashboard-stats', period] as const,
  monitoringDashboard: () => ['monitoring-dashboard'] as const,
  reports: (filters: ReportFilters) => ['reports', filters] as const,
  report: (id: string) => ['report', id] as const,
  layers: (visibleOnly: boolean) => ['layers', visibleOnly] as const,
  layer: (id: string) => ['layer', id] as const,
} as const;

// ===========================================
// TYPES
// ===========================================

export interface ReportFilters {
  page?: number;
  limit?: number;
  status?: string;
  cuenca?: string;
  tipo?: string;
}

// ===========================================
// CUSTOM ERROR CLASS
// ===========================================

export class QueryError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
    public readonly endpoint?: string
  ) {
    super(message);
    this.name = 'QueryError';
  }
}

// ===========================================
// DASHBOARD STATS HOOK
// ===========================================

/**
 * Hook para obtener estadisticas del dashboard.
 * Solo hace fetch si el usuario esta autenticado.
 */
export function useDashboardStats(period = '30d') {
  const { user, loading: authLoading, initialized } = useAuthStore();
  const isAuthenticated = !!user && !authLoading && initialized;

  const query = useQuery({
    queryKey: queryKeys.dashboardStats(period),
    queryFn: () => statsApi.getDashboard(period),
    enabled: isAuthenticated,
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchInterval: 1000 * 60 * 5, // Refresh every 5 minutes
  });

  return {
    stats: query.data,
    isLoading: authLoading || query.isLoading,
    isValidating: query.isFetching && !query.isLoading,
    error: query.error as Error | null,
    refetch: query.refetch,
  };
}

// ===========================================
// MONITORING DASHBOARD HOOK
// ===========================================

/**
 * Hook para obtener datos de monitoring (inundacion por cuenca).
 * Solo hace fetch si el usuario esta autenticado.
 */
export function useMonitoringDashboard() {
  const { user, loading: authLoading, initialized } = useAuthStore();
  const isAuthenticated = !!user && !authLoading && initialized;

  const query = useQuery({
    queryKey: queryKeys.monitoringDashboard(),
    queryFn: () => monitoringApi.getDashboard(),
    enabled: isAuthenticated,
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchInterval: 1000 * 60 * 10, // Refresh every 10 minutes
  });

  return {
    data: query.data,
    rankingCuencas: query.data?.ranking_cuencas ?? [],
    isLoading: authLoading || query.isLoading,
    isValidating: query.isFetching && !query.isLoading,
    error: query.error as Error | null,
    refetch: query.refetch,
  };
}

// ===========================================
// REPORTS HOOKS
// ===========================================

/**
 * Hook para obtener reportes/denuncias con filtros.
 * Solo hace fetch si el usuario esta autenticado.
 */
export function useReports(filters: ReportFilters = {}) {
  const { page = 1, limit = 10, status, cuenca, tipo } = filters;
  const { user, loading: authLoading, initialized } = useAuthStore();
  const isAuthenticated = !!user && !authLoading && initialized;

  const query = useQuery({
    queryKey: queryKeys.reports({ page, limit, status, cuenca, tipo }),
    queryFn: () => reportsApi.getAll({ page, limit, status, cuenca, tipo }),
    enabled: isAuthenticated,
    staleTime: 1000 * 60, // 1 minute
    refetchInterval: 1000 * 60, // Refresh every minute
  });

  return {
    reports: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    currentPage: query.data?.page ?? page,
    isLoading: authLoading || query.isLoading,
    isValidating: query.isFetching && !query.isLoading,
    error: query.error as Error | null,
    refetch: query.refetch,
  };
}

/**
 * Hook para obtener un reporte individual.
 */
export function useReport(id: string | null) {
  const { user, loading: authLoading, initialized } = useAuthStore();
  const isAuthenticated = !!user && !authLoading && initialized;

  const query = useQuery({
    queryKey: queryKeys.report(id ?? ''),
    queryFn: () => reportsApi.get(id!),
    enabled: isAuthenticated && !!id,
  });

  return {
    report: query.data,
    isLoading: authLoading || query.isLoading,
    error: query.error as Error | null,
    refetch: query.refetch,
  };
}

// ===========================================
// LAYERS HOOKS
// ===========================================

/**
 * Hook para obtener las capas del mapa.
 */
export function useLayers(visibleOnly = false) {
  const query = useQuery({
    queryKey: queryKeys.layers(visibleOnly),
    queryFn: () => layersApi.getAll(visibleOnly),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });

  return {
    layers: query.data ?? [],
    isLoading: query.isLoading,
    isValidating: query.isFetching && !query.isLoading,
    error: query.error as Error | null,
    refetch: query.refetch,
  };
}

// ===========================================
// MUTATIONS
// ===========================================

/**
 * Hook para actualizar estado de reporte.
 */
export function useUpdateReportStatus() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, estado, notas }: { id: string; estado: string; notas?: string }) =>
      reportsApi.updateStatus(id, estado, notas),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports'] });
      qc.invalidateQueries({ queryKey: ['dashboard-stats'] });
    },
  });
}

/**
 * Hook para actualizar un reporte.
 */
export function useUpdateReport() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: {
        estado?: string;
        asignado_a?: string;
        notas_internas?: string;
        notas_admin?: string;
        prioridad?: string;
      };
    }) => reportsApi.update(id, data),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ['reports'] });
      qc.invalidateQueries({ queryKey: ['report', variables.id] });
      qc.invalidateQueries({ queryKey: ['dashboard-stats'] });
    },
  });
}

/**
 * Hook para crear capa.
 */
export function useCreateLayer() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (data: Partial<Layer>) => layersApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['layers'] });
    },
  });
}

/**
 * Hook para actualizar capa.
 */
export function useUpdateLayer() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Layer> }) => layersApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['layers'] });
    },
  });
}

/**
 * Hook para eliminar capa.
 */
export function useDeleteLayer() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => layersApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['layers'] });
    },
  });
}

// ===========================================
// CACHE INVALIDATION
// ===========================================

/**
 * Invalida el cache de estadisticas del dashboard.
 */
export function invalidateDashboardStats() {
  return queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] });
}

/**
 * Invalida el cache de reportes.
 */
export function invalidateReports() {
  return queryClient.invalidateQueries({ queryKey: ['reports'] });
}

/**
 * Invalida el cache de capas.
 */
export function invalidateLayers() {
  return queryClient.invalidateQueries({ queryKey: ['layers'] });
}

/**
 * Invalida todo el cache.
 */
export function invalidateAll() {
  return queryClient.invalidateQueries();
}

// ===========================================
// PREFETCH HELPERS
// ===========================================

/**
 * Pre-carga datos del dashboard.
 */
export function prefetchDashboardStats(period = '30d') {
  return queryClient.prefetchQuery({
    queryKey: queryKeys.dashboardStats(period),
    queryFn: () => statsApi.getDashboard(period),
  });
}

/**
 * Pre-carga datos de reportes.
 */
export function prefetchReports(filters: ReportFilters = {}) {
  const { page = 1, limit = 10, status, cuenca, tipo } = filters;
  return queryClient.prefetchQuery({
    queryKey: queryKeys.reports({ page, limit, status, cuenca, tipo }),
    queryFn: () => reportsApi.getAll({ page, limit, status, cuenca, tipo }),
  });
}
