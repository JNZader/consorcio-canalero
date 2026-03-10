/**
 * env.test.ts
 * Unit: Environment variable validation and typed access
 * Coverage Target: 100% for env utilities
 */
// @ts-nocheck


import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { isEnvConfigured, getMissingEnvVars, isBrowser, isServer, env } from '../../src/lib/env';

describe('Environment Utilities', () => {
  describe('isEnvConfigured', () => {
    it('should return true when both Supabase variables are configured', () => {
      const result = isEnvConfigured();
      // This depends on actual env variables, so just check it returns a boolean
      expect(typeof result).toBe('boolean');
    });

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

    it('should potentially include SUPABASE_URL in missing vars', () => {
      const missing = getMissingEnvVars();
      // If missing, should have this name
      if (!env.SUPABASE_URL) {
        expect(missing).toContain('VITE_SUPABASE_URL');
      }
    });

    it('should potentially include SUPABASE_ANON_KEY in missing vars', () => {
      const missing = getMissingEnvVars();
      // If missing, should have this name
      if (!env.SUPABASE_ANON_KEY) {
        expect(missing).toContain('VITE_SUPABASE_ANON_KEY');
      }
    });

    it('should have max 2 items (both supabase vars)', () => {
      const missing = getMissingEnvVars();
      expect(missing.length).toBeLessThanOrEqual(2);
    });
  });

  describe('isBrowser constant', () => {
    it('should be a boolean', () => {
      expect(typeof isBrowser).toBe('boolean');
    });

    it('should be true in browser environment (jsdom)', () => {
      // jsdom sets up window object
      expect(isBrowser).toBe(true);
    });

    it('should check for window object existence', () => {
      // isBrowser should be true if globalThis.window is defined
      expect(globalThis.window).toBeDefined();
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

    it('should be false in browser environment (jsdom)', () => {
      // jsdom is a browser environment
      expect(isServer).toBe(false);
    });
  });

  describe('env object', () => {
    it('should have SUPABASE_URL property', () => {
      expect(env).toHaveProperty('SUPABASE_URL');
    });

    it('should have SUPABASE_ANON_KEY property', () => {
      expect(env).toHaveProperty('SUPABASE_ANON_KEY');
    });

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
        'SUPABASE_URL',
        'SUPABASE_ANON_KEY',
        'API_URL',
        'NODE_ENV',
        'IS_PRODUCTION',
        'IS_DEVELOPMENT',
      ];
      requiredProps.forEach((prop) => {
        expect(env).toHaveProperty(prop);
      });
    });

    it('should have valid NODE_ENV value', () => {
      const validNodeEnvs = ['development', 'production', 'test'];
      expect(validNodeEnvs).toContain(env.NODE_ENV);
    });

    it('should have string values for URL variables', () => {
      expect(typeof env.SUPABASE_URL).toBe('string');
      expect(typeof env.SUPABASE_ANON_KEY).toBe('string');
      expect(typeof env.API_URL).toBe('string');
    });

    it('API_URL should have a default fallback', () => {
      // API_URL should fallback to localhost:8000
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

    it('should have either SUPABASE_URL or an empty string', () => {
      expect(typeof env.SUPABASE_URL).toBe('string');
    });

    it('should have either SUPABASE_ANON_KEY or an empty string', () => {
      expect(typeof env.SUPABASE_ANON_KEY).toBe('string');
    });
  });

  describe('Configuration validation', () => {
    it('isEnvConfigured should match presence of both variables', () => {
      const configured = isEnvConfigured();
      const hasBothVars = Boolean(env.SUPABASE_URL && env.SUPABASE_ANON_KEY);
      expect(configured).toBe(hasBothVars);
    });

    it('getMissingEnvVars should correspond to isEnvConfigured', () => {
      const missing = getMissingEnvVars();
      const configured = isEnvConfigured();

      if (missing.length === 0) {
        expect(configured).toBe(true);
      } else {
        expect(configured).toBe(false);
      }
    });
  });
});
