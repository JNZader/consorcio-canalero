/**
 * api-reexports.test.ts
 * Tests for API re-export files
 * These files should have near 100% coverage as they're just re-exports
 */

import { describe, it, expect } from 'vitest';

describe('API Re-export Files', () => {
  describe('lib/api.ts', () => {
    it('should re-export all core functions', async () => {
      // This forces TypeScript to evaluate the imports
      const api = await import('../../src/lib/api');
      
      expect(api.API_URL).toBeDefined();
      expect(api.API_PREFIX).toBeDefined();
      expect(api.DEFAULT_TIMEOUT).toBeDefined();
      expect(api.LONG_TIMEOUT).toBeDefined();
      expect(api.HEALTH_TIMEOUT).toBeDefined();
      expect(typeof api.apiFetch).toBe('function');
      expect(typeof api.getAuthToken).toBe('function');
      expect(typeof api.clearAuthTokenCache).toBe('function');
      expect(typeof api.healthCheck).toBe('function');
      expect(typeof api.getExportAcceptHeader).toBe('function');
    });

    it('should re-export all report APIs', async () => {
      const api = await import('../../src/lib/api');
      expect(api.reportsApi).toBeDefined();
      expect(api.publicApi).toBeDefined();
      expect(api.statsApi).toBeDefined();
    });

    it('should re-export layers API', async () => {
      const api = await import('../../src/lib/api');
      expect(api.layersApi).toBeDefined();
    });

    it('should re-export sugerencias API', async () => {
      const api = await import('../../src/lib/api');
      expect(api.sugerenciasApi).toBeDefined();
    });

    it('should re-export monitoring API', async () => {
      const api = await import('../../src/lib/api');
      expect(api.monitoringApi).toBeDefined();
    });

    it('should re-export config API', async () => {
      const api = await import('../../src/lib/api');
      expect(api.configApi).toBeDefined();
    });
  });

  describe('lib/api/index.ts', () => {
    it('should re-export all APIs from index', async () => {
      // Import from the explicit index.ts path
      const api = await import('../../src/lib/api/index');
      
      expect(api.API_URL).toBeDefined();
      expect(api.reportsApi).toBeDefined();
      expect(api.layersApi).toBeDefined();
      expect(api.sugerenciasApi).toBeDefined();
      expect(api.monitoringApi).toBeDefined();
    });
  });
});
