/**
 * Notification helpers for consistent user feedback.
 *
 * Every toast goes through this module. Call sites do not import
 * `notifications` from `@mantine/notifications`.
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
import type { ReactNode } from 'react';

export type NotificationColor =
  | 'green'
  | 'red'
  | 'orange'
  | 'blue'
  | 'yellow'
  | 'gray'
  | (string & {});

export interface NotificationExtras {
  readonly icon?: ReactNode;
  readonly autoClose?: number | false;
  /** Identificador estable para actualizar o cerrar el mismo toast. */
  readonly id?: string;
  /** Sitúa el toast debajo del header del sitio. */
  readonly belowHeader?: boolean;
}

export interface ToastInput extends NotificationExtras {
  readonly title?: ReactNode;
  readonly message: ReactNode;
  readonly color: NotificationColor;
}

function emit(
  title: ReactNode | undefined,
  message: ReactNode,
  color: NotificationColor,
  options?: NotificationExtras
): void {
  notifications.show({
    ...(title !== undefined ? { title } : {}),
    message,
    color,
    ...(options?.icon !== undefined ? { icon: options.icon } : {}),
    ...(options?.autoClose !== undefined ? { autoClose: options.autoClose } : {}),
    ...(options?.id !== undefined ? { id: options.id } : {}),
    ...(options?.belowHeader ? { className: 'cc-toast-below-header' } : {}),
  });
}

/**
 * Show a success notification (green).
 */
export function showSuccess(title: string, message: string, options?: NotificationExtras): void {
  emit(title, message, 'green', options);
}

/**
 * Show an error notification (red).
 */
export function showError(title: string, message: string, options?: NotificationExtras): void {
  emit(title, message, 'red', options);
}

/**
 * Show a warning notification (orange).
 */
export function showWarning(title: string, message: string, options?: NotificationExtras): void {
  emit(title, message, 'orange', options);
}

/**
 * Show an info notification (blue).
 */
export function showInfo(title: string, message: string, options?: NotificationExtras): void {
  emit(title, message, 'blue', options);
}

/**
 * Show a notification with custom color.
 * Prefer using the typed helpers above when possible.
 */
export function showNotification(
  title: string,
  message: string,
  color: NotificationColor,
  options?: NotificationExtras
): void {
  emit(title, message, color, options);
}

/**
 * Toast con payload explícito. Cubre avisos sin título y colores que
 * llegan como string (por ejemplo el color de `handleError`).
 */
export function showToast(input: ToastInput): void {
  emit(input.title, input.message, input.color, input);
}

/** Cierra un toast abierto con `id`. No hace nada si ya no está. */
export function hideToast(id: string): void {
  notifications.hide(id);
}

/**
 * Show error notification from an Error object or unknown error.
 * Extracts the message automatically.
 */
export function showErrorFromException(
  title: string,
  error: unknown,
  fallback = 'Error desconocido'
): void {
  const message = error instanceof Error ? error.message : fallback;
  showError(title, message);
}
