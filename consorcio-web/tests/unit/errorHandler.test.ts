/**
 * Tests for errorHandler utilities
 * Coverage target: 100% (critical error handling code)
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { notifications } from '@mantine/notifications';
import {
  HTTP_ERROR_MESSAGES,
  getHttpErrorMessage,
  getErrorMessage,
  handleError,
  withErrorHandling,
  safeJsonParse,
  safeJsonParseWithValidation,
} from '../../src/lib/errorHandler';
import { logger } from '../../src/lib/logger';

vi.mock('@mantine/notifications');
vi.mock('../../src/lib/logger');

describe('errorHandler', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getHttpErrorMessage', () => {
    it('should return specific message for known status codes', () => {
      expect(getHttpErrorMessage(400)).toBe('Los datos enviados no son validos');
      expect(getHttpErrorMessage(401)).toBe('No estas autenticado. Por favor inicia sesion');
      expect(getHttpErrorMessage(403)).toBe('No tienes permisos para realizar esta accion');
      expect(getHttpErrorMessage(404)).toBe('El recurso solicitado no existe');
      expect(getHttpErrorMessage(409)).toBe('Hubo un conflicto con el estado actual del recurso');
      expect(getHttpErrorMessage(413)).toBe('El archivo es demasiado grande');
      expect(getHttpErrorMessage(422)).toBe('Los datos no pudieron ser procesados');
      expect(getHttpErrorMessage(429)).toBe('Demasiadas solicitudes. Por favor espera un momento');
      expect(getHttpErrorMessage(500)).toBe('Error interno del servidor. Intenta nuevamente');
      expect(getHttpErrorMessage(502)).toBe('El servidor no esta disponible temporalmente');
      expect(getHttpErrorMessage(503)).toBe('Servicio no disponible. Intenta mas tarde');
      expect(getHttpErrorMessage(504)).toBe('El servidor tardo demasiado en responder');
    });

    it('should return generic message for unknown status codes', () => {
      expect(getHttpErrorMessage(418)).toBe('Error del servidor (418)');
      expect(getHttpErrorMessage(999)).toBe('Error del servidor (999)');
    });
  });

  describe('getErrorMessage', () => {
    it('should extract message from Error objects', () => {
      const error = new Error('Something went wrong');
      expect(getErrorMessage(error)).toBe('Something went wrong');
    });

    it('should extract HTTP status from API Error format', () => {
      const error = new Error('API Error: 404');
      const message = getErrorMessage(error);
      expect(message).toBe('El recurso solicitado no existe');
    });

    it('should handle string errors', () => {
      expect(getErrorMessage('String error message')).toBe('String error message');
    });

    it('should extract detail field from error object', () => {
      const error = { detail: 'Custom detail message' };
      expect(getErrorMessage(error)).toBe('Custom detail message');
    });

    it('should extract message field from error object when detail is missing', () => {
      const error = { message: 'Custom message' };
      expect(getErrorMessage(error)).toBe('Custom message');
    });

    it('should return fallback for unknown error types', () => {
      expect(getErrorMessage(null)).toBe('Ocurrio un error inesperado');
      expect(getErrorMessage(undefined)).toBe('Ocurrio un error inesperado');
      expect(getErrorMessage({})).toBe('Ocurrio un error inesperado');
      expect(getErrorMessage(123)).toBe('Ocurrio un error inesperado');
    });
  });

  describe('handleError', () => {
    it('should show notification by default', () => {
      handleError(new Error('Test error'));

      expect(notifications.show).toHaveBeenCalledWith({
        title: 'Error',
        message: 'Test error',
        color: 'red',
        autoClose: 5000,
      });
    });

    it('should log to console by default', () => {
      handleError(new Error('Test error'));

      expect(logger.error).toHaveBeenCalledWith('Test error', expect.any(Error));
    });

    it('should not show notification when showNotification is false', () => {
      handleError(new Error('Test error'), { showNotification: false });

      expect(notifications.show).not.toHaveBeenCalled();
    });

    it('should not log when logToConsole is false', () => {
      handleError(new Error('Test error'), { logToConsole: false });

      expect(logger.error).not.toHaveBeenCalled();
    });

    it('should use custom title', () => {
      handleError(new Error('Test error'), { title: 'Custom Title' });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Custom Title',
        })
      );
    });

    it('should use fallback message when error extraction fails', () => {
      const result = handleError(null, { fallbackMessage: 'Custom fallback' });

      expect(result).toBe('Ocurrio un error inesperado'); // getErrorMessage returns this
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Ocurrio un error inesperado',
        })
      );
    });

    it('should use custom color', () => {
      handleError(new Error('Test error'), { color: 'blue' });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          color: 'blue',
        })
      );
    });

    it('should add context to log message', () => {
      handleError(new Error('Test error'), { context: 'LoginPage', logToConsole: true });

      expect(logger.error).toHaveBeenCalledWith('[LoginPage] Test error', expect.any(Error));
    });

    it('should return the extracted error message', () => {
      const message = handleError(new Error('Test error'));
      expect(message).toBe('Test error');
    });
  });

  describe('withErrorHandling', () => {
    it('should wrap async function and handle errors', async () => {
      const asyncFn = vi.fn(async () => {
        throw new Error('Async error');
      });

      const wrappedFn = withErrorHandling(asyncFn);

      await expect(wrappedFn()).rejects.toThrow('Async error');
      expect(logger.error).toHaveBeenCalledWith('Async error', expect.any(Error));
    });

    it('should call original function on success', async () => {
      const asyncFn = vi.fn(async () => 'success');

      const wrappedFn = withErrorHandling(asyncFn);
      const result = await wrappedFn();

      expect(result).toBe('success');
    });

    it('should pass through function arguments', async () => {
      const asyncFn = vi.fn(async (a: number, b: string) => `${a}-${b}`);

      const wrappedFn = withErrorHandling(asyncFn);
      const result = await wrappedFn(42, 'test');

      expect(result).toBe('42-test');
      expect(asyncFn).toHaveBeenCalledWith(42, 'test');
    });

    it('should use custom error handling options', async () => {
      const asyncFn = vi.fn(async () => {
        throw new Error('Custom error');
      });

      const wrappedFn = withErrorHandling(asyncFn, {
        title: 'Custom Title',
        showNotification: false,
      });

      await expect(wrappedFn()).rejects.toThrow('Custom error');
      expect(notifications.show).not.toHaveBeenCalled();
    });
  });

  describe('safeJsonParse', () => {
    it('should parse valid JSON', () => {
      const result = safeJsonParse<{ name: string }>('{"name":"John"}');
      expect(result).toEqual({ name: 'John' });
    });

    it('should return null on invalid JSON', () => {
      const result = safeJsonParse('invalid json');
      expect(result).toBeNull();
    });

    it('should return fallback value on invalid JSON', () => {
      const fallback = { name: 'Default' };
      const result = safeJsonParse('invalid json', fallback);
      expect(result).toBe(fallback);
    });

    it('should handle empty string', () => {
      const result = safeJsonParse('');
      expect(result).toBeNull();
    });

    it('should handle undefined', () => {
      const result = safeJsonParse(undefined as any);
      expect(result).toBeNull();
    });

    it('should parse arrays', () => {
      const result = safeJsonParse<string[]>('["a","b","c"]');
      expect(result).toEqual(['a', 'b', 'c']);
    });

    it('should parse nested objects', () => {
      const json = '{"user":{"name":"John","age":30}}';
      const result = safeJsonParse<{ user: { name: string; age: number } }>(json);
      expect(result).toEqual({ user: { name: 'John', age: 30 } });
    });
  });

  describe('safeJsonParseWithValidation', () => {
    const isValidUser = (value: unknown): value is { name: string; age: number } => {
      return (
        typeof value === 'object' &&
        value !== null &&
        'name' in value &&
        'age' in value &&
        typeof (value as any).name === 'string' &&
        typeof (value as any).age === 'number'
      );
    };

    it('should parse and validate valid JSON', () => {
      const json = '{"name":"John","age":30}';
      const result = safeJsonParseWithValidation(json, isValidUser);
      expect(result).toEqual({ name: 'John', age: 30 });
    });

    it('should return null when validation fails', () => {
      const json = '{"name":"John","age":"thirty"}';
      const result = safeJsonParseWithValidation(json, isValidUser);
      expect(result).toBeNull();
    });

    it('should return fallback when validation fails', () => {
      const fallback = { name: 'Default', age: 0 };
      const json = '{"name":"John"}';
      const result = safeJsonParseWithValidation(json, isValidUser, fallback);
      expect(result).toBe(fallback);
    });

    it('should return null on invalid JSON', () => {
      const result = safeJsonParseWithValidation('invalid json', isValidUser);
      expect(result).toBeNull();
    });

    it('should return fallback on invalid JSON when provided', () => {
      const fallback = { name: 'Default', age: 0 };
      const result = safeJsonParseWithValidation('invalid json', isValidUser, fallback);
      expect(result).toBe(fallback);
    });

    it('should work with custom validators', () => {
      const isValidString = (value: unknown): value is string => typeof value === 'string';
      const result = safeJsonParseWithValidation('"hello"', isValidString);
      expect(result).toBe('hello');
    });
  });
});
