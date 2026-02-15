/**
 * Shared error handling utilities for the Consorcio Canalero application.
 */

import { notifications } from '@mantine/notifications';
import { logger } from './logger';

/**
 * Standard error messages in Spanish for common HTTP status codes.
 */
export const HTTP_ERROR_MESSAGES: Record<number, string> = {
  400: 'Los datos enviados no son validos',
  401: 'No estas autenticado. Por favor inicia sesion',
  403: 'No tienes permisos para realizar esta accion',
  404: 'El recurso solicitado no existe',
  409: 'Hubo un conflicto con el estado actual del recurso',
  413: 'El archivo es demasiado grande',
  422: 'Los datos no pudieron ser procesados',
  429: 'Demasiadas solicitudes. Por favor espera un momento',
  500: 'Error interno del servidor. Intenta nuevamente',
  502: 'El servidor no esta disponible temporalmente',
  503: 'Servicio no disponible. Intenta mas tarde',
  504: 'El servidor tardo demasiado en responder',
};

/**
 * Get a user-friendly error message from an HTTP status code.
 * @param status - The HTTP status code
 * @returns User-friendly error message in Spanish
 */
export function getHttpErrorMessage(status: number): string {
  return HTTP_ERROR_MESSAGES[status] || `Error del servidor (${status})`;
}

/**
 * Extract a user-friendly error message from various error types.
 * @param error - The error object (can be Error, API response, or unknown)
 * @returns User-friendly error message
 */
export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    // Check if it's an API error with a message
    if (error.message.startsWith('API Error:')) {
      const statusMatch = error.message.match(/API Error: (\d+)/);
      if (statusMatch) {
        return getHttpErrorMessage(Number.parseInt(statusMatch[1], 10));
      }
    }
    return error.message;
  }

  if (typeof error === 'string') {
    return error;
  }

  if (error && typeof error === 'object') {
    // Handle API error responses
    const apiError = error as Record<string, unknown>;
    if (typeof apiError.detail === 'string') {
      return apiError.detail;
    }
    if (typeof apiError.message === 'string') {
      return apiError.message;
    }
  }

  return 'Ocurrio un error inesperado';
}

/**
 * Options for the handleError function.
 */
interface HandleErrorOptions {
  /** Title for the notification */
  title?: string;
  /** Custom fallback message if error message extraction fails */
  fallbackMessage?: string;
  /** Whether to show a notification (default: true) */
  showNotification?: boolean;
  /** Notification color (default: 'red') */
  color?: string;
  /** Whether to log to console (default: true) */
  logToConsole?: boolean;
  /** Additional context for console logging */
  context?: string;
}

/**
 * Standard error handler that shows a notification and logs to console.
 * @param error - The error to handle
 * @param options - Configuration options
 * @returns The extracted error message
 */
export function handleError(error: unknown, options: HandleErrorOptions = {}): string {
  const {
    title = 'Error',
    fallbackMessage = 'Ocurrio un error inesperado',
    showNotification = true,
    color = 'red',
    logToConsole = true,
    context,
  } = options;

  const message = getErrorMessage(error) || fallbackMessage;

  if (logToConsole) {
    const logMessage = context ? `[${context}] ${message}` : message;
    logger.error(logMessage, error);
  }

  if (showNotification) {
    notifications.show({
      title,
      message,
      color,
      autoClose: 5000,
    });
  }

  return message;
}

/**
 * Wrapper for async functions that provides standard error handling.
 * @param fn - The async function to wrap
 * @param options - Error handling options
 * @returns The wrapped function
 */
export function withErrorHandling<T extends (...args: unknown[]) => Promise<unknown>>(
  fn: T,
  options: HandleErrorOptions = {}
): T {
  return (async (...args: Parameters<T>) => {
    try {
      return await fn(...args);
    } catch (error) {
      handleError(error, options);
      throw error;
    }
  }) as T;
}

/**
 * Safe JSON parse that returns null on error instead of throwing.
 * WARNING: This function does not validate the parsed data structure.
 * For type-safe parsing, use safeJsonParseValidated from typeGuards.ts.
 *
 * @param json - The JSON string to parse
 * @param fallback - Optional fallback value
 * @returns Parsed object or fallback value
 *
 * @example
 * // Simple usage (no type validation - use with caution)
 * const data = safeJsonParse<MyType>(jsonString);
 *
 * // Preferred: Use safeJsonParseValidated for runtime validation
 * import { safeJsonParseValidated, isValidLayerStyle } from './typeGuards';
 * const style = safeJsonParseValidated(json, isValidLayerStyle);
 */
export function safeJsonParse<T>(json: string, fallback: T | null = null): T | null {
  try {
    return JSON.parse(json) as T;
  } catch {
    return fallback;
  }
}

/**
 * Safe JSON parse with type validation using a type guard.
 * Ensures the parsed data matches the expected structure.
 *
 * @param json - The JSON string to parse
 * @param validator - Type guard function to validate the parsed data
 * @param fallback - Optional fallback value if parsing or validation fails
 * @returns Validated parsed object or fallback value
 *
 * @example
 * const style = safeJsonParseWithValidation(
 *   jsonString,
 *   isValidLayerStyle,
 *   { color: '#3388ff', weight: 2, fillColor: '#3388ff', fillOpacity: 0.1 }
 * );
 */
export function safeJsonParseWithValidation<T>(
  json: string,
  validator: (value: unknown) => value is T,
  fallback: T | null = null
): T | null {
  try {
    const parsed = JSON.parse(json);
    return validator(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}
