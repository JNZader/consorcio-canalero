/**
 * Hook for downloading a QGIS project file (.qgz) from the backend.
 *
 * Calls GET /api/v2/geo/export/qgis with the authenticated user's JWT.
 * On success, triggers a browser file download using the Blob URL pattern
 * (same approach used in AdminDashboard) — no page reload required.
 *
 * Returns:
 *   download      — async function that initiates the download
 *   isDownloading — true while the request is in flight
 *   error         — human-readable error message, null when clear
 */

import { useState } from 'react';
import { API_URL, API_PREFIX, getAuthToken } from '../lib/api/core';

export interface UseQgisExportReturn {
  download: () => Promise<void>;
  isDownloading: boolean;
  error: string | null;
}

export function useQgisExport(): UseQgisExportReturn {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async (): Promise<void> => {
    setIsDownloading(true);
    setError(null);

    try {
      const token = await getAuthToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(`${API_URL}${API_PREFIX}/geo/export/qgis`, {
        method: 'GET',
        headers,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = (body as { detail?: string }).detail;
        throw new Error(detail ?? `Error al descargar el proyecto QGIS (${response.status})`);
      }

      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);

      const anchor = document.createElement('a');
      anchor.href = blobUrl;
      anchor.download = 'consorcio-canalero.qgz';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);

      // Release the object URL after the browser has picked it up.
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Ocurrio un error inesperado al descargar el proyecto QGIS.',
      );
    } finally {
      setIsDownloading(false);
    }
  };

  return { download, isDownloading, error };
}
