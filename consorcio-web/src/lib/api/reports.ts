/**
 * Reports API module - Reports management and public reports.
 */

import { apiFetch, API_URL, API_PREFIX, LONG_TIMEOUT, getAuthToken } from './core';
import type {
  DashboardStats,
  PublicReportCreate,
  PublicReportResponse,
  Report,
} from '../../types';

export const reportsApi = {
  /**
   * Obtener denuncias con filtros.
   * Overload 1: (page, limit, status)
   * Overload 2: (params object)
   */
  getAll: (
    pageOrParams:
      | number
      | {
          page?: number;
          limit?: number;
          status?: string;
          cuenca?: string;
          tipo?: string;
          assigned_to?: string;
        } = 1,
    limit = 10,
    status?: string
  ): Promise<{ items: Report[]; total: number; page: number }> => {
    const searchParams = new URLSearchParams();

    if (typeof pageOrParams === 'number') {
      searchParams.set('page', pageOrParams.toString());
      searchParams.set('limit', limit.toString());
      if (status) searchParams.set('status', status);
    } else {
      if (pageOrParams.page) searchParams.set('page', pageOrParams.page.toString());
      if (pageOrParams.limit) searchParams.set('limit', pageOrParams.limit.toString());
      if (pageOrParams.status) searchParams.set('status', pageOrParams.status);
      if (pageOrParams.cuenca) searchParams.set('cuenca', pageOrParams.cuenca);
      if (pageOrParams.tipo) searchParams.set('tipo', pageOrParams.tipo);
      if (pageOrParams.assigned_to) searchParams.set('assigned_to', pageOrParams.assigned_to);
    }

    return apiFetch(`/reports?${searchParams.toString()}`);
  },

  /**
   * Obtener denuncia con historial.
   */
  get: (id: string): Promise<Report> => apiFetch(`/reports/${id}`),

  /**
   * Actualizar estado de denuncia.
   */
  updateStatus: (id: string, estado: string, notas?: string): Promise<Report> =>
    apiFetch(`/reports/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ estado, notas_admin: notas }),
    }),

  /**
   * Actualizar denuncia.
   */
  update: (
    id: string,
    data: {
      estado?: string;
      asignado_a?: string;
      notas_internas?: string;
      notas_admin?: string;
      prioridad?: string;
    }
  ): Promise<Report> =>
    apiFetch(`/reports/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  /**
   * Asignar denuncia a operador.
   */
  assign: (id: string, operadorId: string, notas?: string): Promise<Report> =>
    apiFetch(`/reports/${id}/assign`, {
      method: 'POST',
      body: JSON.stringify({ operador_id: operadorId, notas }),
    }),

  /**
   * Marcar como resuelta.
   */
  resolve: (id: string, descripcion: string): Promise<Report> =>
    apiFetch(`/reports/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ descripcion }),
    }),

  /**
   * Obtener estadisticas.
   */
  getStats: (): Promise<{
    pendiente: number;
    en_revision: number;
    resuelto: number;
    total: number;
  }> => apiFetch('/reports/stats'),
};

/**
 * Public API (No auth required) for reports and verification.
 */
export const publicApi = {
  /**
   * Crear denuncia publica (sin autenticacion).
   * Requiere contacto verificado.
   */
  createReport: (data: PublicReportCreate): Promise<PublicReportResponse> =>
    apiFetch('/public/reports', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    }),

  /**
   * Subir foto para denuncia.
   */
  uploadPhoto: async (file: File): Promise<{ photo_url: string; filename: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), LONG_TIMEOUT);

    try {
      const response = await fetch(`${API_URL}${API_PREFIX}/public/upload-photo`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Error al subir foto');
      }

      return response.json();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('La subida de la foto excedio el tiempo limite');
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  },
};

/**
 * Stats API for dashboard and export.
 */
export const statsApi = {
  /**
   * Obtener estadisticas del dashboard.
   */
  getDashboard: (period = '30d'): Promise<DashboardStats> =>
    apiFetch(`/stats/dashboard?period=${period}`),

  /**
   * Obtener stats por cuenca.
   */
  getByCuenca: (analysisId?: string) =>
    apiFetch(`/stats/by-cuenca${analysisId ? `?analysis_id=${analysisId}` : ''}`),

  /**
   * Obtener historico.
   */
  getHistorical: (params: { cuenca?: string; limit?: number } = {}) => {
    const searchParams = new URLSearchParams();
    if (params.cuenca) searchParams.set('cuenca', params.cuenca);
    if (params.limit) searchParams.set('limit', params.limit.toString());

    return apiFetch(`/stats/historical?${searchParams.toString()}`);
  },

  /**
   * Obtener resumen.
   */
  getSummary: () => apiFetch('/stats/summary'),

  /**
   * Exportar estadisticas.
   * Backend expects POST with ExportRequest body.
   */
  export: async (
    options: {
      format?: 'csv' | 'xlsx' | 'pdf';
      dateFrom?: Date;
      dateTo?: Date;
      cuencas?: string[];
      includeReports?: boolean;
    } = {}
  ): Promise<Blob> => {
    const { format = 'csv', dateFrom, dateTo, cuencas, includeReports = false } = options;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), LONG_TIMEOUT);

    // Helper function to get Accept header for export format
    function getExportAcceptHeader(fmt: string): string {
      if (fmt === 'csv') return 'text/csv';
      if (fmt === 'json') return 'application/json';
      return 'application/pdf';
    }

    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}${API_PREFIX}/stats/export`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: getExportAcceptHeader(format),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          format,
          date_from: dateFrom?.toISOString().split('T')[0],
          date_to: dateTo?.toISOString().split('T')[0],
          cuencas,
          include_reports: includeReports,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error('Error al exportar');
      }

      return response.blob();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('La exportacion excedio el tiempo limite');
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  },
};
