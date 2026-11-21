/**
 * Monitoring API module - Monitoring dashboard endpoint.
 */

import { LONG_TIMEOUT, apiFetch } from './core';

// ===========================================
// MONITORING TYPES
// ===========================================

export interface MonitoringAnalisisItem {
  id: string;
  tipo: string;
  fecha_inicio: string;
  fecha_fin: string;
  resultados: Record<string, unknown>;
  hectareas_afectadas?: number | null;
  porcentaje_area?: number | null;
  parametros: Record<string, unknown>;
  usuario_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MonitoringDashboardData {
  // Real backend `/monitoring/dashboard` (`DashboardStatsResponse`) fields:
  denuncias?: {
    pendiente: number;
    en_revision: number;
    resuelto: number;
    descartado: number;
    total: number;
  };
  denuncias_nuevas_semana?: number;
  total_assets?: number;
  total_sugerencias?: number;
  total_tramites?: number;
  latest_analyses?: MonitoringAnalisisItem[];
  resumen_financiero?: {
    total_ingresos?: number;
    total_gastos?: number;
    balance?: number;
  };
  // Legacy / mock summary fields preserved as optional for test compatibility:
  summary?: {
    area_total_ha: number;
    area_productiva_ha: number;
    area_problematica_ha: number;
    porcentaje_problematico: number;
  };
  clasificacion?: Record<string, unknown>;
  cuencas?: Record<string, unknown>;
  ranking_cuencas?: Array<{
    cuenca: string;
    porcentaje_problematico: number;
    area_anegada_ha: number;
  }>;
  alertas?: Array<{
    tipo: string;
    severidad: string;
    icono: string;
    cuenca: string;
    mensaje: string;
    detalle: Record<string, unknown>;
    accion_sugerida: string;
  }>;
  total_alertas?: number;
  periodo?: {
    inicio: string;
    fin: string;
  };
  fecha_actualizacion?: string;
}

// ===========================================
// MONITORING API
// ===========================================

export const monitoringApi = {
  /**
   * Obtener datos del dashboard de monitoreo.
   * Usa LONG_TIMEOUT porque hace llamadas a GEE.
   */
  getDashboard: (): Promise<MonitoringDashboardData> =>
    apiFetch('/monitoring/dashboard', { timeout: LONG_TIMEOUT }),
};
