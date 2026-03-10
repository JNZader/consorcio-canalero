/**
 * Mutation tests for src/lib/auth.ts
 * Tests authentication helper functions: role checking, permissions, etc.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getUserRole, hasRole, isAdmin, isOperadorOrAdmin } from '../../../src/lib/auth';
import { userRoleTestCases } from './setup';

// Mock Supabase client
vi.mock('../supabase', () => ({
  getSupabaseClient: vi.fn(() => ({
    from: vi.fn(() => ({
      select: vi.fn(() => ({
        eq: vi.fn(() => ({
          single: vi.fn(),
        })),
      })),
    })),
  })),
}));

// Mock logger
vi.mock('../logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    debug: vi.fn(),
  },
}));

// Mock typeGuards
vi.mock('../typeGuards', () => ({
  safeGetUserRole: vi.fn((value) => {
    const validRoles = ['ciudadano', 'operador', 'admin'];
    return typeof value === 'string' && validRoles.includes(value) ? value : null;
  }),
}));

import { getSupabaseClient } from '../../../src/lib/supabase';
import { safeGetUserRole } from '../../../src/lib/typeGuards';

describe('auth', () => {
  const mockClient = {
    from: vi.fn(() => ({
      select: vi.fn(() => ({
        eq: vi.fn(() => ({
          single: vi.fn(),
        })),
      })),
    })),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (getSupabaseClient as any).mockReturnValue(mockClient);
  });

  describe('getUserRole', () => {
    it('should return user role from database', async () => {
      const userId = 'test-user-123';
      const mockRole = 'operador';

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: mockRole }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await getUserRole(userId);
      expect(result).toBe(mockRole);
    });

    it('should return null for API error', async () => {
      const userId = 'test-user-123';
      const mockError = new Error('Database error');

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: null, error: mockError }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await getUserRole(userId);
      expect(result).toBeNull();
    });

    it('should return null for invalid role', async () => {
      const userId = 'test-user-123';

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'invalid-role' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await getUserRole(userId);
      expect(result).toBeNull();
    });

    it('should return null for exception', async () => {
      const userId = 'test-user-123';

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockRejectedValue(new Error('Unexpected error')),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await getUserRole(userId);
      expect(result).toBeNull();
    });

    it('should handle all valid roles', async () => {
      for (const validRole of userRoleTestCases.valid) {
        const userId = `user-${validRole}`;

        mockClient.from = vi.fn(() => ({
          select: vi.fn(() => ({
            eq: vi.fn(() => ({
              single: vi.fn().mockResolvedValue({ data: { rol: validRole }, error: null }),
            })),
          })),
        }));
        (getSupabaseClient as any).mockReturnValue(mockClient);

        const result = await getUserRole(userId);
        expect(result).toBe(validRole);
      }
    });

    it('should reject all invalid roles', async () => {
      const invalidRoles = userRoleTestCases.invalid.filter((r) => r !== null && r !== undefined);

      for (const invalidRole of invalidRoles) {
        mockClient.from = vi.fn(() => ({
          select: vi.fn(() => ({
            eq: vi.fn(() => ({
              single: vi.fn().mockResolvedValue({ data: { rol: invalidRole }, error: null }),
            })),
          })),
        }));
        (getSupabaseClient as any).mockReturnValue(mockClient);

        const result = await getUserRole(invalidRole);
        // Should be null since role is invalid
      }
    });
  });

  describe('hasRole', () => {
    it('should return true if user has allowed role', async () => {
      const userId = 'test-user-123';
      const allowedRoles = ['operador', 'admin'];

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'operador' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await hasRole(userId, allowedRoles);
      expect(result).toBe(true);
    });

    it('should return false if user does not have allowed role', async () => {
      const userId = 'test-user-123';
      const allowedRoles = ['admin'];

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'ciudadano' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await hasRole(userId, allowedRoles);
      expect(result).toBe(false);
    });

    it('should return false if role cannot be retrieved', async () => {
      const userId = 'test-user-123';
      const allowedRoles = ['admin'];

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: null, error: new Error('Not found') }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await hasRole(userId, allowedRoles);
      expect(result).toBe(false);
    });

    it('should catch mutation on includes check', async () => {
      const userId = 'test-user-123';
      const allowedRoles = ['operador', 'admin'];

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'operador' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await hasRole(userId, allowedRoles);
      expect(result).toBe(true);

      // Change to non-matching role
      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'ciudadano' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result2 = await hasRole(userId, allowedRoles);
      expect(result2).toBe(false);
    });

    it('should handle empty allowed roles array', async () => {
      const userId = 'test-user-123';
      const allowedRoles: string[] = [];

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'admin' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await hasRole(userId, allowedRoles);
      expect(result).toBe(false);
    });

    it('should handle multiple allowed roles', async () => {
      const userId = 'test-user-123';
      const allowedRoles = ['ciudadano', 'operador', 'admin'];

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'operador' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await hasRole(userId, allowedRoles);
      expect(result).toBe(true);
    });
  });

  describe('isAdmin', () => {
    it('should return true if user is admin', async () => {
      const userId = 'admin-user';

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'admin' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await isAdmin(userId);
      expect(result).toBe(true);
    });

    it('should return false if user is not admin', async () => {
      const userId = 'operador-user';

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'operador' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await isAdmin(userId);
      expect(result).toBe(false);
    });

    it('should catch mutation on role comparison', async () => {
      const userId = 'test-user';

      // Test with admin
      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'admin' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      let result = await isAdmin(userId);
      expect(result).toBe(true);

      // Test with operador
      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'operador' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      result = await isAdmin(userId);
      expect(result).toBe(false);
    });
  });

  describe('isOperadorOrAdmin', () => {
    it('should return true if user is operador', async () => {
      const userId = 'operador-user';

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'operador' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await isOperadorOrAdmin(userId);
      expect(result).toBe(true);
    });

    it('should return true if user is admin', async () => {
      const userId = 'admin-user';

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'admin' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await isOperadorOrAdmin(userId);
      expect(result).toBe(true);
    });

    it('should return false if user is ciudadano', async () => {
      const userId = 'ciudadano-user';

      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'ciudadano' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      const result = await isOperadorOrAdmin(userId);
      expect(result).toBe(false);
    });

    it('should catch mutation on role array', async () => {
      const userId = 'test-user';

      // Test with operador (should be in array)
      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'operador' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      let result = await isOperadorOrAdmin(userId);
      expect(result).toBe(true);

      // Test with admin (should be in array)
      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'admin' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      result = await isOperadorOrAdmin(userId);
      expect(result).toBe(true);

      // Test with ciudadano (should not be in array)
      mockClient.from = vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn().mockResolvedValue({ data: { rol: 'ciudadano' }, error: null }),
          })),
        })),
      }));
      (getSupabaseClient as any).mockReturnValue(mockClient);

      result = await isOperadorOrAdmin(userId);
      expect(result).toBe(false);
    });
  });
});
