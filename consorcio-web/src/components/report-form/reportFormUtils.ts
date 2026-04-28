import { notifications } from '@mantine/notifications';
import type { ReactNode } from 'react';
import { publicApi } from '../../lib/api';
import { logger } from '../../lib/logger';
import type { Ubicacion } from './reportFormTypes';

export function showNotification(title: string, message: string, color: string) {
  notifications.show({ title, message, color });
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
  showNotification('Ubicacion obtenida', 'Se detecto tu ubicacion correctamente', 'green');
  announce(`Ubicacion obtenida: latitud ${latitude.toFixed(4)}, longitud ${longitude.toFixed(4)}`);
}

export function handleGeoError(
  setObteniendoUbicacion: (b: boolean) => void,
  announce: (msg: string, priority?: 'polite' | 'assertive') => void
) {
  setObteniendoUbicacion(false);
  showNotification(
    'Error de ubicacion',
    'No se pudo obtener tu ubicacion. Selecciona en el mapa.',
    'red'
  );
  announce(
    'No se pudo obtener tu ubicacion. Usa el mapa o ingresa coordenadas manualmente.',
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
