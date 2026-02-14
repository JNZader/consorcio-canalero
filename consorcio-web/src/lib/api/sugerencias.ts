/**
 * Sugerencias API module - Suggestions and proposals management.
 */

import { apiFetch } from './core';

// ===========================================
// SUGERENCIAS TYPES
// ===========================================

export interface Sugerencia {
  id: string;
  tipo: 'ciudadana' | 'interna';
  titulo: string;
  descripcion: string;
  categoria?: string;
  contacto_nombre?: string;
  contacto_email?: string;
  contacto_telefono?: string;
  autor_id?: string;
  estado: 'pendiente' | 'en_agenda' | 'tratado' | 'descartado';
  prioridad: 'baja' | 'normal' | 'alta' | 'urgente';
  fecha_reunion?: string;
  notas_comision?: string;
  resolucion?: string;
  cuenca_id?: string;
  created_at: string;
  updated_at: string;
}

export interface SugerenciaCreate {
  titulo: string;
  descripcion: string;
  categoria?: string;
  contacto_nombre?: string;
  contacto_email?: string;
  contacto_telefono?: string;
  contacto_verificado: boolean; // Debe ser true para aceptar
}

export interface RateLimitInfo {
  remaining: number;
  limit: number;
  reset_hours: number;
}

export interface SugerenciaInternaCreate {
  titulo: string;
  descripcion: string;
  categoria?: string;
  prioridad?: string;
  cuenca_id?: string;
}

export interface SugerenciasStats {
  pendiente: number;
  en_agenda: number;
  tratado: number;
  descartado: number;
  total: number;
  ciudadanas: number;
  internas: number;
}

export interface HistorialEntry {
  id: string;
  accion: 'creado' | 'estado_cambiado' | 'agendado' | 'resuelto';
  estado_anterior?: string;
  estado_nuevo?: string;
  notas?: string;
  created_at: string;
  perfiles?: { nombre: string } | null;
}

// ===========================================
// SUGERENCIAS API
// ===========================================

export const sugerenciasApi = {
  /**
   * Crear sugerencia publica (sin auth).
   * Requiere contacto verificado.
   */
  createPublic: (
    data: SugerenciaCreate
  ): Promise<{ id: string; message: string; remaining_today: number }> =>
    apiFetch('/sugerencias/public', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    }),

  /**
   * Verificar limite de sugerencias para un contacto.
   */
  checkLimit: (email?: string, telefono?: string): Promise<RateLimitInfo> => {
    const params = new URLSearchParams();
    if (email) params.set('email', email);
    if (telefono) params.set('telefono', telefono);
    return apiFetch(`/sugerencias/public/limit?${params.toString()}`, { skipAuth: true });
  },

  /**
   * Listar sugerencias (requiere auth).
   */
  getAll: (
    params: {
      page?: number;
      limit?: number;
      tipo?: string;
      estado?: string;
      prioridad?: string;
    } = {}
  ): Promise<{ items: Sugerencia[]; total: number; page: number; limit: number }> => {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set('page', params.page.toString());
    if (params.limit) searchParams.set('limit', params.limit.toString());
    if (params.tipo) searchParams.set('tipo', params.tipo);
    if (params.estado) searchParams.set('estado', params.estado);
    if (params.prioridad) searchParams.set('prioridad', params.prioridad);

    return apiFetch(`/sugerencias?${searchParams.toString()}`);
  },

  /**
   * Obtener estadisticas.
   */
  getStats: (): Promise<SugerenciasStats> => apiFetch('/sugerencias/stats'),

  /**
   * Obtener temas para proxima reunion.
   */
  getProximaReunion: (): Promise<Sugerencia[]> => apiFetch('/sugerencias/proxima-reunion'),

  /**
   * Crear tema interno (comision).
   */
  createInternal: (data: SugerenciaInternaCreate): Promise<Sugerencia> =>
    apiFetch('/sugerencias/interna', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /**
   * Obtener detalle de sugerencia.
   */
  get: (id: string): Promise<Sugerencia> => apiFetch(`/sugerencias/${id}`),

  /**
   * Obtener historial de cambios de una sugerencia.
   */
  getHistorial: (id: string): Promise<HistorialEntry[]> => apiFetch(`/sugerencias/${id}/historial`),

  /**
   * Actualizar sugerencia.
   */
  update: (id: string, data: Partial<Sugerencia>): Promise<Sugerencia> =>
    apiFetch(`/sugerencias/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  /**
   * Agendar para reunion.
   */
  agendar: (id: string, fecha: string): Promise<Sugerencia> =>
    apiFetch(`/sugerencias/${id}/agendar`, {
      method: 'POST',
      body: JSON.stringify({ fecha_reunion: fecha }),
    }),

  /**
   * Marcar como tratado/resuelto.
   */
  resolver: (id: string, resolucion: string): Promise<Sugerencia> =>
    apiFetch(`/sugerencias/${id}/resolver`, {
      method: 'POST',
      body: JSON.stringify({ resolucion }),
    }),

  /**
   * Eliminar sugerencia.
   */
  delete: (id: string): Promise<void> => apiFetch(`/sugerencias/${id}`, { method: 'DELETE' }),
};
