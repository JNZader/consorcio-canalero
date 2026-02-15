/**
 * Notification helpers for consistent user feedback.
 *
 * Usage:
 *   import { showSuccess, showError, showWarning, showInfo } from '../lib/notifications';
 *
 *   showSuccess('Guardado', 'Los datos se guardaron correctamente');
 *   showError('Error', 'No se pudo guardar');
 *   showWarning('Atencion', 'Accion requerida');
 *   showInfo('Info', 'Proceso completado');
 */

import { notifications } from '@mantine/notifications';

/**
 * Show a success notification (green).
 */
export function showSuccess(title: string, message: string): void {
  notifications.show({
    title,
    message,
    color: 'green',
  });
}

/**
 * Show an error notification (red).
 */
export function showError(title: string, message: string): void {
  notifications.show({
    title,
    message,
    color: 'red',
  });
}

/**
 * Show a warning notification (orange).
 */
export function showWarning(title: string, message: string): void {
  notifications.show({
    title,
    message,
    color: 'orange',
  });
}

/**
 * Show an info notification (blue).
 */
export function showInfo(title: string, message: string): void {
  notifications.show({
    title,
    message,
    color: 'blue',
  });
}

/**
 * Show a notification with custom color.
 * Prefer using the typed helpers above when possible.
 */
export function showNotification(
  title: string,
  message: string,
  color: 'green' | 'red' | 'orange' | 'blue' | 'yellow' | 'gray'
): void {
  notifications.show({
    title,
    message,
    color,
  });
}

/**
 * Show error notification from an Error object or unknown error.
 * Extracts the message automatically.
 */
export function showErrorFromException(title: string, error: unknown, fallback = 'Error desconocido'): void {
  const message = error instanceof Error ? error.message : fallback;
  showError(title, message);
}
