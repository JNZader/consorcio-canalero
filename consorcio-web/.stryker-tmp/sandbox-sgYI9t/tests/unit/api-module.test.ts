/**
 * Tests for API module re-exports and backwards compatibility
 * Coverage target: 100%
 */
// @ts-nocheck


import { describe, it, expect } from 'vitest';
import * as apiModule from '../../src/lib/api';

describe('api module', () => {
  describe('type exports', () => {
    it('should be importable', () => {
      expect(apiModule).toBeDefined();
    });

    it('should have type definitions available', () => {
      // These are type-only exports, but we verify the module loads
      expect(apiModule).toBeDefined();
    });
  });

  describe('core api exports', () => {
    it('should export API_URL', () => {
      expect(apiModule.API_URL).toBeDefined();
      expect(typeof apiModule.API_URL).toBe('string');
    });

    it('should export API_PREFIX', () => {
      expect(apiModule.API_PREFIX).toBeDefined();
      expect(typeof apiModule.API_PREFIX).toBe('string');
    });

    it('should export DEFAULT_TIMEOUT', () => {
      expect(apiModule.DEFAULT_TIMEOUT).toBeDefined();
      expect(typeof apiModule.DEFAULT_TIMEOUT).toBe('number');
    });

    it('should export LONG_TIMEOUT', () => {
      expect(apiModule.LONG_TIMEOUT).toBeDefined();
      expect(typeof apiModule.LONG_TIMEOUT).toBe('number');
    });

    it('should export HEALTH_TIMEOUT', () => {
      expect(apiModule.HEALTH_TIMEOUT).toBeDefined();
      expect(typeof apiModule.HEALTH_TIMEOUT).toBe('number');
    });

    it('should export apiFetch function', () => {
      expect(typeof apiModule.apiFetch).toBe('function');
    });

    it('should export getAuthToken function', () => {
      expect(typeof apiModule.getAuthToken).toBe('function');
    });

    it('should export clearAuthTokenCache function', () => {
      expect(typeof apiModule.clearAuthTokenCache).toBe('function');
    });

    it('should export healthCheck function', () => {
      expect(typeof apiModule.healthCheck).toBe('function');
    });

    it('should export getExportAcceptHeader function', () => {
      expect(typeof apiModule.getExportAcceptHeader).toBe('function');
    });
  });

  describe('reports api exports', () => {
    it('should export reportsApi', () => {
      expect(apiModule.reportsApi).toBeDefined();
      expect(typeof apiModule.reportsApi).toBe('object');
    });

    it('should export publicApi', () => {
      expect(apiModule.publicApi).toBeDefined();
      expect(typeof apiModule.publicApi).toBe('object');
    });

    it('should export statsApi', () => {
      expect(apiModule.statsApi).toBeDefined();
      expect(typeof apiModule.statsApi).toBe('object');
    });
  });

  describe('layers api exports', () => {
    it('should export layersApi', () => {
      expect(apiModule.layersApi).toBeDefined();
      expect(typeof apiModule.layersApi).toBe('object');
    });
  });

  describe('sugerencias api exports', () => {
    it('should export sugerenciasApi', () => {
      expect(apiModule.sugerenciasApi).toBeDefined();
      expect(typeof apiModule.sugerenciasApi).toBe('object');
    });
  });

  describe('monitoring api exports', () => {
    it('should export monitoringApi', () => {
      expect(apiModule.monitoringApi).toBeDefined();
      expect(typeof apiModule.monitoringApi).toBe('object');
    });
  });

  describe('config api exports', () => {
    it('should export configApi', () => {
      expect(apiModule.configApi).toBeDefined();
      expect(typeof apiModule.configApi).toBe('object');
    });
  });

  describe('backwards compatibility', () => {
    it('should have all core functions and objects available at top level', () => {
      expect(apiModule.API_URL).toBeDefined();
      expect(apiModule.apiFetch).toBeDefined();
      expect(apiModule.reportsApi).toBeDefined();
      expect(apiModule.layersApi).toBeDefined();
      expect(apiModule.sugerenciasApi).toBeDefined();
      expect(apiModule.monitoringApi).toBeDefined();
      expect(apiModule.configApi).toBeDefined();
    });

    it('should re-export all required types for type safety', () => {
      // Verify that the module is properly structured
      expect(apiModule).toBeDefined();
      expect(Object.keys(apiModule).length).toBeGreaterThan(0);
    });

    it('should export timeout constants in ascending order', () => {
      expect(apiModule.HEALTH_TIMEOUT).toBeLessThan(apiModule.DEFAULT_TIMEOUT);
      expect(apiModule.DEFAULT_TIMEOUT).toBeLessThan(apiModule.LONG_TIMEOUT);
    });
  });

  describe('api endpoint objects', () => {
    it('reportsApi should be an object', () => {
      expect(typeof apiModule.reportsApi).toBe('object');
      expect(apiModule.reportsApi).not.toBeNull();
    });

    it('layersApi should be an object', () => {
      expect(typeof apiModule.layersApi).toBe('object');
      expect(apiModule.layersApi).not.toBeNull();
    });

    it('sugerenciasApi should be an object', () => {
      expect(typeof apiModule.sugerenciasApi).toBe('object');
      expect(apiModule.sugerenciasApi).not.toBeNull();
    });

    it('monitoringApi should be an object', () => {
      expect(typeof apiModule.monitoringApi).toBe('object');
      expect(apiModule.monitoringApi).not.toBeNull();
    });

    it('configApi should be an object', () => {
      expect(typeof apiModule.configApi).toBe('object');
      expect(apiModule.configApi).not.toBeNull();
    });

    it('publicApi should be an object', () => {
      expect(typeof apiModule.publicApi).toBe('object');
      expect(apiModule.publicApi).not.toBeNull();
    });

    it('statsApi should be an object', () => {
      expect(typeof apiModule.statsApi).toBe('object');
      expect(apiModule.statsApi).not.toBeNull();
    });
  });

  describe('module structure', () => {
    it('should export correct number of main functions and objects', () => {
      const mainExports = [
        'API_URL',
        'API_PREFIX',
        'DEFAULT_TIMEOUT',
        'LONG_TIMEOUT',
        'HEALTH_TIMEOUT',
        'apiFetch',
        'getAuthToken',
        'clearAuthTokenCache',
        'healthCheck',
        'getExportAcceptHeader',
        'reportsApi',
        'publicApi',
        'statsApi',
        'layersApi',
        'sugerenciasApi',
        'monitoringApi',
        'configApi',
      ];

      mainExports.forEach((exportName) => {
        expect(apiModule[exportName as keyof typeof apiModule]).toBeDefined();
      });
    });

    it('should maintain consistency between imports and exports', () => {
      // API_URL and API_PREFIX are strings
      expect(typeof apiModule.API_URL).toBe('string');
      expect(typeof apiModule.API_PREFIX).toBe('string');

      // Timeouts are numbers
      expect(typeof apiModule.DEFAULT_TIMEOUT).toBe('number');
      expect(typeof apiModule.LONG_TIMEOUT).toBe('number');
      expect(typeof apiModule.HEALTH_TIMEOUT).toBe('number');

      // Functions are functions
      expect(typeof apiModule.apiFetch).toBe('function');
      expect(typeof apiModule.getAuthToken).toBe('function');
      expect(typeof apiModule.clearAuthTokenCache).toBe('function');
      expect(typeof apiModule.healthCheck).toBe('function');
      expect(typeof apiModule.getExportAcceptHeader).toBe('function');
    });
  });

  describe('API configuration values', () => {
    it('should have non-empty API_URL', () => {
      expect(apiModule.API_URL.length).toBeGreaterThan(0);
    });

    it('should have non-empty API_PREFIX', () => {
      expect(apiModule.API_PREFIX.length).toBeGreaterThan(0);
    });

    it('should have reasonable timeout values', () => {
      expect(apiModule.DEFAULT_TIMEOUT).toBeGreaterThan(0);
      expect(apiModule.LONG_TIMEOUT).toBeGreaterThan(0);
      expect(apiModule.HEALTH_TIMEOUT).toBeGreaterThan(0);
    });

    it('should have HEALTH_TIMEOUT shorter than DEFAULT_TIMEOUT', () => {
      expect(apiModule.HEALTH_TIMEOUT).toBeLessThan(apiModule.DEFAULT_TIMEOUT);
    });

    it('should have DEFAULT_TIMEOUT shorter than LONG_TIMEOUT', () => {
      expect(apiModule.DEFAULT_TIMEOUT).toBeLessThan(apiModule.LONG_TIMEOUT);
    });
  });
});
