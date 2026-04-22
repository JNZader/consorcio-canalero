/**
 * Layers API module - Vector layers management.
 */

import type { Layer } from '../../types';
import { API_PREFIX, API_URL, LONG_TIMEOUT, apiFetch, getAuthToken, unwrapItems } from './core';

export const layersApi = {
  /**
   * Obtener todas las capas.
   */
  getAll: async (visibleOnly = false): Promise<Layer[]> =>
    unwrapItems<Layer>(await apiFetch(`/capas?visible_only=${visibleOnly}`)),

  /**
   * Obtener una capa.
   */
  get: (id: string): Promise<Layer> => apiFetch(`/capas/${id}`),

  /**
   * Crear capa.
   */
  create: (data: Partial<Layer>): Promise<Layer> =>
    apiFetch('/capas', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /**
   * Actualizar capa.
   */
  update: (id: string, data: Partial<Layer>): Promise<Layer> =>
    apiFetch(`/capas/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  /**
   * Eliminar capa.
   */
  delete: (id: string): Promise<void> => apiFetch(`/capas/${id}`, { method: 'DELETE' }),

  /**
   * Reordenar capas.
   */
  reorder: (layers: { id: string; orden: number }[]): Promise<void> =>
    apiFetch('/capas/reorder', {
      method: 'PUT',
      body: JSON.stringify({ ordered_ids: layers.map((l) => l.id) }),
    }),

  /**
   * Subir archivo GeoJSON.
   * In v2, upload is done via POST /capas with JSON body (not multipart).
   */
  upload: async (file: File, nombre: string, tipo: string, color: string): Promise<Layer> => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), LONG_TIMEOUT);

    try {
      // Read file content as text (GeoJSON)
      const fileContent = await file.text();
      const geojsonData = JSON.parse(fileContent);

      const token = await getAuthToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(`${API_URL}${API_PREFIX}/capas`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          nombre,
          tipo,
          color,
          geojson_data: geojsonData,
        }),
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
