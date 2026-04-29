/**
 * Reports API module - Reports management and public reports.
 */

import type { DashboardStats, PublicReportCreate, PublicReportResponse, Report } from '../../types';
import { API_PREFIX, API_URL, LONG_TIMEOUT, apiFetch, getAuthToken } from './core';
import type { ResolveInput, ResolveStatus } from './reportsResolve';

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

    return apiFetch(`/denuncias?${searchParams.toString()}`);
  },

  /**
   * Obtener denuncia con historial.
   */
  get: (id: string): Promise<Report> => apiFetch(`/denuncias/${id}`),

  /**
   * Actualizar estado de denuncia.
   */
  updateStatus: (id: string, estado: string, notas?: string): Promise<Report> =>
    apiFetch(`/denuncias/${id}`, {
      method: 'PATCH',
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
    apiFetch(`/denuncias/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  /**
   * Asignar denuncia a operador.
   * In v2, assignment is done via PATCH on the denuncia.
   */
  assign: (id: string, operadorId: string, notas?: string): Promise<Report> =>
    apiFetch(`/denuncias/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ asignado_a: operadorId, notas_internas: notas }),
    }),

  /**
   * Marcar como resuelta.
   * In v2, resolution is done via PATCH with estado=resuelto.
   */
  resolve: (
    id: string,
    resolution: ResolveInput
  ): Promise<{
    id: string;
    status: ResolveStatus;
    resolved_at: string;
    resolved_by: string;
  }> =>
    apiFetch(`/denuncias/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ estado: 'resuelto', notas_admin: resolution.comment }),
    }),

  /**
   * Obtener estadisticas.
   */
  getStats: (): Promise<{
    pendiente: number;
    en_revision: number;
    resuelto: number;
    total: number;
  }> => apiFetch('/denuncias/stats'),
};

/**
 * Citizen-facing denuncias API. The endpoints here ALL require the user
 * to be authenticated — anonymous denuncias were retired on 2026-04-28
 * as an anti-spam measure (the form already gated the UI behind a Google
 * login but the backend was happily accepting unauth POSTs from curl;
 * now both layers agree).
 *
 * Naming kept as `publicApi` for now to minimise touch surface; consider
 * renaming to `citizenApi` in a follow-up rename pass.
 */
export const publicApi = {
  /**
   * Crear una denuncia (requiere user logueado).
   *
   * The server auto-fills `user_id` and `contacto_email` from the JWT —
   * the payload only needs the stuff the citizen typed into the form.
   */
  createReport: (data: PublicReportCreate): Promise<PublicReportResponse> =>
    apiFetch('/denuncias', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /**
   * Attach a photo to a previously-created denuncia. Two-step flow:
   *   1) `createReport(...)`  → returns `{id}`.
   *   2) `uploadPhoto(id, file)` → multipart upload to `/denuncias/{id}/photo`.
   *
   * The server checks ownership (the JWT user must own the denuncia) so
   * we forward the auth token explicitly via `getAuthToken()` — this
   * codepath bypasses `apiFetch` because Mantine-FileInput / FormData
   * needs the raw `fetch` to keep the multipart boundary intact.
   *
   * Photo failure is non-fatal in the form: the denuncia stays saved
   * and the user gets a yellow toast.
   */
  uploadPhoto: async (
    denunciaId: string,
    file: File
  ): Promise<{ photo_url: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), LONG_TIMEOUT);

    try {
      const token = await getAuthToken();
      const response = await fetch(
        `${API_URL}${API_PREFIX}/denuncias/${denunciaId}/photo`,
        {
          method: 'POST',
          body: formData,
          signal: controller.signal,
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        }
      );

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

  /**
   * Lista paginada de denuncias del ciudadano logueado. Backend keeps
   * the response shape symmetric with the operator list endpoint, but
   * the items here are the user's OWN denuncias and include the full
   * detail (`respuesta`, `historial`, `foto_url`) so the "Mis denuncias"
   * tab in `/perfil` doesn't need a second fetch per row.
   */
  listMyReports: (
    page = 1,
    limit = 10
  ): Promise<{ items: Report[]; total: number; page: number; limit: number }> =>
    apiFetch(`/denuncias/mine?page=${page}&limit=${limit}`),

  /**
   * Cuota restante del ciudadano para crear denuncias (5 cada 24 h
   * rolling). Espejo del flujo `sugerenciasApi.checkLimit` — el
   * backend cuenta sobre la base, no sobre Redis.
   */
  checkLimit: (): Promise<ReportRateLimitInfo> =>
    apiFetch('/denuncias/rate-limit'),
};

export interface ReportRateLimitInfo {
  remaining: number;
  limit: number;
  reset_seconds: number;
}

/**
 * Stats API for dashboard and export.
 */
export const statsApi = {
  /**
   * Obtener estadisticas del dashboard.
   */
  getDashboard: (period = '30d'): Promise<DashboardStats> =>
    apiFetch(`/monitoring/dashboard?period=${period}`),

  /**
   * Obtener stats por cuenca.
   * TODO: v2 does not have a dedicated by-cuenca stats endpoint yet.
   */
  getByCuenca: (analysisId?: string) =>
    apiFetch(`/monitoring/dashboard${analysisId ? `?analysis_id=${analysisId}` : ''}`),

  /**
   * Obtener historico.
   * TODO: v2 does not have a dedicated historical stats endpoint yet.
   * Falling back to monitoring/analyses.
   */
  getHistorical: (params: { cuenca?: string; limit?: number } = {}) => {
    const searchParams = new URLSearchParams();
    if (params.cuenca) searchParams.set('cuenca', params.cuenca);
    if (params.limit) searchParams.set('limit', params.limit.toString());

    return apiFetch(`/monitoring/analyses?${searchParams.toString()}`);
  },

  /**
   * Obtener resumen.
   * Maps to monitoring dashboard in v2.
   */
  getSummary: () => apiFetch('/monitoring/dashboard'),

  /**
   * Exportar estadisticas.
   * TODO: v2 does not have a dedicated stats/export endpoint yet.
   * Falling back to monitoring dashboard data export.
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
    const { format = 'csv' } = options;

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
      // TODO: Replace with proper v2 export endpoint when available
      const response = await fetch(`${API_URL}${API_PREFIX}/monitoring/dashboard`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          Accept: getExportAcceptHeader(format),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
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
