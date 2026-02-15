/**
 * Layers API module - Vector layers management.
 */

import { apiFetch, getAuthToken, API_URL, API_PREFIX, LONG_TIMEOUT } from './core';
import type { Layer } from '../../types';

export const layersApi = {
  /**
   * Obtener todas las capas.
   */
  getAll: (visibleOnly = false): Promise<Layer[]> =>
    apiFetch(`/layers?visible_only=${visibleOnly}`),

  /**
   * Obtener una capa.
   */
  get: (id: string): Promise<Layer> => apiFetch(`/layers/${id}`),

  /**
   * Crear capa.
   */
  create: (data: Partial<Layer>): Promise<Layer> =>
    apiFetch('/layers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /**
   * Actualizar capa.
   */
  update: (id: string, data: Partial<Layer>): Promise<Layer> =>
    apiFetch(`/layers/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  /**
   * Eliminar capa.
   */
  delete: (id: string): Promise<void> => apiFetch(`/layers/${id}`, { method: 'DELETE' }),

  /**
   * Reordenar capas.
   */
  reorder: (layers: { id: string; orden: number }[]): Promise<void> =>
    apiFetch('/layers/reorder', {
      method: 'POST',
      body: JSON.stringify({ layers }),
    }),

  /**
   * Subir archivo GeoJSON.
   */
  upload: async (file: File, nombre: string, tipo: string, color: string): Promise<Layer> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('nombre', nombre);
    formData.append('tipo', tipo);
    formData.append('color', color);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), LONG_TIMEOUT);

    try {
      // Get auth token for authenticated upload
      const token = await getAuthToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(`${API_URL}${API_PREFIX}/layers/upload`, {
        method: 'POST',
        headers,
        body: formData,
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Error al subir archivo');
      }

      return response.json();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('La subida del archivo excedio el tiempo limite');
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  },
};
