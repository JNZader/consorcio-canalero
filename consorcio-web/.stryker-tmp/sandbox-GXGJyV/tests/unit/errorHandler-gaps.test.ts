// @ts-nocheck
// tests/unit/errorHandler-gaps.test.ts
// Unit: Error handler coverage gaps
// Coverage Target: Fill in missing lines

import { describe, it, expect } from 'vitest';
import { getErrorMessage, getHttpErrorMessage } from '../../src/lib/errorHandler';

describe('errorHandler - missing lines coverage', () => {
  describe('API error extraction with status codes', () => {
    it('should extract HTTP status code from API Error message (line 45)', () => {
      // Line 45: if (statusMatch) { return getHttpErrorMessage(...) }
      const apiError = new Error('API Error: 404 - Not Found');
      const message = getErrorMessage(apiError);
      
      // Should return the HTTP error message for 404
      expect(message).toBeTruthy();
      expect(message).toContain('no existe');
    });

    it('should handle 500 status code from API error', () => {
      const apiError = new Error('API Error: 500 - Internal Server Error');
      const message = getErrorMessage(apiError);
      
      expect(message).toBeTruthy();
      expect(message).toContain('Error interno');
    });

    it('should handle 401 status code from API error', () => {
      const apiError = new Error('API Error: 401 - Unauthorized');
      const message = getErrorMessage(apiError);
      
      expect(message).toBeTruthy();
      expect(message).toContain('autenticado');
    });

    it('should handle 403 status code from API error', () => {
      const apiError = new Error('API Error: 403 - Forbidden');
      const message = getErrorMessage(apiError);
      
      expect(message).toBeTruthy();
      expect(message).toContain('permisos');
    });

    it('should handle 429 status code from API error', () => {
      const apiError = new Error('API Error: 429 - Too Many Requests');
      const message = getErrorMessage(apiError);
      
      expect(message).toBeTruthy();
      expect(message).toContain('solicitudes');
    });
  });

  describe('getHttpErrorMessage direct calls', () => {
    it('should handle 400 Bad Request', () => {
      const message = getHttpErrorMessage(400);
      expect(message).toContain('datos');
      expect(message).toContain('validos');
    });

    it('should handle 402 Payment Required', () => {
      const message = getHttpErrorMessage(402);
      expect(message).toBeTruthy();
    });

    it('should handle 408 Request Timeout', () => {
      const message = getHttpErrorMessage(408);
      expect(message).toBeTruthy();
    });

    it('should handle 503 Service Unavailable', () => {
      const message = getHttpErrorMessage(503);
      expect(message).toBeTruthy();
    });

    it('should handle unknown status codes', () => {
      const message = getHttpErrorMessage(999);
      expect(message).toBeTruthy();
      expect(typeof message).toBe('string');
    });
  });

  describe('Error message fallback behavior', () => {
    it('should return fallback when error produces empty string', () => {
      // This tests the fallback logic at line 104
      // Create an error object that might result in empty message
      const weirdError = { foo: 'bar' };
      const message = getErrorMessage(weirdError);
      
      // Should return a default error message, not empty
      expect(message).toBeTruthy();
      expect(message).not.toBe('');
    });

    it('should handle null/undefined gracefully', () => {
      const message = getErrorMessage(null);
      expect(message).toBeTruthy();
      expect(message).toBe('Ocurrio un error inesperado');
    });

    it('should handle undefined errors', () => {
      const message = getErrorMessage(undefined);
      expect(message).toBeTruthy();
    });
  });
});
