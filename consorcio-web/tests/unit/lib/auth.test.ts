/**
 * Tests for src/lib/auth.ts
 * Tests authentication helper functions: role checking, permissions, etc.
 * Auth now uses Zustand store (useAuthStore) instead of Supabase.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getUserRole, hasRole, isAdmin, isOperadorOrAdmin } from '../../../src/lib/auth';

// Mock the auth adapter
vi.mock('../../../src/lib/auth/index', () => ({
  authAdapter: {
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    getSession: vi.fn(),
    loginWithGoogle: vi.fn(),
    onAuthStateChange: vi.fn(() => vi.fn()),
  },
}));

// Mock logger
vi.mock('../../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    debug: vi.fn(),
  },
}));

// Mock typeGuards
vi.mock('../../../src/lib/typeGuards', () => ({
  safeGetUserRole: vi.fn((value) => {
    const validRoles = ['ciudadano', 'operador', 'admin'];
    return typeof value === 'string' && validRoles.includes(value) ? value : null;
  }),
}));

// Mock API
vi.mock('../../../src/lib/api', () => ({
  clearAuthTokenCache: vi.fn(),
}));

// Mock authStore — getUserRole reads from useAuthStore.getState().profile
const { mockGetState } = vi.hoisted(() => ({
  mockGetState: vi.fn(),
}));
vi.mock('../../../src/stores/authStore', () => ({
  useAuthStore: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) => selector(mockGetState()),
    { getState: mockGetState }
  ),
}));

describe('auth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: no profile
    mockGetState.mockReturnValue({ profile: null });
  });

  describe('getUserRole', () => {
    it('should return user role from profile', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'operador' } });
      const result = await getUserRole('test-user-123');
      expect(result).toBe('operador');
    });

    it('should return null when no profile', async () => {
      mockGetState.mockReturnValue({ profile: null });
      const result = await getUserRole('test-user-123');
      expect(result).toBeNull();
    });

    it('should return null for invalid role', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'invalid-role' } });
      const result = await getUserRole('test-user-123');
      expect(result).toBeNull();
    });

    it('should handle all valid roles', async () => {
      for (const validRole of ['ciudadano', 'operador', 'admin']) {
        mockGetState.mockReturnValue({ profile: { rol: validRole } });
        const result = await getUserRole(`user-${validRole}`);
        expect(result).toBe(validRole);
      }
    });

    it('should reject all invalid roles', async () => {
      const invalidRoles = ['superadmin', 'root', 'moderator', '', 'ADMIN'];
      for (const invalidRole of invalidRoles) {
        mockGetState.mockReturnValue({ profile: { rol: invalidRole } });
        const result = await getUserRole('test-user');
        expect(result).toBeNull();
      }
    });
  });

  describe('hasRole', () => {
    it('should return true if user has allowed role', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'operador' } });
      const result = await hasRole('test-user-123', ['operador', 'admin']);
      expect(result).toBe(true);
    });

    it('should return false if user does not have allowed role', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'ciudadano' } });
      const result = await hasRole('test-user-123', ['admin']);
      expect(result).toBe(false);
    });

    it('should return false if role cannot be retrieved', async () => {
      mockGetState.mockReturnValue({ profile: null });
      const result = await hasRole('test-user-123', ['admin']);
      expect(result).toBe(false);
    });

    it('should catch mutation on includes check', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'operador' } });
      const result = await hasRole('test-user-123', ['operador', 'admin']);
      expect(result).toBe(true);

      mockGetState.mockReturnValue({ profile: { rol: 'ciudadano' } });
      const result2 = await hasRole('test-user-123', ['operador', 'admin']);
      expect(result2).toBe(false);
    });

    it('should handle empty allowed roles array', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'admin' } });
      const result = await hasRole('test-user-123', []);
      expect(result).toBe(false);
    });

    it('should handle multiple allowed roles', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'operador' } });
      const result = await hasRole('test-user-123', ['ciudadano', 'operador', 'admin']);
      expect(result).toBe(true);
    });
  });

  describe('isAdmin', () => {
    it('should return true if user is admin', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'admin' } });
      const result = await isAdmin('admin-user');
      expect(result).toBe(true);
    });

    it('should return false if user is not admin', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'operador' } });
      const result = await isAdmin('operador-user');
      expect(result).toBe(false);
    });

    it('should catch mutation on role comparison', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'admin' } });
      let result = await isAdmin('test-user');
      expect(result).toBe(true);

      mockGetState.mockReturnValue({ profile: { rol: 'operador' } });
      result = await isAdmin('test-user');
      expect(result).toBe(false);
    });
  });

  describe('isOperadorOrAdmin', () => {
    it('should return true if user is operador', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'operador' } });
      const result = await isOperadorOrAdmin('operador-user');
      expect(result).toBe(true);
    });

    it('should return true if user is admin', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'admin' } });
      const result = await isOperadorOrAdmin('admin-user');
      expect(result).toBe(true);
    });

    it('should return false if user is ciudadano', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'ciudadano' } });
      const result = await isOperadorOrAdmin('ciudadano-user');
      expect(result).toBe(false);
    });

    it('should catch mutation on role array', async () => {
      mockGetState.mockReturnValue({ profile: { rol: 'operador' } });
      let result = await isOperadorOrAdmin('test-user');
      expect(result).toBe(true);

      mockGetState.mockReturnValue({ profile: { rol: 'admin' } });
      result = await isOperadorOrAdmin('test-user');
      expect(result).toBe(true);

      mockGetState.mockReturnValue({ profile: { rol: 'ciudadano' } });
      result = await isOperadorOrAdmin('test-user');
      expect(result).toBe(false);
    });
  });
});
