/**
 * Unit tests for authStore selectors and hooks.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act } from '@testing-library/react';
import {
  useAuthStore,
  selectIsAuthenticated,
  selectUserRole,
  selectCanAccess,
  cleanupAuthListener,
} from '../../src/stores/authStore';

// Mock Supabase client
vi.mock('../../src/lib/supabase', () => ({
  getSupabaseClient: vi.fn(() => ({
    from: vi.fn(() => ({
      select: vi.fn(() => ({
        eq: vi.fn(() => ({
          single: vi.fn().mockResolvedValue({ data: null, error: null }),
        })),
      })),
      insert: vi.fn(() => ({
        select: vi.fn(() => ({
          single: vi.fn().mockResolvedValue({ data: null, error: null }),
        })),
      })),
    })),
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: { session: null },
        error: null,
      }),
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
    },
  })),
}));

describe('authStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    const store = useAuthStore.getState();
    store.reset();
    vi.clearAllMocks();
  });

  describe('initial state', () => {
    it('should have correct initial values', () => {
      const state = useAuthStore.getState();

      // After reset, these should be the values
      expect(state.user).toBeNull();
      expect(state.session).toBeNull();
      expect(state.profile).toBeNull();
      expect(state.loading).toBe(false); // reset sets loading to false
      expect(state.error).toBeNull();
      expect(state.initialized).toBe(true); // reset sets initialized to true
    });
  });

  describe('setters', () => {
    it('should set user', () => {
      const mockUser = { id: 'test-id', email: 'test@example.com' } as any;

      act(() => {
        useAuthStore.getState().setUser(mockUser);
      });

      expect(useAuthStore.getState().user).toEqual(mockUser);
    });

    it('should set session', () => {
      const mockSession = { access_token: 'token', user: { id: 'test' } } as any;

      act(() => {
        useAuthStore.getState().setSession(mockSession);
      });

      expect(useAuthStore.getState().session).toEqual(mockSession);
    });

    it('should set profile', () => {
      const mockProfile = { id: 'test-id', email: 'test@example.com', nombre: 'Test', rol: 'ciudadano' as const };

      act(() => {
        useAuthStore.getState().setProfile(mockProfile);
      });

      expect(useAuthStore.getState().profile).toEqual(mockProfile);
    });

    it('should set loading', () => {
      act(() => {
        useAuthStore.getState().setLoading(true);
      });

      expect(useAuthStore.getState().loading).toBe(true);
    });

    it('should set error', () => {
      act(() => {
        useAuthStore.getState().setError('Test error');
      });

      expect(useAuthStore.getState().error).toBe('Test error');
    });

    it('should set initialized', () => {
      act(() => {
        useAuthStore.getState().setInitialized(true);
      });

      expect(useAuthStore.getState().initialized).toBe(true);
    });
  });

  describe('reset', () => {
    it('should reset state to initial values', () => {
      // Set some state
      act(() => {
        useAuthStore.getState().setUser({ id: 'test' } as any);
        useAuthStore.getState().setLoading(true);
        useAuthStore.getState().setError('Some error');
      });

      // Reset
      act(() => {
        useAuthStore.getState().reset();
      });

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.session).toBeNull();
      expect(state.profile).toBeNull();
      expect(state.loading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.initialized).toBe(true);
    });
  });

  describe('selectIsAuthenticated', () => {
    it('should return false when user is null', () => {
      const state = {
        user: null,
        loading: false,
        initialized: true,
      } as any;

      expect(selectIsAuthenticated(state)).toBe(false);
    });

    it('should return false when loading', () => {
      const state = {
        user: { id: 'test' },
        loading: true,
        initialized: true,
      } as any;

      expect(selectIsAuthenticated(state)).toBe(false);
    });

    it('should return false when not initialized', () => {
      const state = {
        user: { id: 'test' },
        loading: false,
        initialized: false,
      } as any;

      expect(selectIsAuthenticated(state)).toBe(false);
    });

    it('should return true when user exists, not loading, and initialized', () => {
      const state = {
        user: { id: 'test' },
        loading: false,
        initialized: true,
      } as any;

      expect(selectIsAuthenticated(state)).toBe(true);
    });
  });

  describe('selectUserRole', () => {
    it('should return null when profile is null', () => {
      const state = { profile: null } as any;

      expect(selectUserRole(state)).toBeNull();
    });

    it('should return null when profile has no role', () => {
      const state = { profile: { id: 'test' } } as any;

      expect(selectUserRole(state)).toBeNull();
    });

    it('should return the user role from profile', () => {
      const state = {
        profile: { id: 'test', rol: 'admin' },
      } as any;

      expect(selectUserRole(state)).toBe('admin');
    });

    it('should handle ciudadano role', () => {
      const state = {
        profile: { id: 'test', rol: 'ciudadano' },
      } as any;

      expect(selectUserRole(state)).toBe('ciudadano');
    });

    it('should handle operador role', () => {
      const state = {
        profile: { id: 'test', rol: 'operador' },
      } as any;

      expect(selectUserRole(state)).toBe('operador');
    });
  });

  describe('selectCanAccess', () => {
    it('should return false when role is null', () => {
      const state = { profile: null } as any;

      expect(selectCanAccess(state, ['admin'])).toBe(false);
    });

    it('should return false when role is not in allowed list', () => {
      const state = {
        profile: { id: 'test', rol: 'ciudadano' },
      } as any;

      expect(selectCanAccess(state, ['admin', 'operador'])).toBe(false);
    });

    it('should return true when role is in allowed list', () => {
      const state = {
        profile: { id: 'test', rol: 'admin' },
      } as any;

      expect(selectCanAccess(state, ['admin', 'operador'])).toBe(true);
    });

    it('should return true for ciudadano when allowed', () => {
      const state = {
        profile: { id: 'test', rol: 'ciudadano' },
      } as any;

      expect(selectCanAccess(state, ['ciudadano'])).toBe(true);
    });

    it('should return true for any matching role in list', () => {
      const state = {
        profile: { id: 'test', rol: 'operador' },
      } as any;

      expect(selectCanAccess(state, ['admin', 'operador', 'ciudadano'])).toBe(true);
    });
  });

  describe('cleanupAuthListener', () => {
    it('should not throw when called', () => {
      expect(() => cleanupAuthListener()).not.toThrow();
    });
  });
});
