import type { ReactNode } from 'react';
import { publicApi } from '../../lib/api';
import { logger } from '../../lib/logger';
import { showNotification as notify } from '../../lib/notifications';
import { QueryError } from '../../lib/queryError';
import type { Ubicacion } from './reportFormTypes';

export const OFFLINE_SUBMIT_TITLE = 'Sin conexión';
export const OFFLINE_SUBMIT_MESSAGE =
  'No pudimos enviar el reporte. Puede que estés sin conexión. Los datos siguen en el formulario.';

/**
 * El service worker responde 503 (NetworkOnly) cuando el POST sale sin red.
 * Un `fetch` que el worker rechaza llega como TypeError "Failed to fetch".
 * Los dos son el mismo estado para quien está completando la denuncia.
 */
export function isOfflineSubmitError(error: unknown): boolean {
  if (error instanceof QueryError && error.statusCode === 503) return true;
  if (!(error instanceof Error)) return false;
  if (/\b503\b/.test(error.message) || /service unavailable/i.test(error.message)) return true;
  return /failed to fetch|networkerror|network request failed|load failed/i.test(error.message);
}

export function showNotification(title: string, message: string, color: string) {
  notify(title, message, color);
}

export function getBadgeVariant(
  isPrimary: boolean,
  isComplete: boolean
): 'filled' | 'light' | 'outline' {
  if (isPrimary) return isComplete ? 'filled' : 'light';
  return isComplete ? 'light' : 'outline';
}

export function getBadgeColor(isPrimary: boolean, isComplete: boolean): string {
  if (isPrimary) return isComplete ? 'green' : 'blue';
  return isComplete ? 'blue' : 'gray';
}

export function handleGeoSuccess(
  position: GeolocationPosition,
  setUbicacion: (u: Ubicacion) => void,
  setObteniendoUbicacion: (b: boolean) => void,
  announce: (msg: string) => void
) {
  const { latitude, longitude } = position.coords;
  setUbicacion({ lat: latitude, lng: longitude });
  setObteniendoUbicacion(false);
  showNotification('Ubicación obtenida', 'Se detectó tu ubicación correctamente', 'green');
  announce(`Ubicación obtenida: latitud ${latitude.toFixed(4)}, longitud ${longitude.toFixed(4)}`);
}

export function handleGeoError(
  setObteniendoUbicacion: (b: boolean) => void,
  announce: (msg: string, priority?: 'polite' | 'assertive') => void
) {
  setObteniendoUbicacion(false);
  showNotification(
    'Error de ubicación',
    'No se pudo obtener tu ubicación. Seleccioná en el mapa.',
    'red'
  );
  announce(
    'No se pudo obtener tu ubicación. Usá el mapa o ingresá coordenadas manualmente.',
    'assertive'
  );
}

/**
 * Upload the citizen's photo and attach it to an EXISTING denuncia.
 *
 * The denuncia must be created first because the upload endpoint needs
 * its ID in the URL — see `useReportFormSubmission` for the orchestration.
 * Failures here are non-fatal: the denuncia stays saved, we just notify
 * the user that the photo didn't make it (matches the previous UX).
 */
export async function uploadPhotoIfExists(
  denunciaId: string,
  foto: File | null,
  _announce: (msg: string) => void
): Promise<string | undefined> {
  if (!foto) return undefined;

  try {
    const uploadResult = await publicApi.uploadPhoto(denunciaId, foto);
    return uploadResult.photo_url;
  } catch (error) {
    logger.error('Error subiendo foto:', error);
    showNotification(
      'Aviso',
      'No se pudo subir la foto, pero la denuncia se enviara sin ella.',
      'yellow'
    );
    return undefined;
  }
}

export function getErrorString(error: ReactNode): string | undefined {
  if (typeof error === 'string') {
    return error;
  }
  return undefined;
}
