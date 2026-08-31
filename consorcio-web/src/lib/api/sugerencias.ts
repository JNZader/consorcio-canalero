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
  geometry?: {
    type: 'FeatureCollection';
    features: Array<{
      type: 'Feature';
      geometry: { type: 'LineString'; coordinates: number[][] };
      properties?: Record<string, unknown>;
    }>;
  } | null;
  contacto_nombre?: string;
  contacto_email?: string;
  contacto_telefono?: string;
  autor_id?: string;
  // Values mirror the backend `EstadoSugerencia` enum exactly. The
  // previous typing had invented states (`en_agenda`, `tratado`) that
  // the backend rejected with a 500 — see commit 53161da.
  estado: 'pendiente' | 'revisada' | 'implementada' | 'descartada';
  prioridad: 'baja' | 'normal' | 'alta' | 'urgente';
  fecha_reunion?: string;
  /**
   * Comentario público que el operador escribe para el ciudadano. Se
   * muestra en `MySuggestionsSection`. Antes el frontend usaba
   * `resolucion`, que NO ES UN CAMPO REAL del backend — Pydantic lo
   * descartaba silenciosamente y nada se persistía. Ahora ambos lados
   * usan `respuesta`, que es lo único que existe en el modelo.
   */
  respuesta?: string;
  /**
   * Notas internas de la comisión (privadas). Sólo viaja al frontend
   * en respuestas de endpoints de operador (`SugerenciaResponse`); el
   * endpoint citizen `/sugerencias/mine` usa `SugerenciaCitizenResponse`
   * que NO incluye este campo.
   */
  notas_internas?: string;
  cuenca_id?: string;
  created_at: string;
  updated_at: string;
}

export interface SugerenciaCreate {
  titulo: string;
  descripcion: string;
  categoria?: string;
  geometry?: {
    type: 'FeatureCollection';
    features: Array<{
      type: 'Feature';
      geometry:
        | { type: 'LineString'; coordinates: number[][] }
        | { type: 'Point'; coordinates: number[] };
      properties?: Record<string, unknown>;
    }>;
  } | null;
  contacto_nombre?: string;
}

export interface RateLimitInfo {
  /** Cuántos envíos le quedan al usuario en la ventana actual. */
  remaining: number;
  /** Tope absoluto (5/24h por usuario). */
  limit: number;
  /** Segundos hasta que el envío más viejo del usuario salga de la ventana de 24h. */
  reset_seconds: number;
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
   * Crear sugerencia. Requiere ciudadano autenticado — el backend
   * autollena `usuario_id` y `contacto_email` desde el JWT (espejo
   * exacto del flujo `POST /denuncias`). Esto es lo que permite que
   * la sugerencia aparezca después en `GET /sugerencias/mine`.
   */
  create: (data: SugerenciaCreate): Promise<Sugerencia> =>
    apiFetch('/sugerencias', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /**
   * Cuota restante del usuario logueado (5 cada 24 h rolling).
   * Backed by `GET /sugerencias/rate-limit` — la base es source-of-truth,
   * NO un stub. El backend cuenta sugerencias creadas por este usuario
   * en las últimas 24h y devuelve `limit - count`.
   */
  checkLimit: (): Promise<RateLimitInfo> => apiFetch('/sugerencias/rate-limit'),

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
   * Listar las sugerencias del ciudadano logueado (auth required).
   * Mirror de `/denuncias/mine`. Backend filtra por usuario_id del JWT.
   */
  listMine: (
    page = 1,
    limit = 10
  ): Promise<{ items: Sugerencia[]; total: number; page: number; limit: number }> =>
    apiFetch(`/sugerencias/mine?page=${page}&limit=${limit}`),

  /**
   * Obtener estadisticas.
   */
  getStats: (): Promise<SugerenciasStats> => apiFetch('/sugerencias/stats'),

  /**
   * Obtener temas para proxima reunion.
   */
  getProximaReunion: (): Promise<Sugerencia[]> => apiFetch('/sugerencias/proxima-reunion'),

  /**
   * Obtener detalle de sugerencia.
   */
  get: (id: string): Promise<Sugerencia> => apiFetch(`/sugerencias/${id}`),

  /**
   * Actualizar sugerencia.
   */
  update: (id: string, data: Partial<Sugerencia>): Promise<Sugerencia> =>
    apiFetch(`/sugerencias/${id}`, {
      method: 'PATCH',
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
};
