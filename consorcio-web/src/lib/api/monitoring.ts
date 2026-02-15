/**
 * Monitoring API module - Monitoring dashboard endpoint.
 */

import { apiFetch, LONG_TIMEOUT } from './core';

// ===========================================
// MONITORING TYPES
// ===========================================

export interface MonitoringDashboardData {
  summary: {
    area_total_ha: number;
    area_productiva_ha: number;
    area_problematica_ha: number;
    porcentaje_problematico: number;
  };
  clasificacion: Record<string, unknown>;
  cuencas: Record<string, unknown>;
  ranking_cuencas: Array<{
    cuenca: string;
    porcentaje_problematico: number;
    area_anegada_ha: number;
  }>;
  alertas: Array<{
    tipo: string;
    severidad: string;
    icono: string;
    cuenca: string;
    mensaje: string;
    detalle: Record<string, unknown>;
    accion_sugerida: string;
  }>;
  total_alertas: number;
  periodo: {
    inicio: string;
    fin: string;
  };
  fecha_actualizacion: string;
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
