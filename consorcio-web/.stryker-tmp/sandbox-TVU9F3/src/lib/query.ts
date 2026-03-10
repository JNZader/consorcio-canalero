/**
 * TanStack Query configuration and hooks.
 * Replaces SWR with better TypeScript support and auth-aware fetching.
 */
// @ts-nocheck
function stryNS_9fa48() {
  var g = typeof globalThis === 'object' && globalThis && globalThis.Math === Math && globalThis || new Function("return this")();
  var ns = g.__stryker__ || (g.__stryker__ = {});
  if (ns.activeMutant === undefined && g.process && g.process.env && g.process.env.__STRYKER_ACTIVE_MUTANT__) {
    ns.activeMutant = g.process.env.__STRYKER_ACTIVE_MUTANT__;
  }
  function retrieveNS() {
    return ns;
  }
  stryNS_9fa48 = retrieveNS;
  return retrieveNS();
}
stryNS_9fa48();
function stryCov_9fa48() {
  var ns = stryNS_9fa48();
  var cov = ns.mutantCoverage || (ns.mutantCoverage = {
    static: {},
    perTest: {}
  });
  function cover() {
    var c = cov.static;
    if (ns.currentTestId) {
      c = cov.perTest[ns.currentTestId] = cov.perTest[ns.currentTestId] || {};
    }
    var a = arguments;
    for (var i = 0; i < a.length; i++) {
      c[a[i]] = (c[a[i]] || 0) + 1;
    }
  }
  stryCov_9fa48 = cover;
  cover.apply(null, arguments);
}
function stryMutAct_9fa48(id) {
  var ns = stryNS_9fa48();
  function isActive(id) {
    if (ns.activeMutant === id) {
      if (ns.hitCount !== void 0 && ++ns.hitCount > ns.hitLimit) {
        throw new Error('Stryker: Hit count limit reached (' + ns.hitCount + ')');
      }
      return true;
    }
    return false;
  }
  stryMutAct_9fa48 = isActive;
  return isActive(id);
}
import { QueryClient, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../stores/authStore';
import { type Layer, layersApi, monitoringApi, reportsApi, statsApi } from './api';

// ===========================================
// QUERY CLIENT
// ===========================================

export const queryClient = new QueryClient(stryMutAct_9fa48("167") ? {} : (stryCov_9fa48("167"), {
  defaultOptions: stryMutAct_9fa48("168") ? {} : (stryCov_9fa48("168"), {
    queries: stryMutAct_9fa48("169") ? {} : (stryCov_9fa48("169"), {
      staleTime: stryMutAct_9fa48("170") ? 1000 / 60 : (stryCov_9fa48("170"), 1000 * 60),
      // 1 minute
      gcTime: stryMutAct_9fa48("171") ? 1000 * 60 / 5 : (stryCov_9fa48("171"), (stryMutAct_9fa48("172") ? 1000 / 60 : (stryCov_9fa48("172"), 1000 * 60)) * 5),
      // 5 minutes (formerly cacheTime)
      retry: 3,
      retryDelay: stryMutAct_9fa48("173") ? () => undefined : (stryCov_9fa48("173"), attemptIndex => stryMutAct_9fa48("174") ? Math.max(1000 * 2 ** attemptIndex, 30000) : (stryCov_9fa48("174"), Math.min(stryMutAct_9fa48("175") ? 1000 / 2 ** attemptIndex : (stryCov_9fa48("175"), 1000 * 2 ** attemptIndex), 30000))),
      refetchOnWindowFocus: stryMutAct_9fa48("176") ? true : (stryCov_9fa48("176"), false),
      refetchOnReconnect: stryMutAct_9fa48("177") ? false : (stryCov_9fa48("177"), true)
    }),
    mutations: stryMutAct_9fa48("178") ? {} : (stryCov_9fa48("178"), {
      retry: 1
    })
  })
}));

// ===========================================
// QUERY KEYS
// ===========================================

export const queryKeys = {
  dashboardStats: (period: string) => ['dashboard-stats', period] as const,
  monitoringDashboard: () => ['monitoring-dashboard'] as const,
  reports: (filters: ReportFilters) => ['reports', filters] as const,
  report: (id: string) => ['report', id] as const,
  layers: (visibleOnly: boolean) => ['layers', visibleOnly] as const,
  layer: (id: string) => ['layer', id] as const
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
  constructor(message: string, public readonly statusCode?: number, public readonly endpoint?: string) {
    super(message);
    this.name = stryMutAct_9fa48("179") ? "" : (stryCov_9fa48("179"), 'QueryError');
  }
}

// ===========================================
// DASHBOARD STATS HOOK
// ===========================================

/**
 * Hook para obtener estadisticas del dashboard.
 * Solo hace fetch si el usuario esta autenticado.
 */
export function useDashboardStats(period = stryMutAct_9fa48("180") ? "" : (stryCov_9fa48("180"), '30d')) {
  if (stryMutAct_9fa48("181")) {
    {}
  } else {
    stryCov_9fa48("181");
    const {
      user,
      loading: authLoading,
      initialized
    } = useAuthStore();
    const isAuthenticated = stryMutAct_9fa48("184") ? !!user && !authLoading || initialized : stryMutAct_9fa48("183") ? false : stryMutAct_9fa48("182") ? true : (stryCov_9fa48("182", "183", "184"), (stryMutAct_9fa48("186") ? !!user || !authLoading : stryMutAct_9fa48("185") ? true : (stryCov_9fa48("185", "186"), (stryMutAct_9fa48("187") ? !user : (stryCov_9fa48("187"), !(stryMutAct_9fa48("188") ? user : (stryCov_9fa48("188"), !user)))) && (stryMutAct_9fa48("189") ? authLoading : (stryCov_9fa48("189"), !authLoading)))) && initialized);
    const query = useQuery(stryMutAct_9fa48("190") ? {} : (stryCov_9fa48("190"), {
      queryKey: queryKeys.dashboardStats(period),
      queryFn: stryMutAct_9fa48("191") ? () => undefined : (stryCov_9fa48("191"), () => statsApi.getDashboard(period)),
      enabled: isAuthenticated,
      staleTime: stryMutAct_9fa48("192") ? 1000 * 60 / 5 : (stryCov_9fa48("192"), (stryMutAct_9fa48("193") ? 1000 / 60 : (stryCov_9fa48("193"), 1000 * 60)) * 5),
      // 5 minutes
      refetchInterval: stryMutAct_9fa48("194") ? 1000 * 60 / 5 : (stryCov_9fa48("194"), (stryMutAct_9fa48("195") ? 1000 / 60 : (stryCov_9fa48("195"), 1000 * 60)) * 5) // Refresh every 5 minutes
    }));
    return stryMutAct_9fa48("196") ? {} : (stryCov_9fa48("196"), {
      stats: query.data,
      isLoading: stryMutAct_9fa48("199") ? authLoading && query.isLoading : stryMutAct_9fa48("198") ? false : stryMutAct_9fa48("197") ? true : (stryCov_9fa48("197", "198", "199"), authLoading || query.isLoading),
      isValidating: stryMutAct_9fa48("202") ? query.isFetching || !query.isLoading : stryMutAct_9fa48("201") ? false : stryMutAct_9fa48("200") ? true : (stryCov_9fa48("200", "201", "202"), query.isFetching && (stryMutAct_9fa48("203") ? query.isLoading : (stryCov_9fa48("203"), !query.isLoading))),
      error: query.error as Error | null,
      refetch: query.refetch
    });
  }
}

// ===========================================
// MONITORING DASHBOARD HOOK
// ===========================================

/**
 * Hook para obtener datos de monitoring (inundacion por cuenca).
 * Solo hace fetch si el usuario esta autenticado.
 */
export function useMonitoringDashboard() {
  if (stryMutAct_9fa48("204")) {
    {}
  } else {
    stryCov_9fa48("204");
    const {
      user,
      loading: authLoading,
      initialized
    } = useAuthStore();
    const isAuthenticated = stryMutAct_9fa48("207") ? !!user && !authLoading || initialized : stryMutAct_9fa48("206") ? false : stryMutAct_9fa48("205") ? true : (stryCov_9fa48("205", "206", "207"), (stryMutAct_9fa48("209") ? !!user || !authLoading : stryMutAct_9fa48("208") ? true : (stryCov_9fa48("208", "209"), (stryMutAct_9fa48("210") ? !user : (stryCov_9fa48("210"), !(stryMutAct_9fa48("211") ? user : (stryCov_9fa48("211"), !user)))) && (stryMutAct_9fa48("212") ? authLoading : (stryCov_9fa48("212"), !authLoading)))) && initialized);
    const query = useQuery(stryMutAct_9fa48("213") ? {} : (stryCov_9fa48("213"), {
      queryKey: queryKeys.monitoringDashboard(),
      queryFn: stryMutAct_9fa48("214") ? () => undefined : (stryCov_9fa48("214"), () => monitoringApi.getDashboard()),
      enabled: isAuthenticated,
      staleTime: stryMutAct_9fa48("215") ? 1000 * 60 / 5 : (stryCov_9fa48("215"), (stryMutAct_9fa48("216") ? 1000 / 60 : (stryCov_9fa48("216"), 1000 * 60)) * 5),
      // 5 minutes
      refetchInterval: stryMutAct_9fa48("217") ? 1000 * 60 / 10 : (stryCov_9fa48("217"), (stryMutAct_9fa48("218") ? 1000 / 60 : (stryCov_9fa48("218"), 1000 * 60)) * 10) // Refresh every 10 minutes
    }));
    return stryMutAct_9fa48("219") ? {} : (stryCov_9fa48("219"), {
      data: query.data,
      rankingCuencas: stryMutAct_9fa48("220") ? query.data?.ranking_cuencas && [] : (stryCov_9fa48("220"), (stryMutAct_9fa48("221") ? query.data.ranking_cuencas : (stryCov_9fa48("221"), query.data?.ranking_cuencas)) ?? (stryMutAct_9fa48("222") ? ["Stryker was here"] : (stryCov_9fa48("222"), []))),
      isLoading: stryMutAct_9fa48("225") ? authLoading && query.isLoading : stryMutAct_9fa48("224") ? false : stryMutAct_9fa48("223") ? true : (stryCov_9fa48("223", "224", "225"), authLoading || query.isLoading),
      isValidating: stryMutAct_9fa48("228") ? query.isFetching || !query.isLoading : stryMutAct_9fa48("227") ? false : stryMutAct_9fa48("226") ? true : (stryCov_9fa48("226", "227", "228"), query.isFetching && (stryMutAct_9fa48("229") ? query.isLoading : (stryCov_9fa48("229"), !query.isLoading))),
      error: query.error as Error | null,
      refetch: query.refetch
    });
  }
}

// ===========================================
// REPORTS HOOKS
// ===========================================

/**
 * Hook para obtener reportes/denuncias con filtros.
 * Solo hace fetch si el usuario esta autenticado.
 */
export function useReports(filters: ReportFilters = {}) {
  if (stryMutAct_9fa48("230")) {
    {}
  } else {
    stryCov_9fa48("230");
    const {
      page = 1,
      limit = 10,
      status,
      cuenca,
      tipo
    } = filters;
    const {
      user,
      loading: authLoading,
      initialized
    } = useAuthStore();
    const isAuthenticated = stryMutAct_9fa48("233") ? !!user && !authLoading || initialized : stryMutAct_9fa48("232") ? false : stryMutAct_9fa48("231") ? true : (stryCov_9fa48("231", "232", "233"), (stryMutAct_9fa48("235") ? !!user || !authLoading : stryMutAct_9fa48("234") ? true : (stryCov_9fa48("234", "235"), (stryMutAct_9fa48("236") ? !user : (stryCov_9fa48("236"), !(stryMutAct_9fa48("237") ? user : (stryCov_9fa48("237"), !user)))) && (stryMutAct_9fa48("238") ? authLoading : (stryCov_9fa48("238"), !authLoading)))) && initialized);
    const query = useQuery(stryMutAct_9fa48("239") ? {} : (stryCov_9fa48("239"), {
      queryKey: queryKeys.reports(stryMutAct_9fa48("240") ? {} : (stryCov_9fa48("240"), {
        page,
        limit,
        status,
        cuenca,
        tipo
      })),
      queryFn: stryMutAct_9fa48("241") ? () => undefined : (stryCov_9fa48("241"), () => reportsApi.getAll(stryMutAct_9fa48("242") ? {} : (stryCov_9fa48("242"), {
        page,
        limit,
        status,
        cuenca,
        tipo
      }))),
      enabled: isAuthenticated,
      staleTime: stryMutAct_9fa48("243") ? 1000 / 60 : (stryCov_9fa48("243"), 1000 * 60),
      // 1 minute
      refetchInterval: stryMutAct_9fa48("244") ? 1000 / 60 : (stryCov_9fa48("244"), 1000 * 60) // Refresh every minute
    }));
    return stryMutAct_9fa48("245") ? {} : (stryCov_9fa48("245"), {
      reports: stryMutAct_9fa48("246") ? query.data?.items && [] : (stryCov_9fa48("246"), (stryMutAct_9fa48("247") ? query.data.items : (stryCov_9fa48("247"), query.data?.items)) ?? (stryMutAct_9fa48("248") ? ["Stryker was here"] : (stryCov_9fa48("248"), []))),
      total: stryMutAct_9fa48("249") ? query.data?.total && 0 : (stryCov_9fa48("249"), (stryMutAct_9fa48("250") ? query.data.total : (stryCov_9fa48("250"), query.data?.total)) ?? 0),
      currentPage: stryMutAct_9fa48("251") ? query.data?.page && page : (stryCov_9fa48("251"), (stryMutAct_9fa48("252") ? query.data.page : (stryCov_9fa48("252"), query.data?.page)) ?? page),
      isLoading: stryMutAct_9fa48("255") ? authLoading && query.isLoading : stryMutAct_9fa48("254") ? false : stryMutAct_9fa48("253") ? true : (stryCov_9fa48("253", "254", "255"), authLoading || query.isLoading),
      isValidating: stryMutAct_9fa48("258") ? query.isFetching || !query.isLoading : stryMutAct_9fa48("257") ? false : stryMutAct_9fa48("256") ? true : (stryCov_9fa48("256", "257", "258"), query.isFetching && (stryMutAct_9fa48("259") ? query.isLoading : (stryCov_9fa48("259"), !query.isLoading))),
      error: query.error as Error | null,
      refetch: query.refetch
    });
  }
}

/**
 * Hook para obtener un reporte individual.
 */
export function useReport(id: string | null) {
  if (stryMutAct_9fa48("260")) {
    {}
  } else {
    stryCov_9fa48("260");
    const {
      user,
      loading: authLoading,
      initialized
    } = useAuthStore();
    const isAuthenticated = stryMutAct_9fa48("263") ? !!user && !authLoading || initialized : stryMutAct_9fa48("262") ? false : stryMutAct_9fa48("261") ? true : (stryCov_9fa48("261", "262", "263"), (stryMutAct_9fa48("265") ? !!user || !authLoading : stryMutAct_9fa48("264") ? true : (stryCov_9fa48("264", "265"), (stryMutAct_9fa48("266") ? !user : (stryCov_9fa48("266"), !(stryMutAct_9fa48("267") ? user : (stryCov_9fa48("267"), !user)))) && (stryMutAct_9fa48("268") ? authLoading : (stryCov_9fa48("268"), !authLoading)))) && initialized);
    const query = useQuery(stryMutAct_9fa48("269") ? {} : (stryCov_9fa48("269"), {
      queryKey: queryKeys.report(stryMutAct_9fa48("270") ? id && '' : (stryCov_9fa48("270"), id ?? (stryMutAct_9fa48("271") ? "Stryker was here!" : (stryCov_9fa48("271"), '')))),
      queryFn: stryMutAct_9fa48("272") ? () => undefined : (stryCov_9fa48("272"), () => reportsApi.get(id!)),
      enabled: stryMutAct_9fa48("275") ? isAuthenticated || !!id : stryMutAct_9fa48("274") ? false : stryMutAct_9fa48("273") ? true : (stryCov_9fa48("273", "274", "275"), isAuthenticated && (stryMutAct_9fa48("276") ? !id : (stryCov_9fa48("276"), !(stryMutAct_9fa48("277") ? id : (stryCov_9fa48("277"), !id)))))
    }));
    return stryMutAct_9fa48("278") ? {} : (stryCov_9fa48("278"), {
      report: query.data,
      isLoading: stryMutAct_9fa48("281") ? authLoading && query.isLoading : stryMutAct_9fa48("280") ? false : stryMutAct_9fa48("279") ? true : (stryCov_9fa48("279", "280", "281"), authLoading || query.isLoading),
      error: query.error as Error | null,
      refetch: query.refetch
    });
  }
}

// ===========================================
// LAYERS HOOKS
// ===========================================

/**
 * Hook para obtener las capas del mapa.
 */
export function useLayers(visibleOnly = stryMutAct_9fa48("282") ? true : (stryCov_9fa48("282"), false)) {
  if (stryMutAct_9fa48("283")) {
    {}
  } else {
    stryCov_9fa48("283");
    const query = useQuery(stryMutAct_9fa48("284") ? {} : (stryCov_9fa48("284"), {
      queryKey: queryKeys.layers(visibleOnly),
      queryFn: stryMutAct_9fa48("285") ? () => undefined : (stryCov_9fa48("285"), () => layersApi.getAll(visibleOnly)),
      staleTime: stryMutAct_9fa48("286") ? 1000 * 60 / 5 : (stryCov_9fa48("286"), (stryMutAct_9fa48("287") ? 1000 / 60 : (stryCov_9fa48("287"), 1000 * 60)) * 5) // 5 minutes
    }));
    return stryMutAct_9fa48("288") ? {} : (stryCov_9fa48("288"), {
      layers: stryMutAct_9fa48("289") ? query.data && [] : (stryCov_9fa48("289"), query.data ?? (stryMutAct_9fa48("290") ? ["Stryker was here"] : (stryCov_9fa48("290"), []))),
      isLoading: query.isLoading,
      isValidating: stryMutAct_9fa48("293") ? query.isFetching || !query.isLoading : stryMutAct_9fa48("292") ? false : stryMutAct_9fa48("291") ? true : (stryCov_9fa48("291", "292", "293"), query.isFetching && (stryMutAct_9fa48("294") ? query.isLoading : (stryCov_9fa48("294"), !query.isLoading))),
      error: query.error as Error | null,
      refetch: query.refetch
    });
  }
}

// ===========================================
// MUTATIONS
// ===========================================

/**
 * Hook para actualizar estado de reporte.
 */
export function useUpdateReportStatus() {
  if (stryMutAct_9fa48("295")) {
    {}
  } else {
    stryCov_9fa48("295");
    const qc = useQueryClient();
    return useMutation(stryMutAct_9fa48("296") ? {} : (stryCov_9fa48("296"), {
      mutationFn: stryMutAct_9fa48("297") ? () => undefined : (stryCov_9fa48("297"), ({
        id,
        estado,
        notas
      }: {
        id: string;
        estado: string;
        notas?: string;
      }) => reportsApi.updateStatus(id, estado, notas)),
      onSuccess: () => {
        if (stryMutAct_9fa48("298")) {
          {}
        } else {
          stryCov_9fa48("298");
          qc.invalidateQueries(stryMutAct_9fa48("299") ? {} : (stryCov_9fa48("299"), {
            queryKey: stryMutAct_9fa48("300") ? [] : (stryCov_9fa48("300"), [stryMutAct_9fa48("301") ? "" : (stryCov_9fa48("301"), 'reports')])
          }));
          qc.invalidateQueries(stryMutAct_9fa48("302") ? {} : (stryCov_9fa48("302"), {
            queryKey: stryMutAct_9fa48("303") ? [] : (stryCov_9fa48("303"), [stryMutAct_9fa48("304") ? "" : (stryCov_9fa48("304"), 'dashboard-stats')])
          }));
        }
      }
    }));
  }
}

/**
 * Hook para actualizar un reporte.
 */
export function useUpdateReport() {
  if (stryMutAct_9fa48("305")) {
    {}
  } else {
    stryCov_9fa48("305");
    const qc = useQueryClient();
    return useMutation(stryMutAct_9fa48("306") ? {} : (stryCov_9fa48("306"), {
      mutationFn: stryMutAct_9fa48("307") ? () => undefined : (stryCov_9fa48("307"), ({
        id,
        data
      }: {
        id: string;
        data: {
          estado?: string;
          asignado_a?: string;
          notas_internas?: string;
          notas_admin?: string;
          prioridad?: string;
        };
      }) => reportsApi.update(id, data)),
      onSuccess: (_, variables) => {
        if (stryMutAct_9fa48("308")) {
          {}
        } else {
          stryCov_9fa48("308");
          qc.invalidateQueries(stryMutAct_9fa48("309") ? {} : (stryCov_9fa48("309"), {
            queryKey: stryMutAct_9fa48("310") ? [] : (stryCov_9fa48("310"), [stryMutAct_9fa48("311") ? "" : (stryCov_9fa48("311"), 'reports')])
          }));
          qc.invalidateQueries(stryMutAct_9fa48("312") ? {} : (stryCov_9fa48("312"), {
            queryKey: stryMutAct_9fa48("313") ? [] : (stryCov_9fa48("313"), [stryMutAct_9fa48("314") ? "" : (stryCov_9fa48("314"), 'report'), variables.id])
          }));
          qc.invalidateQueries(stryMutAct_9fa48("315") ? {} : (stryCov_9fa48("315"), {
            queryKey: stryMutAct_9fa48("316") ? [] : (stryCov_9fa48("316"), [stryMutAct_9fa48("317") ? "" : (stryCov_9fa48("317"), 'dashboard-stats')])
          }));
        }
      }
    }));
  }
}

/**
 * Hook para crear capa.
 */
export function useCreateLayer() {
  if (stryMutAct_9fa48("318")) {
    {}
  } else {
    stryCov_9fa48("318");
    const qc = useQueryClient();
    return useMutation(stryMutAct_9fa48("319") ? {} : (stryCov_9fa48("319"), {
      mutationFn: stryMutAct_9fa48("320") ? () => undefined : (stryCov_9fa48("320"), (data: Partial<Layer>) => layersApi.create(data)),
      onSuccess: () => {
        if (stryMutAct_9fa48("321")) {
          {}
        } else {
          stryCov_9fa48("321");
          qc.invalidateQueries(stryMutAct_9fa48("322") ? {} : (stryCov_9fa48("322"), {
            queryKey: stryMutAct_9fa48("323") ? [] : (stryCov_9fa48("323"), [stryMutAct_9fa48("324") ? "" : (stryCov_9fa48("324"), 'layers')])
          }));
        }
      }
    }));
  }
}

/**
 * Hook para actualizar capa.
 */
export function useUpdateLayer() {
  if (stryMutAct_9fa48("325")) {
    {}
  } else {
    stryCov_9fa48("325");
    const qc = useQueryClient();
    return useMutation(stryMutAct_9fa48("326") ? {} : (stryCov_9fa48("326"), {
      mutationFn: stryMutAct_9fa48("327") ? () => undefined : (stryCov_9fa48("327"), ({
        id,
        data
      }: {
        id: string;
        data: Partial<Layer>;
      }) => layersApi.update(id, data)),
      onSuccess: () => {
        if (stryMutAct_9fa48("328")) {
          {}
        } else {
          stryCov_9fa48("328");
          qc.invalidateQueries(stryMutAct_9fa48("329") ? {} : (stryCov_9fa48("329"), {
            queryKey: stryMutAct_9fa48("330") ? [] : (stryCov_9fa48("330"), [stryMutAct_9fa48("331") ? "" : (stryCov_9fa48("331"), 'layers')])
          }));
        }
      }
    }));
  }
}

/**
 * Hook para eliminar capa.
 */
export function useDeleteLayer() {
  if (stryMutAct_9fa48("332")) {
    {}
  } else {
    stryCov_9fa48("332");
    const qc = useQueryClient();
    return useMutation(stryMutAct_9fa48("333") ? {} : (stryCov_9fa48("333"), {
      mutationFn: stryMutAct_9fa48("334") ? () => undefined : (stryCov_9fa48("334"), (id: string) => layersApi.delete(id)),
      onSuccess: () => {
        if (stryMutAct_9fa48("335")) {
          {}
        } else {
          stryCov_9fa48("335");
          qc.invalidateQueries(stryMutAct_9fa48("336") ? {} : (stryCov_9fa48("336"), {
            queryKey: stryMutAct_9fa48("337") ? [] : (stryCov_9fa48("337"), [stryMutAct_9fa48("338") ? "" : (stryCov_9fa48("338"), 'layers')])
          }));
        }
      }
    }));
  }
}

// ===========================================
// CACHE INVALIDATION
// ===========================================

/**
 * Invalida el cache de estadisticas del dashboard.
 */
export function invalidateDashboardStats() {
  if (stryMutAct_9fa48("339")) {
    {}
  } else {
    stryCov_9fa48("339");
    return queryClient.invalidateQueries(stryMutAct_9fa48("340") ? {} : (stryCov_9fa48("340"), {
      queryKey: stryMutAct_9fa48("341") ? [] : (stryCov_9fa48("341"), [stryMutAct_9fa48("342") ? "" : (stryCov_9fa48("342"), 'dashboard-stats')])
    }));
  }
}

/**
 * Invalida el cache de reportes.
 */
export function invalidateReports() {
  if (stryMutAct_9fa48("343")) {
    {}
  } else {
    stryCov_9fa48("343");
    return queryClient.invalidateQueries(stryMutAct_9fa48("344") ? {} : (stryCov_9fa48("344"), {
      queryKey: stryMutAct_9fa48("345") ? [] : (stryCov_9fa48("345"), [stryMutAct_9fa48("346") ? "" : (stryCov_9fa48("346"), 'reports')])
    }));
  }
}

/**
 * Invalida el cache de capas.
 */
export function invalidateLayers() {
  if (stryMutAct_9fa48("347")) {
    {}
  } else {
    stryCov_9fa48("347");
    return queryClient.invalidateQueries(stryMutAct_9fa48("348") ? {} : (stryCov_9fa48("348"), {
      queryKey: stryMutAct_9fa48("349") ? [] : (stryCov_9fa48("349"), [stryMutAct_9fa48("350") ? "" : (stryCov_9fa48("350"), 'layers')])
    }));
  }
}

/**
 * Invalida todo el cache.
 */
export function invalidateAll() {
  if (stryMutAct_9fa48("351")) {
    {}
  } else {
    stryCov_9fa48("351");
    return queryClient.invalidateQueries();
  }
}

// ===========================================
// PREFETCH HELPERS
// ===========================================

/**
 * Pre-carga datos del dashboard.
 */
export function prefetchDashboardStats(period = stryMutAct_9fa48("352") ? "" : (stryCov_9fa48("352"), '30d')) {
  if (stryMutAct_9fa48("353")) {
    {}
  } else {
    stryCov_9fa48("353");
    return queryClient.prefetchQuery(stryMutAct_9fa48("354") ? {} : (stryCov_9fa48("354"), {
      queryKey: queryKeys.dashboardStats(period),
      queryFn: stryMutAct_9fa48("355") ? () => undefined : (stryCov_9fa48("355"), () => statsApi.getDashboard(period))
    }));
  }
}

/**
 * Pre-carga datos de reportes.
 */
export function prefetchReports(filters: ReportFilters = {}) {
  if (stryMutAct_9fa48("356")) {
    {}
  } else {
    stryCov_9fa48("356");
    const {
      page = 1,
      limit = 10,
      status,
      cuenca,
      tipo
    } = filters;
    return queryClient.prefetchQuery(stryMutAct_9fa48("357") ? {} : (stryCov_9fa48("357"), {
      queryKey: queryKeys.reports(stryMutAct_9fa48("358") ? {} : (stryCov_9fa48("358"), {
        page,
        limit,
        status,
        cuenca,
        tipo
      })),
      queryFn: stryMutAct_9fa48("359") ? () => undefined : (stryCov_9fa48("359"), () => reportsApi.getAll(stryMutAct_9fa48("360") ? {} : (stryCov_9fa48("360"), {
        page,
        limit,
        status,
        cuenca,
        tipo
      })))
    }));
  }
}