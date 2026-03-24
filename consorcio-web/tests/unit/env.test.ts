/**
 * env.test.ts
 * Unit: Environment variable validation and typed access
 * Coverage Target: 100% for env utilities
 */

import { describe, it, expect } from 'vitest';
import { isEnvConfigured, getMissingEnvVars, isBrowser, isServer, env } from '../../src/lib/env';

describe('Environment Utilities', () => {
  describe('isEnvConfigured', () => {
    it('should return a boolean value', () => {
      expect(typeof isEnvConfigured()).toBe('boolean');
    });
  });

  describe('getMissingEnvVars', () => {
    it('should return an array of missing environment variable names', () => {
      const missing = getMissingEnvVars();
      expect(Array.isArray(missing)).toBe(true);
    });

    it('should only return VITE_ prefixed variable names', () => {
      const missing = getMissingEnvVars();
      missing.forEach((varName) => {
        expect(varName).toMatch(/^VITE_/);
      });
    });
  });

  describe('isBrowser constant', () => {
    it('should be a boolean', () => {
      expect(typeof isBrowser).toBe('boolean');
    });

    it('should be true in browser environment (jsdom)', () => {
      expect(isBrowser).toBe(true);
    });
  });

  describe('isServer constant', () => {
    it('should be a boolean', () => {
      expect(typeof isServer).toBe('boolean');
    });

    it('should be opposite of isBrowser', () => {
      expect(isServer).toBe(!isBrowser);
    });
  });

  describe('env object', () => {
    it('should have API_URL property', () => {
      expect(env).toHaveProperty('API_URL');
    });

    it('should have NODE_ENV property', () => {
      expect(env).toHaveProperty('NODE_ENV');
      expect(['development', 'production', 'test']).toContain(env.NODE_ENV);
    });

    it('should have IS_PRODUCTION property', () => {
      expect(env).toHaveProperty('IS_PRODUCTION');
      expect(typeof env.IS_PRODUCTION).toBe('boolean');
    });

    it('should have IS_DEVELOPMENT property', () => {
      expect(env).toHaveProperty('IS_DEVELOPMENT');
      expect(typeof env.IS_DEVELOPMENT).toBe('boolean');
    });

    it('should have all required properties', () => {
      const requiredProps = [
        'API_URL',
        'NODE_ENV',
        'IS_PRODUCTION',
        'IS_DEVELOPMENT',
      ];
      requiredProps.forEach((prop) => {
        expect(env).toHaveProperty(prop);
      });
    });

    it('API_URL should have a default fallback', () => {
      expect(env.API_URL).toBeTruthy();
      expect(typeof env.API_URL).toBe('string');
    });
  });

  describe('Environment consistency', () => {
    it('should have consistent IS_PRODUCTION and NODE_ENV values', () => {
      if (env.NODE_ENV === 'production') {
        expect(env.IS_PRODUCTION).toBe(true);
      }
    });

    it('should have consistent IS_DEVELOPMENT and NODE_ENV values', () => {
      if (env.NODE_ENV === 'development') {
        expect(env.IS_DEVELOPMENT).toBe(true);
      }
    });
  });

  describe('Configuration validation', () => {
    it('isEnvConfigured should return boolean', () => {
      const configured = isEnvConfigured();
      expect(typeof configured).toBe('boolean');
    });
  });
});
